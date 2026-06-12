"""Budget threshold notifications (80% / 100%)."""
import datetime
from sqlalchemy.orm import Session as DBSession
from models.audit import Notification
from services.dashboard_service import get_budget_progress
from services.notification_service import deliver_household_alert


def check_budget_threshold_alerts(db: DBSession, household_id: int):
    progress = get_budget_progress(db, household_id)
    if not progress:
        return
    today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    for row in progress:
        pct = row["pct"]
        if pct < 80:
            continue
        if pct >= 100:
            title = f"🚨 Over budget: {row['category']}"
            msg = (
                f"You've spent {row['spent']:.2f} of {row['limit']:.2f} "
                f"on **{row['category']}** this pay cycle."
            )
            msg_type = "warning"
        else:
            title = f"⚠️ Budget warning: {row['category']}"
            msg = (
                f"You've used {pct:.0f}% of your **{row['category']}** budget "
                f"({row['spent']:.2f} / {row['limit']:.2f})."
            )
            msg_type = "info"
        duplicate = db.query(Notification).filter(
            Notification.household_id == household_id,
            Notification.title == title,
            Notification.sent_at >= today_start,
        ).first()
        if not duplicate:
            deliver_household_alert(db, household_id, title, msg.replace("**", ""), msg_type=msg_type)
