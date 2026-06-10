import streamlit as st
import datetime
import pandas as pd
from database import get_db
from models.household import Household, Setting
from models.finance import Income, Expense, Subscription, PayPeriod
from services.finance_service import generate_pay_periods
from utils.helpers import format_currency

# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────
FREQ_LABELS = {
    "weekly":      "Weekly",
    "fortnightly": "Fortnightly",
    "monthly":     "Monthly",
}
FREQ_PER_YEAR = {
    "weekly":      52,
    "fortnightly": 26,
    "monthly":     12,
}
FREQ_PER_MONTH = {
    "weekly":      52 / 12,   # ≈ 4.333
    "fortnightly": 26 / 12,   # ≈ 2.167
    "monthly":     1.0,
}

def _get_setting(db, household_id: int, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == key
    ).first()
    return row.value if row else default

def _set_setting(db, household_id: int, key: str, value: str):
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == key
    ).first()
    if row:
        row.value = value
    else:
        db.add(Setting(household_id=household_id, key=key, value=value))
    db.commit()


# ─────────────────────────────────────────────────────────────
# Main view
# ─────────────────────────────────────────────────────────────
def show_pay_settings(household_id: int):
    st.markdown("<h1 class='app-title'>Pay & Budget Settings</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='app-subtitle'>Configure your pay cycle, budget method, periods, and view projected savings</p>",
        unsafe_allow_html=True,
    )

    currency = st.session_state.get("household_currency", "FJD")
    role = st.session_state.get("user_role", "viewer")

    tab_cycle, tab_calc, tab_periods, tab_savings = st.tabs([
        "⚙️ Pay & Budget Cycle",
        "🔢 Budget Calculator",
        "📅 Period Manager",
        "📈 Projected Savings",
    ])

    with get_db() as db:
        household = db.query(Household).filter(Household.id == household_id).first()
        if not household:
            st.error("Household not found.")
            return

        # Read persisted settings
        pay_freq      = _get_setting(db, household_id, "pay_frequency",
                                     household.budget_method or "fortnightly")
        budget_method = household.budget_method or "fortnightly"

        # ══════════════════════════════════════════════════════
        # TAB 1 – PAY & BUDGET CYCLE
        # ══════════════════════════════════════════════════════
        with tab_cycle:
            st.subheader("⚙️ Pay Frequency & Budget Method")

            if role == "viewer":
                st.info("ℹ️ Read-Only Mode: Viewers cannot change cycle settings.")
                st.write(f"**Pay Frequency:** {FREQ_LABELS.get(pay_freq, pay_freq.capitalize())}")
                st.write(f"**Budget Method:** {FREQ_LABELS.get(budget_method, budget_method.capitalize())}")
            else:
                col1, col2 = st.columns(2)

                with col1:
                    with st.container(border=True):
                        st.markdown("#### 💵 How often are you paid?")
                        st.caption("This is your actual pay frequency — how often money lands in your account.")
                        freq_keys   = list(FREQ_LABELS.keys())
                        cur_pf_idx  = freq_keys.index(pay_freq) if pay_freq in freq_keys else 1
                        new_pay_freq = st.radio(
                            "Pay Frequency",
                            freq_keys,
                            index=cur_pf_idx,
                            format_func=lambda k: f"{FREQ_LABELS[k]} ({FREQ_PER_YEAR[k]} pays/year)",
                            key="radio_pay_freq",
                            label_visibility="collapsed",
                        )

                with col2:
                    with st.container(border=True):
                        st.markdown("#### 📊 How do you want to budget?")
                        st.caption(
                            "Your budget view frequency. Can differ from your pay frequency "
                            "— e.g., get paid fortnightly but budget monthly."
                        )
                        cur_bm_idx   = freq_keys.index(budget_method) if budget_method in freq_keys else 1
                        new_budget_method = st.radio(
                            "Budget Method",
                            freq_keys,
                            index=cur_bm_idx,
                            format_func=lambda k: f"{FREQ_LABELS[k]} ({FREQ_PER_YEAR[k]} periods/year)",
                            key="radio_budget_method",
                            label_visibility="collapsed",
                        )

                # Cross-frequency note
                if new_pay_freq != new_budget_method:
                    pays_per_budget = FREQ_PER_MONTH[new_pay_freq] / FREQ_PER_MONTH[new_budget_method]
                    st.info(
                        f"ℹ️ You get paid **{FREQ_LABELS[new_pay_freq]}** but budget **{FREQ_LABELS[new_budget_method]}**. "
                        f"Each {FREQ_LABELS[new_budget_method].lower()} budget period spans "
                        f"**{pays_per_budget:.2f} pay cheques**. "
                        f"Use the **Budget Calculator** tab to see the income/expense breakdown."
                    )

                st.write("")
                if st.button("💾 Save Cycle Settings", type="primary"):
                    _set_setting(db, household_id, "pay_frequency", new_pay_freq)
                    household.budget_method = new_budget_method
                    db.commit()
                    st.session_state["pay_freq_cache"]    = new_pay_freq
                    st.session_state["budget_method_cache"] = new_budget_method
                    st.success(
                        f"✅ Saved! Pay frequency: **{FREQ_LABELS[new_pay_freq]}** · "
                        f"Budget method: **{FREQ_LABELS[new_budget_method]}**"
                    )
                    st.rerun()

            # Summary cards
            st.markdown("---")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Pay Periods / Year",   FREQ_PER_YEAR[pay_freq])
            mc2.metric("Budget Periods / Year", FREQ_PER_YEAR[budget_method])
            mc3.metric(
                "Pays per Budget Period",
                f"{FREQ_PER_MONTH[pay_freq] / FREQ_PER_MONTH[budget_method]:.2f}",
            )

        # ══════════════════════════════════════════════════════
        # TAB 2 – BUDGET CALCULATOR
        # ══════════════════════════════════════════════════════
        with tab_calc:
            st.subheader("🔢 Cross-Frequency Budget Calculator")
            st.write(
                "Enter your per-pay-cheque income and expenses. The calculator will "
                "automatically scale them to your chosen **budget period** and to a "
                "monthly view."
            )

            with st.container(border=True):
                cc1, cc2 = st.columns(2)
                with cc1:
                    pay_freq_sel = st.selectbox(
                        "Your Pay Frequency",
                        list(FREQ_LABELS.keys()),
                        format_func=lambda k: FREQ_LABELS[k],
                        index=list(FREQ_LABELS.keys()).index(pay_freq),
                        key="calc_pay_freq",
                    )
                    income_per_pay = st.number_input(
                        f"Income per {FREQ_LABELS[pay_freq_sel]} pay",
                        min_value=0.0, value=0.0, step=50.0,
                        key="calc_income",
                    )
                with cc2:
                    budget_sel = st.selectbox(
                        "Budget View Period",
                        list(FREQ_LABELS.keys()),
                        format_func=lambda k: FREQ_LABELS[k],
                        index=list(FREQ_LABELS.keys()).index(budget_method),
                        key="calc_budget",
                    )
                    expenses_per_pay = st.number_input(
                        f"Total expenses per {FREQ_LABELS[pay_freq_sel]} pay",
                        min_value=0.0, value=0.0, step=50.0,
                        key="calc_expenses",
                    )

            # Scaling factors
            scale_to_monthly  = FREQ_PER_MONTH[pay_freq_sel]           # pays per month
            scale_to_budget   = FREQ_PER_MONTH[pay_freq_sel] / FREQ_PER_MONTH[budget_sel]

            monthly_income    = income_per_pay    * scale_to_monthly
            monthly_expenses  = expenses_per_pay  * scale_to_monthly
            monthly_net       = monthly_income    - monthly_expenses

            budget_income     = income_per_pay    * scale_to_budget
            budget_expenses   = expenses_per_pay  * scale_to_budget
            budget_net        = budget_income     - budget_expenses

            st.write("")
            st.markdown(f"#### 📊 Scaled to {FREQ_LABELS[budget_sel]} Budget Period")
            b1, b2, b3 = st.columns(3)
            b1.metric(f"Income / {FREQ_LABELS[budget_sel]}",   format_currency(budget_income,   currency))
            b2.metric(f"Expenses / {FREQ_LABELS[budget_sel]}", format_currency(budget_expenses, currency))
            b3.metric(
                f"Available / {FREQ_LABELS[budget_sel]}",
                format_currency(budget_net, currency),
                delta=f"{'▲' if budget_net >= 0 else '▼'} {abs(budget_net):.2f}",
            )

            st.markdown("#### 📅 Always-On Monthly View")
            m1, m2, m3 = st.columns(3)
            m1.metric("Monthly Income",    format_currency(monthly_income,   currency))
            m2.metric("Monthly Expenses",  format_currency(monthly_expenses, currency))
            m3.metric(
                "Monthly Available",
                format_currency(monthly_net, currency),
                delta=f"{'▲' if monthly_net >= 0 else '▼'} {abs(monthly_net):.2f}",
            )

            if pay_freq_sel != budget_sel:
                st.caption(
                    f"ℹ️ Formula: {FREQ_LABELS[pay_freq_sel]} amount × {scale_to_budget:.4f} "
                    f"= {FREQ_LABELS[budget_sel]} amount "
                    f"(based on {FREQ_PER_YEAR[pay_freq_sel]} pays/yr vs {FREQ_PER_YEAR[budget_sel]} periods/yr)"
                )

        # ══════════════════════════════════════════════════════
        # TAB 3 – PERIOD MANAGER
        # ══════════════════════════════════════════════════════
        with tab_periods:
            st.subheader("📅 Pay Period Manager")

            all_periods = db.query(PayPeriod).filter(
                PayPeriod.household_id == household_id
            ).order_by(PayPeriod.start_date.asc()).all()

            periods_per_year = FREQ_PER_YEAR[budget_method]
            st.info(
                f"Your budget method is **{FREQ_LABELS[budget_method]}** → "
                f"**{periods_per_year} periods/year**. "
                f"You currently have **{len(all_periods)} period(s)** generated."
            )

            # Generate new periods
            if role != "viewer":
                with st.expander("➕ Generate More Periods", expanded=len(all_periods) == 0):
                    gc1, gc2 = st.columns(2)
                    with gc1:
                        gen_start = st.date_input(
                            "Start Date (your next payday)",
                            value=datetime.date.today(),
                            key="pm_gen_start",
                        )
                    with gc2:
                        gen_num = st.slider(
                            "Number of periods to generate",
                            min_value=4, max_value=52,
                            value=periods_per_year,
                            step=1, key="pm_gen_num",
                        )
                    st.caption(
                        f"Tip: Generating {periods_per_year} periods covers exactly 1 year "
                        f"for {FREQ_LABELS[budget_method].lower()} budgeting."
                    )
                    if st.button("🗓️ Generate Periods", type="primary", key="pm_gen_btn"):
                        new_periods = generate_pay_periods(
                            db, household_id, gen_start, num_periods=gen_num
                        )
                        st.success(f"✅ {len(new_periods)} periods generated!")
                        st.rerun()

            # Show all periods table
            if all_periods:
                today = datetime.date.today()
                period_rows = []
                for p in all_periods:
                    is_active = p.start_date <= today <= p.end_date
                    days_left = (p.end_date - today).days if is_active else None
                    period_rows.append({
                        "Period Name":  p.name,
                        "Start Date":   p.start_date.strftime("%d %b %Y"),
                        "End Date":     p.end_date.strftime("%d %b %Y"),
                        "Status":       "🟢 Active" if is_active else ("⏳ Upcoming" if p.start_date > today else "✅ Past"),
                        "Days Left":    days_left if days_left is not None else "—",
                    })
                df_periods = pd.DataFrame(period_rows)
                st.dataframe(df_periods, hide_index=True, use_container_width=True)

                # Delete a period
                if role != "viewer":
                    st.markdown("---")
                    st.markdown("**🗑️ Delete a Period**")
                    st.caption("⚠️ Deleting a period will unlink any expenses/income tied to it (they are not deleted).")
                    period_names = {p.name: p.id for p in all_periods}
                    del_period_name = st.selectbox("Select Period to Delete", list(period_names.keys()), key="pm_del_sel")
                    if st.button("🗑️ Confirm Delete Period", type="secondary", key="pm_del_btn"):
                        del_target = db.query(PayPeriod).filter(
                            PayPeriod.id == period_names[del_period_name],
                            PayPeriod.household_id == household_id
                        ).first()
                        if del_target:
                            db.delete(del_target)
                            db.commit()
                            st.success(f"Period '{del_period_name}' deleted.")
                            st.rerun()
            else:
                st.info("No periods found. Use the form above to generate them.")

        # ══════════════════════════════════════════════════════
        # TAB 4 – PROJECTED SAVINGS
        # ══════════════════════════════════════════════════════
        with tab_savings:
            st.subheader("📈 Projected Savings")
            st.write(
                "Based on your recurring income and committed recurring expenses/subscriptions, "
                "here is your projected surplus and savings for the year."
            )

            # Recurring income
            rec_incomes = db.query(Income).filter(
                Income.household_id == household_id,
                Income.is_recurring == True
            ).all()

            # Recurring expenses
            rec_expenses = db.query(Expense).filter(
                Expense.household_id == household_id,
                Expense.is_recurring == True
            ).all()

            # Active subscriptions
            subscriptions = db.query(Subscription).filter(
                Subscription.household_id == household_id,
                Subscription.status == "active"
            ).all()

            def to_annual(amount: float, freq: str) -> float:
                freq = (freq or "monthly").lower()
                mapping = {
                    "weekly": 52, "fortnightly": 26, "monthly": 12,
                    "annual": 1, "yearly": 1, "payday": 26,
                }
                return amount * mapping.get(freq, 12)

            annual_income = sum(to_annual(i.amount, i.frequency or pay_freq) for i in rec_incomes)
            annual_exp    = sum(to_annual(e.amount, e.frequency or budget_method) for e in rec_expenses)
            annual_subs   = sum(to_annual(s.amount, s.frequency) for s in subscriptions)
            annual_total_out = annual_exp + annual_subs
            annual_net    = annual_income - annual_total_out

            # Scale to budget period
            periods_yr    = FREQ_PER_YEAR[budget_method]
            per_period_in  = annual_income / periods_yr
            per_period_out = annual_total_out / periods_yr
            per_period_net = annual_net / periods_yr

            # KPI row
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Recurring Income / Year",    format_currency(annual_income,     currency))
            k2.metric("Recurring Expenses / Year",  format_currency(annual_exp,        currency))
            k3.metric("Subscriptions / Year",       format_currency(annual_subs,       currency))
            k4.metric(
                "Net Projected Savings / Year",
                format_currency(annual_net, currency),
                delta=f"{'▲' if annual_net >= 0 else '▼'} {abs(annual_net):.2f}",
            )

            st.markdown("---")
            st.markdown(f"#### Per {FREQ_LABELS[budget_method]} Budget Period")
            p1, p2, p3 = st.columns(3)
            p1.metric(f"Income / {FREQ_LABELS[budget_method]}",   format_currency(per_period_in,  currency))
            p2.metric(f"Committed Out / {FREQ_LABELS[budget_method]}", format_currency(per_period_out, currency))
            p3.metric(
                f"Projected Surplus / {FREQ_LABELS[budget_method]}",
                format_currency(per_period_net, currency),
                delta=f"{'▲' if per_period_net >= 0 else '▼'} {abs(per_period_net):.2f}",
            )

            # Income breakdown table
            if rec_incomes:
                st.markdown("#### 💰 Recurring Income Sources")
                inc_rows = []
                for i in rec_incomes:
                    ann = to_annual(i.amount, i.frequency or pay_freq)
                    inc_rows.append({
                        "Source":         i.source,
                        "Frequency":      (i.frequency or pay_freq).capitalize(),
                        f"Per Pay":       format_currency(i.amount, currency),
                        "Annual Total":   format_currency(ann, currency),
                    })
                st.dataframe(pd.DataFrame(inc_rows), hide_index=True, use_container_width=True)

            # Expense breakdown table
            if rec_expenses or subscriptions:
                st.markdown("#### 💸 Committed Recurring Outgoings")
                out_rows = []
                for e in rec_expenses:
                    ann = to_annual(e.amount, e.frequency or budget_method)
                    out_rows.append({
                        "Description":  e.merchant or "Recurring Expense",
                        "Type":         "Fixed Expense",
                        "Frequency":    (e.frequency or budget_method).capitalize(),
                        "Per Occurrence": format_currency(e.amount, currency),
                        "Annual Total": format_currency(ann, currency),
                    })
                for s in subscriptions:
                    ann = to_annual(s.amount, s.frequency)
                    out_rows.append({
                        "Description":  s.name,
                        "Type":         "Subscription",
                        "Frequency":    s.frequency.capitalize(),
                        "Per Occurrence": format_currency(s.amount, currency),
                        "Annual Total": format_currency(ann, currency),
                    })
                st.dataframe(pd.DataFrame(out_rows), hide_index=True, use_container_width=True)

            if not rec_incomes and not rec_expenses and not subscriptions:
                st.info(
                    "No recurring transactions found. "
                    "Mark income and expenses as 'Recurring' in the Financial Ledger to see projections here."
                )

            # 12-month projection chart
            st.markdown("---")
            st.markdown("#### 📅 12-Month Cumulative Savings Projection")
            today_yr = datetime.date.today()
            monthly_in  = annual_income / 12
            monthly_out = annual_total_out / 12
            monthly_net_m = monthly_in - monthly_out
            cum_rows = []
            running = 0.0
            for m in range(1, 13):
                month_date = (today_yr.replace(day=1) + datetime.timedelta(days=31 * (m - 1))).replace(day=1)
                running += monthly_net_m
                cum_rows.append({
                    "Month":          month_date.strftime("%b %Y"),
                    "Monthly Surplus": round(monthly_net_m, 2),
                    "Cumulative Savings": round(running, 2),
                })
            df_proj = pd.DataFrame(cum_rows)
            st.dataframe(df_proj, hide_index=True, use_container_width=True)
