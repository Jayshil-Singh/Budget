"""Tests for finance calculations."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.household import Household
from models.finance import Expense, ExpenseCategory, PayPeriod, Income
from services.finance_service import (
    calculate_expenses_for_period,
    calculate_income_for_period,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    h = Household(name="Test", currency="FJD", budget_method="payday")
    session.add(h)
    session.commit()
    cat = ExpenseCategory(name="Groceries", is_system=True)
    session.add(cat)
    session.commit()
    period = PayPeriod(
        household_id=h.id,
        name="Test Period",
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 6, 14),
    )
    session.add(period)
    session.commit()
    yield session, h.id, cat.id, period
    session.close()


def test_expenses_exclude_recurring_double_count(db):
    session, hid, cat_id, period = db
    session.add(Expense(
        household_id=hid, category_id=cat_id, amount=50.0,
        date=datetime.date(2026, 6, 5), is_recurring=False,
    ))
    session.add(Expense(
        household_id=hid, category_id=cat_id, amount=100.0,
        date=datetime.date(2026, 6, 1), is_recurring=True, frequency="monthly",
    ))
    session.commit()
    total = calculate_expenses_for_period(
        session, hid, period.start_date, period.end_date,
    )
    assert total == 150.0


def test_recurring_income_includes_anchor_payday(db):
    session, hid, cat_id, period = db
    anchor = datetime.date(2026, 6, 11)
    session.add(Income(
        household_id=hid, source="Salary", amount=800.0,
        date=anchor, is_recurring=True, frequency="fortnightly",
        next_date=anchor,
    ))
    session.commit()
    total = calculate_income_for_period(
        session, hid, period.start_date, period.end_date,
    )
    assert total == 800.0

    from services.finance_service import _get_occurrences_in_range
    occ = _get_occurrences_in_range(anchor, "fortnightly", anchor, anchor)
    assert occ == [anchor]


def test_income_for_period(db):
    session, hid, cat_id, period = db
    session.add(Income(
        household_id=hid, source="Salary", amount=1200.0,
        date=datetime.date(2026, 6, 1), is_recurring=False,
    ))
    session.commit()
    total = calculate_income_for_period(
        session, hid, period.start_date, period.end_date,
    )
    assert total == 1200.0
