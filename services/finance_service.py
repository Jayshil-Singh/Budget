import datetime
from collections import defaultdict
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession
from models.finance import PayPeriod, Income, Expense, ExpenseCategory, Subscription, BankTransaction
from models.budget import Budget, BudgetItem, SavingsGoal, Debt, SinkingFund
from models.household import Household
from models.audit import FinancialScore
from utils.helpers import get_emergency_fund_rating


def _get_occurrences_in_range(start_date: datetime.date, frequency: str,
                               range_start: datetime.date, range_end: datetime.date) -> list[datetime.date]:
    """
    Expands a recurring schedule into all occurrence dates within [range_start, range_end].
    Uses the same logic as get_next_date in recurring_service to advance the schedule.
    """
    from services.recurring_service import get_next_date
    occurrences: list[datetime.date] = []
    if not start_date or not frequency:
        return occurrences
    curr = start_date
    for _ in range(500):          # safety cap
        if curr > range_end:
            break
        if curr >= range_start:
            occurrences.append(curr)
        nxt = get_next_date(curr, frequency)
        if nxt <= curr:           # prevent infinite loop on bad frequency
            break
        curr = nxt
    return occurrences


def calculate_income_for_period(db: DBSession, household_id: int,
                                 range_start: datetime.date, range_end: datetime.date) -> float:
    """
    Returns total income for the household within [range_start, range_end].
    Includes:
      - All logged (non-recurring) income records whose date falls in the range.
      - All occurrences of recurring templates that land in the range.
    This ensures that, e.g., two fortnightly pays within a calendar month are both counted.
    """
    # 1. Logged one-off incomes
    logged = db.query(func.sum(Income.amount)).filter(
        Income.household_id == household_id,
        Income.is_recurring == False,
        Income.date >= range_start,
        Income.date <= range_end,
    ).scalar() or 0.0

    # 2. Recurring templates – expand occurrences
    templates = db.query(Income).filter(
        Income.household_id == household_id,
        Income.is_recurring == True,
    ).all()
    recurring_total = 0.0
    for t in templates:
        occ = _get_occurrences_in_range(t.date, t.frequency, range_start, range_end)
        recurring_total += t.amount * len(occ)

    return logged + recurring_total


def calculate_expenses_for_period(db: DBSession, household_id: int,
                                   range_start: datetime.date, range_end: datetime.date,
                                   category_id: int = None) -> float:
    """
    Returns total expenses for the household within [range_start, range_end].
    Includes:
      - All logged (non-recurring) expense records whose date falls in the range.
      - All occurrences of recurring expense templates that land in the range.
    Optionally filter by category_id.
    """
    q_logged = db.query(func.sum(Expense.amount)).filter(
        Expense.household_id == household_id,
        Expense.is_recurring == False,
        Expense.date >= range_start,
        Expense.date <= range_end,
    )
    if category_id is not None:
        q_logged = q_logged.filter(Expense.category_id == category_id)
    logged = q_logged.scalar() or 0.0

    # Recurring expense templates
    q_templates = db.query(Expense).filter(
        Expense.household_id == household_id,
        Expense.is_recurring == True,
    )
    if category_id is not None:
        q_templates = q_templates.filter(Expense.category_id == category_id)
    templates = q_templates.all()

    recurring_total = 0.0
    for t in templates:
        occ = _get_occurrences_in_range(t.date, t.frequency, range_start, range_end)
        recurring_total += t.amount * len(occ)

    return logged + recurring_total

def generate_pay_periods(db: DBSession, household_id: int, start_date: datetime.date, num_periods: int = 12) -> list[PayPeriod]:
    """
    Generates and saves pay periods for a household based on its budget method.
    """
    household = db.query(Household).filter(Household.id == household_id).first()
    if not household:
        return []
        
    method = household.budget_method.lower()
    created_periods = []
    
    current_start = start_date
    for i in range(num_periods):
        if method == "weekly":
            current_end = current_start + datetime.timedelta(days=6)
            next_start = current_start + datetime.timedelta(days=7)
        elif method == "fortnightly" or method == "payday":  # Payday defaults to fortnightly in Fiji context if not custom
            current_end = current_start + datetime.timedelta(days=13)
            next_start = current_start + datetime.timedelta(days=14)
        elif method == "monthly":
            # Add calendar month
            if current_start.month == 12:
                next_start = datetime.date(current_start.year + 1, 1, 1)
            else:
                next_start = datetime.date(current_start.year, current_start.month + 1, 1)
            current_end = next_start - datetime.timedelta(days=1)
        else:
            # Custom
            current_end = current_start + datetime.timedelta(days=13)
            next_start = current_start + datetime.timedelta(days=14)
            
        name = f"Period {i+1} ({current_start.strftime('%d %b')} - {current_end.strftime('%d %b %Y')})"
        
        # Check if already exists
        exists = db.query(PayPeriod).filter(
            PayPeriod.household_id == household_id,
            PayPeriod.start_date == current_start,
            PayPeriod.end_date == current_end
        ).first()
        
        if not exists:
            period = PayPeriod(
                household_id=household_id,
                start_date=current_start,
                end_date=current_end,
                name=name
            )
            db.add(period)
            created_periods.append(period)
        else:
            created_periods.append(exists)
            
        current_start = next_start
        
    db.commit()
    return created_periods

