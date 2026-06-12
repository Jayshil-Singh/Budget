import streamlit as st
import datetime
import calendar
from database import get_db
from models.finance import Income, Expense, Subscription, PaymentDueDate
from models.budget import SavingsGoal, Debt, SinkingFund
from utils.helpers import format_currency


def _render_month_grid(events: list, year: int, month: int, today: datetime.date):
    """Native month grid — works inside nested Streamlit tabs (no iframe)."""
    events_by_date: dict[datetime.date, list] = {}
    for e in events:
        events_by_date.setdefault(e["date"], []).append(e)

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    header = st.columns(7)
    for i, label in enumerate(weekday_labels):
        with header[i]:
            st.markdown(f"<div style='text-align:center;font-weight:700;font-size:0.8rem;'>{label}</div>",
                        unsafe_allow_html=True)

    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdatescalendar(year, month):
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                in_month = day.month == month
                is_today = in_month and day == today
                day_events = events_by_date.get(day, []) if in_month else []

                if not in_month:
                    box_class = "cal-day-box cal-day-muted"
                elif is_today:
                    box_class = "cal-day-box cal-day-today"
                else:
                    box_class = "cal-day-box cal-day-normal"

                chips = ""
                for ev in day_events[:4]:
                    chips += (
                        f'<div class="calendar-cell {ev["color_class"]}" '
                        f'style="font-size:0.68rem;padding:3px 5px;margin:2px 0;line-height:1.2;">'
                        f'{ev["title"]}</div>'
                    )
                if len(day_events) > 4:
                    chips += (
                        f'<div style="font-size:0.65rem;color:#64748b;margin-top:2px;">'
                        f'+{len(day_events) - 4} more</div>'
                    )

                st.markdown(
                    f'<div class="{box_class}">'
                    f'<div style="font-weight:700;font-size:0.85rem;margin-bottom:4px;">{day.day}</div>'
                    f'{chips}</div>',
                    unsafe_allow_html=True,
                )


