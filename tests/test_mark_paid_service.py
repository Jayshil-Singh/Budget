"""Tests for mark-paid helpers."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.household import Household
from models.finance import Expense, ExpenseCategory, Subscription
from services.mark_paid_service import mark_recurring_expense_paid, mark_subscription_paid


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    h = Household(name="Test", currency="FJD", budget_method="monthly")
    session.add(h)
    session.commit()
    cat = ExpenseCategory(name="Utilities", is_system=True)
    session.add(cat)
    session.commit()
    yield session, h.id, cat.id
    session.close()


def test_mark_recurring_expense_paid(db):
    session, hid, cat_id = db
    template = Expense(
        household_id=hid, category_id=cat_id, amount=100.0,
        date=datetime.date(2026, 6, 1), merchant="Rent",
        is_recurring=True, frequency="monthly",
    )
    session.add(template)
    session.commit()
    ok = mark_recurring_expense_paid(session, hid, template, datetime.date(2026, 6, 13))
    assert ok
    logged = session.query(Expense).filter(Expense.is_recurring == False).all()
    assert len(logged) == 1
    assert logged[0].amount == 100.0


def test_mark_subscription_paid_advances_renewal(db):
    session, hid, cat_id = db
    renewal = datetime.date(2026, 6, 13)
    sub = Subscription(
        household_id=hid, name="Netflix", amount=15.0,
        frequency="monthly", next_renewal=renewal, category_id=cat_id, status="active",
    )
    session.add(sub)
    session.commit()
    assert mark_subscription_paid(session, hid, sub)
    assert sub.next_renewal > renewal
