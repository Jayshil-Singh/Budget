"""
Run background jobs for all households (no Streamlit required).

Usage:
    python scripts/run_background_jobs.py

Schedule on Windows Task Scheduler or cron every hour for payment reminders
(and once daily is fine for recurring auto-post if preferred).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import SessionLocal, init_db
from models.household import Household


def run_all():
    init_db()
    with SessionLocal() as db:
        households = db.query(Household).all()
        if not households:
            print("[BG] No households found.")
            return
        from services.recurring_service import post_recurring_transactions
        from services.notification_service import check_due_date_email_notifications
        from services.budget_alert_service import check_budget_threshold_alerts
        from services.goal_alert_service import check_goal_threshold_alerts

        for h in households:
            hid = h.id
            print(f"[BG] Household {hid} ({h.name})")
            try:
                post_recurring_transactions(db, hid)
            except Exception as e:
                print(f"  [RECURRING ERROR] {e}")
            try:
                check_due_date_email_notifications(db, hid)
            except Exception as e:
                print(f"  [REMINDER ERROR] {e}")
            try:
                check_budget_threshold_alerts(db, hid)
            except Exception as e:
                print(f"  [BUDGET ALERT ERROR] {e}")
            try:
                check_goal_threshold_alerts(db, hid)
            except Exception as e:
                print(f"  [GOAL ALERT ERROR] {e}")
        print(f"[BG] Done — processed {len(households)} household(s).")


if __name__ == "__main__":
    run_all()
