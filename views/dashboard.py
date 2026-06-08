import streamlit as st
import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from database import get_db
from models.finance import Income, Expense, PayPeriod, ExpenseCategory
from models.budget import Budget, SavingsGoal, Debt, SinkingFund
from services.finance_service import (
    get_current_pay_period, 
    calculate_financial_health_score, 
    calculate_emergency_fund_coverage,
    get_essential_expenses_monthly
)
from services.forecast_service import calculate_current_balance, generate_cashflow_projection
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
