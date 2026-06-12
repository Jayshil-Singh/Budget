"""Export household financial data to JSON."""
import datetime
import json
from sqlalchemy.orm import Session as DBSession
from models.household import Household
from models.finance import Income, Expense, Subscription, PayPeriod, PaymentDueDate
from models.budget import Budget, BudgetItem, SavingsGoal, Debt, SinkingFund


def export_household_json(db: DBSession, household_id: int) -> dict:
    h = db.query(Household).filter(Household.id == household_id).first()
    if not h:
        return {}

    def _rows(query, fields):
        return [dict((f, getattr(r, f)) for f in fields if hasattr(r, f)) for r in query]

    payload = {
        "exported_at": datetime.datetime.utcnow().isoformat(),
        "household": {
            "id": h.id,
            "name": h.name,
            "currency": h.currency,
            "budget_method": h.budget_method,
        },
        "pay_periods": _rows(
            db.query(PayPeriod).filter(PayPeriod.household_id == household_id),
            ["id", "name", "start_date", "end_date"],
        ),
        "income": _rows(
            db.query(Income).filter(Income.household_id == household_id),
            ["id", "source", "amount", "date", "is_recurring", "frequency", "description"],
        ),
        "expenses": _rows(
            db.query(Expense).filter(Expense.household_id == household_id),
            ["id", "amount", "date", "merchant", "is_recurring", "frequency", "notes"],
        ),
        "subscriptions": _rows(
            db.query(Subscription).filter(Subscription.household_id == household_id),
            ["id", "name", "amount", "frequency", "next_renewal", "status"],
        ),
        "payment_due_dates": _rows(
            db.query(PaymentDueDate).filter(PaymentDueDate.household_id == household_id),
            ["id", "name", "amount", "due_date", "is_paid"],
        ),
        "savings_goals": _rows(
            db.query(SavingsGoal).filter(SavingsGoal.household_id == household_id),
            ["id", "name", "target_amount", "current_amount", "target_date", "status"],
        ),
        "debts": _rows(
            db.query(Debt).filter(Debt.household_id == household_id),
            ["id", "name", "current_balance", "minimum_payment", "payment_frequency", "start_date"],
        ),
        "sinking_funds": _rows(
            db.query(SinkingFund).filter(SinkingFund.household_id == household_id),
            ["id", "name", "target_amount", "current_amount", "target_date", "contribution_amount"],
        ),
        "budgets": [],
    }
    for b in db.query(Budget).filter(Budget.household_id == household_id).all():
        items = db.query(BudgetItem).filter(BudgetItem.budget_id == b.id).all()
        payload["budgets"].append({
            "id": b.id,
            "name": b.name,
            "pay_period_id": b.pay_period_id,
            "total_limit": b.total_limit,
            "items": [{"category_id": i.category_id, "limit_amount": i.limit_amount} for i in items],
        })

    # Serialize dates
    def _default(o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        raise TypeError

    return json.loads(json.dumps(payload, default=_default))
