import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
from database import get_db
from models.budget import SavingsGoal, Debt
from services.finance_service import calculate_emergency_fund_coverage, get_essential_expenses_monthly
from services.forecast_service import calculate_debt_payoff_forecast
from config import SAVINGS_GOALS_TYPES, DEBT_TYPES
from utils.helpers import format_currency, get_days_remaining

def show_savings_debt(household_id: int):
    """
    Renders the Savings goals, Emergency coverage, and Debt Snowball/Avalanche forecaster.
    """
    st.markdown("<h1 class='app-title'>Savings & Debts</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Optimize debt payoffs, build emergency funds, and check long-term goals</p>", unsafe_allow_html=True)
    
    tab_goal, tab_debt = st.tabs(["🎯 Savings Goals", "⛓️ Debt payoff forecaster"])
    currency = st.session_state.get("household_currency", "FJD")
    
    with get_db() as db:
        # ----------------------------------------------------
        # SAVINGS GOALS TAB
        # ----------------------------------------------------
        with tab_goal:
            # 1. Emergency Fund Card
            total_funds, coverage_months, rating = calculate_emergency_fund_coverage(db, household_id)
            essential_m = get_essential_expenses_monthly(db, household_id)
            
            st.markdown(f"### Emergency Fund Health: **{rating}**")
            col_e1, col_e2, col_e3 = st.columns(3)
            col_e1.metric("Total Emergency Cash", format_currency(total_funds, currency))
            col_e2.metric("Monthly Essential Bills", format_currency(essential_m, currency))
            col_e3.metric("Coverage Duration", f"{coverage_months:.1f} Months", delta=f"{coverage_months - 6.0:.1f} to 6m target")
            
            role = st.session_state.get("user_role", "viewer")
            st.markdown("---")
            
            # 2. Add Savings Goal Form
            if role == "viewer":
                st.info("ℹ️ Read-Only Mode: Viewers cannot create savings goals.")
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
                            goal = SavingsGoal(
                                household_id=household_id,
                                name=final_name,
                                target_amount=g_target,
                                current_amount=g_current,
                                target_date=g_date,
                                priority=g_priority.lower(),
                                status="active"
                            )
                            db.add(goal)
                            db.commit()
                            st.success("Savings Goal created successfully!")
                            st.rerun()
                        
            # 3. List active goals
            st.subheader("Active Savings Goals")
            goals = db.query(SavingsGoal).filter(SavingsGoal.household_id == household_id, SavingsGoal.status == "active").all()
            
            if not goals:
                st.info("No active savings goals found.")
            else:
                for goal in goals:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 1, 1])
                        pct = (goal.current_amount / goal.target_amount) * 100 if goal.target_amount > 0 else 0.0
                        days_left = get_days_remaining(goal.target_date)
                        
                        with c1:
                            st.write(f"### 🎯 {goal.name} (Priority: {goal.priority.upper()})")
                            st.progress(pct / 100)
                            st.write(f"Saved: **{format_currency(goal.current_amount, currency)}** of **{format_currency(goal.target_amount, currency)}** ({pct:.1f}%)")
                        with c2:
                            st.write(f"📅 Target: **{goal.target_date.strftime('%d %b %Y')}**")
                            st.write(f"⏳ Days Left: **{days_left} days**")
                        with c3:
                            # Deposit options
                            if role != "viewer":
                                extra_sav = st.number_input(f"Deposit to {goal.name}", min_value=0.0, step=20.0, key=f"sav_dep_{goal.id}")
                                if st.button(f"Save Deposit", key=f"btn_sav_{goal.id}"):
                                    goal.current_amount += extra_sav
                                    if goal.current_amount >= goal.target_amount:
                                        goal.status = "achieved"
                                    db.commit()
                                    st.success("Savings added!")
                                    st.rerun()
                                
                        if role != "viewer":
                            if st.button("Delete Goal", key=f"del_goal_{goal.id}", type="secondary"):
                                db.delete(goal)
                                db.commit()
                                st.success("Goal deleted!")
                                st.rerun()

        # ----------------------------------------------------
        # DEBT PAYOFF TAB
        # ----------------------------------------------------
        with tab_debt:
            # 1. Add Debt Form
            if role == "viewer":
                st.info("ℹ️ Read-Only Mode: Viewers cannot log debts.")
            else:
                with st.expander("➕ Add Outstanding Debt", expanded=False):
                    with st.form("add_debt_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            d_name = st.text_input("Debt Name", placeholder="e.g. BSP Car Loan")
                            d_type = st.selectbox("Debt Type", DEBT_TYPES)
                            d_balance = st.number_input("Current Balance", min_value=1.0, value=5000.0, step=100.0)
                        with col2:
                            d_original = st.number_input("Original Borrowed Balance", min_value=1.0, value=7500.0, step=100.0)
                            d_rate = st.number_input("Interest Rate (%)", min_value=0.0, value=6.5, step=0.1)
                            d_min_pay = st.number_input("Minimum Payment Amount", min_value=1.0, value=150.0, step=10.0)
                            
                        submit_debt = st.form_submit_button("Add Debt", type="primary")
                        if submit_debt:
                            db.add(Debt(
                                household_id=household_id,
                                name=d_name,
                                type=d_type,
                                current_balance=d_balance,
                                original_balance=d_original,
                                interest_rate=d_rate,
                                minimum_payment=d_min_pay,
                                start_date=datetime.date.today()
                            ))
                            db.commit()
                            st.success("Debt record added successfully!")
                            st.rerun()
                        
            # 2. List Debts
            debts = db.query(Debt).filter(Debt.household_id == household_id).all()
            
            if not debts:
                st.info("You don't have any outstanding debts. Add a debt to enable Snowball/Avalanche simulations.")
            else:
                st.subheader("Your Outstanding Debts")
                debt_rows = []
                for d in debts:
                    debt_rows.append({
                        "ID": d.id,
                        "Name": d.name,
                        "Type": d.type,
                        "Interest": f"{d.interest_rate}%",
                        "Balance": format_currency(d.current_balance, currency),
                        "Min Payment": format_currency(d.minimum_payment, currency)
                    })
                st.dataframe(pd.DataFrame(debt_rows), width="stretch", hide_index=True)
                
                # Option to delete
                if role != "viewer":
                    del_debt_id = st.number_input("Enter Debt ID to Delete", min_value=0, step=1)
                    if st.button("Delete Debt Record", type="secondary"):
                        target = db.query(Debt).filter(Debt.id == del_debt_id, Debt.household_id == household_id).first()
                        if target:
                            db.delete(target)
                            db.commit()
                            st.success("Debt record deleted!")
                            st.rerun()
                        else:
                            st.error("Debt ID not found.")
                        
                st.markdown("---")
                
                # 3. Payoff Simulations
                st.subheader("Payoff Schedule Simulator (Snowball vs. Avalanche)")
                extra_surplus = st.number_input("Optional extra monthly payment to roll over", min_value=0.0, value=100.0, step=20.0)
                
                forecast_res = calculate_debt_payoff_forecast(db, household_id, extra_surplus)
                
                snow = forecast_res.get("snowball")
                avalanche = forecast_res.get("avalanche")
                
                if snow and avalanche:
                    col_res1, col_res2 = st.columns(2)
                    
                    with col_res1:
                        st.markdown("#### ❄️ Debt Snowball (Smallest Balance First)")
                        st.write(f"Months to Payoff: **{snow['months_to_payoff']} months**")
                        st.write(f"Total Interest: **{format_currency(snow['total_interest_paid'], currency)}**")
                        
                    with col_res2:
                        st.markdown("#### 🏔️ Debt Avalanche (Highest Interest First)")
                        st.write(f"Months to Payoff: **{avalanche['months_to_payoff']} months**")
                        st.write(f"Total Interest: **{format_currency(avalanche['total_interest_paid'], currency)}**")
                        
                    # Graph comparison
                    st.write("")
                    chart_data = []
                    for i in range(max(len(snow["schedule"]), len(avalanche["schedule"]))):
                        # Snowball balance
                        s_bal = snow["schedule"][i]["remaining_total"] if i < len(snow["schedule"]) else 0
                        # Avalanche balance
                        a_bal = avalanche["schedule"][i]["remaining_total"] if i < len(avalanche["schedule"]) else 0
                        
                        chart_data.append({
                            "Month": i + 1,
                            "Snowball Balance": s_bal,
                            "Avalanche Balance": a_bal
                        })
                        
                    df_chart = pd.DataFrame(chart_data)
                    fig = px.line(df_chart, x="Month", y=["Snowball Balance", "Avalanche Balance"], 
                                  title="Remaining Balance Comparison Over Time")
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font_color="white", font_family="Outfit"
                    )
                    st.plotly_chart(fig, use_container_width=True)
