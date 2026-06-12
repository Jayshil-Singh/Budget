"""Lightweight UI labels — extend per household locale later."""
from models.household import Setting

LABELS = {
    "en": {
        "money_in": "Money In",
        "money_out": "Money Out",
        "left_until_payday": "Left Until Payday",
        "this_week": "This Week",
        "this_pay_cycle": "This Pay Cycle",
        "budget_progress": "Budget Progress",
        "upcoming_bills": "Upcoming Bills",
        "vs_last_cycle": "vs Last Pay Cycle",
        "no_transactions": "No transactions yet — use Quick Add above.",
        "no_budget": "No budget set for this pay cycle.",
        "no_bills": "No bills due in the next 14 days.",
        "payday_countdown": "days until payday",
        "budget_alert": "Budget alert",
        "track_subscription": "Track as subscription",
    },
}

DEFAULT_LOCALE = "en"


def get_household_locale(db, household_id: int) -> str:
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == "ui_locale",
    ).first()
    if row and row.value in LABELS:
        return row.value
    return DEFAULT_LOCALE


def t(key: str, locale: str = DEFAULT_LOCALE) -> str:
    return LABELS.get(locale, LABELS[DEFAULT_LOCALE]).get(key, key)
