import streamlit as st
import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from database import get_db
from models.finance import Income, Expense, ExpenseCategory, PayPeriod, Subscription
from models.budget import Budget, BudgetItem, SavingsGoal, Debt, SinkingFund
from models.audit import Notification
from services.finance_service import (
    get_current_pay_period,
    calculate_financial_health_score,
    calculate_emergency_fund_coverage,
    calculate_income_for_period,
    calculate_expenses_for_period,
    detect_recurring_patterns,
)
from services.forecast_service import calculate_current_balance, generate_cashflow_projection
from utils.helpers import format_currency, get_health_score_rating
from views.quick_add import render_quick_add
from views.quick_start import render_quick_start
from services.dashboard_service import (
    get_period_comparison,
    get_budget_progress,
    get_upcoming_bills,
    get_member_spending,
)
from utils.ux import render_screen_tour, render_undo_bar, render_empty_state, toast_success
from utils.helpers import can_modify
from utils.i18n import t, get_household_locale
from utils.styles import get_chart_colors


def _cycle_status(period_income, period_expenses, days_remaining, currency) -> tuple[str, str]:
    left = period_income - period_expenses
    if left < 0:
        return "critical", f"You're {format_currency(abs(left), currency)} over budget this pay cycle."
    if days_remaining > 0 and left > 0:
        daily = left / days_remaining
        return "good", (
            f"You're on track — {format_currency(left, currency)} left until payday "
            f"({days_remaining} days). About {format_currency(daily, currency)} per day."
        )
    if left >= 0:
        return "good", f"You're on track with {format_currency(left, currency)} left this cycle."
    return "warning", "Review your spending for this pay cycle."