def get_current_pay_period(db: DBSession, household_id: int, check_date: datetime.date = None) -> PayPeriod | None:
    """
    Retrieves the pay period containing the given date (default today).
    """
    if check_date is None:
        check_date = datetime.date.today()
        
    return db.query(PayPeriod).filter(
        PayPeriod.household_id == household_id,
        PayPeriod.start_date <= check_date,
        PayPeriod.end_date >= check_date
    ).first()

def get_essential_expenses_monthly(db: DBSession, household_id: int) -> float:
    """
    Estimates the essential expenses for a household in a typical month.
    Looks at mortgage/rent, utilities, insurance, childcare, and basic loan payments.
    """
    # Sum of matching category expenses in last 90 days / 3
    three_months_ago = datetime.date.today() - datetime.timedelta(days=90)
    
    essential_categories = ["Rent/Mortgage", "Utilities", "Insurance", "School Fees", "Childcare", "Transport", "Loan Payments"]
    
    total_essential = db.query(func.sum(Expense.amount)).join(ExpenseCategory).filter(
        Expense.household_id == household_id,
        Expense.date >= three_months_ago,
        ExpenseCategory.name.in_(essential_categories)
    ).scalar() or 0.0
    
    # If no historical expense data, use fixed subscriptions or default FJD 1000
    if total_essential == 0.0:
        subs_essential = db.query(func.sum(Subscription.amount)).join(ExpenseCategory).filter(
            Subscription.household_id == household_id,
            Subscription.status == "active",
            ExpenseCategory.name.in_(essential_categories)
        ).scalar() or 0.0
        if subs_essential > 0.0:
            return subs_essential * 1.2  # Add buffer
        return 1200.0  # Default estimate for Fiji family
        
    return total_essential / 3.0

def calculate_emergency_fund_coverage(db: DBSession, household_id: int) -> tuple[float, float, str]:
    """
    Calculates: Emergency Fund Total / Monthly Essential Expenses.
    Returns (total_funds, months_covered, rating)
    """
    # Total emergency savings is the sum of "Emergency Fund" savings goals
    # plus the "Emergency" sinking fund balance.
    sinking_total = db.query(func.sum(SinkingFund.current_amount)).filter(
        SinkingFund.household_id == household_id,
        SinkingFund.name.ilike("%emergency%")
    ).scalar() or 0.0
    
    goal_total = db.query(func.sum(SavingsGoal.current_amount)).filter(
        SavingsGoal.household_id == household_id,
        SavingsGoal.name.ilike("%emergency%")
    ).scalar() or 0.0
    
    total_emergency_funds = sinking_total + goal_total
    
    essential_monthly = get_essential_expenses_monthly(db, household_id)
    
    months_covered = total_emergency_funds / essential_monthly if essential_monthly > 0 else 0.0
    rating = get_emergency_fund_rating(months_covered)
    
    return total_emergency_funds, months_covered, rating

