"""Log a payment when user marks a bill or subscription as paid."""
import datetime
from sqlalchemy.orm import Session as DBSession
from models.finance import Expense, Subscription, PayPeriod
from services.finance_service import _logged_expense_on_date
from services.recurring_service import get_next_date


def _link_period(db: DBSession, household_id: int, pay_date: datetime.date):
    return db.query(PayPeriod).filter(
        PayPeriod.household_id == household_id,
        PayPeriod.start_date <= pay_date,
        PayPeriod.end_date >= pay_date,
    ).first()


def mark_recurring_expense_paid(
    db: DBSession,
    household_id: int,
    template: Expense,
    pay_date: datetime.date | None = None,
) -> bool:
    """Record a one-off expense for this recurring bill occurrence."""
    if not template.is_recurring:
        return False
    pay_date = pay_date or datetime.date.today()
    if _logged_expense_on_date(
        db, household_id, template.category_id, template.amount, pay_date, template.merchant,
    ):
        return False
    period = _link_period(db, household_id, pay_date)
    db.add(Expense(
        household_id=household_id,
        category_id=template.category_id,
        amount=template.amount,
        date=pay_date,
        merchant=template.merchant,
        notes=f"Marked paid (recurring bill #{template.id})",
        is_recurring=False,
        pay_period_id=period.id if period else None,
    ))
    db.commit()
    return True


def mark_subscription_paid(
    db: DBSession,
    household_id: int,
    sub: Subscription,
    pay_date: datetime.date | None = None,
) -> bool:
    """Log subscription charge and advance next renewal."""
    if sub.status != "active":
        return False
    pay_date = pay_date or sub.next_renewal or datetime.date.today()
    if _logged_expense_on_date(
        db, household_id, sub.category_id, sub.amount, pay_date, sub.name,
    ):
        sub.next_renewal = get_next_date(pay_date, sub.frequency)
        db.commit()
        return True
    period = _link_period(db, household_id, pay_date)
    db.add(Expense(
        household_id=household_id,
        category_id=sub.category_id,
        amount=sub.amount,
        date=pay_date,
        merchant=sub.name,
        notes="Subscription renewal marked paid",
        is_recurring=False,
        pay_period_id=period.id if period else None,
    ))
    sub.next_renewal = get_next_date(pay_date, sub.frequency)
    db.commit()
    return True
