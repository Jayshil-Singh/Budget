import datetime
import calendar
from sqlalchemy.orm import Session as DBSession
from models.finance import Income, Expense, Subscription, PayPeriod
from models.audit import Notification
from services.notification_service import create_notification

def add_month(d: datetime.date) -> datetime.date:
    month = d.month
    year = d.year
    if month == 12:
        month = 1
        year += 1
    else:
        month += 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return datetime.date(year, month, day)

def add_fortnight(d: datetime.date) -> datetime.date:
    return d + datetime.timedelta(days=14)

def add_week(d: datetime.date) -> datetime.date:
    return d + datetime.timedelta(days=7)

def add_year(d: datetime.date) -> datetime.date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        # Handle leap year Feb 29
        return datetime.date(d.year + 1, 2, 28)

def get_next_date(d: datetime.date, frequency: str) -> datetime.date:
    freq = (frequency or "").lower()
    if freq == "weekly":
        return add_week(d)
    elif freq == "fortnightly" or freq == "payday":
        return add_fortnight(d)
    elif freq == "monthly":
        return add_month(d)
    elif freq in ["annual", "yearly"]:
        return add_year(d)
    else:
        return d + datetime.timedelta(days=30) # default fallback

def post_recurring_transactions(db: DBSession, household_id: int):
    """
    Checks recurring income, expenses, and active subscriptions.
    Auto-posts them when their schedule date arrives and sends notifications.
    """
    today = datetime.date.today()
    posts_count = 0
    notifications_created = []

    # 1. Process recurring incomes
    recurring_incomes = db.query(Income).filter(
        Income.household_id == household_id,
        Income.is_recurring == True
    ).all()

    for inc in recurring_incomes:
        # If next_date is None, initialize it using its original date + frequency
        if not inc.next_date:
            inc.next_date = get_next_date(inc.date, inc.frequency)
            db.commit()

        while inc.next_date and inc.next_date <= today:
            post_date = inc.next_date
            
            # Find matching pay period for the posted transaction
            curr_period = db.query(PayPeriod).filter(
                PayPeriod.household_id == household_id,
                PayPeriod.start_date <= post_date,
                PayPeriod.end_date >= post_date
            ).first()

            # Create the historical income entry (representing the paycheck hit)
            new_income = Income(
                household_id=household_id,
                source=inc.source,
                amount=inc.amount,
                date=post_date,
                is_recurring=False,
                frequency=None,
                next_date=None,
                pay_period_id=curr_period.id if curr_period else None,
                description=f"Auto-posted from recurring template (ID: {inc.id})"
            )
            db.add(new_income)
            
            # Advance template's next_date
            inc.next_date = get_next_date(inc.next_date, inc.frequency)
            posts_count += 1
            
            title = f"💰 Recurring Income Posted"
            message = f"Income of ${inc.amount:.2f} from '{inc.source}' has been auto-posted for {post_date.strftime('%d %b %Y')}."
            notifications_created.append((title, message, "success"))

    # 2. Process subscriptions
    active_subs = db.query(Subscription).filter(
        Subscription.household_id == household_id,
        Subscription.status == "active"
    ).all()

    for sub in active_subs:
        while sub.next_renewal <= today:
            post_date = sub.next_renewal
            
            curr_period = db.query(PayPeriod).filter(
                PayPeriod.household_id == household_id,
                PayPeriod.start_date <= post_date,
                PayPeriod.end_date >= post_date
            ).first()

            # Create expense
            new_expense = Expense(
                household_id=household_id,
                category_id=sub.category_id,
                amount=sub.amount,
                date=post_date,
                merchant=sub.name,
                notes=f"Auto-posted renewal from subscription tracker (ID: {sub.id})",
                is_recurring=False,
                frequency=None,
                pay_period_id=curr_period.id if curr_period else None
            )
            db.add(new_expense)

            # Advance next renewal date
            sub.next_renewal = get_next_date(sub.next_renewal, sub.frequency)
            posts_count += 1
            
            title = f"💸 Subscription Renewal Posted"
            message = f"Subscription '{sub.name}' (${sub.amount:.2f}) was auto-posted for {post_date.strftime('%d %b %Y')}."
            notifications_created.append((title, message, "info"))

    # 3. Process recurring expenses (without next_date, using template-advancing logic)
    recurring_expenses = db.query(Expense).filter(
        Expense.household_id == household_id,
        Expense.is_recurring == True
    ).all()

    # To ensure we only process the latest template for each pattern:
    # Sort them by date descending. We only process an expense template if there isn't a newer
    # recurring expense of the same merchant, category, and amount.
    processed_patterns = set()
    
    for exp in sorted(recurring_expenses, key=lambda e: e.date, reverse=True):
        pattern_key = (exp.category_id, (exp.merchant or "").strip().lower(), exp.amount)
        if pattern_key in processed_patterns:
            # We already processed a newer template for this exact pattern, so mark this older one as non-recurring
            exp.is_recurring = False
            continue
        processed_patterns.add(pattern_key)

        # Now check if this template needs to post occurrences
        current_template = exp
        while True:
            next_due = get_next_date(current_template.date, current_template.frequency)
            if next_due > today:
                break
                
            post_date = next_due
            curr_period = db.query(PayPeriod).filter(
                PayPeriod.household_id == household_id,
                PayPeriod.start_date <= post_date,
                PayPeriod.end_date >= post_date
            ).first()

            # Create the next occurrence as the new template
            new_template = Expense(
                household_id=household_id,
                category_id=current_template.category_id,
                amount=current_template.amount,
                date=post_date,
                merchant=current_template.merchant,
                notes=current_template.notes,
                is_recurring=True,
                frequency=current_template.frequency,
                pay_period_id=curr_period.id if curr_period else None
            )
            db.add(new_template)
            
            # The previous template is no longer the active template
            current_template.is_recurring = False
            
            # Flush so that new_template has id set
            db.flush()
            
            posts_count += 1
            title = f"💸 Recurring Expense Posted"
            message = f"Recurring expense '{current_template.merchant or 'Bill'}' (${current_template.amount:.2f}) was auto-posted for {post_date.strftime('%d %b %Y')}."
            notifications_created.append((title, message, "info"))
            
            # Now the new template becomes the current template to check for further occurrences
            current_template = new_template

    if posts_count > 0:
        db.commit()
        # Create notifications in the DB
        for title, message, msg_type in notifications_created:
            create_notification(db, household_id, title, message, msg_type=msg_type, channel="in_app")
            
    return posts_count
