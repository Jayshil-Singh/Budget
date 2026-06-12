"""Shared Quick Add flow — log money in or out in seconds."""
import datetime
import streamlit as st
from database import get_db
from models.finance import Income, Expense, ExpenseCategory, PayPeriod
from services.ai_service import auto_tag_category
from config import INCOME_SOURCES
from utils.helpers import format_currency, can_modify
from utils.ux import store_undo, toast_success
from utils.attachments import save_receipt


@st.fragment
def render_quick_add(household_id: int, *, expanded: bool = True, key_prefix: str = "qa"):
    """
    Renders a compact money-in / money-out form.
    Advanced options (recurring, category override) sit behind an expander.
    """
    currency = st.session_state.get("household_currency", "FJD")
    role = st.session_state.get("user_role", "viewer")

    if not can_modify(role):
        st.info("View only — you cannot log transactions.")
        return

    with get_db() as db:
        categories = db.query(ExpenseCategory).filter(
            (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
        ).all()
        cat_choices = {c.name: c.id for c in categories}
        cat_names = list(cat_choices.keys())

        wrapper = st.container(border=True)
        with wrapper:
            st.markdown("### ⚡ Quick Add")
            st.caption("Log money in or out in a few seconds")
            direction = st.radio(
                "Type",
                ["💸 Spent money", "💰 Received money"],
                horizontal=True,
                key=f"{key_prefix}_dir",
            )
            is_expense = direction.startswith("💸")

            c1, c2 = st.columns([2, 1])
            with c1:
                label = st.text_input(
                    "What was it for?",
                    placeholder="e.g. MH Supermarket, Salary, Vodafone",
                    key=f"{key_prefix}_label",
                )
            with c2:
                amount = st.number_input(
                    "Amount",
                    min_value=0.01,
                    step=5.0,
                    value=20.0,
                    key=f"{key_prefix}_amt",
                )

            suggested_cat = ""
            if is_expense and label:
                suggested_cat = auto_tag_category(label, cat_names)

            default_cat_idx = cat_names.index(suggested_cat) if suggested_cat in cat_names else 0
            if suggested_cat and is_expense:
                st.caption(f"Suggested category: **{suggested_cat}**")

            tx_date = datetime.date.today()
            category = cat_names[default_cat_idx] if is_expense else None
            source = INCOME_SOURCES[0]
            is_recurring = False
            frequency = None

            receipt_file = None
            with st.expander("More options", expanded=False):
                tx_date = st.date_input("Date", datetime.date.today(), key=f"{key_prefix}_date")
                if is_expense:
                    receipt_file = st.file_uploader(
                        "Receipt (optional)", type=["png", "jpg", "jpeg", "pdf"],
                        key=f"{key_prefix}_receipt",
                    )
                    category = st.selectbox(
                        "Category", cat_names, index=default_cat_idx, key=f"{key_prefix}_cat",
                    )
                    is_recurring = st.checkbox("Repeats regularly", key=f"{key_prefix}_rec")
                    if is_recurring:
                        frequency = st.selectbox(
                            "How often?", ["Weekly", "Fortnightly", "Monthly"], index=1, key=f"{key_prefix}_freq",
                        ).lower()
                else:
                    source = st.selectbox("Income source", INCOME_SOURCES, key=f"{key_prefix}_src")
                    is_recurring = st.checkbox("Repeating income", key=f"{key_prefix}_rec_inc")
                    if is_recurring:
                        frequency = st.selectbox(
                            "How often?", ["Weekly", "Fortnightly", "Monthly"], index=1, key=f"{key_prefix}_freq_inc",
                        ).lower()

            if st.button("Save", type="primary", width="stretch", key=f"{key_prefix}_save"):
                if not label.strip():
                    st.error("Please describe what the money was for.")
                    return

                curr_period = db.query(PayPeriod).filter(
                    PayPeriod.household_id == household_id,
                    PayPeriod.start_date <= tx_date,
                    PayPeriod.end_date >= tx_date,
                ).first()

                user_id = st.session_state.get("user_id")
                if is_expense:
                    attach = save_receipt(household_id, receipt_file) if receipt_file else None
                    exp = Expense(
                        household_id=household_id,
                        category_id=cat_choices[category],
                        amount=amount,
                        date=tx_date,
                        merchant=label.strip(),
                        is_recurring=is_recurring,
                        frequency=frequency,
                        pay_period_id=curr_period.id if curr_period else None,
                        logged_by_user_id=user_id,
                        attachment_note=attach,
                    )
                    db.add(exp)
                    db.commit()
                    db.refresh(exp)
                    store_undo(household_id, "expense", exp.id)
                    toast_success(f"Logged expense: {format_currency(amount, currency)} — {label}")
                else:
                    inc = Income(
                        household_id=household_id,
                        source=source,
                        amount=amount,
                        date=tx_date,
                        description=label.strip(),
                        is_recurring=is_recurring,
                        frequency=frequency,
                        next_date=tx_date if is_recurring and frequency else None,
                        pay_period_id=curr_period.id if curr_period else None,
                    )
                    db.add(inc)
                    db.commit()
                    db.refresh(inc)
                    store_undo(household_id, "income", inc.id)
                    toast_success(f"Logged income: {format_currency(amount, currency)} — {label}")

                _mark_quick_start_step(db, household_id, "logged_transaction")
                st.rerun()


def _mark_quick_start_step(db, household_id: int, step_key: str):
    import json
    from models.household import Setting
    setting_key = "quick_start_progress"
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == setting_key,
    ).first()
    progress = json.loads(row.value) if row else {}
    progress[step_key] = True
    if row:
        row.value = json.dumps(progress)
    else:
        db.add(Setting(household_id=household_id, key=setting_key, value=json.dumps(progress)))
    db.commit()