def show_calendar(household_id: int, embedded: bool = False):
    """
    Renders a color-coded interactive financial calendar monthly grid,
    showing Paydays, Bills, Subscriptions, Debt, Savings Goals, and custom Due Dates.
    Also provides a tool to add, toggle paid status, and delete custom due dates.
    """
    if not embedded:
        st.markdown("<h1 class='app-title'>Financial Calendar</h1>", unsafe_allow_html=True)
        st.markdown("<p class='app-subtitle'>Track, manage, and anticipate upcoming financial events</p>", unsafe_allow_html=True)
    
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
        # Load all transactions and templates
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
        
        custom_dues = db.query(PaymentDueDate).filter(
            PaymentDueDate.household_id == household_id,
            PaymentDueDate.due_date >= start_date, PaymentDueDate.due_date <= end_date
        ).all()
        
        # Compile events
        events = []
        currency = st.session_state.get("household_currency", "FJD")
        
        # 1. Income events (Paydays - actual & projected)
        # 1a. Actual logged incomes
        for inc in incomes:
            if not inc.is_recurring:
                events.append({
                    "date": inc.date,
                    "title": f"💰 Pay: {inc.source}",
                    "amount": inc.amount,
                    "type": "income",
                    "color_class": "calendar-income",
                    "color_hex": "#28a745"
                })
                
        # 1b. Scheduled recurring paydays (from anchor date, includes first payday)
        from services.finance_service import _get_occurrences_in_range, _logged_income_on_date
        recurring_incomes = db.query(Income).filter(
            Income.household_id == household_id,
            Income.is_recurring == True
        ).all()
        for inc in recurring_incomes:
            if not inc.date or not inc.frequency:
                continue
            for occ in _get_occurrences_in_range(inc.date, inc.frequency, start_date, end_date):
                if _logged_income_on_date(db, household_id, inc.source, inc.amount, occ):
                    continue
                suffix = " (Projected)" if occ > today else ""
                events.append({
                    "date": occ,
                    "title": f"💰 Pay: {inc.source}{suffix}",
                    "amount": inc.amount,
                    "type": "income",
                    "color_class": "calendar-income",
                    "color_hex": "#28a745"
                })
            
        # 2. General Expense events (Bills)
        for exp in expenses:
            events.append({
                "date": exp.date,
                "title": f"🔴 Bill: {exp.merchant or 'Recurring Expense'}",
                "amount": exp.amount,
                "type": "bill",
                "color_class": "calendar-bill",
                "color_hex": "#dc3545"
            })
                
        # 3. Subscriptions
        for sub in subs:
            renewal_date = datetime.date(selected_year, selected_month, min(sub.next_renewal.day, last_day))
            events.append({
                "date": renewal_date,
                "title": f"🍇 Sub: {sub.name}",
                "amount": sub.amount,
                "type": "subscription",
                "color_class": "calendar-subscription",
                "color_hex": "#ba55d3"
            })
            
        # 4. Debt payment dates (from start_date schedule)
        from services.finance_service import _get_occurrences_in_range
        for d in debts:
            if not d.start_date or not d.payment_frequency:
                continue
            for pay_date in _get_occurrences_in_range(
                d.start_date, d.payment_frequency, start_date, end_date,
            ):
                events.append({
                    "date": pay_date,
                    "title": f"🟠 Debt: {d.name} Payment",
                    "amount": d.minimum_payment,
                    "type": "debt",
                    "color_class": "calendar-debt",
                    "color_hex": "#fd7e14"
                })
            
        # 5. Goal Targets
        for g in goals:
            if start_date <= g.target_date <= end_date:
                events.append({
                    "date": g.target_date,
                    "title": f"🟣 Goal Target: {g.name}",
                    "amount": g.target_amount - g.current_amount,
                    "type": "goal",
                    "color_class": "calendar-goal",
                    "color_hex": "#6f42c1"
                })
                
        # 6. Custom Due Dates
        for cd in custom_dues:
            events.append({
                "date": cd.due_date,
                "title": f"🔔 Due: {cd.name}" + (" (Paid)" if cd.is_paid else ""),
                "amount": cd.amount,
                "type": "custom_due",
                "color_class": "calendar-custom-due" if not cd.is_paid else "calendar-paid",
                "color_hex": "#007bff" if not cd.is_paid else "#6c757d"
            })
                
        # Sort by date
        events.sort(key=lambda x: x["date"])
        
        # Render Legend
        st.markdown("""
        <div style='display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;'>
            <span class="status-pill good" style="background-color: rgba(40, 167, 69, 0.15); color: #28a745; border: 1px solid rgba(40, 167, 69, 0.3);">🟢 Payday</span>
            <span class="status-pill critical" style="background-color: rgba(220, 53, 69, 0.15); color: #dc3545; border: 1px solid rgba(220, 53, 69, 0.3);">🔴 Bills</span>
            <span class="status-pill poor" style="background-color: rgba(253, 126, 20, 0.15); color: #fd7e14; border: 1px solid rgba(253, 126, 20, 0.3);">🟠 Debt Payment</span>
            <span class="status-pill exceptional" style="background-color: rgba(111, 66, 193, 0.15); color: #6f42c1; border: 1px solid rgba(111, 66, 193, 0.3);">🟣 Goals</span>
            <span class="status-pill" style="background-color: rgba(186, 85, 211, 0.15); color: #ba55d3; border: 1px solid rgba(186, 85, 211, 0.3);">🍇 Subscriptions</span>
            <span class="status-pill" style="background-color: rgba(0, 123, 255, 0.15); color: #007bff; border: 1px solid rgba(0, 123, 255, 0.3);">🔵 Custom Bill Due</span>
            <span class="status-pill" style="background-color: rgba(108, 117, 125, 0.15); color: #6c757d; border: 1px solid rgba(108, 117, 125, 0.3);">⚪ Paid Bill</span>
        </div>
        """, unsafe_allow_html=True)

        # Display month grid (native — streamlit-calendar iframe fails in nested tabs)
        with st.container(border=True):
            st.markdown(
                f"### 📅 {calendar.month_name[selected_month]} {selected_year} — Monthly Calendar"
            )
            if events:
                st.caption(f"{len(events)} event(s) this month. Scroll the list below for full amounts.")
            _render_month_grid(events, selected_year, selected_month, today)
            
        st.write("")
        
        # Split into Add Custom Due Date Form and Due Dates Manager
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            with st.container(border=True):
                st.subheader("➕ Set Custom Payment / Due Date")
                st.markdown(
                    "<p class='app-subtitle'>Add bills not captured elsewhere. "
                    "All dated payments (custom bills, subscriptions, recurring bills, debt, "
                    "sinking funds, and goals) trigger a day-before email digest with budget context.</p>",
                    unsafe_allow_html=True,
                )
                with st.form("add_due_date_form"):
                    due_name = st.text_input("Payment/Bill Name", placeholder="e.g., EFL Electricity, BSP Loan, Rent")
                    due_amount = st.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
                    due_dt = st.date_input("Due Date", min_value=today)
                    
                    submit_due = st.form_submit_button("Save Due Date", type="primary")
                    if submit_due:
                        if not due_name.strip() or due_amount <= 0:
                            st.error("Please enter a valid bill name and amount.")
                        else:
                            new_due = PaymentDueDate(
                                household_id=household_id,
                                name=due_name.strip(),
                                amount=due_amount,
                                due_date=due_dt,
                                is_paid=False,
                                email_notified=False
                            )
                            db.add(new_due)
                            db.commit()
                            st.success(f"✅ Due date for '{due_name}' set successfully for {due_dt.strftime('%d %b %Y')}!")
                            st.rerun()
                            
        with col_m2:
            with st.container(border=True):
                st.subheader("📋 Custom Due Dates Manager")
                st.markdown("<p class='app-subtitle'>Manage and complete custom due dates for this selected month</p>", unsafe_allow_html=True)
                
                month_custom_dues = db.query(PaymentDueDate).filter(
                    PaymentDueDate.household_id == household_id,
                    PaymentDueDate.due_date >= start_date, PaymentDueDate.due_date <= end_date
                ).order_by(PaymentDueDate.due_date).all()
                
                if not month_custom_dues:
                    st.info("No custom due dates found for this month.")
                else:
                    for cd in month_custom_dues:
                        status_str = "✅ Paid" if cd.is_paid else "⏳ Unpaid"
                        
                        col_card1, col_card2, col_card3 = st.columns([5, 4, 3])
                        with col_card1:
                            st.markdown(f"**{cd.name}**  \n`{format_currency(cd.amount, currency)}` | due {cd.due_date.strftime('%d %b')}")
                        with col_card2:
                            # Checkbox to toggle paid state
                            new_paid_status = st.checkbox("Mark as Paid", value=cd.is_paid, key=f"pay_state_{cd.id}")
                            if new_paid_status != cd.is_paid:
                                cd.is_paid = new_paid_status
                                db.commit()
                                st.rerun()
                        with col_card3:
                            if st.button("Delete", key=f"del_due_{cd.id}", type="secondary", width="stretch"):
                                db.delete(cd)
                                db.commit()
                                st.rerun()
                                
        st.write("")
        
        # Render Listed Events below for reference
        with st.expander("📄 View Listed Schedule of Events", expanded=False):
            if not events:
                st.info(f"No scheduled financial events for {calendar.month_name[selected_month]} {selected_year}.")
            else:
                grouped_events = {}
                for e in events:
                    grouped_events.setdefault(e["date"], []).append(e)
                    
                for dt, day_evs in sorted(grouped_events.items()):
                    st.markdown(f"📅 **{dt.strftime('%A, %d %b %Y')}**")
                    for e in day_evs:
                        st.markdown(f"""
                        <div class="calendar-cell {e['color_class']}">
                            <strong>{e['title']}</strong> - {format_currency(e['amount'], currency)}
                        </div>
                        """, unsafe_allow_html=True)
                    st.write("")
