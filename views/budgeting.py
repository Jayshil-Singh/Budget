import streamlit as st
import datetime
import pandas as pd
from database import get_db
from models.finance import PayPeriod, ExpenseCategory, Expense
from models.budget import Budget, BudgetItem, SinkingFund
from services.finance_service import get_current_pay_period
from config import SINKING_FUND_TYPES
from utils.helpers import format_currency, get_days_remaining

def show_budgeting(household_id: int):
    """
    Renders the Budget and Sinking Funds management views.
    """
    st.markdown("<h1 class='app-title'>Budgets & Sinking Funds</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Set targets, check variance, and compile sinking reserve goals</p>", unsafe_allow_html=True)
    
    tab_bud, tab_sink = st.tabs(["📊 Cycle Budgets", "🏺 Sinking Funds"])
    currency = st.session_state.get("household_currency", "FJD")
    
    with get_db() as db:
        # Load active categories and current period
        categories = db.query(ExpenseCategory).filter(
            (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
        ).all()
        cat_choices = {c.name: c.id for c in categories}
        
        current_period = get_current_pay_period(db, household_id)
        
        # ----------------------------------------------------
        # CYCLE BUDGETS TAB
        # ----------------------------------------------------
        with tab_bud:
            if not current_period:
                st.info("No active pay cycle found today. Please generate pay periods.")
            else:
                st.subheader(f"Current Budget: {current_period.name}")
                
                # Fetch or create budget for the current pay period
                budget = db.query(Budget).filter(
                    Budget.household_id == household_id,
                    Budget.pay_period_id == current_period.id
                ).first()
                
                if not budget:
                    # Create placeholder budget
                    budget = Budget(
                        household_id=household_id,
                        pay_period_id=current_period.id,
                        name=f"Budget for {current_period.name}",
                        total_limit=1000.0 # Default limit
                    )
                    db.add(budget)
                    db.commit()
                    db.refresh(budget)
                    
                role = st.session_state.get("user_role", "viewer")
                
                # Configure category budget limits
                if role == "viewer":
                    st.info("ℹ️ Read-Only Mode: Viewers cannot configure budget limits.")
                else:
                    with st.expander("⚙️ Configure Budget Limits", expanded=False):
                        with st.form("budget_limits_form"):
                            st.write("Set limit amounts for each category for this period:")
                        item_inputs = {}
                        for cat_name, cat_id in cat_choices.items():
                            # Fetch existing item limit
                            item = db.query(BudgetItem).filter(
                                BudgetItem.budget_id == budget.id,
                                BudgetItem.category_id == cat_id
                            ).first()
                            existing_limit = item.limit_amount if item else 0.0
                            item_inputs[cat_id] = st.number_input(f"{cat_name} Limit", min_value=0.0, value=existing_limit, step=10.0)
                            
                        save_limits = st.form_submit_button("Save Budget Limits", type="primary")
                        if save_limits:
                            total_limit = 0.0
                            for cat_id, limit_val in item_inputs.items():
                                total_limit += limit_val
                                # Create or update
                                item = db.query(BudgetItem).filter(
                                    BudgetItem.budget_id == budget.id,
                                    BudgetItem.category_id == cat_id
                                ).first()
                                if item:
                                    item.limit_amount = limit_val
                                else:
                                    db.add(BudgetItem(budget_id=budget.id, category_id=cat_id, limit_amount=limit_val))
                                    
                            budget.total_limit = total_limit
                            db.commit()
                            st.success("Budget limits updated successfully!")
                            st.rerun()
                            
                # Display Budget vs Actual Table
                st.write("")
                budget_items = db.query(BudgetItem).filter(BudgetItem.budget_id == budget.id).all()
                
                if not budget_items:
                    st.info("Set some budget limits to see variance analysis.")
                else:
                    report_rows = []
                    total_actual = 0.0
                    total_budgeted = 0.0
                    
                    for item in budget_items:
                        # Calculate actual expenses in this period for this category
                        actual = db.query(Expense).filter(
                            Expense.household_id == household_id,
                            Expense.category_id == item.category_id,
                            Expense.pay_period_id == current_period.id
                        ).sum_amount = sum(e.amount for e in db.query(Expense).filter(
                            Expense.household_id == household_id,
                            Expense.category_id == item.category_id,
                            Expense.pay_period_id == current_period.id
                        ).all())
                        
                        variance = item.limit_amount - actual
                        status = "✅ OK"
                        if variance < 0:
                            status = "🚨 Overspent"
                        elif variance < (item.limit_amount * 0.1):
                            status = "⚠️ Warning"
                            
                        report_rows.append({
                            "Category": item.category.name,
                            "Budget Limit": format_currency(item.limit_amount, currency),
                            "Actual Spent": format_currency(actual, currency),
                            "Variance": format_currency(variance, currency),
                            "Status": status
                        })
                        total_actual += actual
                        total_budgeted += item.limit_amount
                        
                    df_budget = pd.DataFrame(report_rows)
                    st.dataframe(df_budget, width="stretch", hide_index=True)
                    
                    # Summary metrics
                    col_s1, col_s2, col_s3 = st.columns(3)
                    col_s1.metric("Total Budgeted", format_currency(total_budgeted, currency))
                    col_s2.metric("Total Spent", format_currency(total_actual, currency))
                    col_s3.metric("Remaining Budget", format_currency(total_budgeted - total_actual, currency), 
                                  delta=f"{(total_budgeted-total_actual):.2f}")

        # ----------------------------------------------------
        # SINKING FUNDS TAB
        # ----------------------------------------------------
        with tab_sink:
            st.subheader("🏺 Sinking Funds")
            st.write("Sinking funds help you save gradually for large planned expenses like Christmas, vehicle repairs, or annual insurance bills.")
            
            role = st.session_state.get("user_role", "viewer")
            
            # Form to add Sinking Fund
            if role == "viewer":
                st.info("ℹ️ Read-Only Mode: Viewers cannot create sinking funds.")
            else:
                with st.expander("➕ Create Sinking Fund", expanded=False):
                    with st.form("create_sinking_fund_form"):
                        col1, col2 = st.columns(2)
                    with col1:
                        sf_name = st.selectbox("Fund Name / Type", SINKING_FUND_TYPES)
                        sf_target = st.number_input("Target Goal Amount", min_value=10.0, value=500.0, step=50.0)
                        sf_current = st.number_input("Starting Balance", min_value=0.0, value=0.0, step=10.0)
                    with col2:
                        sf_date = st.date_input("Target Date", datetime.date.today() + datetime.timedelta(days=180))
                        sf_freq = st.selectbox("Contribution Frequency", ["Weekly", "Fortnightly", "Monthly"], index=1)
                        
                    submit_sf = st.form_submit_button("Create Fund", type="primary")
                    if submit_sf:
                        # Calculate initial contribution
                        days_left = (sf_date - datetime.date.today()).days
                        periods_left = max(1.0, days_left / (14.0 if sf_freq == "Fortnightly" else 7.0 if sf_freq == "Weekly" else 30.0))
                        contrib = max(0.0, (sf_target - sf_current) / periods_left)
                        
                        sf = SinkingFund(
                            household_id=household_id,
                            name=sf_name,
                            target_amount=sf_target,
                            current_amount=sf_current,
                            target_date=sf_date,
                            contribution_amount=contrib,
                            frequency=sf_freq.lower()
                        )
                        db.add(sf)
                        db.commit()
                        st.success("Sinking Fund created successfully!")
                        st.rerun()
                        
            # List Sinking Funds
            funds = db.query(SinkingFund).filter(SinkingFund.household_id == household_id).all()
            
            if not funds:
                st.info("You don't have any active Sinking Funds. Create one to begin saving.")
            else:
                for fund in funds:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 1, 1])
                        
                        days_left = get_days_remaining(fund.target_date)
                        # Recalculate contributions needed
                        periods_left = max(1.0, days_left / (14.0 if fund.frequency == "fortnightly" else 7.0 if fund.frequency == "weekly" else 30.0))
                        needed_contrib = max(0.0, (fund.target_amount - fund.current_amount) / periods_left)
                        
                        pct = (fund.current_amount / fund.target_amount) * 100 if fund.target_amount > 0 else 0.0
                        
                        with c1:
                            st.write(f"### 🏺 {fund.name}")
                            st.progress(pct / 100)
                            st.write(f"Saved: **{format_currency(fund.current_amount, currency)}** of **{format_currency(fund.target_amount, currency)}** ({pct:.1f}%)")
                        with c2:
                            st.write(f"📅 Target: **{fund.target_date.strftime('%d %b %Y')}**")
                            st.write(f"⏳ Days remaining: **{days_left} days**")
                        with c3:
                            st.write(f"💸 Needed per {fund.frequency}:")
                            st.subheader(format_currency(needed_contrib, currency))
                            
                            # Add contribution button
                            if role != "viewer":
                                extra_contrib = st.number_input(f"Deposit to {fund.name}", min_value=0.0, step=10.0, key=f"dep_{fund.id}")
                                if st.button(f"Add Deposit", key=f"btn_dep_{fund.id}"):
                                    fund.current_amount += extra_contrib
                                    db.commit()
                                    st.success("Deposit saved!")
                                    st.rerun()
                                    
                        if role != "viewer":
                            if st.button("Delete Fund", key=f"del_sf_{fund.id}", type="secondary"):
                                db.delete(fund)
                                db.commit()
                                st.success("Sinking Fund deleted!")
                                st.rerun()
