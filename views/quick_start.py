"""First-run checklist — get users to value in under 2 minutes."""
import json
import streamlit as st
from database import get_db
from models.household import Setting
from models.finance import Income, Expense, PayPeriod, BankTransaction


QUICK_START_STEPS = [
    ("logged_transaction", "Log your first transaction", "Use Quick Add above"),
    ("has_income", "Add your income", "Salary or other pay"),
    ("has_fixed_bill", "Add a regular bill", "Rent, utilities, or loan"),
    ("has_pay_period", "Pay cycle ready", "Auto-created on setup"),
    ("imported_bank", "Import a bank CSV or SMS (optional)", "Skip if you log manually"),
]


def get_quick_start_progress(db, household_id: int) -> dict:
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == "quick_start_progress",
    ).first()
    stored = json.loads(row.value) if row else {}

    # Auto-detect completed steps from data
    if db.query(Income).filter(Income.household_id == household_id).count() > 0:
        stored["has_income"] = True
    if db.query(Expense).filter(Expense.household_id == household_id).count() > 0:
        stored["has_fixed_bill"] = True
        stored["logged_transaction"] = True
    if db.query(PayPeriod).filter(PayPeriod.household_id == household_id).count() > 0:
        stored["has_pay_period"] = True
    if db.query(BankTransaction).filter(BankTransaction.household_id == household_id).count() > 0:
        stored["imported_bank"] = True

    return stored


def render_quick_start(household_id: int):
    with get_db() as db:
        progress = get_quick_start_progress(db, household_id)
        done = sum(1 for k, _, _ in QUICK_START_STEPS if progress.get(k))
        total = len(QUICK_START_STEPS)

        if progress.get("dismissed") or done >= total:
            return

        with st.container(border=True):
            st.subheader("🚀 Quick Start")
            st.caption(f"{done} of {total} done — finish setup to get the most from your dashboard")
            st.progress(done / total)

            for key, title, hint in QUICK_START_STEPS:
                checked = progress.get(key, False)
                icon = "✅" if checked else "⬜"
                st.markdown(f"{icon} **{title}** — _{hint}_")

            if st.button("Dismiss checklist", type="secondary", key="dismiss_quick_start"):
                row = db.query(Setting).filter(
                    Setting.household_id == household_id,
                    Setting.key == "quick_start_progress",
                ).first()
                progress["dismissed"] = True
                if row:
                    row.value = json.dumps(progress)
                else:
                    db.add(Setting(
                        household_id=household_id,
                        key="quick_start_progress",
                        value=json.dumps(progress),
                    ))
                db.commit()
                st.rerun()
