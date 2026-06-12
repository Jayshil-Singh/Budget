"""Manage recurring pay schedules (salary, side income, etc.)."""
import datetime
import streamlit as st
from database import get_db
from models.finance import Income, PayPeriod
from config import INCOME_SOURCES
from services.finance_service import _get_occurrences_in_range
from utils.helpers import format_currency, can_modify, can_delete
from utils.fx import get_fx_rates, convert_to_fjd
from utils.ux import confirm_button, toast_success, render_empty_state


def _next_payday(anchor: datetime.date, frequency: str, after: datetime.date | None = None) -> datetime.date | None:
    if not anchor or not frequency:
        return None
    start = after or datetime.date.today()
    hits = _get_occurrences_in_range(anchor, frequency, start, start + datetime.timedelta(days=366))
    return hits[0] if hits else None


def show_income_schedule(household_id: int):
    st.markdown("<h1 class='app-title'>Pay Schedule</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='app-subtitle'>Set up recurring pay — salary, business income, and other regular money in</p>",
        unsafe_allow_html=True,
    )
    currency = st.session_state.get("household_currency", "FJD")
    today = datetime.date.today()

    with get_db() as db:
        role = st.session_state.get("user_role", "viewer")

        if can_modify(role):
            with st.container(border=True):
                st.subheader("➕ Add recurring pay")
                with st.form("add_recurring_income", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        source = st.selectbox("Source", INCOME_SOURCES)
                        raw_amount = st.number_input("Net amount", min_value=0.01, step=50.0, value=500.0)
                        inc_currency = st.selectbox("Currency", list(get_fx_rates().keys()))
                    with c2:
                        first_pay = st.date_input("First payday", value=today)
                        freq = st.selectbox(
                            "Repeats", ["weekly", "fortnightly", "monthly"],
                            format_func=str.title,
                        )
                        notes = st.text_input("Notes (optional)")
                    if st.form_submit_button("Save pay schedule", type="primary"):
                        amount_fjd, _ = convert_to_fjd(raw_amount, inc_currency)
                        period = db.query(PayPeriod).filter(
                            PayPeriod.household_id == household_id,
                            PayPeriod.start_date <= first_pay,
                            PayPeriod.end_date >= first_pay,
                        ).first()
                        db.add(Income(
                            household_id=household_id,
                            source=source,
                            amount=amount_fjd,
                            date=first_pay,
                            is_recurring=True,
                            frequency=freq,
                            next_date=first_pay,
                            pay_period_id=period.id if period else None,
                            description=notes or None,
                        ))
                        db.commit()
                        toast_success(f"Pay schedule saved: {source}")
                        st.rerun()

        st.markdown("---")
        st.subheader("📋 Active pay schedules")
        templates = db.query(Income).filter(
            Income.household_id == household_id,
            Income.is_recurring == True,
        ).order_by(Income.date.desc()).all()

        if not templates:
            render_empty_state("📅", "No pay schedule yet", "Add your salary or regular income above.")
            return

        for inc in templates:
            next_pay = _next_payday(inc.date, inc.frequency or "")
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 2, 2])
                with c1:
                    st.markdown(f"**{inc.source}** · {format_currency(inc.amount, currency)} · {(inc.frequency or '').title()}")
                    st.caption(f"Started {inc.date.strftime('%d %b %Y')}")
                with c2:
                    if next_pay:
                        st.metric("Next payday", next_pay.strftime("%d %b"))
                with c3:
                    if can_modify(role) and st.button("Edit in Income Setup", key=f"goto_inc_{inc.id}"):
                        st.session_state["nav_route"] = "income_setup"
                        st.rerun()
                if can_delete(role) and confirm_button(
                    f"inc_sched_del_{inc.id}", "Remove schedule", "delete",
                    f"Stop tracking recurring pay for **{inc.source}**?",
                ):
                    inc.is_recurring = False
                    inc.next_date = None
                    db.commit()
                    toast_success("Pay schedule removed")
                    st.rerun()
