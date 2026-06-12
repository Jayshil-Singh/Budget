import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from database import get_db
from models.budget import SavingsGoal, Debt
from services.finance_service import calculate_emergency_fund_coverage, get_essential_expenses_monthly
from services.forecast_service import calculate_debt_payoff_forecast
from config import SAVINGS_GOALS_TYPES, DEBT_TYPES
from utils.helpers import format_currency, get_days_remaining, can_modify, can_delete


def show_savings_debt(household_id: int, *, savings_only: bool = False, debt_only: bool = False):
    """Savings goals, emergency fund, and debt payoff tools."""
    if not savings_only and not debt_only:
        st.markdown("<h1 class='app-title'>Savings & Debts</h1>", unsafe_allow_html=True)
        st.markdown("<p class='app-subtitle'>Optimize debt payoffs, build emergency funds, and check long-term goals</p>", unsafe_allow_html=True)

    currency = st.session_state.get("household_currency", "FJD")
    role = st.session_state.get("user_role", "viewer")

    with get_db() as db:
        show_savings = not debt_only
        show_debt = not savings_only

        if show_savings and show_debt:
            tab_goal, tab_debt = st.tabs(["🎯 Savings Goals", "⛓️ Debt payoff forecaster"])
            savings_block = tab_goal
            debt_block = tab_debt
        elif show_savings:
            savings_block = st.container()
            debt_block = None
        else:
            savings_block = None
            debt_block = st.container()

        if savings_block is not None:
            with savings_block:
                _render_savings_section(db, household_id, currency, role)

        if debt_block is not None:
            with debt_block:
                _render_debt_section(db, household_id, currency, role)


def _render_savings_section(db, household_id: int, currency: str, role: str):
    total_funds, coverage_months, rating = calculate_emergency_fund_coverage(db, household_id)
    essential_m = get_essential_expenses_monthly(db, household_id)

    st.markdown(f"### Emergency Fund Health: **{rating}**")
    col_e1, col_e2, col_e3 = st.columns(3)
    col_e1.metric("Total Emergency Cash", format_currency(total_funds, currency))
    col_e2.metric("Monthly Essential Bills", format_currency(essential_m, currency))
    col_e3.metric("Coverage Duration", f"{coverage_months:.1f} Months", delta=f"{coverage_months - 6.0:.1f} to 6m target")
    st.markdown("---")

    if not can_modify(role):
        st.info("View only — you cannot create savings goals.")
    else:
        with st.expander("➕ Create New Savings Goal", expanded=False):
            with st.form("create_goal_form"):
                col1, col2 = st.columns(2)
                with col1:
                    g_name = st.selectbox("Goal Category", SAVINGS_GOALS_TYPES)
                    g_custom_name = st.text_input("Custom Goal Name (Optional)", placeholder="e.g. Dream House Fund")
                    g_target = st.number_input("Target Amount", min_value=10.0, value=2000.0, step=100.0)
                with col2:
                    g_current = st.number_input("Current Saved Balance", min_value=0.0, value=100.0, step=50.0)
                    g_date = st.date_input("Target Date", datetime.date.today() + datetime.timedelta(days=365))
                    g_priority = st.selectbox("Priority Level", ["Low", "Medium", "High"], index=1)
                submit_goal = st.form_submit_button("Create Goal", type="primary")
                if submit_goal:
                    final_name = g_custom_name if g_custom_name else g_name
                    db.add(SavingsGoal(
                        household_id=household_id, name=final_name,
                        target_amount=g_target, current_amount=g_current,
                        target_date=g_date, priority=g_priority.lower(), status="active",
                    ))
                    db.commit()
                    st.success("Savings Goal created successfully!")
                    st.rerun()

    st.subheader("Active Savings Goals")
    goals = db.query(SavingsGoal).filter(
        SavingsGoal.household_id == household_id, SavingsGoal.status == "active"
    ).all()

    if not goals:
        st.info("No active savings goals yet. Create one above.")
    else:
        for goal in goals:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1])
                pct = (goal.current_amount / goal.target_amount) * 100 if goal.target_amount > 0 else 0.0
                days_left = get_days_remaining(goal.target_date)
                with c1:
                    st.write(f"### 🎯 {goal.name}")
                    st.progress(pct / 100)
                    st.write(f"Saved: **{format_currency(goal.current_amount, currency)}** of **{format_currency(goal.target_amount, currency)}** ({pct:.1f}%)")
                with c2:
                    st.write(f"📅 Target: **{goal.target_date.strftime('%d %b %Y')}**")
                    st.write(f"⏳ **{days_left} days** left")
                with c3:
                    if can_modify(role):
                        extra_sav = st.number_input("Deposit", min_value=0.0, step=20.0, key=f"sav_dep_{goal.id}")
                        if st.button("Add", key=f"btn_sav_{goal.id}"):
                            goal.current_amount += extra_sav
                            if goal.current_amount >= goal.target_amount:
                                goal.status = "achieved"
                            db.commit()
                            st.success("Saved!")
                            st.rerun()
                if can_delete(role) and st.button("Delete", key=f"del_goal_{goal.id}", type="secondary"):
                    db.delete(goal)
                    db.commit()
                    st.rerun()


