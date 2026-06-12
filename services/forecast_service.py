import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession
from models.finance import Income, Expense, Subscription
from models.budget import Debt
from models.household import Household

def calculate_current_balance(db: DBSession, household_id: int) -> float:
    """
    Computes current cash balance for the household.
    Sum of all incomes minus sum of all expenses.
    """
    total_income = db.query(func.sum(Income.amount)).filter(Income.household_id == household_id).scalar() or 0.0
    total_expense = db.query(func.sum(Expense.amount)).filter(Expense.household_id == household_id).scalar() or 0.0
    return total_income - total_expense

def generate_cashflow_projection(
    db: DBSession, 
    household_id: int, 
    days: int = 90
) -> list[dict]:
    """
    Generates a daily cashflow projection for the next 'days' days.
    Calculates expected income occurrences and recurring bill dates.
    """
    start_date = datetime.date.today()
    current_balance = calculate_current_balance(db, household_id)
    
    # 1. Fetch recurring incomes (schedule anchored on template date)
    recurring_incomes = db.query(Income).filter(
        Income.household_id == household_id,
        Income.is_recurring == True,
    ).all()
    
    # 2. Fetch active subscriptions and recurring expenses
    active_subs = db.query(Subscription).filter(
        Subscription.household_id == household_id,
        Subscription.status == "active"
    ).all()
    
    # 3. Fetch recurring fixed expenses (manual entries marked as recurring)
    recurring_expenses = db.query(Expense).filter(
        Expense.household_id == household_id,
        Expense.is_recurring == True,
        Expense.date >= (start_date - datetime.timedelta(days=31))
    ).all()
    
    # Map out day-by-day adjustments
    projections = []
    running_balance = current_balance
    
    for day_offset in range(days + 1):
        target_date = start_date + datetime.timedelta(days=day_offset)
        day_income = 0.0
        day_expense = 0.0
        events = []
        
        # Check income hits
        for inc in recurring_incomes:
            if not inc.date or not inc.frequency:
                continue
            if is_event_date_hit(inc.date, inc.frequency, target_date):
                day_income += inc.amount
                events.append(f"Income: {inc.source} (+{inc.amount:.2f})")
                
        # Check subscription hits
        for sub in active_subs:
            if is_sub_date_hit(sub.next_renewal, sub.frequency, target_date):
                day_expense += sub.amount
                events.append(f"Sub: {sub.name} (-{sub.amount:.2f})")
                
        # Check recurring expenses hits
        for exp in recurring_expenses:
            if is_event_date_hit(exp.date, exp.frequency, target_date):
                day_expense += exp.amount
                events.append(f"Fixed Bill: {exp.merchant or 'Recurring Expense'} (-{exp.amount:.2f})")
                
        running_balance += (day_income - day_expense)
        projections.append({
            "date": target_date,
            "income": day_income,
            "expense": day_expense,
            "balance": running_balance,
            "events": ", ".join(events) if events else None
        })
        
    return projections

def is_event_date_hit(start_date: datetime.date, frequency: str, target_date: datetime.date) -> bool:
    """
    Checks if a recurring transaction frequency aligns on target_date.
    """
    if not start_date or not frequency:
        return False
    if target_date < start_date:
        return False
    if target_date == start_date:
        return True
        
    diff_days = (target_date - start_date).days
    freq = frequency.lower()
    if freq == "weekly":
        return diff_days % 7 == 0
    elif freq == "fortnightly" or freq == "payday":
        return diff_days % 14 == 0
    elif freq == "monthly":
        # Match day of the month or last day if month is shorter
        return target_date.day == start_date.day or (
            target_date.day == 28 and target_date.month == 2 and start_date.day > 28
        )
    elif freq.startswith("custom:"):
        try:
            days = int(freq.split(":")[1].strip())
            return diff_days % days == 0
        except Exception:
            pass
    return False

