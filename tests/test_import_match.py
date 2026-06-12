"""Tests for bank import ledger matching."""
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.household import Household
from models.finance import Expense, ExpenseCategory
from services.import_service import _find_ledger_match


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    h = Household(name="Test", currency="FJD", budget_method="monthly")
    session.add(h)
    session.commit()
    cat = ExpenseCategory(name="Groceries", is_system=True)
    session.add(cat)
    session.commit()
    yield session, h.id, cat.id
    session.close()


def test_fuzzy_match_by_merchant(db):
    session, hid, cat_id = db
    session.add(Expense(
        household_id=hid, category_id=cat_id, amount=250.0,
        date=datetime.date(2026, 6, 12), merchant="Shopping", is_recurring=False,
    ))
    session.commit()
    match = _find_ledger_match(
        session, hid, datetime.date(2026, 6, 13), -250.0, "Card payment Shopping MH",
    )
    assert match is not None
    assert match.merchant == "Shopping"
