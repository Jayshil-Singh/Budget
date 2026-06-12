"""Inline row actions for Money Log."""
import datetime
import streamlit as st
from models.finance import PayPeriod
from config import INCOME_SOURCES
from utils.helpers import format_currency, can_modify, can_delete
from utils.ux import confirm_button, toast_success
from utils.fx import convert_to_fjd, get_fx_rates


def _link_pay_period(db, household_id: int, tx_date: datetime.date):
    return db.query(PayPeriod).filter(
        PayPeriod.household_id == household_id,
        PayPeriod.start_date <= tx_date,
        PayPeriod.end_date >= tx_date,
    ).first()


def render_expense_rows(db, household_id: int, expenses: list, cat_choices: dict, currency: str, role: str):
    cat_list = list(cat_choices.keys())
    for e in expenses[:25]:
        label = f"{e.merchant or 'Expense'} · {format_currency(e.amount, currency)} · {e.date}"
        with st.expander(label, expanded=False):
            if e.attachment_note and e.attachment_note.startswith("receipts"):
                st.caption(f"📎 Receipt: {e.attachment_note}")
            if can_modify(role):
                nc1, nc2 = st.columns(2)
                with nc1:
                    new_amount = st.number_input(
                        "Amount (FJD)", min_value=0.01, value=float(e.amount),
                        step=5.0, key=f"exp_amt_{e.id}",
                    )
                    cur_cat = e.category.name if e.category else cat_list[0]
                    new_cat = st.selectbox(
                        "Category", cat_list,
                        index=cat_list.index(cur_cat) if cur_cat in cat_list else 0,
                        key=f"exp_cat_{e.id}",
                    )
                    new_date = st.date_input("Date", value=e.date, key=f"exp_date_{e.id}")
                with nc2:
                    new_merchant = st.text_input("Merchant", value=e.merchant or "", key=f"exp_merch_{e.id}")
                    new_notes = st.text_area("Notes", value=e.notes or "", key=f"exp_notes_{e.id}")
                    new_attach = st.text_input(
                        "Receipt note", value=e.attachment_note or "", key=f"exp_attach_{e.id}",
                    )
                if st.button("Save changes", key=f"exp_save_{e.id}", type="primary"):
                    e.amount = new_amount
                    e.category_id = cat_choices[new_cat]
                    e.date = new_date
                    e.merchant = new_merchant
                    e.notes = new_notes
                    e.attachment_note = new_attach.strip() or None
                    period = _link_pay_period(db, household_id, new_date)
                    e.pay_period_id = period.id if period else None
                    db.commit()
                    toast_success("Expense updated")
                    st.rerun()
            if can_delete(role) and confirm_button(
                f"exp_del_{e.id}", "Delete", "delete",
                f"Delete **{e.merchant or 'expense'}**?",
            ):
                db.delete(e)
                db.commit()
                toast_success("Expense deleted")
                st.rerun()


def render_income_rows(db, household_id: int, incomes: list, currency: str, role: str):
    for inc in incomes[:25]:
        label = f"{inc.source} · {format_currency(inc.amount, currency)} · {inc.date}"
        with st.expander(label, expanded=False):
            if can_modify(role):
                ic1, ic2 = st.columns(2)
                with ic1:
                    src_idx = INCOME_SOURCES.index(inc.source) if inc.source in INCOME_SOURCES else 0
                    new_source = st.selectbox("Source", INCOME_SOURCES, index=src_idx, key=f"inc_src_{inc.id}")
                    new_amount = st.number_input(
                        "Amount (FJD)", min_value=0.01, value=float(inc.amount),
                        step=50.0, key=f"inc_amt_{inc.id}",
                    )
                    new_date = st.date_input("Date", value=inc.date, key=f"inc_date_{inc.id}")
                with ic2:
                    new_recurring = st.checkbox("Recurring", value=bool(inc.is_recurring), key=f"inc_rec_{inc.id}")
                    new_freq = None
                    if new_recurring:
                        freq_opts = ["weekly", "fortnightly", "monthly"]
                        cur = (inc.frequency or "fortnightly").lower()
                        new_freq = st.selectbox(
                            "Frequency", freq_opts,
                            index=freq_opts.index(cur) if cur in freq_opts else 1,
                            key=f"inc_freq_{inc.id}",
                        )
                    new_desc = st.text_area("Notes", value=inc.description or "", key=f"inc_desc_{inc.id}")
                if st.button("Save changes", key=f"inc_save_{inc.id}", type="primary"):
                    inc.source = new_source
                    inc.amount = new_amount
                    inc.date = new_date
                    inc.is_recurring = new_recurring
                    inc.frequency = new_freq
                    inc.description = new_desc or None
                    inc.next_date = new_date if new_recurring else None
                    period = _link_pay_period(db, household_id, new_date)
                    inc.pay_period_id = period.id if period else None
                    db.commit()
                    toast_success("Income updated")
                    st.rerun()
            if can_delete(role) and confirm_button(
                f"inc_del_{inc.id}", "Delete", "delete",
                f"Delete **{inc.source}**?",
            ):
                db.delete(inc)
                db.commit()
                toast_success("Income deleted")
                st.rerun()
