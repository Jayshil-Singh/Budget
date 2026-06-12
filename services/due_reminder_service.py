"""Day-before email digest for bills, subscriptions, and other dated payments."""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from sqlalchemy.orm import Session as DBSession

from models.budget import Budget, BudgetItem, Debt, SinkingFund, SavingsGoal
from models.finance import Expense, PaymentDueDate, Subscription
from models.household import Household, Setting
from services.dashboard_service import get_budget_progress, get_upcoming_bills
from services.finance_service import _get_occurrences_in_range, get_current_pay_period
from services.forecast_service import is_sub_date_hit
from services.notification_service import (
    create_notification,
    get_notification_channels,
    send_email_notification,
)

REMINDER_TITLE_PREFIX = "📅 Payment reminder — "
REMINDER_INTERVAL = datetime.timedelta(hours=1)


@dataclass
class DueItem:
    name: str
    amount: float
    due_date: datetime.date
    kind: str
    where: str
    category: str | None = None


def reminder_title(due_date: datetime.date) -> str:
    return f"{REMINDER_TITLE_PREFIX}{due_date.strftime('%d %b %Y')}"


def parse_reminder_due_date(title: str) -> datetime.date | None:
    if not title.startswith(REMINDER_TITLE_PREFIX):
        return None
    raw = title[len(REMINDER_TITLE_PREFIX):].strip()
    try:
        return datetime.datetime.strptime(raw, "%d %b %Y").date()
    except ValueError:
        return None


def _setting_key(prefix: str, due_date: datetime.date) -> str:
    return f"{prefix}_{due_date.isoformat()}"


def _get_setting(db: DBSession, household_id: int, key: str) -> str | None:
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == key,
    ).first()
    return row.value if row else None


def _set_setting(db: DBSession, household_id: int, key: str, value: str):
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == key,
    ).first()
    if row:
        row.value = value
    else:
        db.add(Setting(household_id=household_id, key=key, value=value))


def is_reminder_acknowledged(db: DBSession, household_id: int, due_date: datetime.date) -> bool:
    return _get_setting(db, household_id, _setting_key("payment_reminder_ack", due_date)) == "1"


def acknowledge_payment_reminder(db: DBSession, household_id: int, due_date: datetime.date):
    """Stop hourly reminders for payments due on due_date."""
    _set_setting(db, household_id, _setting_key("payment_reminder_ack", due_date), "1")
    db.commit()


def _last_reminder_sent_at(
    db: DBSession,
    household_id: int,
    due_date: datetime.date,
) -> datetime.datetime | None:
    raw = _get_setting(db, household_id, _setting_key("payment_reminder_last_sent", due_date))
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def _record_reminder_sent(db: DBSession, household_id: int, due_date: datetime.date):
    _set_setting(
        db,
        household_id,
        _setting_key("payment_reminder_last_sent", due_date),
        datetime.datetime.utcnow().isoformat(timespec="seconds"),
    )


def _latest_recurring_expense_templates(db: DBSession, household_id: int) -> list[Expense]:
    """Return the newest recurring expense template per merchant/category/amount pattern."""
    recurring = db.query(Expense).filter(
        Expense.household_id == household_id,
        Expense.is_recurring == True,
    ).all()
    seen: set[tuple] = set()
    templates: list[Expense] = []
    for exp in sorted(recurring, key=lambda e: e.date, reverse=True):
        key = (exp.category_id, (exp.merchant or "").strip().lower(), exp.amount)
        if key in seen:
            continue
        seen.add(key)
        templates.append(exp)
    return templates


def _sinking_fund_anchor(fund: SinkingFund) -> datetime.date:
    if fund.last_contribution:
        return fund.last_contribution
    if fund.created_at:
        return fund.created_at.date()
    return fund.target_date


