import streamlit as st
import datetime
import calendar
from database import get_db
from models.finance import Income, Expense, Subscription
from models.budget import SavingsGoal, Debt, SinkingFund
from utils.helpers import format_currency

def show_calendar(household_id: int):
    """
    Renders a color-coded financial calendar events list.
    Displays Paydays, Bills, Subscriptions, Debt, and Savings Goals.
    """
    st.markdown("<h1 class='app-title'>Financial Calendar</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Track and anticipate upcoming financial events</p>", unsafe_allow_html=True)
    
    # Selection for month/year
    today = datetime.date.today()
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        selected_month = st.selectbox("Month", range(1, 13), index=today.month - 1, format_func=lambda x: calendar.month_name[x])
    with col_sel2:
        selected_year = st.selectbox("Year", range(today.year - 1, today.year + 2), index=1)
        
    start_date = datetime.date(selected_year, selected_month, 1)
    # Get last day of month
    last_day = calendar.monthrange(selected_year, selected_month)[1]
    end_date = datetime.date(selected_year, selected_month, last_day)
    
    with get_db() as db:
        # Load all recurring events
        incomes = db.query(Income).filter(
            Income.household_id == household_id,
            Income.date >= start_date, Income.date <= end_date
        ).all()
        
        expenses = db.query(Expense).filter(
            Expense.household_id == household_id,
            Expense.date >= start_date, Expense.date <= end_date
        ).all()
        
        subs = db.query(Subscription).filter(
            Subscription.household_id == household_id,
            Subscription.status == "active"
        ).all()
        
        debts = db.query(Debt).filter(
            Debt.household_id == household_id
        ).all()
        
        goals = db.query(SavingsGoal).filter(
            SavingsGoal.household_id == household_id,
            SavingsGoal.status == "active"
        ).all()
        
        # Compile events
        events = []
        currency = st.session_state.get("household_currency", "FJD")
        
        # 1. Income events (Paydays)
        for inc in incomes:
            events.append({
                "date": inc.date,
                "title": f"Income: {inc.source}",
                "amount": inc.amount,
                "type": "income",
                "color_class": "calendar-income"
            })
            
        # 2. General Expense events (Bills)
        for exp in expenses:
            if exp.is_recurring:
                events.append({
                    "date": exp.date,
                    "title": f"Bill: {exp.merchant or 'Recurring Expense'}",
                    "amount": exp.amount,
                    "type": "bill",
                    "color_class": "calendar-bill"
                })
                
        # 3. Subscriptions
        for sub in subs:
            # Check if renews this month
            # Calculate renewal in selected month
            renewal_date = datetime.date(selected_year, selected_month, min(sub.next_renewal.day, last_day))
            events.append({
                "date": renewal_date,
                "title": f"Sub: {sub.name}",
                "amount": sub.amount,
                "type": "subscription",
                "color_class": "calendar-subscription"
            })
            
        # 4. Debt Due Dates
        for d in debts:
            # Simulate monthly payment on 15th
            pay_date = datetime.date(selected_year, selected_month, 15)
            events.append({
                "date": pay_date,
                "title": f"Debt: {d.name} Payment",
                "amount": d.minimum_payment,
                "type": "debt",
                "color_class": "calendar-debt"
            })
            
        # 5. Goal Targets
        for g in goals:
            if start_date <= g.target_date <= end_date:
                events.append({
                    "date": g.target_date,
                    "title": f"Goal Target: {g.name}",
                    "amount": g.target_amount - g.current_amount,
                    "type": "goal",
                    "color_class": "calendar-goal"
                })
                
        # Sort by date
        events.sort(key=lambda x: x["date"])
        
        # Render Legend
        st.markdown("""
        <div style='display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;'>
            <span class="status-pill good">🟢 Payday</span>
            <span class="status-pill critical">🔴 Bills</span>
            <span class="status-pill poor">🟠 Debt Payment</span>
            <span class="status-pill exceptional">🟣 Goals</span>
            <span class="status-pill" style="background-color: rgba(186, 85, 211, 0.15); color: #ba55d3; border: 1px solid rgba(186, 85, 211, 0.3);">🍇 Subscriptions</span>
        </div>
        """, unsafe_allow_html=True)
        
        if not events:
            st.info(f"No scheduled financial events for {calendar.month_name[selected_month]} {selected_year}.")
        else:
            # Group events by date
            grouped_events = {}
            for e in events:
                grouped_events.setdefault(e["date"], []).append(e)
                
            for dt, day_evs in sorted(grouped_events.items()):
                st.write(f"📅 **{dt.strftime('%A, %d %b %Y')}**")
                for e in day_evs:
                    st.markdown(f"""
                    <div class="calendar-cell {e['color_class']}">
                        <strong>{e['title']}</strong> - {format_currency(e['amount'], currency)}
                    </div>
                    """, unsafe_allow_html=True)
                st.write("")
