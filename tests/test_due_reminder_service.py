"""Tests for day-before payment reminder digest."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.household import Household
from models.finance import ExpenseCategory, PaymentDueDate, Subscription
from models.budget import Budget, BudgetItem
from services.due_reminder_service import (
    build_reminder_message,
    collect_items_due_on_date,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    h = Household(name="Test Home", currency="FJD", budget_method="monthly")
    session.add(h)
    session.commit()
    cat = ExpenseCategory(household_id=h.id, name="Utilities", is_system=False)
    session.add(cat)
    session.commit()
    yield session, h.id, cat.id
    session.close()


def test_collect_custom_bill_and_subscription(db):
    session, household_id, cat_id = db
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)

    session.add(PaymentDueDate(
        household_id=household_id,
        name="Water bill",
        amount=45.0,
        due_date=tomorrow,
    ))
    session.add(Subscription(
        household_id=household_id,
        name="Netflix",
        amount=19.99,
        frequency="monthly",
        next_renewal=tomorrow,
        category_id=cat_id,
        status="active",
    ))
    session.commit()

    items = collect_items_due_on_date(session, household_id, tomorrow)
    names = {i.name for i in items}
    assert "Water bill" in names
    assert "Netflix" in names
    assert sum(i.amount for i in items) == pytest.approx(64.99)


def test_build_reminder_includes_budget_context(db):
    session, household_id, cat_id = db
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    from models.finance import PayPeriod

    period = PayPeriod(
        household_id=household_id,
        name="June Period",
        start_date=datetime.date.today() - datetime.timedelta(days=3),
        end_date=datetime.date.today() + datetime.timedelta(days=10),
    )
    session.add(period)
    session.flush()
    budget = Budget(
        household_id=household_id,
        pay_period_id=period.id,
        name="June Budget",
        total_limit=500.0,
    )
    session.add(budget)
    session.flush()
    session.add(BudgetItem(budget_id=budget.id, category_id=cat_id, limit_amount=200.0))
    session.add(PaymentDueDate(
        household_id=household_id,
        name="Power bill",
        amount=80.0,
        due_date=tomorrow,
    ))
    session.commit()

    items = collect_items_due_on_date(session, household_id, tomorrow)
    message = build_reminder_message(session, household_id, items, tomorrow, currency="FJD")

    assert "Power bill" in message
    assert "FJD 80.00" in message
    assert "PAY CYCLE BUDGET" in message
    assert "Utilities" in message
    assert "ACTION REQUIRED" in message
    assert "every hour" in message


def test_build_reminder_personalized_greeting(db):
    session, household_id, cat_id = db
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    session.add(PaymentDueDate(
        household_id=household_id,
        name="Water",
        amount=30.0,
        due_date=tomorrow,
    ))
    session.commit()

    items = collect_items_due_on_date(session, household_id, tomorrow)
    generic = build_reminder_message(session, household_id, items, tomorrow, currency="FJD")
    personal = build_reminder_message(
        session, household_id, items, tomorrow, currency="FJD", recipient_name="Jayshil",
    )

    assert generic.startswith("Hello,")
    assert "Hello from SmartBudget AI" not in generic
    assert personal.startswith("Hello Jayshil,")


def test_reminder_ack_stops_sends(db):
    session, household_id, cat_id = db
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    session.add(PaymentDueDate(
        household_id=household_id,
        name="Rent",
        amount=500.0,
        due_date=tomorrow,
    ))
    session.commit()

    from services.due_reminder_service import (
        _should_send_reminder,
        acknowledge_payment_reminder,
        is_reminder_acknowledged,
    )

    should, _ = _should_send_reminder(session, household_id, tomorrow)
    assert should is True
    assert is_reminder_acknowledged(session, household_id, tomorrow) is False

    acknowledge_payment_reminder(session, household_id, tomorrow)
    should_after, _ = _should_send_reminder(session, household_id, tomorrow)
    assert should_after is False
    assert is_reminder_acknowledged(session, household_id, tomorrow) is True


def test_reminder_hourly_throttle(db):
    session, household_id, cat_id = db
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    session.add(PaymentDueDate(
        household_id=household_id,
        name="Internet",
        amount=75.0,
        due_date=tomorrow,
    ))
    session.commit()

    from services.due_reminder_service import _record_reminder_sent, _should_send_reminder

    should_first, is_repeat = _should_send_reminder(session, household_id, tomorrow)
    assert should_first is True
    assert is_repeat is False

    _record_reminder_sent(session, household_id, tomorrow)
    session.commit()

    should_second, is_repeat2 = _should_send_reminder(session, household_id, tomorrow)
    assert should_second is False
    assert is_repeat2 is False
