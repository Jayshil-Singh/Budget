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
    
    # Attempt channel-specific delivery
    if channel == "email":
        send_email_notification(title, message)
    elif channel == "whatsapp":
        send_whatsapp_notification(title, message)
        
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
            
            with smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT) as server:
                server.starttls()
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

def send_whatsapp_notification(title: str, message: str) -> bool:
    """
    Sends a WhatsApp notification. Currently simulated unless a custom hook is set.
    """
    try:
        print(f"[SIMULATED WHATSAPP] Message: *{title}*\n{message}")
    except UnicodeEncodeError:
        clean_title = title.encode('ascii', 'replace').decode()
        clean_message = message.encode('ascii', 'replace').decode()
        print(f"[SIMULATED WHATSAPP] Message: *{clean_title}*\n{clean_message}")
    return True

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
    Checks for custom payment due dates set for tomorrow (1 day before due date)
    that are unpaid and have not yet sent emails.
    Sends emails and creates in-app notifications.
    """
    import datetime
    from models.finance import PaymentDueDate
    from models.household import HouseholdMember
    
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    
    # Query due dates due tomorrow, unpaid, not notified
    upcoming_dues = db.query(PaymentDueDate).filter(
        PaymentDueDate.household_id == household_id,
        PaymentDueDate.due_date == tomorrow,
        PaymentDueDate.is_paid == False,
        PaymentDueDate.email_notified == False
    ).all()
    
    if not upcoming_dues:
        return
        
    # Get all members of the household
    members = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id
    ).all()
    
    for due in upcoming_dues:
        subject = f"⚠️ Reminder: Bill Due Tomorrow - {due.name}"
        body = (
            f"Hello,\n\n"
            f"This is a reminder from SmartBudget AI.\n\n"
            f"The following payment is due tomorrow:\n"
            f"• Bill/Payment: {due.name}\n"
            f"• Amount: {due.amount:,.2f} FJD\n"
            f"• Due Date: {due.due_date.strftime('%A, %d %b %Y')}\n\n"
            f"Please log in to your dashboard to complete or adjust this payment.\n\n"
            f"Regards,\n"
            f"SmartBudget AI Team"
        )
        
        # Send emails to all members
        for member in members:
            user = member.user
            if user and user.email:
                send_email_notification(subject, body, to_email=user.email)
                
        # Also create in-app notification
        create_notification(
            db,
            household_id=household_id,
            title=f"⚠️ Due Tomorrow: {due.name}",
            message=f"Bill '{due.name}' (${due.amount:,.2f}) is due tomorrow.",
            msg_type="warning",
            channel="in_app"
        )
        
        # Mark notified
        due.email_notified = True
        
    db.commit()