def collect_items_due_on_date(
    db: DBSession,
    household_id: int,
    target_date: datetime.date,
) -> list[DueItem]:
    """Gather all payments and planned spends scheduled for target_date."""
    items: list[DueItem] = []

    for due in db.query(PaymentDueDate).filter(
        PaymentDueDate.household_id == household_id,
        PaymentDueDate.due_date == target_date,
        PaymentDueDate.is_paid == False,
    ).all():
        items.append(DueItem(
            name=due.name,
            amount=due.amount,
            due_date=due.due_date,
            kind="Custom bill",
            where="Calendar · custom due date",
        ))

    for sub in db.query(Subscription).filter(
        Subscription.household_id == household_id,
        Subscription.status == "active",
    ).all():
        if not is_sub_date_hit(sub.next_renewal, sub.frequency, target_date):
            continue
        where_parts = []
        if sub.category and sub.category.name:
            where_parts.append(sub.category.name)
        if sub.service_url:
            where_parts.append(sub.service_url)
        items.append(DueItem(
            name=sub.name,
            amount=sub.amount,
            due_date=target_date,
            kind="Subscription",
            where=" · ".join(where_parts) if where_parts else "Subscription renewal",
            category=sub.category.name if sub.category else None,
        ))

    for exp in _latest_recurring_expense_templates(db, household_id):
        if not exp.frequency:
            continue
        hits = _get_occurrences_in_range(exp.date, exp.frequency, target_date, target_date)
        if not hits:
            continue
        merchant = (exp.merchant or "Recurring bill").strip()
        cat_name = exp.category.name if exp.category else None
        where = merchant
        if cat_name:
            where = f"{merchant} · {cat_name}"
        items.append(DueItem(
            name=merchant,
            amount=exp.amount,
            due_date=target_date,
            kind="Recurring bill",
            where=where,
            category=cat_name,
        ))

    for debt in db.query(Debt).filter(Debt.household_id == household_id).all():
        hits = _get_occurrences_in_range(
            debt.start_date, debt.payment_frequency, target_date, target_date
        )
        if not hits:
            continue
        items.append(DueItem(
            name=debt.name,
            amount=debt.minimum_payment,
            due_date=target_date,
            kind="Debt payment",
            where=f"{debt.type} · minimum payment",
        ))

    for fund in db.query(SinkingFund).filter(SinkingFund.household_id == household_id).all():
        if fund.current_amount >= fund.target_amount:
            continue
        anchor = _sinking_fund_anchor(fund)
        hits = _get_occurrences_in_range(anchor, fund.frequency, target_date, target_date)
        if not hits:
            continue
        items.append(DueItem(
            name=fund.name,
            amount=fund.contribution_amount,
            due_date=target_date,
            kind="Sinking fund",
            where=f"Planned contribution · target {fund.target_date.strftime('%d %b %Y')}",
        ))

    for goal in db.query(SavingsGoal).filter(
        SavingsGoal.household_id == household_id,
        SavingsGoal.status == "active",
        SavingsGoal.target_date == target_date,
    ).all():
        remaining = max(0.0, goal.target_amount - goal.current_amount)
        if remaining <= 0:
            continue
        items.append(DueItem(
            name=goal.name,
            amount=remaining,
            due_date=target_date,
            kind="Savings goal",
            where=f"Target date · {goal.priority} priority",
        ))

    items.sort(key=lambda x: (x.kind, x.name))
    return items


def _format_money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _next_reminder_note(db: DBSession, household_id: int, due_date: datetime.date) -> str:
    upcoming = get_upcoming_bills(db, household_id, limit=50, days_ahead=365)
    future = [e for e in upcoming if e["date"] > due_date]
    if not future:
        return "After you confirm, reminders will resume one day before your next scheduled bill or payment."
    nxt = future[0]
    remind_on = nxt["date"] - datetime.timedelta(days=1)
    return (
        f"After you confirm, your next reminder will be sent on "
        f"{remind_on.strftime('%A, %d %b %Y')} (one day before "
        f"{nxt['name']} on {nxt['date'].strftime('%d %b %Y')})."
    )