def is_sub_date_hit(next_renewal: datetime.date, frequency: str, target_date: datetime.date) -> bool:
    """
    Checks if subscription renews on target_date.
    """
    if not next_renewal:
        return False
    if target_date < next_renewal:
        return False
    if target_date == next_renewal:
        return True

    from services.recurring_service import get_next_date
    freq = frequency.lower()
    if freq == "monthly":
        curr = next_renewal
        for _ in range(500):
            if curr == target_date:
                return True
            if curr > target_date:
                return False
            nxt = get_next_date(curr, "monthly")
            if nxt <= curr:
                break
            curr = nxt
        return False
    elif freq == "annual" or freq == "yearly":
        return target_date.month == next_renewal.month and target_date.day == next_renewal.day
    return False

def get_bill_overdraft_warnings(db: DBSession, household_id: int) -> list[dict]:
    """
    Analyzes cashflow projections for the next 30 days.
    Generates warnings if the daily balance is expected to drop below zero.
    """
    projections = generate_cashflow_projection(db, household_id, days=30)
    warnings = []
    
    for day in projections:
        if day["balance"] < 0:
            warnings.append({
                "date": day["date"],
                "balance": day["balance"],
                "events_that_day": day["events"],
                "severity": "CRITICAL" if day["balance"] < -100 else "WARNING"
            })
            # To avoid duplicate warnings, only alert on the first overdraft day
            break
            
    return warnings

def calculate_debt_payoff_forecast(
    db: DBSession, 
    household_id: int, 
    extra_payment: float = 0.0
) -> dict:
    """
    Forecasts payoff outcomes comparing:
    - Debt Snowball (lowest balance first)
    - Debt Avalanche (highest interest rate first)
    Returns schedules and months to pay off.
    """
    debts = db.query(Debt).filter(
        Debt.household_id == household_id,
        Debt.current_balance > 0
    ).all()
    
    if not debts:
        return {"snowball": {}, "avalanche": {}}

    def _monthly_payment(debt) -> float:
        """Convert minimum payment to a monthly equivalent."""
        freq = (debt.payment_frequency or "monthly").lower()
        if freq == "weekly":
            return debt.minimum_payment * 52 / 12
        if freq == "fortnightly":
            return debt.minimum_payment * 26 / 12
        return debt.minimum_payment

    # Build models
    results = {}
    for method in ["snowball", "avalanche"]:
        # Order debts
        active_debts = []
        for d in debts:
            active_debts.append({
                "id": d.id,
                "name": d.name,
                "balance": d.current_balance,
                "interest_rate": d.interest_rate,
                "min_payment": _monthly_payment(d),
            })
            
        if method == "snowball":
            active_debts.sort(key=lambda x: x["balance"])
        else: # avalanche
            active_debts.sort(key=lambda x: x["interest_rate"], reverse=True)
            
        months = 0
        total_interest_paid = 0.0
        schedule = []
        
        # Simulate month-by-month
        while any(d["balance"] > 0 for d in active_debts) and months < 360: # Limit 30 years
            months += 1
            available_extra = extra_payment
            monthly_interest = 0.0
            
            # Apply interest first and calculate minimums
            for d in active_debts:
                if d["balance"] > 0:
                    interest = d["balance"] * ((d["interest_rate"] / 100) / 12)
                    d["balance"] += interest
                    monthly_interest += interest
                    total_interest_paid += interest
                    
            # Apply minimum payments
            for d in active_debts:
                if d["balance"] > 0:
                    payment = min(d["balance"], d["min_payment"])
                    d["balance"] -= payment
                    
            # Apply extra payment to active targets
            # Snowball: smallest active. Avalanche: highest interest active.
            # (Because list is already sorted, we can just scan for first active)
            for d in active_debts:
                if d["balance"] > 0 and available_extra > 0:
                    payment = min(d["balance"], available_extra)
                    d["balance"] -= payment
                    available_extra -= payment
                    
            schedule.append({
                "month": months,
                "remaining_total": sum(d["balance"] for d in active_debts),
                "interest_added": monthly_interest
            })
            
        results[method] = {
            "months_to_payoff": months,
            "total_interest_paid": total_interest_paid,
            "schedule": schedule,
            "debts_cleared": months < 360
        }
        
    return results
