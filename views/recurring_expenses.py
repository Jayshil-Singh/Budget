"""Manage recurring bills and fixed expenses (rent, utilities, loan payments, etc.)."""
import datetime
import streamlit as st
from database import get_db
from models.finance import Expense, ExpenseCategory, PayPeriod
from services.finance_service import _get_occurrences_in_range
from services.ai_service import auto_tag_category
from utils.helpers import format_currency, can_modify, can_delete
from services.mark_paid_service import mark_recurring_expense_paid
from utils.ux import confirm_button, toast_success, render_empty_state


def _next_due_date(anchor: datetime.date, frequency: str, after: datetime.date | None = None) -> datetime.date | None:
    if not anchor or not frequency:
        return None
    start = after or datetime.date.today()
    window_end = start + datetime.timedelta(days=366)
    hits = _get_occurrences_in_range(anchor, frequency, start, window_end)
    return hits[0] if hits else None


def show_recurring_expenses(household_id: int):
    st.markdown("<h1 class='app-title'>Recurring Bills</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='app-subtitle'>Set up fixed bills that repeat — rent, utilities, loan payments, and more</p>",
        unsafe_allow_html=True,
    )

    currency = st.session_state.get("household_currency", "FJD")
    today = datetime.date.today()

    with get_db() as db:
        categories = db.query(ExpenseCategory).filter(
            (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
        ).all()
        cat_choices = {c.name: c.id for c in categories}
        cat_list = list(cat_choices.keys())
        role = st.session_state.get("user_role", "viewer")

        if not can_modify(role):
            st.info("ℹ️ Read-only — viewers cannot add or edit recurring bills.")
        else:
            with st.container(border=True):
                st.subheader("➕ Add Recurring Bill")
                st.caption(
                    "These appear on your calendar and count toward forecasts. "
                    "One-off purchases belong in **Money Log**."
                )

                suggest_cols = st.columns([3, 1])
                with suggest_cols[0]:
                    autotag_merchant = st.text_input(
                        "Merchant / bill name",
                        placeholder="e.g. Rent, EFL, BSP Loan",
                        key="rec_exp_merchant",
                    )
                with suggest_cols[1]:
                    st.write("")
                    st.write("")
                    if st.button("🔍 Suggest category", key="rec_exp_autotag"):
                        if autotag_merchant.strip():
                            suggestion = auto_tag_category(autotag_merchant, cat_list)
                            if suggestion:
                                st.session_state["rec_exp_cat_hint"] = suggestion
                                st.success(f"Suggested: {suggestion}")
                            else:
                                st.info("Pick a category manually.")

                hint = st.session_state.get("rec_exp_cat_hint")
                default_idx = cat_list.index(hint) if hint and hint in cat_list else 0

                with st.form("add_recurring_expense_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        amount = st.number_input("Amount (FJD)", min_value=0.01, step=10.0, value=100.0)
                        category = st.selectbox("Category", cat_list, index=default_idx)
                        start_date = st.date_input(
                            "First due date",
                            value=today,
                            help="When this bill is due (or when the schedule starts).",
                        )
                    with c2:
                        merchant = st.text_input(
                            "Label on calendar",
                            value=autotag_merchant or "",
                            placeholder="Same as merchant name",
                        )
                        freq_choice = st.selectbox(
                            "Repeats",
                            ["Weekly", "Fortnightly", "Monthly", "Custom"],
                            index=2,
                        )
                        if freq_choice == "Custom":
                            custom_days = st.number_input(
                                "Every X days", min_value=1, max_value=365, value=30, step=1,
                            )
                            frequency = f"custom:{custom_days}"
                        else:
                            frequency = freq_choice.lower()
                        notes = st.text_area("Notes (optional)", placeholder="Account number, reference…")

                    submitted = st.form_submit_button("Save recurring bill", type="primary")
                    if submitted:
                        label = (merchant or autotag_merchant or category).strip()
                        if not label or amount <= 0:
                            st.error("Enter a bill name and amount.")
                        else:
                            period = db.query(PayPeriod).filter(
                                PayPeriod.household_id == household_id,
                                PayPeriod.start_date <= start_date,
                                PayPeriod.end_date >= start_date,
                            ).first()
                            db.add(Expense(
                                household_id=household_id,
                                category_id=cat_choices[category],
                                amount=amount,
                                date=start_date,
                                merchant=label,
                                notes=notes.strip() or None,
                                is_recurring=True,
                                frequency=frequency,
                                pay_period_id=period.id if period else None,
                                logged_by_user_id=st.session_state.get("user_id"),
                            ))
                            db.commit()
                            toast_success(f"Recurring bill saved: {label}")
                            st.session_state.pop("rec_exp_cat_hint", None)
                            st.rerun()

        st.markdown("---")
        st.subheader("📋 Active recurring bills")

        templates = db.query(Expense).filter(
            Expense.household_id == household_id,
            Expense.is_recurring == True,
        ).order_by(Expense.date.desc()).all()

        if not templates:
            render_empty_state(
                "🔁",
                "No recurring bills yet",
                "Add rent, utilities, loan payments, or other fixed bills above.",
            )
            return

        seen: set[tuple] = set()
        active: list[Expense] = []
        for exp in templates:
            key = (exp.category_id, (exp.merchant or "").strip().lower(), exp.amount)
            if key in seen:
                continue
            seen.add(key)
            active.append(exp)

        active.sort(key=lambda e: (_next_due_date(e.date, e.frequency or "") or e.date, e.merchant or ""))

        total_monthly = 0.0
        for exp in active:
            freq = (exp.frequency or "monthly").lower()
            if freq == "weekly":
                total_monthly += exp.amount * (52 / 12)
            elif freq in ("fortnightly", "payday"):
                total_monthly += exp.amount * (26 / 12)
            elif freq.startswith("custom:"):
                try:
                    days = int(freq.split(":")[1])
                    total_monthly += exp.amount * (30 / max(days, 1))
                except Exception:
                    total_monthly += exp.amount
            else:
                total_monthly += exp.amount

        m1, m2 = st.columns(2)
        m1.metric("Active bills", len(active))
        m2.metric("Est. monthly total", format_currency(total_monthly, currency))

        for exp in active:
            next_due = _next_due_date(exp.date, exp.frequency or "")
            freq_label = (exp.frequency or "monthly").replace("custom:", "every ").title()
            days_until = (next_due - today).days if next_due else None
            due_hint = ""
            if next_due:
                if days_until == 0:
                    due_hint = " · **due today**"
                elif days_until == 1:
                    due_hint = " · due tomorrow"
                elif days_until and days_until > 0:
                    due_hint = f" · due in {days_until} days"

            with st.container(border=True):
                head1, head2 = st.columns([4, 2])
                with head1:
                    st.markdown(
                        f"**{exp.merchant or 'Bill'}** · "
                        f"{format_currency(exp.amount, currency)} · {freq_label}"
                    )
                    st.caption(
                        f"{exp.category.name if exp.category else 'Uncategorised'}"
                        f" · started {exp.date.strftime('%d %b %Y')}"
                        f"{due_hint}"
                    )
                with head2:
                    if next_due:
                        st.metric("Next due", next_due.strftime("%d %b %Y"))

                if can_modify(role):
                    pay_col1, pay_col2 = st.columns(2)
                    with pay_col1:
                        if st.button("✅ Mark paid", key=f"rec_paid_{exp.id}", type="primary"):
                            if mark_recurring_expense_paid(db, household_id, exp, next_due or today):
                                toast_success(f"Logged payment for {exp.merchant or 'bill'}")
                            else:
                                st.info("Already logged for this date.")
                            st.rerun()

                if can_modify(role):
                    with st.expander("Edit bill", expanded=False):
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            new_amount = st.number_input(
                                "Amount", min_value=0.01, value=float(exp.amount),
                                step=10.0, key=f"rec_amt_{exp.id}",
                            )
                            cur_cat = exp.category.name if exp.category else cat_list[0]
                            new_cat = st.selectbox(
                                "Category", cat_list,
                                index=cat_list.index(cur_cat) if cur_cat in cat_list else 0,
                                key=f"rec_cat_{exp.id}",
                            )
                            new_start = st.date_input(
                                "First due date", value=exp.date, key=f"rec_start_{exp.id}",
                            )
                        with ec2:
                            new_merchant = st.text_input(
                                "Label", value=exp.merchant or "", key=f"rec_merch_{exp.id}",
                            )
                            freq_opts = ["weekly", "fortnightly", "monthly"]
                            cur_f = (exp.frequency or "monthly").lower()
                            if cur_f.startswith("custom:"):
                                freq_display = "custom"
                            elif cur_f in freq_opts:
                                freq_display = cur_f
                            else:
                                freq_display = "monthly"
                            new_freq = st.selectbox(
                                "Repeats",
                                ["weekly", "fortnightly", "monthly", "custom"],
                                index=["weekly", "fortnightly", "monthly", "custom"].index(freq_display),
                                format_func=lambda x: x.title(),
                                key=f"rec_freq_{exp.id}",
                            )
                            new_frequency = new_freq
                            if new_freq == "custom":
                                try:
                                    cur_days = int(cur_f.split(":")[1]) if cur_f.startswith("custom:") else 30
                                except Exception:
                                    cur_days = 30
                                days = st.number_input(
                                    "Every X days", min_value=1, value=cur_days, key=f"rec_days_{exp.id}",
                                )
                                new_frequency = f"custom:{days}"
                            new_notes = st.text_area(
                                "Notes", value=exp.notes or "", key=f"rec_notes_{exp.id}",
                            )

                        if st.button("Save changes", key=f"rec_save_{exp.id}", type="primary"):
                            exp.amount = new_amount
                            exp.category_id = cat_choices[new_cat]
                            exp.date = new_start
                            exp.merchant = new_merchant.strip() or exp.merchant
                            exp.frequency = new_frequency
                            exp.notes = new_notes.strip() or None
                            period = db.query(PayPeriod).filter(
                                PayPeriod.household_id == household_id,
                                PayPeriod.start_date <= new_start,
                                PayPeriod.end_date >= new_start,
                            ).first()
                            exp.pay_period_id = period.id if period else None
                            db.commit()
                            toast_success("Recurring bill updated")
                            st.rerun()

                if can_delete(role) and confirm_button(
                    f"rec_del_{exp.id}",
                    "Stop tracking",
                    "delete",
                    f"Remove recurring bill **{exp.merchant or 'bill'}**?",
                ):
                    exp.is_recurring = False
                    db.commit()
                    toast_success("Recurring bill removed")
                    st.rerun()
