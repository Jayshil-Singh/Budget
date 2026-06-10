import streamlit as st
import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from database import get_db
from models.finance import Income, Expense, ExpenseCategory, PayPeriod
from models.budget import Budget, BudgetItem, SavingsGoal, Debt, SinkingFund
from models.audit import Notification
from models.household import HouseholdMember
from models.auth import User
from services.finance_service import (
    get_current_pay_period, 
    calculate_financial_health_score, 
    calculate_emergency_fund_coverage,
    get_essential_expenses_monthly
)
try:
    from services.forecast_service import calculate_current_balance, generate_cashflow_projection
except Exception:
    def calculate_current_balance(db, household_id):
        from sqlalchemy import func
        from models.finance import Income, Expense
        total_income = db.query(func.sum(Income.amount)).filter(Income.household_id == household_id).scalar() or 0.0
        total_expense = db.query(func.sum(Expense.amount)).filter(Expense.household_id == household_id).scalar() or 0.0
        return total_income - total_expense
    def generate_cashflow_projection(db, household_id, days=90):
        return []
from utils.helpers import format_currency, get_health_score_rating

def show_dashboard(household_id: int):
    """
    Renders the modern banking-style command center dashboard.
    """
    with get_db() as db:
        # Load core configurations
        h_name = st.session_state.get("household_name", "Household")
        currency = st.session_state.get("household_currency", "FJD")
        
        # 1. Fetch current balance & totals
        balance = calculate_current_balance(db, household_id)
        
        goals_total = sum(g.current_amount for g in db.query(SavingsGoal).filter(
            SavingsGoal.household_id == household_id, SavingsGoal.status == "active"
        ).all())
        
        sinking_total = sum(f.current_amount for f in db.query(SinkingFund).filter(
            SinkingFund.household_id == household_id
        ).all())
        
        savings_total = goals_total + sinking_total
        
        debt_total = sum(d.current_balance for d in db.query(Debt).filter(
            Debt.household_id == household_id
        ).all())
        
        net_worth = balance + savings_total - debt_total
        
        # 2. Get current pay period details
        current_period = get_current_pay_period(db, household_id)
        
        period_income = 0.0
        period_expenses = 0.0
        days_remaining = 0
        
        if current_period:
            period_income = sum(i.amount for i in db.query(Income).filter(
                Income.household_id == household_id,
                Income.date >= current_period.start_date,
                Income.date <= current_period.end_date
            ).all())
            
            period_expenses = sum(e.amount for e in db.query(Expense).filter(
                Expense.household_id == household_id,
                Expense.date >= current_period.start_date,
                Expense.date <= current_period.end_date
            ).all())
            
            today = datetime.date.today()
            if today <= current_period.end_date:
                days_remaining = max(0, (current_period.end_date - today).days)
                
        # 3. Calculate scores
        health_score, health_details = calculate_financial_health_score(db, household_id)
        _, coverage_months, coverage_rating = calculate_emergency_fund_coverage(db, household_id)
        
        # 4. Cashflow Trend (last 30 days)
        last_30_days = datetime.date.today() - datetime.timedelta(days=30)
        recent_expenses = db.query(Expense).filter(
            Expense.household_id == household_id, Expense.date >= last_30_days
        ).all()
        
        # Title Header
        st.markdown(f"<h1 class='app-title'>{h_name} Command Center</h1>", unsafe_allow_html=True)
        st.markdown(f"<p class='app-subtitle'>Payday Tracker & Insights • Currency: <strong>{currency}</strong></p>", unsafe_allow_html=True)
        
        # Show Alerts
        if coverage_months < 3.0:
            st.warning(f"⚠️ **Low Emergency Fund Alert:** You have only {coverage_months:.1f} months of essential coverage. Consider increasing contributions to your Emergency Sinking Fund.")
            
        # ----------------------------------------------------
        # ROW 1: PRIMARY KPI METRIC CARDS
        # ----------------------------------------------------
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-label">Current Balance</div>
                <div class="kpi-value">{format_currency(balance, currency)}</div>
                <div class="kpi-delta neutral">Cash ledger available</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-label">Cycle Net Flow</div>
                <div class="kpi-value">{format_currency(period_income - period_expenses, currency)}</div>
                <div class="kpi-delta {'up' if period_income >= period_expenses else 'down'}">
                    {'Positive' if period_income >= period_expenses else 'Deficit'} this period
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-label">Total Savings</div>
                <div class="kpi-value">{format_currency(savings_total, currency)}</div>
                <div class="kpi-delta up">Goals & Sinking Funds</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col4:
            st.markdown(f"""
            <div class="kpi-container">
                <div class="kpi-label">Net Worth</div>
                <div class="kpi-value">{format_currency(net_worth, currency)}</div>
                <div class="kpi-delta {'up' if net_worth >= 0 else 'down'}">
                    {'Assets exceed debt' if net_worth >= 0 else 'Net liability'}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        st.write("")
        
        # ----------------------------------------------------
        # ROW 2: SCORES & CYCLE STATS
        # ----------------------------------------------------
        sc1, sc2, sc3 = st.columns([1, 1, 1])
        
        with sc1:
            with st.container(border=True):
                st.subheader("Financial Health Index")
                
                # Plotly Health Score Gauge
                fig_health = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = health_score,
                    domain = {'x': [0, 1], 'y': [0, 1]},
                    title = {'text': f"Rating: {get_health_score_rating(health_score)}", 'font': {'size': 14}},
                    gauge = {
                        'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "white"},
                        'bar': {'color': "#00C9FF"},
                        'bgcolor': "rgba(0,0,0,0)",
                        'borderwidth': 2,
                        'bordercolor': "rgba(255,255,255,0.1)",
                        'steps': [
                            {'range': [0, 40], 'color': 'rgba(255, 82, 82, 0.2)'},
                            {'range': [40, 75], 'color': 'rgba(255, 177, 66, 0.2)'},
                            {'range': [75, 100], 'color': 'rgba(46, 213, 115, 0.2)'}
                        ]
                    }
                ))
                fig_health.update_layout(
                    height=180, margin=dict(l=10, r=10, t=30, b=10),
                    paper_bgcolor="rgba(0,0,0,0)", font={'color': "white", 'family': "Outfit"}
                )
                st.plotly_chart(fig_health, use_container_width=True)
                
        with sc2:
            with st.container(border=True):
                st.subheader("Emergency Fund")
                
                # Plotly Emergency coverage Gauge
                fig_cover = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = coverage_months,
                    domain = {'x': [0, 1], 'y': [0, 1]},
                    title = {'text': f"Coverage: {coverage_rating}", 'font': {'size': 14}},
                    gauge = {
                        'axis': {'range': [None, 12], 'tickwidth': 1, 'tickcolor': "white"},
                        'bar': {'color': "#2ED573"},
                        'bgcolor': "rgba(0,0,0,0)",
                        'steps': [
                            {'range': [0, 3], 'color': 'rgba(255, 82, 82, 0.2)'},
                            {'range': [3, 6], 'color': 'rgba(255, 177, 66, 0.2)'},
                            {'range': [6, 12], 'color': 'rgba(46, 213, 115, 0.2)'}
                        ]
                    }
                ))
                fig_cover.update_layout(
                    height=180, margin=dict(l=10, r=10, t=30, b=10),
                    paper_bgcolor="rgba(0,0,0,0)", font={'color': "white", 'family': "Outfit"}
                )
                st.plotly_chart(fig_cover, use_container_width=True)
                
        with sc3:
            with st.container(border=True):
                st.subheader("Current Pay Cycle")
                if current_period:
                    st.write(f"📅 **{current_period.name}**")
                    st.write(f"💰 Available Income: **{format_currency(period_income, currency)}**")
                    st.write(f"💸 Actual Expenses: **{format_currency(period_expenses, currency)}**")
                    
                    # Daily spending limit calculation
                    daily_limit = 0.0
                    if days_remaining > 0:
                        daily_limit = max(0.0, (period_income - period_expenses) / days_remaining)
                    st.metric("Suggested Daily Limit", format_currency(daily_limit, currency), f"{days_remaining} days left")
                else:
                    st.info("No active pay cycle found for today. Generate cycles under the Budgeting panel.")
                    
        # ----------------------------------------------------
        # ROW 3: CHARTS
        # ----------------------------------------------------
        ch1, ch2 = st.columns(2)
        
        with ch1:
            with st.container(border=True):
                st.subheader("Spending by Category (Last 30 Days)")
                if recent_expenses:
                    # Group data
                    cat_data = []
                    for e in recent_expenses:
                        cat_data.append({
                            "Category": e.category.name if e.category else "Other",
                            "Amount": e.amount
                        })
                    df_cat = pd.DataFrame(cat_data).groupby("Category").sum().reset_index()
                    
                    fig_pie = px.pie(
                        df_cat, values='Amount', names='Category', hole=0.4,
                        color_discrete_sequence=px.colors.sequential.Tealgrn
                    )
                    fig_pie.update_layout(
                        margin=dict(l=10, r=10, t=10, b=10), height=280,
                        paper_bgcolor="rgba(0,0,0,0)", legend_font_color="white", font_family="Outfit"
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("No expenses logged in the last 30 days. Log them in the Ledger tab.")
                    
        with ch2:
            with st.container(border=True):
                st.subheader("90-Day Cashflow Forecast")
                # Generate forecast data
                forecast = generate_cashflow_projection(db, household_id, days=90)
                if forecast:
                    df_fore = pd.DataFrame(forecast)
                    fig_line = px.line(
                        df_fore, x="date", y="balance", 
                        labels={"balance": "Projected Balance", "date": "Date"}
                    )
                    fig_line.update_traces(line_color="#00C9FF", line_width=3)
                    fig_line.update_layout(
                        margin=dict(l=10, r=10, t=10, b=10), height=280,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font_color="white", font_family="Outfit",
                        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
                    )
                    st.plotly_chart(fig_line, use_container_width=True)
                else:
                    st.info("Insufficient recurring data to generate forecast projections.")

        # ----------------------------------------------------
        # ROW 4: BUDGET VS ACTUAL & SPENDING TREND
        # ----------------------------------------------------
        st.write("")
        row4_c1, row4_c2 = st.columns(2)

        with row4_c1:
            with st.container(border=True):
                st.subheader("Budget vs Actual (Current Period)")
                if current_period:
                    # Get budget items for current period
                    budget = db.query(Budget).filter(
                        Budget.household_id == household_id,
                        Budget.pay_period_id == current_period.id
                    ).first()

                    if budget and budget.items:
                        bv_categories, bv_budgeted, bv_actual = [], [], []
                        for item in budget.items:
                            cat_name = item.category.name if item.category else "Other"
                            actual_spend = sum(
                                e.amount for e in db.query(Expense).filter(
                                    Expense.household_id == household_id,
                                    Expense.category_id == item.category_id,
                                    Expense.date >= current_period.start_date,
                                    Expense.date <= current_period.end_date
                                ).all()
                            )
                            bv_categories.append(cat_name)
                            bv_budgeted.append(item.limit_amount)
                            bv_actual.append(actual_spend)

                        fig_bva = go.Figure(data=[
                            go.Bar(name="Budgeted", x=bv_categories, y=bv_budgeted,
                                   marker_color="rgba(0, 201, 255, 0.7)"),
                            go.Bar(name="Actual Spend", x=bv_categories, y=bv_actual,
                                   marker_color="rgba(255, 82, 82, 0.7)")
                        ])
                        fig_bva.update_layout(
                            barmode="group", height=280,
                            margin=dict(l=10, r=10, t=10, b=10),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font_color="white", font_family="Outfit",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02),
                            xaxis=dict(tickangle=-30, showgrid=False),
                            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
                        )
                        st.plotly_chart(fig_bva, use_container_width=True)
                    else:
                        st.info("No budget items found for the current pay period. Set up a budget under Budgets & Sinking Funds.")
                else:
                    st.info("No active pay period found.")

        with row4_c2:
            with st.container(border=True):
                st.subheader("6-Month Spending Trend")
                today = datetime.date.today()
                months_data = []
                for i in range(5, -1, -1):
                    # Calculate month start/end going 6 months back
                    month_date = today.replace(day=1) - datetime.timedelta(days=i * 30)
                    m_start = month_date.replace(day=1)
                    # End of that month
                    if m_start.month == 12:
                        m_end = m_start.replace(year=m_start.year + 1, month=1, day=1) - datetime.timedelta(days=1)
                    else:
                        m_end = m_start.replace(month=m_start.month + 1, day=1) - datetime.timedelta(days=1)

                    m_income = sum(
                        inc.amount for inc in db.query(Income).filter(
                            Income.household_id == household_id,
                            Income.date >= m_start, Income.date <= m_end
                        ).all()
                    )
                    m_expense = sum(
                        exp.amount for exp in db.query(Expense).filter(
                            Expense.household_id == household_id,
                            Expense.date >= m_start, Expense.date <= m_end
                        ).all()
                    )
                    months_data.append({
                        "Month": m_start.strftime("%b %Y"),
                        "Income": m_income,
                        "Expenses": m_expense
                    })

                df_trend = pd.DataFrame(months_data)
                if df_trend["Income"].sum() > 0 or df_trend["Expenses"].sum() > 0:
                    fig_trend = go.Figure(data=[
                        go.Bar(name="Income", x=df_trend["Month"], y=df_trend["Income"],
                               marker_color="rgba(46, 213, 115, 0.75)"),
                        go.Bar(name="Expenses", x=df_trend["Month"], y=df_trend["Expenses"],
                               marker_color="rgba(255, 177, 66, 0.75)")
                    ])
                    fig_trend.update_layout(
                        barmode="group", height=280,
                        margin=dict(l=10, r=10, t=10, b=10),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font_color="white", font_family="Outfit",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
                    )
                    st.plotly_chart(fig_trend, use_container_width=True)
                else:
                    st.info("No income or expense data available for the last 6 months.")

        # ----------------------------------------------------
        # ROW 5: QUICK ADD EXPENSE & MEMBER SPENDING BREAKDOWN
        # ----------------------------------------------------
        st.write("")
        row5_c1, row5_c2 = st.columns([1, 1])

        with row5_c1:
            with st.container(border=True):
                st.subheader("⚡ Quick Add Expense")
                role = st.session_state.get("user_role", "viewer")
                if role == "viewer":
                    st.info("Read-Only Mode: Viewers cannot log expenses.")
                else:
                    categories = db.query(ExpenseCategory).filter(
                        (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
                    ).all()
                    cat_choices = {c.name: c.id for c in categories}

                    with st.form("quick_add_expense_form"):
                        qa_cols = st.columns([2, 1])
                        with qa_cols[0]:
                            qa_merchant = st.text_input("Merchant / Description", placeholder="e.g. MH Supermarket")
                        with qa_cols[1]:
                            qa_amount = st.number_input("Amount", min_value=0.01, step=1.0, value=20.0)
                        qa_category = st.selectbox("Category", list(cat_choices.keys()))
                        qa_submit = st.form_submit_button("➕ Add Expense", type="primary", use_container_width=True)

                        if qa_submit:
                            today_date = datetime.date.today()
                            curr_period = db.query(PayPeriod).filter(
                                PayPeriod.household_id == household_id,
                                PayPeriod.start_date <= today_date,
                                PayPeriod.end_date >= today_date
                            ).first()
                            db.add(Expense(
                                household_id=household_id,
                                category_id=cat_choices[qa_category],
                                amount=qa_amount,
                                date=today_date,
                                merchant=qa_merchant,
                                pay_period_id=curr_period.id if curr_period else None
                            ))
                            db.commit()
                            st.success(f"✅ {format_currency(qa_amount, currency)} added to {qa_category}!")
                            st.rerun()

        with row5_c2:
            with st.container(border=True):
                st.subheader("👥 Member Spending Breakdown")
                # Get all household members
                members = db.query(HouseholdMember).filter(
                    HouseholdMember.household_id == household_id
                ).all()
                
                # Note: Expenses don't have a logged_by user field currently.
                # We show per-category this-month totals as a proxy and member roles.
                if members:
                    member_rows = []
                    for m in members:
                        user = m.user
                        if user:
                            member_rows.append({
                                "Member": user.full_name,
                                "Role": m.role.upper(),
                                "Status": "✅ Active" if user.is_active else "❌ Inactive"
                            })
                    
                    if member_rows:
                        st.dataframe(pd.DataFrame(member_rows), hide_index=True, use_container_width=True)
                    
                    # Shared household this-month expenses
                    m_start = today.replace(day=1) if "today" in dir() else datetime.date.today().replace(day=1)
                    today_now = datetime.date.today()
                    this_month_exp = sum(
                        e.amount for e in db.query(Expense).filter(
                            Expense.household_id == household_id,
                            Expense.date >= today_now.replace(day=1),
                            Expense.date <= today_now
                        ).all()
                    )
                    st.metric("Household Spend This Month", format_currency(this_month_exp, currency))
                else:
                    st.info("No members found in this household.")

        # ----------------------------------------------------
        # ROW 6: IN-APP NOTIFICATIONS
        # ----------------------------------------------------
        unread_notifs = db.query(Notification).filter(
            Notification.household_id == household_id,
            Notification.is_read == False
        ).order_by(Notification.sent_at.desc()).limit(5).all()

        if unread_notifs:
            st.write("")
            with st.container(border=True):
                st.subheader(f"🔔 Notifications ({len(unread_notifs)} unread)")
                for notif in unread_notifs:
                    icon = {"success": "✅", "warning": "⚠️", "info": "ℹ️", "alert": "🚨"}.get(notif.type, "🔔")
                    with st.container():
                        col_n1, col_n2 = st.columns([5, 1])
                        with col_n1:
                            st.write(f"{icon} **{notif.title}** — {notif.message}")
                            st.caption(notif.sent_at.strftime("%d %b %Y %H:%M"))
                        with col_n2:
                            if st.button("Mark Read", key=f"notif_read_{notif.id}", type="secondary"):
                                notif.is_read = True
                                db.commit()
                                st.rerun()

        # ----------------------------------------------------
        # ROW 7: SAVINGS CHALLENGES WIDGET
        # ----------------------------------------------------
        import json
        from models.household import Setting

        CHALLENGE_TEMPLATES = {
            "52-Week Challenge": {
                "desc": "Save incremental amounts each week — Week 1: $1, Week 2: $2 … Week 52: $52. Total saved: $1,378.",
                "icon": "📅",
                "total_weeks": 52
            },
            "FJD $5 No-Spend Streak": {
                "desc": "Put away FJD $5 for every day you make zero discretionary purchases.",
                "icon": "🚫",
                "total_weeks": None
            },
            "30-Day Coffee Challenge": {
                "desc": "Skip buying coffee for 30 days. Save your average FJD $4.50/day — total FJD $135.",
                "icon": "☕",
                "total_weeks": None
            }
        }

        st.write("")
        with st.container(border=True):
            st.subheader("🏅 Savings Challenges")
            st.caption("Pick a challenge, track your progress, and build the habit of saving.")

            # Load challenge state from Settings
            setting_key = "active_savings_challenges"
            setting_row = db.query(Setting).filter(
                Setting.household_id == household_id,
                Setting.key == setting_key
            ).first()

            challenges_state = json.loads(setting_row.value) if setting_row else {}

            def save_challenges(state_dict):
                nonlocal setting_row
                if setting_row:
                    setting_row.value = json.dumps(state_dict)
                else:
                    new_s = Setting(
                        household_id=household_id,
                        key=setting_key,
                        value=json.dumps(state_dict)
                    )
                    db.add(new_s)
                db.commit()

            ch_cols = st.columns(len(CHALLENGE_TEMPLATES))
            for idx, (ch_name, ch_info) in enumerate(CHALLENGE_TEMPLATES.items()):
                with ch_cols[idx]:
                    with st.container(border=True):
                        st.markdown(f"### {ch_info['icon']} {ch_name}")
                        st.caption(ch_info["desc"])

                        ch_state = challenges_state.get(ch_name, {})
                        is_active = ch_state.get("active", False)
                        contributions = ch_state.get("contributions", 0)
                        total_saved = ch_state.get("total_saved", 0.0)

                        if is_active:
                            st.success(f"✅ Active — FJD **{total_saved:.2f}** saved")
                            if ch_name == "52-Week Challenge":
                                pct = min(100, (contributions / 52) * 100)
                                st.progress(int(pct), text=f"Week {contributions}/52")
                            else:
                                st.metric("Contributions Logged", contributions)

                            contrib_amount = st.number_input(
                                "Log Contribution (FJD)",
                                min_value=0.01, value=5.0, step=1.0,
                                key=f"contrib_{idx}"
                            )
                            col_ca, col_cb = st.columns(2)
                            with col_ca:
                                if st.button("➕ Add", key=f"add_{idx}", use_container_width=True):
                                    ch_state["contributions"] = contributions + 1
                                    ch_state["total_saved"] = total_saved + contrib_amount
                                    challenges_state[ch_name] = ch_state
                                    save_challenges(challenges_state)
                                    st.rerun()
                            with col_cb:
                                if st.button("⏹ Stop", key=f"stop_{idx}", use_container_width=True):
                                    ch_state["active"] = False
                                    challenges_state[ch_name] = ch_state
                                    save_challenges(challenges_state)
                                    st.rerun()
                        else:
                            if total_saved > 0:
                                st.info(f"Completed — FJD {total_saved:.2f} saved in {contributions} contributions.")
                            if st.button("▶ Start Challenge", key=f"start_{idx}", use_container_width=True, type="primary"):
                                challenges_state[ch_name] = {
                                    "active": True,
                                    "contributions": 0,
                                    "total_saved": 0.0
                                }
                                save_challenges(challenges_state)
                                st.rerun()

