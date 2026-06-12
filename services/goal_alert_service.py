"""Savings goal milestone notifications (80% / 100%)."""
import datetime
from sqlalchemy.orm import Session as DBSession
from models.audit import Notification
from models.budget import SavingsGoal
from services.notification_service import deliver_household_alert


def check_goal_threshold_alerts(db: DBSession, household_id: int):
    goals = db.query(SavingsGoal).filter(
        SavingsGoal.household_id == household_id,
        SavingsGoal.status == "active",
    ).all()
    today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    for goal in goals:
        if goal.target_amount <= 0:
            continue
        pct = (goal.current_amount / goal.target_amount) * 100
        if pct < 80:
            continue
        if pct >= 100:
            title = f"🎯 Goal reached: {goal.name}"
            msg = f"You hit your **{goal.name}** target of {goal.target_amount:,.2f}!"
            msg_type = "success"
        else:
            title = f"🎯 Goal progress: {goal.name}"
            msg = (
                f"**{goal.name}** is {pct:.0f}% funded "
                f"({goal.current_amount:,.2f} / {goal.target_amount:,.2f})."
            )
            msg_type = "info"
        dup = db.query(Notification).filter(
            Notification.household_id == household_id,
            Notification.title == title,
            Notification.sent_at >= today_start,
        ).first()
        if not dup:
            deliver_household_alert(
                db, household_id, title, msg.replace("**", ""), msg_type=msg_type,
            )
