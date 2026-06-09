import streamlit as st
import datetime
import pandas as pd
from database import get_db
from models.finance import Income, Expense, ExpenseCategory, PayPeriod
from services.finance_service import get_current_pay_period
from services.ai_service import auto_tag_category
from config import INCOME_SOURCES
from utils.helpers import format_currency
from services.recurring_service import get_next_date


def show_transaction_ledger(household_id: int):
    """
    Renders the transaction ledger view for adding, listing, and filtering incomes and expenses.
    """
    st.markdown("<h1 class='app-title'>Financial Ledger</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Manage and review your transaction logs</p>", unsafe_allow_html=True)
    
    tab_exp, tab_inc = st.tabs(["💸 Expenses", "💰 Incomes"])
    currency = st.session_state.get("household_currency", "FJD")
    
    with get_db() as db:
        # Fetch categories and pay periods
        categories = db.query(ExpenseCategory).filter(
            (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
        ).all()
        cat_choices = {c.name: c.id for c in categories}
        
        periods = db.query(PayPeriod).filter(PayPeriod.household_id == household_id).order_by(PayPeriod.start_date.desc()).all()
        period_choices = {p.name: p.id for p in periods}
        
        role = st.session_state.get("user_role", "viewer")
        
        # ----------------------------------------------------
        # EXPENSES TAB
        # ----------------------------------------------------
        with tab_exp:
            # 1. Form to add Expense
            if role == "viewer":
                st.info("ℹ️ Read-Only Mode: Viewers cannot log expenses.")
            else:
                with st.expander("➕ Log New Expense", expanded=False):
                    # AI Auto-Tag helper (outside the form so it can interact)
                    ai_tag_cols = st.columns([3, 1])
                    with ai_tag_cols[0]:
                        autotag_merchant = st.text_input("🤖 Type Merchant to Auto-Suggest Category",
                                                          placeholder="e.g. Shell, MH Supermarket...",
                                                          key="autotag_merchant_input")
                    with ai_tag_cols[1]:
                        st.write("")
                        st.write("")
                        if st.button("🔍 Suggest Category", key="btn_autotag"):
                            if autotag_merchant:
                                suggestion = auto_tag_category(autotag_merchant, list(cat_choices.keys()))
                                if suggestion:
                                    st.session_state["autotag_suggestion"] = suggestion
                                    st.success(f"💡 Suggested: **{suggestion}**")
                                else:
                                    st.info("No category suggestion found. Please select manually.")

                    suggested_cat = st.session_state.get("autotag_suggestion", None)
                    cat_list = list(cat_choices.keys())
                    default_cat_idx = cat_list.index(suggested_cat) if suggested_cat and suggested_cat in cat_list else 0

                    with st.form("add_expense_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            amount = st.number_input("Amount", min_value=0.01, step=5.0)
                            category_name = st.selectbox("Category", cat_list, index=default_cat_idx)
                            date = st.date_input("Date", datetime.date.today())
                        with col2:
                            merchant = st.text_input("Merchant", value=autotag_merchant or "", placeholder="e.g. MH Supermarket")
                            notes = st.text_area("Notes", placeholder="Extra details...")
                            is_recurring = st.checkbox("Is Recurring Bill?")
                            frequency = st.selectbox("Frequency", ["Weekly", "Fortnightly", "Monthly"], index=2) if is_recurring else None
                            
                        submit_exp = st.form_submit_button("Log Expense", type="primary")
                        
                        if submit_exp:
                            # Find matching pay period
                            curr_period = db.query(PayPeriod).filter(
                                PayPeriod.household_id == household_id,
                                PayPeriod.start_date <= date,
                                PayPeriod.end_date >= date
                            ).first()
                            
                            exp = Expense(
                                household_id=household_id,
                                category_id=cat_choices[category_name],
                                amount=amount,
                                date=date,
                                merchant=merchant,
                                notes=notes,
                                is_recurring=is_recurring,
                                frequency=frequency.lower() if frequency else None,
                                pay_period_id=curr_period.id if curr_period else None
                            )
                            db.add(exp)
                            db.commit()
                            st.success("Expense logged successfully!")
                            st.rerun()
            
            # 2. Filter & List Expenses
            st.subheader("Logged Expenses")
            
            col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
            with col_f1:
                f_cat = st.multiselect("Filter Category", list(cat_choices.keys()))
            with col_f2:
                f_merchant = st.text_input("Filter Merchant").strip()
            with col_f3:
                f_period = st.selectbox("Filter Pay Period", ["All"] + list(period_choices.keys()))
                
            # Query builder
            query = db.query(Expense).filter(Expense.household_id == household_id)
            if f_cat:
                query = query.filter(Expense.category_id.in_([cat_choices[c] for c in f_cat]))
            if f_merchant:
                query = query.filter(Expense.merchant.ilike(f"%{f_merchant}%"))
            if f_period != "All":
                query = query.filter(Expense.pay_period_id == period_choices[f_period])
                
            expenses_list = query.order_by(Expense.date.desc()).all()
            
            if not expenses_list:
                st.info("No matching expenses found.")
            else:
                expense_rows = []
                for e in expenses_list:
                    expense_rows.append({
                        "ID": e.id,
                        "Date": e.date,
                        "Category": e.category.name if e.category else "Other",
                        "Merchant": e.merchant or "",
                        "Amount": format_currency(e.amount, currency),
                        "Recurring": "Yes" if e.is_recurring else "No"
                    })
                df_exp = pd.DataFrame(expense_rows)
                st.dataframe(df_exp, width="stretch", hide_index=True)
                
                # Option to delete
                if role != "viewer":
                    delete_id = st.number_input("Enter Expense ID to Delete", min_value=0, step=1)
                    if st.button("Delete Expense", type="secondary"):
                        target = db.query(Expense).filter(Expense.id == delete_id, Expense.household_id == household_id).first()
                        if target:
                            db.delete(target)
                            db.commit()
                            st.success("Expense deleted successfully!")
                            st.rerun()
                        else:
                            st.error("Expense ID not found.")

        # ----------------------------------------------------
        # INCOMES TAB
        # ----------------------------------------------------
        with tab_inc:
            # 1. Form to add Income
            if role == "viewer":
                st.info("ℹ️ Read-Only Mode: Viewers cannot log income.")
            else:
                with st.expander("➕ Log New Income", expanded=False):
                    with st.form("add_income_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            inc_source_input = st.selectbox("Source", INCOME_SOURCES)
                            inc_amount_input = st.number_input("Net Amount", min_value=0.01, step=50.0)
                        with col2:
                            inc_date = st.date_input("Date Received", datetime.date.today())
                            inc_recurring = st.checkbox("Is Recurring Paycheck?")
                            inc_freq_input = st.selectbox("Pay Interval", ["Weekly", "Fortnightly", "Monthly"], index=1) if inc_recurring else None
                            
                        submit_inc = st.form_submit_button("Log Income", type="primary")
                        
                        if submit_inc:
                            curr_period = db.query(PayPeriod).filter(
                                PayPeriod.household_id == household_id,
                                PayPeriod.start_date <= inc_date,
                                PayPeriod.end_date >= inc_date
                            ).first()
                            
                            inc = Income(
                                household_id=household_id,
                                source=inc_source_input,
                                amount=inc_amount_input,
                                date=inc_date,
                                is_recurring=inc_recurring,
                                frequency=inc_freq_input.lower() if inc_freq_input else None,
                                next_date=get_next_date(inc_date, inc_freq_input) if inc_recurring else None,
                                pay_period_id=curr_period.id if curr_period else None
                            )
                            db.add(inc)
                            db.commit()
                            st.success("Income logged successfully!")
                            st.rerun()
                        
            # 2. List Incomes
            st.subheader("Logged Income Records")
            incomes_list = db.query(Income).filter(Income.household_id == household_id).order_by(Income.date.desc()).all()
            
            if not incomes_list:
                st.info("No income records found.")
            else:
                income_rows = []
                for i in incomes_list:
                    income_rows.append({
                        "ID": i.id,
                        "Date": i.date,
                        "Source": i.source,
                        "Amount": format_currency(i.amount, currency),
                        "Recurring": "Yes" if i.is_recurring else "No",
                        "Frequency": i.frequency or ""
                    })
                df_inc = pd.DataFrame(income_rows)
                st.dataframe(df_inc, width="stretch", hide_index=True)
                
                # Delete income
                if role != "viewer":
                    delete_inc_id = st.number_input("Enter Income ID to Delete", min_value=0, step=1)
                    if st.button("Delete Income", type="secondary"):
                        target = db.query(Income).filter(Income.id == delete_inc_id, Income.household_id == household_id).first()
                        if target:
                            db.delete(target)
                            db.commit()
                            st.success("Income record deleted successfully!")
                            st.rerun()
                        else:
                            st.error("Income ID not found.")
