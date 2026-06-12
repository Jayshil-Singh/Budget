import streamlit as st
import datetime
from database import get_db
from models.finance import Income, Expense, ExpenseCategory, PayPeriod
from services.finance_service import get_current_pay_period
from services.ai_service import auto_tag_category
from config import INCOME_SOURCES
from utils.helpers import can_modify
from utils.ux import toast_success, render_empty_state
from utils.fx import get_fx_rates, convert_to_fjd
from utils.attachments import save_receipt
from views.ledger_helpers import render_expense_rows, render_income_rows



def show_transaction_ledger(household_id: int, mode: str = "both"):
    """
    Renders the transaction ledger.
    mode: 'both' | 'income' | 'expense'
    """
    _titles = {
        "both": ("Money Log", "Everything you've spent and received"),
        "income": ("Income Setup", "Log pay cheques and set up recurring income"),
        "expense": ("Expense Setup", "Log one-off spending — use Recurring Bills for fixed bills"),
    }
    title, subtitle = _titles.get(mode, _titles["both"])
    st.markdown(f"<h1 class='app-title'>{title}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p class='app-subtitle'>{subtitle}</p>", unsafe_allow_html=True)

    if mode == "both":
        from views.quick_add import render_quick_add
        render_quick_add(household_id, key_prefix="ledger_qa")
        st.write("")

    if mode == "both":
        tab_exp, tab_inc = st.tabs(["💸 Spent", "💰 Received"])
    else:
        tab_exp = tab_inc = None

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
        # EXPENSES
        # ----------------------------------------------------
        if mode in ("both", "expense"):
            _exp_ctx = tab_exp if mode == "both" else st.container()
            with _exp_ctx:
                # 1. Form to add Expense
                if not can_modify(role):
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
                                        st.success(f"💡 Suggested: {suggestion}")
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
                                exp_currency = st.selectbox("Currency", list(get_fx_rates().keys()), index=0,
                                                            help="Amount will be converted to FJD at current rates.", key="new_exp_currency")
                                category_name = st.selectbox("Category", cat_list, index=default_cat_idx, key="new_exp_category")
                                if is_recurring:
                                    date = st.date_input("As of Date (Recurrence Start)", datetime.date.today(), key="new_exp_date_rec")
                                else:
                                    date = st.date_input("Date", datetime.date.today(), key="new_exp_date_normal")
                            with col2:
                                merchant = st.text_input("Merchant", value=autotag_merchant or "", placeholder="e.g. MH Supermarket", key="new_exp_merchant")
                                notes = st.text_area("Notes", placeholder="Extra details...", key="new_exp_notes")
                                receipt_file = st.file_uploader(
                                    "Receipt photo (optional)", type=["png", "jpg", "jpeg", "pdf"],
                                    key="new_exp_receipt",
                                )
                                attachment_note = st.text_input(
                                    "Receipt note (optional)",
                                    placeholder="e.g. receipt #1234",
                                    key="new_exp_attach",
                                )
                                is_recurring = False
                                frequency = None
                                if mode == "both":
                                    is_recurring = st.checkbox(
                                        "Is Recurring Bill?", value=is_recurring, key="new_exp_is_recurring",
                                    )
                                    if is_recurring:
                                        frequency_choice = st.selectbox(
                                            "Frequency",
                                            ["Weekly", "Fortnightly", "Monthly", "Custom"],
                                            index=2, key="new_exp_freq",
                                        )
                                        if frequency_choice == "Custom":
                                            custom_days = st.number_input(
                                                "Every X Days", min_value=1, max_value=365,
                                                value=30, step=1, key="new_exp_custom_days",
                                            )
                                            frequency = f"custom:{custom_days}"
                                        else:
                                            frequency = frequency_choice
                                elif mode == "expense":
                                    st.caption("Fixed bills → **Recurring Bills** in the sidebar.")

                            submit_exp = st.button("Log Expense", type="primary", key="new_exp_submit")

                            if submit_exp:
                                amount_fjd, fx_rate = convert_to_fjd(raw_amount, exp_currency)
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

                                attach_path = attachment_note.strip() or None
                                if receipt_file:
                                    attach_path = save_receipt(household_id, receipt_file)
                                exp = Expense(
                                    household_id=household_id,
                                    category_id=cat_choices[category_name],
                                    amount=amount_fjd,
                                    date=date,
                                    merchant=merchant,
                                    notes=final_notes,
                                    attachment_note=attach_path,
                                    is_recurring=is_recurring,
                                    frequency=frequency.lower() if frequency else None,
                                    pay_period_id=curr_period.id if curr_period else None,
                                    logged_by_user_id=st.session_state.get("user_id"),
                                )
                                db.add(exp)
                                db.commit()
                                msg = f"Expense logged: FJD {amount_fjd:.2f}"
                                if exp_currency != "FJD":
                                    msg += f" (converted from {raw_amount:.2f} {exp_currency})"
                                toast_success(msg)
                                st.rerun()
            
                # 2. Filter & List Expenses
                st.subheader("Logged Expenses")
            
                col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1, 1, 1])
                with col_f1:
                    f_search = st.text_input("Search", placeholder="Merchant, notes, receipt…").strip()
                with col_f2:
                    f_cat = st.multiselect("Filter Category", list(cat_choices.keys()))
                with col_f3:
                    f_merchant = st.text_input("Filter Merchant").strip()
                with col_f4:
                    f_period = st.selectbox("Filter Pay Period", ["All"] + list(period_choices.keys()))
                
                # Query builder
                query = db.query(Expense).filter(Expense.household_id == household_id)
                if f_cat:
                    query = query.filter(Expense.category_id.in_([cat_choices[c] for c in f_cat]))
                if f_merchant:
                    query = query.filter(Expense.merchant.ilike(f"%{f_merchant}%"))
                if f_search:
                    like = f"%{f_search}%"
                    query = query.filter(
                        (Expense.merchant.ilike(like))
                        | (Expense.notes.ilike(like))
                        | (Expense.attachment_note.ilike(like))
                    )
                if f_period != "All":
                    query = query.filter(Expense.pay_period_id == period_choices[f_period])
                
                expenses_list = query.order_by(Expense.date.desc()).all()
            
                if not expenses_list:
                    render_empty_state("📒", "No expenses found", "Try adjusting filters or log a new expense above.")
                else:
                    st.caption(f"{len(expenses_list)} expense(s) — expand a row to edit or delete")
                    render_expense_rows(db, household_id, expenses_list, cat_choices, currency, role)

        # ----------------------------------------------------
        # INCOME
        # ----------------------------------------------------
        if mode in ("both", "income"):
            _inc_ctx = tab_inc if mode == "both" else st.container()
            with _inc_ctx:
                # 1. Form to add Income
                if not can_modify(role):
                    st.info("ℹ️ Read-Only Mode: Viewers cannot log income.")
                else:
                    with st.expander("➕ Log New Income", expanded=False):
                        with st.container(border=True):
                            inc_recurring = st.session_state.get("new_inc_is_recurring", False)
                            col1, col2 = st.columns(2)
                            with col1:
                                inc_source_input = st.selectbox("Source", INCOME_SOURCES, key="new_inc_source")
                                inc_raw_amount = st.number_input("Net Amount", min_value=0.01, step=50.0, key="new_inc_amount")
                                inc_currency = st.selectbox("Currency", list(get_fx_rates().keys()), index=0,
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
                                inc_amount_fjd, fx_rate = convert_to_fjd(inc_raw_amount, inc_currency)
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
                                    next_date=inc_date if inc_recurring else None,
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
                    render_empty_state("💰", "No income yet", "Log salary or other money received above.")
                else:
                    st.caption(f"{len(incomes_list)} income record(s) — expand a row to edit or delete")
                    render_income_rows(db, household_id, incomes_list, currency, role)


def show_income_setup(household_id: int):
    show_transaction_ledger(household_id, mode="income")


def show_expense_setup(household_id: int):
    show_transaction_ledger(household_id, mode="expense")

