"""Unified Plans & Bills hub — subscriptions, savings, debts in one place."""
import streamlit as st
from views.subscription_view import show_subscriptions
from views.savings_debt import show_savings_debt


def show_plans_bills(household_id: int):
    st.markdown("<h1 class='app-title'>Plans & Bills</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='app-subtitle'>Regular bills, savings goals, and debts — all in one place</p>",
        unsafe_allow_html=True,
    )

    tab_bills, tab_save, tab_debt, tab_cal = st.tabs([
        "📅 Regular Bills & Subscriptions",
        "🎯 Saving For",
        "⛓️ Debts",
        "🗓️ Calendar",
    ])

    with tab_bills:
        show_subscriptions(household_id, embedded=True)

    with tab_save:
        _show_savings_only(household_id)

    with tab_debt:
        _show_debts_only(household_id)

    with tab_cal:
        from views.calendar_view import show_calendar
        show_calendar(household_id, embedded=True)


def _show_savings_only(household_id: int):
    """Savings goals tab without debt simulator noise."""
    import streamlit as st
    from views import savings_debt
    # Re-use savings_debt but only goals — call internal with flag via session
    st.session_state["_plans_bills_savings_only"] = True
    savings_debt.show_savings_debt(household_id, savings_only=True)
    st.session_state.pop("_plans_bills_savings_only", None)


def _show_debts_only(household_id: int):
    from views import savings_debt
    st.session_state["_plans_bills_debt_only"] = True
    savings_debt.show_savings_debt(household_id, debt_only=True)
    st.session_state.pop("_plans_bills_debt_only", None)