def show_dashboard(household_id: int):
    with get_db() as db:
        h_name = st.session_state.get("household_name", "Household")
        currency = st.session_state.get("household_currency", "FJD")
        today = datetime.date.today()

        locale = get_household_locale(db, household_id)
        view_mode = st.radio(
            "View",
            [t("this_pay_cycle", locale), t("this_week", locale)],
            horizontal=True,
            key="dash_view_mode",
        )
        use_week = view_mode == t("this_week", locale)

        current_period = get_current_pay_period(db, household_id)
        period_income = 0.0
        period_expenses = 0.0
        days_remaining = 0
        period_label = "this pay cycle"
        range_start = today - datetime.timedelta(days=6)
        range_end = today

        if use_week:
            period_label = "this week"
            period_income = calculate_income_for_period(db, household_id, range_start, range_end)
            period_expenses = calculate_expenses_for_period(db, household_id, range_start, range_end)
            days_remaining = max(0, 6 - (today - range_start).days)
        elif current_period:
            period_label = current_period.name
            range_start = current_period.start_date
            range_end = current_period.end_date
            period_income = calculate_income_for_period(db, household_id, range_start, range_end)
            period_expenses = calculate_expenses_for_period(db, household_id, range_start, range_end)
            if today <= current_period.end_date:
                days_remaining = max(0, (current_period.end_date - today).days)
                
        left_to_spend = period_income - period_expenses
        status_style, status_msg = _cycle_status(period_income, period_expenses, days_remaining, currency)

        st.markdown(f"<h1 class='app-title'>{h_name}</h1>", unsafe_allow_html=True)
        if current_period:
            st.markdown(
                f"<p class='app-subtitle'><strong>This pay cycle:</strong> "
                f"{current_period.start_date.strftime('%d %b')} – "
                f"{current_period.end_date.strftime('%d %b %Y')} · "
                f"<strong>{days_remaining} days until payday</strong></p>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<p class='app-subtitle'>Set up your pay cycle under "
                "<strong>Budget Setup</strong> in the sidebar.</p>",
                unsafe_allow_html=True,
            )

        render_screen_tour(db, household_id, "dashboard", [
            "Use **Quick Add** to log spending in seconds.",
            "**Setup** menu: Income Setup → Budget Setup → Expense Setup → Recurring Bills.",
            "**Track** menu: Budget vs Actual shows limits vs spending.",
            "Use quick links below to jump to any section.",
        ])

        st.markdown("### Quick links")
        ql = [
            ("💰 Income", "income_setup"),
            ("📅 Pay Schedule", "pay_schedule"),
            ("📋 Budget", "budget_setup"),
            ("💸 Expenses", "expense_setup"),
            ("🔁 Bills", "recurring_bills"),
            ("⚖️ vs Actual", "budget_vs_actual"),
        ]
        qcols = st.columns(len(ql))
        for col, (lbl, rkey) in zip(qcols, ql):
            with col:
                if st.button(lbl, key=f"dash_ql_{rkey}", width="stretch"):
                    st.session_state["nav_route"] = rkey
                    st.rerun()
        render_quick_add(household_id, key_prefix="dash_qa")
        render_undo_bar(db, household_id)
        st.write("")
        render_quick_start(household_id)
        st.write("")
        
        # ── 3 simple numbers ──────────────────────────────────────
        c1, c2, c3 = st.columns(3)
        comparison = get_period_comparison(db, household_id) if not use_week else None
        with c1:
            st.metric(t("money_in", locale), format_currency(period_income, currency), help=f"Total income for {period_label}")
        with c2:
            delta_cmp = None
            if comparison and comparison.get("has_prev"):
                delta_cmp = f"{comparison['pct']:+.0f}% {t('vs_last_cycle', locale)}"
            st.metric(t("money_out", locale), format_currency(period_expenses, currency), delta=delta_cmp, delta_color="inverse")
        with c3:
            st.metric(
                t("left_until_payday", locale) if not use_week else "Left This Week",
                format_currency(left_to_spend, currency),
                delta=f"{days_remaining}d left" if days_remaining else None,
                delta_color="normal" if left_to_spend >= 0 else "inverse",
            )

        if period_income == 0 and period_expenses == 0:
            render_empty_state("📭", "Nothing logged yet", t("no_transactions", locale))

        # Budget progress
        if not use_week:
            progress = get_budget_progress(db, household_id)
            if progress:
                st.markdown(f"### {t('budget_progress', locale)}")
                for row in progress:
                    label = f"{row['category']} — {format_currency(row['spent'], currency)} / {format_currency(row['limit'], currency)}"
                    st.progress(min(1.0, row["pct"] / 100.0), text=label)
                    if row["over"]:
                        st.caption(f"Over by {format_currency(abs(row['remaining']), currency)}")
            elif current_period:
                st.caption(t("no_budget", locale))

        # Upcoming bills
        upcoming = get_upcoming_bills(db, household_id)
        st.markdown(f"### {t('upcoming_bills', locale)}")
        if upcoming:
            for bill in upcoming:
                when = "today" if bill["days"] == 0 else f"in {bill['days']}d"
                st.write(f"**{bill['name']}** — {format_currency(bill['amount'], currency)} · {when}")
        else:
            st.caption(t("no_bills", locale))

        if status_style == "good":
            st.success(status_msg.replace("$", r"\$"))
        elif status_style == "critical":
            st.error(status_msg.replace("$", r"\$"))
        else:
            st.warning(status_msg.replace("$", r"\$"))

        # Recurring pattern suggestions
        patterns = detect_recurring_patterns(db, household_id)
        if patterns:
            with st.expander(f"💡 {len(patterns)} recurring bill(s) detected — track as subscriptions?", expanded=False):
                role = st.session_state.get("user_role", "viewer")
                for i, p in enumerate(patterns[:3]):
                    pc1, pc2 = st.columns([4, 1])
                    with pc1:
                        st.write(
                            f"**{p['merchant']}** — ~{format_currency(p['avg_amount'], currency)} "
                            f"{p['frequency']} ({p['category_name']})"
                        )
                    with pc2:
                        if can_modify(role) and st.button("Track", key=f"dash_track_sub_{i}"):
                            db.add(Subscription(
                                household_id=household_id,
                                name=p["merchant"],
                                amount=round(p["avg_amount"], 2),
                                frequency=p["frequency"],
                                next_renewal=p["next_date"],
                                category_id=p["category_id"],
                                status="active",
                            ))
                            db.commit()
                            toast_success(f"Now tracking {p['merchant']} as a subscription")
                            st.rerun()

        with st.expander("🗓️ Financial calendar", expanded=False):
            from views.calendar_view import show_calendar
            show_calendar(household_id, embedded=True)

        # ── Detailed insights (collapsed by default) ──────────────
        with st.expander("📊 See more insights", expanded=False):
            balance = calculate_current_balance(db, household_id)
            health_score, _ = calculate_financial_health_score(db, household_id)
            _, coverage_months, coverage_rating = calculate_emergency_fund_coverage(db, household_id)

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Cash Balance", format_currency(balance, currency))
            k2.metric("Health Score", f"{health_score}/100")
            k3.metric("Emergency Fund", f"{coverage_months:.1f} mo ({coverage_rating})")
            goals_total = sum(g.current_amount for g in db.query(SavingsGoal).filter(
                SavingsGoal.household_id == household_id, SavingsGoal.status == "active"
            ).all())
            sinking_total = sum(f.current_amount for f in db.query(SinkingFund).filter(
                SinkingFund.household_id == household_id
            ).all())
            debt_total = sum(d.current_balance for d in db.query(Debt).filter(Debt.household_id == household_id).all())
            k4.metric("Net Worth", format_currency(balance + goals_total + sinking_total - debt_total, currency))

            if current_period and not use_week:
                member_rows = get_member_spending(
                    db, household_id, current_period.start_date, current_period.end_date,
                )
                if member_rows:
                    st.markdown("**Spending by person**")
                    for m in member_rows:
                        st.write(f"**{m['name']}** — {format_currency(m['total'], currency)}")

            last_30 = today - datetime.timedelta(days=30)
            recent_expenses = db.query(Expense).filter(
                Expense.household_id == household_id, Expense.date >= last_30
            ).all()

            chart_colors = get_chart_colors()
            chart_font = chart_colors.get("font") or "#94a3b8"
        ch1, ch2 = st.columns(2)
        with ch1:
                if recent_expenses:
                    cat_data = [{"Category": e.category.name if e.category else "Other", "Amount": e.amount} for e in recent_expenses]
                    df_cat = pd.DataFrame(cat_data).groupby("Category").sum().reset_index()
                    fig_pie = px.pie(df_cat, values="Amount", names="Category", hole=0.4)
                    fig_pie.update_layout(
                        height=260, paper_bgcolor=chart_colors["paper"],
                        font_color=chart_font, font_family="Outfit",
                    )
                    st.plotly_chart(fig_pie, width="stretch")
        with ch2:
                forecast = generate_cashflow_projection(db, household_id, days=60)
                if forecast:
                    df_fore = pd.DataFrame(forecast)
                    fig_line = px.line(df_fore, x="date", y="balance")
                    fig_line.update_traces(line_color="#00C9FF")
                    fig_line.update_layout(
                        height=260, paper_bgcolor=chart_colors["paper"],
                        plot_bgcolor=chart_colors["plot"], font_color=chart_font,
                    )
                    st.plotly_chart(fig_line, width="stretch")

        unread_count = db.query(Notification).filter(
            Notification.household_id == household_id, Notification.is_read == False,
        ).count()
        if unread_count:
            st.write("")
            label = f"🔔 {unread_count} unread notification{'s' if unread_count != 1 else ''}"
            if st.button(f"{label} — open Notifications", key="dash_open_notif", width="stretch"):
                st.session_state["nav_route"] = "notifications"
                st.session_state["notif_selected_id"] = None
                st.rerun()