def build_reminder_message(
    db: DBSession,
    household_id: int,
    items: list[DueItem],
    due_date: datetime.date,
    currency: str = "FJD",
    *,
    is_repeat: bool = False,
    recipient_name: str | None = None,
) -> str:
    """Build a plain-text digest with payment details and pay-cycle budget context."""
    household = db.query(Household).filter(Household.id == household_id).first()
    household_name = household.name if household else "your household"
    total_due = sum(i.amount for i in items)
    date_label = due_date.strftime("%A, %d %b %Y")
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"

    lines = [
        greeting,
        "",
        f"Here is what {household_name} has coming up on {date_label} (tomorrow):",
        "",
    ]
    if is_repeat:
        lines.append("This is a follow-up reminder (sent every hour until you confirm).")
        lines.append("")

    lines.extend([
        f"PAYMENTS & SPENDS DUE — {date_label}",
        f"{'─' * 42}",
        f"Total due tomorrow: {_format_money(total_due, currency)}",
        "",
    ])

    for item in items:
        lines.append(f"• {item.name}")
        lines.append(f"  Amount: {_format_money(item.amount, currency)}")
        lines.append(f"  Type: {item.kind}")
        lines.append(f"  Where: {item.where}")
        lines.append("")

    period = get_current_pay_period(db, household_id, check_date=due_date)
    progress = get_budget_progress(db, household_id)

    lines.append("YOUR PAY CYCLE BUDGET")
    lines.append(f"{'─' * 42}")

    if period:
        lines.append(f"Current period: {period.name}")
        lines.append(
            f"({period.start_date.strftime('%d %b')} – {period.end_date.strftime('%d %b %Y')})"
        )
    else:
        lines.append("No active pay period found for this date.")

    if progress:
        total_limit = sum(r["limit"] for r in progress)
        total_spent = sum(r["spent"] for r in progress)
        total_remaining = sum(max(0.0, r["remaining"]) for r in progress)
        lines.append(
            f"Budget tracked: {_format_money(total_spent, currency)} spent of "
            f"{_format_money(total_limit, currency)} ({_format_money(total_remaining, currency)} remaining)"
        )
        lines.append("")
        lines.append("By category:")
        due_by_category: dict[str, float] = {}
        for item in items:
            if item.category:
                due_by_category[item.category] = due_by_category.get(item.category, 0.0) + item.amount

        for row in progress:
            remaining = row["remaining"]
            cat_line = (
                f"  • {row['category']}: {_format_money(row['spent'], currency)} spent of "
                f"{_format_money(row['limit'], currency)} "
                f"({_format_money(max(0.0, remaining), currency)} left, {row['pct']:.0f}% used)"
            )
            if row["category"] in due_by_category:
                cat_line += (
                    f" — includes {_format_money(due_by_category[row['category']], currency)} "
                    f"due tomorrow"
                )
            lines.append(cat_line)
    else:
        budget = None
        if period:
            budget = db.query(Budget).filter(
                Budget.household_id == household_id,
                Budget.pay_period_id == period.id,
            ).first()
        if not budget:
            lines.append("No budget set for the current pay cycle yet.")
        else:
            lines.append("Budget exists but has no category limits configured.")

    lines.extend([
        "",
        "ACTION REQUIRED",
        f"{'─' * 42}",
        "Please log in to SmartBudget AI to update your scheduled payments and bills,",
        "or open the app and click \"Stop reminders\" on the payment reminder notification.",
        "",
        "Reminders are sent every hour until you confirm.",
        _next_reminder_note(db, household_id, due_date),
        "",
        "Regards,",
        "SmartBudget AI",
    ])
    return "\n".join(lines)


def _should_send_reminder(
    db: DBSession,
    household_id: int,
    due_date: datetime.date,
) -> tuple[bool, bool]:
    """
    Returns (should_send, is_repeat).
    Sends on the day before due_date, then every hour until acknowledged.
    """
    if is_reminder_acknowledged(db, household_id, due_date):
        return False, False

    items = collect_items_due_on_date(db, household_id, due_date)
    if not items:
        return False, False

    last_sent = _last_reminder_sent_at(db, household_id, due_date)
    if last_sent and datetime.datetime.utcnow() - last_sent < REMINDER_INTERVAL:
        return False, False

    return True, last_sent is not None


def check_due_reminder_notifications(db: DBSession, household_id: int):
    """
    Sends household members a day-before digest email listing everything due tomorrow,
    with pay-cycle budget context. Repeats every hour until the user acknowledges.
    """
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    should_send, is_repeat = _should_send_reminder(db, household_id, tomorrow)
    if not should_send:
        return

    items = collect_items_due_on_date(db, household_id, tomorrow)
    household = db.query(Household).filter(Household.id == household_id).first()
    currency = household.currency if household else "FJD"
    title = reminder_title(tomorrow)
    channels = get_notification_channels(db, household_id)

    if "in_app" in channels and not is_repeat:
        in_app_message = build_reminder_message(
            db, household_id, items, tomorrow, currency=currency, is_repeat=is_repeat,
        )
        create_notification(
            db, household_id, title=title, message=in_app_message, msg_type="warning", channel="in_app",
        )

    if "email" in channels:
        from models.household import HouseholdMember
        members = db.query(HouseholdMember).filter(HouseholdMember.household_id == household_id).all()
        for member in members:
            user = member.user
            if not user or not user.email:
                continue
            recipient_name = (user.full_name or "").strip() or None
            personal_message = build_reminder_message(
                db,
                household_id,
                items,
                tomorrow,
                currency=currency,
                is_repeat=is_repeat,
                recipient_name=recipient_name,
            )
            send_email_notification(title, personal_message, to_email=user.email)

    _record_reminder_sent(db, household_id, tomorrow)

    for due in db.query(PaymentDueDate).filter(
        PaymentDueDate.household_id == household_id,
        PaymentDueDate.due_date == tomorrow,
        PaymentDueDate.is_paid == False,
        PaymentDueDate.email_notified == False,
    ).all():
        due.email_notified = True

    db.commit()
