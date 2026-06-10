import streamlit as st
import datetime
import calendar
import pandas as pd
from database import get_db
from models.finance import PayPeriod, ExpenseCategory, Expense, Income, Subscription
from models.budget import Budget, BudgetItem, SinkingFund
from models.household import Household
from services.finance_service import get_current_pay_period, generate_pay_periods, calculate_income_for_period, calculate_expenses_for_period
from config import SINKING_FUND_TYPES
from utils.helpers import format_currency, get_days_remaining

FREQ_PER_YEAR = {"weekly": 52, "fortnightly": 26, "monthly": 12, "payday": 26}

def show_budgeting(household_id: int):
    """
    Renders the Budget and Sinking Funds management views.
    """
    st.markdown("<h1 class='app-title'>Budgets & Sinking Funds</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Set targets, check variance, and compile sinking reserve goals</p>", unsafe_allow_html=True)
    
    tab_bud, tab_sink, tab_forecast = st.tabs(["📊 Cycle Budgets", "🏺 Sinking Funds", "🔮 Interactive Forecaster"])
    currency = st.session_state.get("household_currency", "FJD")
    
    with get_db() as db:
        # Load active categories and current period
        categories = db.query(ExpenseCategory).filter(
            (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
        ).all()
        cat_choices = {c.name: c.id for c in categories}
        
        current_period = get_current_pay_period(db, household_id)
        
        # Load all periods for navigation
        all_periods = db.query(PayPeriod).filter(
            PayPeriod.household_id == household_id
        ).order_by(PayPeriod.start_date.desc()).all()

        hh = db.query(Household).filter(Household.id == household_id).first()
        budget_method    = hh.budget_method if hh else "fortnightly"
        periods_per_year = FREQ_PER_YEAR.get(budget_method, 26)
        
        # ----------------------------------------------------
        # CYCLE BUDGETS TAB
        # ----------------------------------------------------
        with tab_bud:
            if not all_periods:
                st.warning("⚠️ No pay periods found. Generate periods to get started.")
                st.markdown("---")
                st.subheader("📅 Generate Pay Periods")
                st.write(
                    f"Your budget method is **{budget_method.capitalize()}** "
                    f"({periods_per_year} periods/year). Choose a start date and generate."
                )
                gen_start = st.date_input(
                    "Pay Period Start Date",
                    value=datetime.date.today(),
                    help="Pick your next payday or the start of your current pay cycle."
                )
                gen_num = st.slider(
                    "Number of periods to generate",
                    min_value=4, max_value=52,
                    value=periods_per_year, step=1,
                    help=f"{periods_per_year} = exactly 1 year of {budget_method} periods"
                )

                if st.button("🗓️ Generate Pay Periods", type="primary"):
                    with get_db() as db_gen:
                        new_periods = generate_pay_periods(db_gen, household_id, gen_start, num_periods=gen_num)
                    if new_periods:
                        st.success(f"✅ {len(new_periods)} pay periods generated! Refreshing...")
                        st.rerun()
                    else:
                        st.error("Failed to generate pay periods. Please check your household settings.")

            else:
                # ── Period Navigator ──────────────────────────────────────
                period_map = {p.name: p for p in all_periods}
                today = datetime.date.today()

                nav_col1, nav_col2, nav_col3 = st.columns([4, 1, 1])
                with nav_col1:
                    default_name = current_period.name if current_period else list(period_map.keys())[0]
                    default_idx  = list(period_map.keys()).index(default_name) \
                                   if default_name in period_map else 0
                    selected_period_name = st.selectbox(
                        "📅 Browse Pay Period",
                        list(period_map.keys()),
                        index=default_idx,
                        help="Switch between any past, active, or upcoming period.",
                        key="bud_period_sel",
                    )
                with nav_col2:
                    st.metric("Total Periods", len(all_periods))
                with nav_col3:
                    st.metric(f"{budget_method.capitalize()}/yr", periods_per_year)

                selected_period = period_map[selected_period_name]
                is_active_period = selected_period.start_date <= today <= selected_period.end_date
                is_past_period   = selected_period.end_date < today

                if is_active_period:
                    days_left = (selected_period.end_date - today).days
                    st.success(
                        f"🟢 **Active Period** · "
                        f"{selected_period.start_date.strftime('%d %b %Y')} – "
                        f"{selected_period.end_date.strftime('%d %b %Y')} · "
                        f"**{days_left} day(s) remaining**"
                    )
                elif is_past_period:
                    st.info(
                        f"📁 **Past Period** · "
                        f"{selected_period.start_date.strftime('%d %b %Y')} – "
                        f"{selected_period.end_date.strftime('%d %b %Y')}"
                    )
                else:
                    st.warning(
                        f"⏳ **Upcoming Period** · "
                        f"{selected_period.start_date.strftime('%d %b %Y')} – "
                        f"{selected_period.end_date.strftime('%d %b %Y')}"
                    )

                st.subheader(f"Budget: {selected_period.name}")
                
                # Fetch or create budget for the selected pay period
                budget = db.query(Budget).filter(
                    Budget.household_id == household_id,
                    Budget.pay_period_id == selected_period.id
                ).first()
                
                if not budget:
                    # Create placeholder budget for the selected period
                    budget = Budget(
                        household_id=household_id,
                        pay_period_id=selected_period.id,
                        name=f"Budget for {selected_period.name}",
                        total_limit=1000.0
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
                        actual = calculate_expenses_for_period(
                            db, household_id,
                            selected_period.start_date, selected_period.end_date,
                            category_id=item.category_id
                        )
                        
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

        # ══════════════════════════════════════════════════════
        # TAB 3 – INTERACTIVE FORECASTER
        # ══════════════════════════════════════════════════════
        with tab_forecast:
            st.subheader("🔮 Interactive Savings & Cashflow Forecaster")
            st.markdown(
                "This tool helps you project your exact savings by grouping actual and recurring "
                "transactions. You can toggle between a full calendar month or a single pay cycle, "
                "and select which bills to include in your surplus projection."
            )
            
            # Helper to get occurrences
            def get_occurrences_in_range(start_date, frequency, range_start, range_end):
                occurrences = []
                if not start_date or not frequency:
                    return occurrences
                curr = start_date
                iterations = 0
                while curr <= range_end and iterations < 200:
                    if curr >= range_start:
                        occurrences.append(curr)
                    from services.recurring_service import get_next_date
                    next_dt = get_next_date(curr, frequency)
                    if next_dt <= curr:
                        break
                    curr = next_dt
                    iterations += 1
                return occurrences

            # Choose forecast mode
            forecast_mode = st.radio(
                "Forecast Range Mode",
                ["📅 Full Calendar Month", "🕒 Selected Pay Cycle Period"],
                horizontal=True,
                key="fore_mode_radio"
            )
            
            today_date = datetime.date.today()
            
            if forecast_mode == "📅 Full Calendar Month":
                months = [calendar.month_name[i] for i in range(1, 13)]
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    sel_m_name = st.selectbox("Forecast Month", months, index=today_date.month - 1, key="fore_month_sel")
                    sel_m = months.index(sel_m_name) + 1
                with col_m2:
                    sel_y = st.selectbox("Forecast Year", range(today_date.year - 1, today_date.year + 2), index=1, key="fore_year_sel")
                
                start_range = datetime.date(sel_y, sel_m, 1)
                last_day = calendar.monthrange(sel_y, sel_m)[1]
                end_range = datetime.date(sel_y, sel_m, last_day)
                st.info(f"Targeting: **{start_range.strftime('%B %Y')}** ({start_range.strftime('%d %b %Y')} – {end_range.strftime('%d %b %Y')})")
            else:
                # Use navigated selected period
                if 'selected_period' in locals() and selected_period:
                    start_range = selected_period.start_date
                    end_range = selected_period.end_date
                    st.info(f"Targeting Pay Cycle: **{selected_period.name}** ({start_range.strftime('%d %b %Y')} – {end_range.strftime('%d %b %Y')})")
                else:
                    # Fallback if no pay period selected or available
                    st.warning("Please navigate to a valid pay period in the 'Cycle Budgets' tab.")
                    start_range = today_date
                    end_range = today_date + datetime.timedelta(days=14)

            # Fetch Incomes
            # 1. Actual
            actual_incomes = db.query(Income).filter(
                Income.household_id == household_id,
                Income.is_recurring == False,
                Income.date >= start_range,
                Income.date <= end_range
            ).all()
            
            # 2. Recurring templates
            recurring_incomes = db.query(Income).filter(
                Income.household_id == household_id,
                Income.is_recurring == True
            ).all()
            
            income_items = []
            for i in actual_incomes:
                income_items.append({
                    "name": f"💰 {i.source} (Logged)",
                    "amount": i.amount,
                    "date": i.date,
                    "type": "Logged"
                })
            for template in recurring_incomes:
                occ_dates = get_occurrences_in_range(template.date, template.frequency, start_range, end_range)
                for od in occ_dates:
                    if od > today_date:
                        income_items.append({
                            "name": f"💰 {template.source} (Projected)",
                            "amount": template.amount,
                            "date": od,
                            "type": "Projected"
                        })
                        
            # Fetch Expenses
            # 1. Actual
            actual_expenses = db.query(Expense).filter(
                Expense.household_id == household_id,
                Expense.is_recurring == False,
                Expense.date >= start_range,
                Expense.date <= end_range
            ).all()
            
            # 2. Recurring templates
            recurring_expenses = db.query(Expense).filter(
                Expense.household_id == household_id,
                Expense.is_recurring == True
            ).all()
            
            # 3. Subscriptions
            subscriptions = db.query(Subscription).filter(
                Subscription.household_id == household_id,
                Subscription.status == "active"
            ).all()
            
            # 4. Custom calendar dues
            from models.finance import PaymentDueDate
            custom_dues = db.query(PaymentDueDate).filter(
                PaymentDueDate.household_id == household_id,
                PaymentDueDate.due_date >= start_range,
                PaymentDueDate.due_date <= end_range
            ).all()
            
            expense_items = []
            for e in actual_expenses:
                expense_items.append({
                    "id": f"act_{e.id}",
                    "name": f"🔴 {e.merchant or 'Expense'} ({e.category.name if e.category else 'Other'})",
                    "amount": e.amount,
                    "date": e.date,
                    "type": "Logged"
                })
            for template in recurring_expenses:
                occ_dates = get_occurrences_in_range(template.date, template.frequency, start_range, end_range)
                for od in occ_dates:
                    if od > today_date:
                        expense_items.append({
                            "id": f"proj_exp_{template.id}_{od.strftime('%Y%m%d')}",
                            "name": f"🔴 {template.merchant or 'Bill'} (Projected)",
                            "amount": template.amount,
                            "date": od,
                            "type": "Projected"
                        })
            for sub in subscriptions:
                occ_dates = get_occurrences_in_range(sub.next_renewal, sub.frequency, start_range, end_range)
                for od in occ_dates:
                    if od > today_date:
                        expense_items.append({
                            "id": f"proj_sub_{sub.id}_{od.strftime('%Y%m%d')}",
                            "name": f"🍇 Sub: {sub.name} (Projected)",
                            "amount": sub.amount,
                            "date": od,
                            "type": "Projected"
                        })
            for cd in custom_dues:
                expense_items.append({
                    "id": f"due_{cd.id}",
                    "name": f"🔔 Calendar Due: {cd.name} " + ("(Paid)" if cd.is_paid else "(Unpaid)"),
                    "amount": cd.amount,
                    "date": cd.due_date,
                    "type": "Calendar Scheduled"
                })
                
            # Sort
            income_items.sort(key=lambda x: x["date"])
            expense_items.sort(key=lambda x: x["date"])

            # Render forecaster layout
            if not income_items and not expense_items:
                st.info("No transaction data found for this forecast range.")
            else:
                st.markdown("---")
                
                # Check/Uncheck actions
                act_col1, act_col2, _ = st.columns([1, 1, 4])
                with act_col1:
                    if st.button("Check All Bills", key="fore_check_all"):
                        for item in expense_items:
                            st.session_state[f"sel_fore_{item['id']}"] = True
                        st.rerun()
                with act_col2:
                    if st.button("Uncheck All Bills", key="fore_uncheck_all"):
                        for item in expense_items:
                            st.session_state[f"sel_fore_{item['id']}"] = False
                        st.rerun()

                # Split layout: Incomes (left) & Expenses Checklist (right)
                col_l, col_r = st.columns([2, 3])
                
                selected_expense_amounts = []
                
                with col_l:
                    st.markdown("#### 💰 Expected Incomes")
                    if not income_items:
                        st.caption("No incomes expected in this range.")
                    else:
                        inc_table = []
                        for i in income_items:
                            inc_table.append({
                                "Date": i["date"].strftime("%d %b %Y"),
                                "Income Source": i["name"],
                                "Amount": format_currency(i["amount"], currency)
                            })
                        st.dataframe(pd.DataFrame(inc_table), hide_index=True, use_container_width=True)
                
                with col_r:
                    st.markdown("#### 📝 Expected Outgoings (Check to include)")
                    if not expense_items:
                        st.caption("No expenses expected in this range.")
                    else:
                        for idx, item in enumerate(expense_items):
                            chk_key = f"sel_fore_{item['id']}"
                            # Default to True
                            if chk_key not in st.session_state:
                                st.session_state[chk_key] = True
                            
                            label = f"📅 {item['date'].strftime('%d %b')} · {item['name']} · **{format_currency(item['amount'], currency)}**"
                            is_checked = st.checkbox(label, value=st.session_state[chk_key], key=chk_key)
                            if is_checked:
                                selected_expense_amounts.append(item["amount"])
                                
                # Summary Box at the bottom
                total_income_sum = sum(i["amount"] for i in income_items)
                total_expenses_sum = sum(selected_expense_amounts)
                net_savings = total_income_sum - total_expenses_sum
                
                st.markdown("---")
                st.markdown("#### 📊 Selected Range Savings Projection Summary")
                s_col1, s_col2, s_col3 = st.columns(3)
                s_col1.metric("Total Projected Income", format_currency(total_income_sum, currency))
                s_col2.metric("Projected Outgoings", format_currency(total_expenses_sum, currency))
                s_col3.metric(
                    "Remaining Balance / Savings", 
                    format_currency(net_savings, currency),
                    delta=f"{'▲' if net_savings >= 0 else '▼'} {abs(net_savings):.2f}"
                )

                # ── CUMULATIVE SAVINGS: today → end_range ──────────────────────────────
                # Only show if the end_range is in the future
                if end_range > today_date:
                    st.markdown("---")
                    st.markdown("#### 🚀 Cumulative Savings: Today → " + end_range.strftime("%d %b %Y"))
                    st.caption(
                        f"Projects how much you will accumulate from **today ({today_date.strftime('%d %b %Y')})** "
                        f"through to **{end_range.strftime('%d %b %Y')}**, "
                        "counting every recurring income & selected expense occurrence along the way."
                    )

                    # Build checked-expense id set for filtering
                    checked_exp_ids = {
                        item["id"]
                        for item in expense_items
                        if st.session_state.get(f"sel_fore_{item['id']}", True)
                    }

                    # ── Month-by-month breakdown from today to end_range ──
                    import plotly.graph_objects as go

                    # Determine month boundaries to iterate
                    def _month_ranges_between(d_start: datetime.date, d_end: datetime.date):
                        """Yields (month_label, m_start, m_end) for each calendar month in range."""
                        cur = d_start.replace(day=1)
                        while cur <= d_end:
                            if cur.month == 12:
                                nxt = datetime.date(cur.year + 1, 1, 1)
                            else:
                                nxt = datetime.date(cur.year, cur.month + 1, 1)
                            m_end = nxt - datetime.timedelta(days=1)
                            yield cur.strftime("%b %Y"), cur, min(m_end, d_end)
                            cur = nxt

                    cum_months = []
                    running_cum = 0.0

                    # Collect all recurring income templates (not yet filtered by range)
                    all_rec_incomes = db.query(Income).filter(
                        Income.household_id == household_id,
                        Income.is_recurring == True
                    ).all()
                    all_rec_expenses = db.query(Expense).filter(
                        Expense.household_id == household_id,
                        Expense.is_recurring == True
                    ).all()
                    all_subs = db.query(Subscription).filter(
                        Subscription.household_id == household_id,
                        Subscription.status == "active"
                    ).all()

                    for m_label, m_start, m_end in _month_ranges_between(today_date, end_range):
                        # Clamp range start to today for the first month
                        eff_start = max(m_start, today_date)

                        # Income: logged (non-recurring) in range
                        m_logged_inc = sum(
                            i.amount for i in db.query(Income).filter(
                                Income.household_id == household_id,
                                Income.is_recurring == False,
                                Income.date >= eff_start,
                                Income.date <= m_end
                            ).all()
                        )
                        # Income: recurring template occurrences
                        m_rec_inc = 0.0
                        for t in all_rec_incomes:
                            occ = get_occurrences_in_range(t.date, t.frequency, eff_start, m_end)
                            m_rec_inc += t.amount * len(occ)

                        m_total_inc = m_logged_inc + m_rec_inc

                        # Expenses: logged (non-recurring) in range — only include if their id is checked
                        m_logged_exp = sum(
                            e.amount for e in db.query(Expense).filter(
                                Expense.household_id == household_id,
                                Expense.is_recurring == False,
                                Expense.date >= eff_start,
                                Expense.date <= m_end
                            ).all()
                            if f"act_{e.id}" in checked_exp_ids
                        )
                        # Expenses: recurring template occurrences — only if checked
                        m_rec_exp = 0.0
                        for t in all_rec_expenses:
                            occ = get_occurrences_in_range(t.date, t.frequency, eff_start, m_end)
                            for od in occ:
                                exp_id = f"proj_exp_{t.id}_{od.strftime('%Y%m%d')}"
                                if exp_id in checked_exp_ids:
                                    m_rec_exp += t.amount
                        # Subscriptions
                        for sub in all_subs:
                            occ = get_occurrences_in_range(sub.next_renewal, sub.frequency, eff_start, m_end)
                            for od in occ:
                                sub_id = f"proj_sub_{sub.id}_{od.strftime('%Y%m%d')}"
                                if sub_id in checked_exp_ids:
                                    m_rec_exp += sub.amount

                        m_total_exp = m_logged_exp + m_rec_exp
                        m_net = m_total_inc - m_total_exp
                        running_cum += m_net

                        cum_months.append({
                            "Month": m_label,
                            "Income": round(m_total_inc, 2),
                            "Expenses": round(m_total_exp, 2),
                            "Net Saved": round(m_net, 2),
                            "Cumulative": round(running_cum, 2),
                        })

                    if cum_months:
                        # KPI row
                        total_cum_inc  = sum(r["Income"]   for r in cum_months)
                        total_cum_exp  = sum(r["Expenses"] for r in cum_months)
                        total_cum_save = running_cum

                        kc1, kc2, kc3, kc4 = st.columns(4)
                        kc1.metric("📅 Months Covered", len(cum_months))
                        kc2.metric("💰 Total Projected Income",
                                   format_currency(total_cum_inc, currency))
                        kc3.metric("💸 Total Projected Expenses",
                                   format_currency(total_cum_exp, currency))
                        kc4.metric(
                            "🏦 Total Projected Savings",
                            format_currency(total_cum_save, currency),
                            delta=f"{'▲' if total_cum_save >= 0 else '▼'} {abs(total_cum_save):.2f}"
                        )

                        st.write("")

                        import plotly.graph_objects as go
                        df_cum = pd.DataFrame(cum_months)

                        # Stacked income/expense bar + cumulative line
                        fig_cum = go.Figure()
                        fig_cum.add_trace(go.Bar(
                            name="Income",
                            x=df_cum["Month"], y=df_cum["Income"],
                            marker_color="rgba(46, 213, 115, 0.75)",
                            hovertemplate="%{x}<br>Income: %{y:,.2f}<extra></extra>"
                        ))
                        fig_cum.add_trace(go.Bar(
                            name="Expenses",
                            x=df_cum["Month"], y=df_cum["Expenses"],
                            marker_color="rgba(255, 82, 82, 0.7)",
                            hovertemplate="%{x}<br>Expenses: %{y:,.2f}<extra></extra>"
                        ))
                        fig_cum.add_trace(go.Scatter(
                            name="Cumulative Savings",
                            x=df_cum["Month"], y=df_cum["Cumulative"],
                            mode="lines+markers+text",
                            line=dict(color="#FFD700", width=3, dash="dot"),
                            marker=dict(size=8, color="#FFD700"),
                            text=[format_currency(v, currency) for v in df_cum["Cumulative"]],
                            textposition="top center",
                            textfont=dict(size=11, color="#FFD700"),
                            yaxis="y2",
                            hovertemplate="%{x}<br>Cumulative: %{y:,.2f}<extra></extra>"
                        ))
                        fig_cum.update_layout(
                            barmode="group",
                            height=340,
                            margin=dict(l=10, r=10, t=30, b=10),
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            font_color="white",
                            font_family="Outfit",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02),
                            xaxis=dict(showgrid=False),
                            yaxis=dict(
                                title="Amount",
                                showgrid=True,
                                gridcolor="rgba(255,255,255,0.05)"
                            ),
                            yaxis2=dict(
                                title="Cumulative Savings",
                                overlaying="y",
                                side="right",
                                showgrid=False,
                                tickfont=dict(color="#FFD700")
                            )
                        )
                        st.plotly_chart(fig_cum, use_container_width=True)

                        # Month-by-month detail table
                        with st.expander("📋 Month-by-Month Breakdown", expanded=False):
                            detail_rows = []
                            for r in cum_months:
                                detail_rows.append({
                                    "Month": r["Month"],
                                    "Income": format_currency(r["Income"], currency),
                                    "Expenses": format_currency(r["Expenses"], currency),
                                    "Net Saved": format_currency(r["Net Saved"], currency),
                                    "Running Total": format_currency(r["Cumulative"], currency),
                                })
                            st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)