def calculate_financial_health_score(db: DBSession, household_id: int) -> tuple[float, dict]:
    """
    Calculates a credit-score style health index from 0 to 100.
    Factors:
    - Savings Rate (Target 20%): max 30 points
    - Budget Discipline (Variance from targets): max 20 points
    - Debt Ratio (Debt to Income ratio): max 20 points
    - Emergency Fund (Coverage months): max 20 points
    - Cashflow Stability (Net cash positive): max 10 points
    """
    # 1. Savings Rate
    # Fetch income and expenses in the last 30 days
    last_30_days = datetime.date.today() - datetime.timedelta(days=30)
    
    total_income = db.query(func.sum(Income.amount)).filter(
        Income.household_id == household_id,
        Income.date >= last_30_days
    ).scalar() or 0.0
    
    total_expenses = db.query(func.sum(Expense.amount)).filter(
        Expense.household_id == household_id,
        Expense.date >= last_30_days
    ).scalar() or 0.0
    
    savings = max(0.0, total_income - total_expenses)
    savings_rate = (savings / total_income) if total_income > 0 else 0.0
    
    savings_points = min(30.0, (savings_rate / 0.20) * 30.0) if total_income > 0 else 10.0
    
    # 2. Budget Discipline
    # Sum actual expenses compared to budget limits for current or last period
    budget = db.query(Budget).filter(Budget.household_id == household_id).order_by(Budget.created_at.desc()).first()
    discipline_points = 20.0
    if budget and budget.total_limit > 0:
        actual_in_budget = db.query(func.sum(Expense.amount)).filter(
            Expense.household_id == household_id,
            Expense.pay_period_id == budget.pay_period_id if budget.pay_period_id else True,
            Expense.date >= last_30_days
        ).scalar() or 0.0
        
        overspent = actual_in_budget - budget.total_limit
        if overspent > 0:
            percentage_over = (overspent / budget.total_limit)
            discipline_points = max(0.0, 20.0 - (percentage_over * 40.0))
            
    # 3. Debt Ratio
    # Minimum payment total / Income total
    min_debt_payments = db.query(func.sum(Debt.minimum_payment)).filter(
        Debt.household_id == household_id
    ).scalar() or 0.0
    
    debt_ratio = min_debt_payments / total_income if total_income > 0 else 0.0
    if debt_ratio == 0:
        debt_points = 20.0
    elif debt_ratio < 0.15:
        debt_points = 20.0
    elif debt_ratio < 0.35:
        debt_points = 15.0
    elif debt_ratio < 0.50:
        debt_points = 10.0
    else:
        debt_points = max(0.0, 10.0 - ((debt_ratio - 0.5) * 20.0))
        
    # 4. Emergency Fund
    _, coverage_months, _ = calculate_emergency_fund_coverage(db, household_id)
    emergency_points = min(20.0, (coverage_months / 6.0) * 20.0)
    
    # 5. Cashflow Stability
    # Did we have positive cashflow this month?
    cashflow_points = 10.0 if total_income > total_expenses else 3.0
    if total_income == 0:
        cashflow_points = 0.0
        
    total_score = round(savings_points + discipline_points + debt_points + emergency_points + cashflow_points)
    total_score = min(100, max(0, total_score))
    
    details = {
        "savings_rate_score": round(savings_points, 1),
        "savings_rate_pct": round(savings_rate * 100, 1),
        "budget_discipline_score": round(discipline_points, 1),
        "debt_ratio_score": round(debt_points, 1),
        "debt_ratio_pct": round(debt_ratio * 100, 1),
        "emergency_fund_score": round(emergency_points, 1),
        "emergency_fund_months": round(coverage_months, 1),
        "cashflow_stability_score": round(cashflow_points, 1)
    }
    
    # Store history
    score_record = FinancialScore(
        household_id=household_id,
        score=total_score,
        details=str(details)
    )
    db.add(score_record)
    db.commit()
    
    return total_score, details

def detect_recurring_patterns(db: DBSession, household_id: int) -> list[dict]:
    """
    Analyzes bank transactions or general expenses to find repeating merchants or amounts.
    Groups transactions by description/merchant and checks if they occur at intervals.
    """
    # Query last 180 days of expenses
    half_year_ago = datetime.date.today() - datetime.timedelta(days=180)
    expenses = db.query(Expense).filter(
        Expense.household_id == household_id,
        Expense.date >= half_year_ago
    ).all()
    
    if len(expenses) < 5:
        return []
        
    # Map merchant to list of dates and amounts
    merchant_map = defaultdict(list)
    for exp in expenses:
        if exp.merchant:
            merchant_map[exp.merchant.strip().lower()].append(exp)
            
    recommendations = []
    
    for merchant, list_of_exps in merchant_map.items():
        if len(list_of_exps) < 3:
            continue
            
        # Sort by date
        list_of_exps.sort(key=lambda x: x.date)
        
        # Calculate diff intervals
        intervals = []
        amounts = [x.amount for x in list_of_exps]
        
        for idx in range(len(list_of_exps) - 1):
            diff = (list_of_exps[idx+1].date - list_of_exps[idx].date).days
            intervals.append(diff)
            
        # Calculate standard deviation of intervals and amounts
        avg_interval = sum(intervals) / len(intervals)
        avg_amount = sum(amounts) / len(amounts)
        
        # Simple clustering: if intervals are highly regular (e.g. 26-32 days, or 12-16 days, or 6-8 days)
        # and amounts are close (within 5% variance)
        is_regular_days = False
        detected_frequency = None
        
        if 25 <= avg_interval <= 35:
            is_regular_days = True
            detected_frequency = "monthly"
        elif 12 <= avg_interval <= 16:
            is_regular_days = True
            detected_frequency = "fortnightly"
        elif 5 <= avg_interval <= 9:
            is_regular_days = True
            detected_frequency = "weekly"
            
        amount_variance = max(amounts) - min(amounts)
        is_stable_amount = amount_variance / avg_amount < 0.10 if avg_amount > 0 else False
        
        if is_regular_days and is_stable_amount:
            # Check if this is already tracked as a subscription
            sub_exists = db.query(Subscription).filter(
                Subscription.household_id == household_id,
                Subscription.name.ilike(f"%{merchant}%")
            ).first()
            
            if not sub_exists:
                # Recommend tracking this as a subscription
                category_id = list_of_exps[0].category_id
                cat_name = db.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first().name
                recommendations.append({
                    "merchant": list_of_exps[0].merchant,
                    "avg_amount": avg_amount,
                    "frequency": detected_frequency,
                    "category_id": category_id,
                    "category_name": cat_name,
                    "next_date": list_of_exps[-1].date + datetime.timedelta(days=round(avg_interval))
                })
                
    return recommendations
