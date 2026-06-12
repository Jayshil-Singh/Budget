import smtplib
from email.mime.text import MIMEText
from sqlalchemy.orm import Session as DBSession
from models.audit import Notification
import config

def create_notification(
    db: DBSession, 
    household_id: int, 
    title: str, 
    message: str, 
    msg_type: str = "info", 
    channel: str = "in_app"
) -> Notification:
    """
    Creates a new notification record in the DB and attempts external delivery.
    """
    notification = Notification(
        household_id=household_id,
        title=title,
        message=message,
        type=msg_type,
        channel=channel,
        is_read=False
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    
    if channel == "email":
        send_email_notification(title, message)

    return notification

def send_email_notification(title: str, message: str, to_email: str = None) -> bool:
    """
    Sends an email notification. Fallback to simulation if config is missing.
    """
    recipient = to_email if to_email else config.EMAIL_SMTP_USER
    status = "Pending"
    success = False
    
    if not config.EMAIL_SMTP_USER or not config.EMAIL_SMTP_PASSWORD:
        # Simulated delivery log
        try:
            print(f"[SIMULATED EMAIL] To: {recipient} | Subject: {title} | Body: {message}")
        except UnicodeEncodeError:
            clean_title = title.encode('ascii', 'replace').decode()
            clean_message = message.encode('ascii', 'replace').decode()
            print(f"[SIMULATED EMAIL] To: {recipient} | Subject: {clean_title} | Body: {clean_message}")
        status = "Simulated"
        success = True
    else:
        try:
            msg = MIMEText(message)
            msg['Subject'] = title
            msg['From'] = config.EMAIL_SMTP_USER
            msg['To'] = recipient

            use_ssl = getattr(config, "EMAIL_SMTP_USE_SSL", False)
            if use_ssl:
                with smtplib.SMTP_SSL(
                    config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT, timeout=30,
                ) as server:
                    server.login(config.EMAIL_SMTP_USER, config.EMAIL_SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(
                    config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT, timeout=30,
                ) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(config.EMAIL_SMTP_USER, config.EMAIL_SMTP_PASSWORD)
                    server.send_message(msg)
            status = "Success"
            success = True
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send email to {recipient}: {e}")
            status = f"Failed: {str(e)}"
            success = False

    # Log to Database
    from database import SessionLocal
    from models.audit import EmailLog
    try:
        with SessionLocal() as db:
            log = EmailLog(
                recipient=recipient,
                subject=title,
                body=message,
                status=status
            )
            db.add(log)
            db.commit()
    except Exception as db_err:
        print(f"[DATABASE ERROR] Failed to log email: {db_err}")
        
    return success

def send_invite_email(
    to_email: str,
    household_name: str,
    inviter_name: str,
    temp_password: str,
    role: str,
) -> bool:
    subject = f"You're invited to {household_name} on SmartBudget AI"
    body = (
        f"Hello,\n\n"
        f"{inviter_name} invited you to join **{household_name}** as a {role}.\n\n"
        f"Log in with:\n"
        f"• Email: {to_email}\n"
        f"• Temporary password: {temp_password}\n\n"
        f"You will be asked to set a new password on first login.\n\n"
        f"Regards,\nSmartBudget AI"
    )
    return send_email_notification(subject, body.replace("**", ""), to_email=to_email)


def get_notification_channels(db: DBSession, household_id: int) -> list[str]:
    """Returns enabled delivery channels: in_app and email only."""
    from models.household import Setting
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == "notification_channels",
    ).first()
    if not row:
        return ["in_app", "email"]
    try:
        import json
        channels = json.loads(row.value)
        if isinstance(channels, list) and channels:
            return [c for c in channels if c in ("in_app", "email")]
    except Exception:
        pass
    return ["in_app", "email"]


def deliver_household_alert(
    db: DBSession,
    household_id: int,
    title: str,
    message: str,
    msg_type: str = "info",
):
    """Create in-app notification and optional email per household prefs."""
    channels = get_notification_channels(db, household_id)
    if "in_app" in channels:
        create_notification(db, household_id, title, message, msg_type=msg_type, channel="in_app")
    if "email" in channels:
        from models.household import HouseholdMember
        members = db.query(HouseholdMember).filter(HouseholdMember.household_id == household_id).all()
        for member in members:
            user = member.user
            if not user:
                continue
            if user.email:
                send_email_notification(title, message, to_email=user.email)

def mark_notification_read(db: DBSession, notification_id: int) -> bool:
    """
    Marks a notification as read.
    """
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if notif:
        notif.is_read = True
        db.commit()
        return True
    return False


def check_due_date_email_notifications(db: DBSession, household_id: int):
    """
    Day-before digest: bills, subscriptions, recurring expenses, debt, sinking funds,
    and savings goals due tomorrow, with pay-cycle budget context.
    Repeats every hour until the user acknowledges in the app.
    """
    from services.due_reminder_service import check_due_reminder_notifications
    check_due_reminder_notifications(db, household_id)

