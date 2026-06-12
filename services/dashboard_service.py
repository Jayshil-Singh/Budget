"""Dashboard widgets: budget progress, comparisons, upcoming bills, member spending."""
import datetime
from sqlalchemy.orm import Session as DBSession
from models.finance import PayPeriod, Subscription, PaymentDueDate, Expense
from models.budget import Budget, BudgetItem
from models.household import HouseholdMember
from services.finance_service import calculate_expenses_for_period, get_current_pay_period


def get_previous_pay_period(db: DBSession, household_id: int, current: PayPeriod) -> PayPeriod | None:
    if not current:
        return None
    return db.query(PayPeriod).filter(
        PayPeriod.household_id == household_id,
        PayPeriod.end_date < current.start_date,
    ).order_by(PayPeriod.end_date.desc()).first()


def get_period_comparison(db: DBSession, household_id: int) -> dict | None:
    current = get_current_pay_period(db, household_id)
    if not current:
        return None
    prev = get_previous_pay_period(db, household_id, current)
    cur_exp = calculate_expenses_for_period(
        db, household_id, current.start_date, current.end_date
    )
    if not prev:
        return {"current_spend": cur_exp, "delta": 0.0, "pct": 0.0, "has_prev": False}
    prev_exp = calculate_expenses_for_period(
        db, household_id, prev.start_date, prev.end_date
    )
    delta = cur_exp - prev_exp
    pct = (delta / prev_exp * 100) if prev_exp > 0 else 0.0
    return {
        "current_spend": cur_exp,
        "previous_spend": prev_exp,
        "delta": delta,
        "pct": pct,
        "has_prev": True,
    }


def get_budget_progress(db: DBSession, household_id: int) -> list[dict]:
    current = get_current_pay_period(db, household_id)
    if not current:
        return []
    budget = db.query(Budget).filter(
        Budget.household_id == household_id,
        Budget.pay_period_id == current.id,
    ).first()
    if not budget:
        return []
    items = db.query(BudgetItem).filter(BudgetItem.budget_id == budget.id).all()
    rows = []
    for item in items:
        if item.limit_amount <= 0:
            continue
        actual = calculate_expenses_for_period(
            db, household_id,
            current.start_date, current.end_date,
            category_id=item.category_id,
        )
        pct = min(100.0, (actual / item.limit_amount) * 100) if item.limit_amount else 0
        rows.append({
            "category": item.category.name if item.category else "Other",
            "limit": item.limit_amount,
            "spent": actual,
            "remaining": item.limit_amount - actual,
            "pct": pct,
            "over": actual > item.limit_amount,
        })
    rows.sort(key=lambda x: x["pct"], reverse=True)
    return rows[:6]


def get_upcoming_bills(db: DBSession, household_id: int, limit: int = 5, days_ahead: int = 14) -> list[dict]:
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=days_ahead)
    events = []

    for sub in db.query(Subscription).filter(
        Subscription.household_id == household_id,
        Subscription.status == "active",
    ).all():
        if today <= sub.next_renewal <= horizon:
            days = (sub.next_renewal - today).days
            events.append({
                "date": sub.next_renewal,
                "days": days,
                "name": sub.name,
                "amount": sub.amount,
                "kind": "subscription",
            })

    for due in db.query(PaymentDueDate).filter(
        PaymentDueDate.household_id == household_id,
        PaymentDueDate.is_paid == False,
        PaymentDueDate.due_date >= today,
        PaymentDueDate.due_date <= horizon,
    ).all():
        days = (due.due_date - today).days
        events.append({
            "date": due.due_date,
            "days": days,
            "name": due.name,
            "amount": due.amount,
            "kind": "bill",
        })

    events.sort(key=lambda x: x["date"])
    return events[:limit]


def get_member_spending(db: DBSession, household_id: int, start: datetime.date, end: datetime.date) -> list[dict]:
    members = db.query(HouseholdMember).filter(HouseholdMember.household_id == household_id).all()
    rows = []
    for m in members:
        total = sum(
            e.amount for e in db.query(Expense).filter(
                Expense.household_id == household_id,
                Expense.logged_by_user_id == m.user_id,
                Expense.date >= start,
                Expense.date <= end,
            ).all()
        )
        if m.user:
            rows.append({
                "name": m.user.full_name,
                "role": m.role,
                "total": total,
            })
    unassigned = sum(
        e.amount for e in db.query(Expense).filter(
            Expense.household_id == household_id,
            Expense.logged_by_user_id == None,
            Expense.date >= start,
            Expense.date <= end,
        ).all()
    )
    if unassigned > 0:
        rows.append({"name": "Unassigned", "role": "—", "total": unassigned})
    rows.sort(key=lambda x: x["total"], reverse=True)
    return rows
