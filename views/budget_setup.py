"""Budget setup — pay cycle, periods, reminders, and category limits."""
import streamlit as st
from database import get_db
from views.pay_settings import show_pay_settings
from services.budget_limits_service import render_budget_limits_editor


def show_budget_setup(household_id: int):
    show_pay_settings(household_id, embedded=False, page_title="Budget Setup")
    currency = st.session_state.get("household_currency", "FJD")
    role = st.session_state.get("user_role", "viewer")
    with get_db() as db:
        render_budget_limits_editor(db, household_id, role, currency)