def _render_debt_section(db, household_id: int, currency: str, role: str):
    if not can_modify(role):
        st.info("View only — you cannot log debts.")
    else:
        with st.expander("➕ Add Outstanding Debt", expanded=False):
            with st.form("add_debt_form"):
                col1, col2 = st.columns(2)
                with col1:
                    d_name = st.text_input("Debt Name", placeholder="e.g. BSP Car Loan")
                    d_type = st.selectbox("Debt Type", DEBT_TYPES)
                    d_balance = st.number_input("Current Balance", min_value=1.0, value=5000.0, step=100.0)
                with col2:
                    d_original = st.number_input("Original Balance", min_value=1.0, value=7500.0, step=100.0)
                    d_rate = st.number_input("Interest Rate (%)", min_value=0.0, value=6.5, step=0.1)
                    d_min_pay = st.number_input("Minimum Payment", min_value=1.0, value=150.0, step=10.0)
                if st.form_submit_button("Add Debt", type="primary"):
                    db.add(Debt(
                        household_id=household_id, name=d_name, type=d_type,
                        current_balance=d_balance, original_balance=d_original,
                        interest_rate=d_rate, minimum_payment=d_min_pay,
                        start_date=datetime.date.today(),
                    ))
                    db.commit()
                    st.success("Debt added!")
                    st.rerun()

    debts = db.query(Debt).filter(Debt.household_id == household_id).all()
    if not debts:
        st.info("No outstanding debts — you're debt-free!")
        return

    st.subheader("Your Outstanding Debts")
    for d in debts:
        with st.container(border=True):
            dc1, dc2, dc3 = st.columns([2, 1, 1])
            with dc1:
                st.write(f"**{d.name}** ({d.type})")
                st.write(f"Balance: **{format_currency(d.current_balance, currency)}** @ {d.interest_rate}%")
            with dc2:
                st.write(f"Min payment: **{format_currency(d.minimum_payment, currency)}**")
            with dc3:
                if can_delete(role) and st.button("Delete", key=f"del_debt_{d.id}"):
                    db.delete(d)
                    db.commit()
                    st.rerun()

    st.markdown("---")
    st.subheader("Payoff Simulator")
    extra_surplus = st.number_input("Extra monthly payment", min_value=0.0, value=100.0, step=20.0)
    forecast_res = calculate_debt_payoff_forecast(db, household_id, extra_surplus)
    snow = forecast_res.get("snowball", {})
    avalanche = forecast_res.get("avalanche", {})
    if snow and avalanche:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### ❄️ Snowball")
            st.write(f"**{snow['months_to_payoff']} months** · Interest {format_currency(snow['total_interest_paid'], currency)}")
        with c2:
            st.markdown("#### 🏔️ Avalanche")
            st.write(f"**{avalanche['months_to_payoff']} months** · Interest {format_currency(avalanche['total_interest_paid'], currency)}")
