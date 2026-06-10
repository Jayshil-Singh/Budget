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

# Static FX conversion rates → FJD (updated periodically, no external API needed)
FX_TO_FJD = {
    "FJD": 1.0,
    "AUD": 1.54,
    "NZD": 1.41,
    "USD": 2.28,
}


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

                    with st.container(border=True):
                        is_recurring = st.session_state.get("new_exp_is_recurring", False)
                        col1, col2 = st.columns(2)
                        with col1:
                            raw_amount = st.number_input("Amount", min_value=0.01, step=5.0, key="new_exp_amount")
                            exp_currency = st.selectbox("Currency", list(FX_TO_FJD.keys()), index=0,
                                                        help="Amount will be converted to FJD at current rates.", key="new_exp_currency")
                            category_name = st.selectbox("Category", cat_list, index=default_cat_idx, key="new_exp_category")
                            if is_recurring:
                                date = st.date_input("As of Date (Recurrence Start)", datetime.date.today(), key="new_exp_date_rec")
                            else:
                                date = st.date_input("Date", datetime.date.today(), key="new_exp_date_normal")
                        with col2:
                            merchant = st.text_input("Merchant", value=autotag_merchant or "", placeholder="e.g. MH Supermarket", key="new_exp_merchant")
                            notes = st.text_area("Notes", placeholder="Extra details...", key="new_exp_notes")
                            is_recurring = st.checkbox("Is Recurring Bill?", value=is_recurring, key="new_exp_is_recurring")
                            if is_recurring:
                                frequency_choice = st.selectbox("Frequency", ["Weekly", "Fortnightly", "Monthly", "Custom"], index=2, key="new_exp_freq")
                                if frequency_choice == "Custom":
                                    custom_days = st.number_input("Every X Days", min_value=1, max_value=365, value=30, step=1, key="new_exp_custom_days")
                                    frequency = f"custom:{custom_days}"
                                else:
                                    frequency = frequency_choice
                            else:
                                frequency = None

                        submit_exp = st.button("Log Expense", type="primary", key="new_exp_submit")

                        if submit_exp:
                            fx_rate = FX_TO_FJD.get(exp_currency, 1.0)
                            amount_fjd = round(raw_amount * fx_rate, 2)
                            conversion_note = ""
                            if exp_currency != "FJD":
                                conversion_note = f"[Converted from {raw_amount:.2f} {exp_currency} @ rate {fx_rate}]"
                            final_notes = (notes + "\n" + conversion_note).strip() if conversion_note else notes

                            # Find matching pay period
                            curr_period = db.query(PayPeriod).filter(
                                PayPeriod.household_id == household_id,
                                PayPeriod.start_date <= date,
                                PayPeriod.end_date >= date
                            ).first()

                            exp = Expense(
                                household_id=household_id,
                                category_id=cat_choices[category_name],
                                amount=amount_fjd,
                                date=date,
                                merchant=merchant,
                                notes=final_notes,
                                is_recurring=is_recurring,
                                frequency=frequency.lower() if frequency else None,
                                pay_period_id=curr_period.id if curr_period else None
                            )
                            db.add(exp)
                            db.commit()
                            msg = f"Expense logged: FJD {amount_fjd:.2f}"
                            if exp_currency != "FJD":
                                msg += f" (converted from {raw_amount:.2f} {exp_currency})"
                            st.success(msg)
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
                
                # Edit & Delete options
                if role != "viewer":
                    st.markdown("---")
                    col_edit, col_del = st.columns(2)

                    # ── EDIT EXPENSE ──
                    with col_edit:
                        with st.expander("✏️ Edit an Expense", expanded=False):
                            edit_id = st.number_input("Expense ID to Edit", min_value=0, step=1, key="edit_exp_id")
                            if edit_id > 0:
                                edit_target = db.query(Expense).filter(
                                    Expense.id == edit_id, Expense.household_id == household_id
                                ).first()
                                if edit_target:
                                    with st.container(border=True):
                                        st.caption(f"Editing Expense #{edit_id}")
                                        rec_key = f"edit_exp_rec_{edit_id}"
                                        if rec_key not in st.session_state:
                                            st.session_state[rec_key] = bool(edit_target.is_recurring)
                                        new_recurring = st.session_state[rec_key]

                                        ec1, ec2 = st.columns(2)
                                        cat_list_e = list(cat_choices.keys())
                                        cur_cat = edit_target.category.name if edit_target.category else cat_list_e[0]
                                        cur_cat_idx = cat_list_e.index(cur_cat) if cur_cat in cat_list_e else 0
                                        with ec1:
                                            new_amount = st.number_input("Amount (FJD)", min_value=0.01, value=float(edit_target.amount), step=5.0, key=f"edit_exp_amt_{edit_id}")
                                            new_cat = st.selectbox("Category", cat_list_e, index=cur_cat_idx, key=f"edit_exp_cat_{edit_id}")
                                            if new_recurring:
                                                new_date = st.date_input("As of Date (Recurrence Start)", value=edit_target.date, key=f"edit_exp_date_{edit_id}")
                                            else:
                                                new_date = st.date_input("Date", value=edit_target.date, key=f"edit_exp_date_{edit_id}")
                                        with ec2:
                                            new_merchant = st.text_input("Merchant", value=edit_target.merchant or "", key=f"edit_exp_merch_{edit_id}")
                                            new_notes = st.text_area("Notes", value=edit_target.notes or "", key=f"edit_exp_notes_{edit_id}")
                                            new_recurring = st.checkbox("Recurring?", value=new_recurring, key=rec_key)
                                            if new_recurring:
                                                freq_opts = ["Weekly", "Fortnightly", "Monthly", "Custom"]
                                                cur_freq = edit_target.frequency or ""
                                                if cur_freq.startswith("custom:"):
                                                    cur_freq_idx = 3
                                                else:
                                                    cur_freq_cap = cur_freq.capitalize()
                                                    cur_freq_idx = freq_opts.index(cur_freq_cap) if cur_freq_cap in freq_opts else 2
                                                new_freq_choice = st.selectbox("Frequency", freq_opts, index=cur_freq_idx, key=f"edit_exp_freq_{edit_id}")
                                                if new_freq_choice == "Custom":
                                                    existing_days = 30
                                                    if cur_freq.startswith("custom:"):
                                                        try:
                                                            existing_days = int(cur_freq.split(":")[1].strip())
                                                        except Exception:
                                                            pass
                                                    new_custom_days = st.number_input("Every X Days", min_value=1, max_value=365, value=existing_days, step=1, key=f"edit_exp_custom_days_{edit_id}")
                                                    new_freq = f"custom:{new_custom_days}"
                                                else:
                                                    new_freq = new_freq_choice
                                            else:
                                                new_freq = None

                                        save_exp = st.button("💾 Save Changes", type="primary", key=f"edit_exp_save_{edit_id}")
                                        if save_exp:
                                            edit_target.amount = new_amount
                                            edit_target.category_id = cat_choices[new_cat]
                                            edit_target.date = new_date
                                            edit_target.merchant = new_merchant
                                            edit_target.notes = new_notes
                                            edit_target.is_recurring = new_recurring
                                            edit_target.frequency = new_freq.lower() if new_freq else None
                                            # Re-link pay period based on updated date
                                            updated_period = db.query(PayPeriod).filter(
                                                PayPeriod.household_id == household_id,
                                                PayPeriod.start_date <= new_date,
                                                PayPeriod.end_date >= new_date
                                            ).first()
                                            edit_target.pay_period_id = updated_period.id if updated_period else None
                                            db.commit()
                                            st.success(f"✅ Expense #{edit_id} updated successfully!")
                                            st.rerun()
                                else:
                                    st.error("Expense ID not found.")

                    # ── DELETE EXPENSE ──
                    with col_del:
                        with st.expander("🗑️ Delete an Expense", expanded=False):
                            delete_id = st.number_input("Expense ID to Delete", min_value=0, step=1, key="del_exp_id")
                            if delete_id > 0:
                                del_target = db.query(Expense).filter(
                                    Expense.id == delete_id, Expense.household_id == household_id
                                ).first()
                                if del_target:
                                    st.warning(f"⚠️ You are about to delete: **{del_target.merchant or 'Expense'}** — {format_currency(del_target.amount, currency)} on {del_target.date}")
                                    if st.button("🗑️ Confirm Delete Expense", type="secondary", key="confirm_del_exp"):
                                        db.delete(del_target)
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
                    with st.container(border=True):
                        inc_recurring = st.session_state.get("new_inc_is_recurring", False)
                        col1, col2 = st.columns(2)
                        with col1:
                            inc_source_input = st.selectbox("Source", INCOME_SOURCES, key="new_inc_source")
                            inc_raw_amount = st.number_input("Net Amount", min_value=0.01, step=50.0, key="new_inc_amount")
                            inc_currency = st.selectbox("Currency", list(FX_TO_FJD.keys()), index=0,
                                                        help="Amount will be converted to FJD at current rates.", key="new_inc_currency")
                            if inc_recurring:
                                inc_date = st.date_input("As of Date (Recurrence Start)", datetime.date.today(), key="new_inc_date_rec")
                            else:
                                inc_date = st.date_input("Date Received", datetime.date.today(), key="new_inc_date_normal")
                        with col2:
                            inc_recurring = st.checkbox("Is Recurring Paycheck?", value=inc_recurring, key="new_inc_is_recurring")
                            if inc_recurring:
                                inc_freq_choice = st.selectbox("Pay Interval", ["Weekly", "Fortnightly", "Monthly", "Custom"], index=1, key="new_inc_freq")
                                if inc_freq_choice == "Custom":
                                    inc_custom_days = st.number_input("Every X Days", min_value=1, max_value=365, value=14, step=1, key="new_inc_custom_days")
                                    inc_freq_input = f"custom:{inc_custom_days}"
                                else:
                                    inc_freq_input = inc_freq_choice
                            else:
                                inc_freq_input = None

                        submit_inc = st.button("Log Income", type="primary", key="new_inc_submit")

                        if submit_inc:
                            fx_rate = FX_TO_FJD.get(inc_currency, 1.0)
                            inc_amount_fjd = round(inc_raw_amount * fx_rate, 2)
                            inc_desc = ""
                            if inc_currency != "FJD":
                                inc_desc = f"Converted from {inc_raw_amount:.2f} {inc_currency} @ rate {fx_rate}"

                            curr_period = db.query(PayPeriod).filter(
                                PayPeriod.household_id == household_id,
                                PayPeriod.start_date <= inc_date,
                                PayPeriod.end_date >= inc_date
                            ).first()

                            inc = Income(
                                household_id=household_id,
                                source=inc_source_input,
                                amount=inc_amount_fjd,
                                date=inc_date,
                                is_recurring=inc_recurring,
                                frequency=inc_freq_input.lower() if inc_freq_input else None,
                                next_date=get_next_date(inc_date, inc_freq_input) if inc_recurring else None,
                                pay_period_id=curr_period.id if curr_period else None,
                                description=inc_desc or None
                            )
                            db.add(inc)
                            db.commit()
                            msg = f"Income logged: FJD {inc_amount_fjd:.2f}"
                            if inc_currency != "FJD":
                                msg += f" (converted from {inc_raw_amount:.2f} {inc_currency})"
                            st.success(msg)
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
                
                # Edit & Delete options
                if role != "viewer":
                    st.markdown("---")
                    col_inc_edit, col_inc_del = st.columns(2)

                    # ── EDIT INCOME ──
                    with col_inc_edit:
                        with st.expander("✏️ Edit an Income Record", expanded=False):
                            edit_inc_id = st.number_input("Income ID to Edit", min_value=0, step=1, key="edit_inc_id")
                            if edit_inc_id > 0:
                                edit_inc = db.query(Income).filter(
                                    Income.id == edit_inc_id, Income.household_id == household_id
                                ).first()
                                if edit_inc:
                                    with st.container(border=True):
                                        st.caption(f"Editing Income #{edit_inc_id}")
                                        inc_rec_key = f"edit_inc_rec_{edit_inc_id}"
                                        if inc_rec_key not in st.session_state:
                                            st.session_state[inc_rec_key] = bool(edit_inc.is_recurring)
                                        new_inc_recurring = st.session_state[inc_rec_key]

                                        ic1, ic2 = st.columns(2)
                                        cur_src_idx = INCOME_SOURCES.index(edit_inc.source) if edit_inc.source in INCOME_SOURCES else 0
                                        with ic1:
                                            new_inc_source = st.selectbox("Source", INCOME_SOURCES, index=cur_src_idx, key=f"edit_inc_source_{edit_inc_id}")
                                            new_inc_amount = st.number_input("Amount (FJD)", min_value=0.01, value=float(edit_inc.amount), step=50.0, key=f"edit_inc_amount_{edit_inc_id}")
                                            if new_inc_recurring:
                                                new_inc_date = st.date_input("As of Date (Recurrence Start)", value=edit_inc.date, key=f"edit_inc_date_{edit_inc_id}")
                                            else:
                                                new_inc_date = st.date_input("Date", value=edit_inc.date, key=f"edit_inc_date_{edit_inc_id}")
                                        with ic2:
                                            new_inc_recurring = st.checkbox("Recurring?", value=new_inc_recurring, key=inc_rec_key)
                                            if new_inc_recurring:
                                                freq_opts_i = ["Weekly", "Fortnightly", "Monthly", "Custom"]
                                                cur_freq_i_val = edit_inc.frequency or ""
                                                if cur_freq_i_val.startswith("custom:"):
                                                    cur_freq_i = 3
                                                else:
                                                    cur_freq_cap_i = cur_freq_i_val.capitalize()
                                                    cur_freq_i = freq_opts_i.index(cur_freq_cap_i) if cur_freq_cap_i in freq_opts_i else 1
                                                new_inc_freq_choice = st.selectbox("Frequency", freq_opts_i, index=cur_freq_i, key=f"edit_inc_freq_{edit_inc_id}")
                                                if new_inc_freq_choice == "Custom":
                                                    existing_days_i = 14
                                                    if cur_freq_i_val.startswith("custom:"):
                                                        try:
                                                            existing_days_i = int(cur_freq_i_val.split(":")[1].strip())
                                                        except Exception:
                                                            pass
                                                    new_inc_custom_days = st.number_input("Every X Days", min_value=1, max_value=365, value=existing_days_i, step=1, key=f"edit_inc_custom_days_{edit_inc_id}")
                                                    new_inc_freq = f"custom:{new_inc_custom_days}"
                                                else:
                                                    new_inc_freq = new_inc_freq_choice
                                            else:
                                                new_inc_freq = None
                                            new_inc_desc = st.text_area("Description / Notes", value=edit_inc.description or "", key=f"edit_inc_desc_{edit_inc_id}")

                                        save_inc = st.button("💾 Save Changes", type="primary", key=f"edit_inc_save_{edit_inc_id}")
                                        if save_inc:
                                            edit_inc.source = new_inc_source
                                            edit_inc.amount = new_inc_amount
                                            edit_inc.date = new_inc_date
                                            edit_inc.is_recurring = new_inc_recurring
                                            edit_inc.frequency = new_inc_freq.lower() if new_inc_freq else None
                                            edit_inc.description = new_inc_desc or None
                                            if new_inc_recurring:
                                                edit_inc.next_date = get_next_date(new_inc_date, new_inc_freq)
                                            else:
                                                edit_inc.next_date = None
                                            # Re-link pay period based on updated date
                                            updated_inc_period = db.query(PayPeriod).filter(
                                                PayPeriod.household_id == household_id,
                                                PayPeriod.start_date <= new_inc_date,
                                                PayPeriod.end_date >= new_inc_date
                                            ).first()
                                            edit_inc.pay_period_id = updated_inc_period.id if updated_inc_period else None
                                            db.commit()
                                            st.success(f"✅ Income #{edit_inc_id} updated successfully!")
                                            st.rerun()
                                else:
                                    st.error("Income ID not found.")

                    # ── DELETE INCOME ──
                    with col_inc_del:
                        with st.expander("🗑️ Delete an Income Record", expanded=False):
                            delete_inc_id = st.number_input("Income ID to Delete", min_value=0, step=1, key="del_inc_id")
                            if delete_inc_id > 0:
                                del_inc = db.query(Income).filter(
                                    Income.id == delete_inc_id, Income.household_id == household_id
                                ).first()
                                if del_inc:
                                    st.warning(f"⚠️ You are about to delete: **{del_inc.source}** — {format_currency(del_inc.amount, currency)} on {del_inc.date}")
                                    if st.button("🗑️ Confirm Delete Income", type="secondary", key="confirm_del_inc"):
                                        db.delete(del_inc)
                                        db.commit()
                                        st.success("Income record deleted successfully!")
                                        st.rerun()
                                else:
                                    st.error("Income ID not found.")

