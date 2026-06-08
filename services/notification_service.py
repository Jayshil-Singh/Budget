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

def send_email_notification(title: str, message: str) -> bool:
    """
    Sends an email notification. Fallback to simulation if config is missing.
    """
    if not config.EMAIL_SMTP_USER or not config.EMAIL_SMTP_PASSWORD:
        # Simulated delivery log
        print(f"[SIMULATED EMAIL] To: Household Members | Subject: {title} | Body: {message}")
        return True
        
    try:
        msg = MIMEText(message)
        msg['Subject'] = title
        msg['From'] = config.EMAIL_SMTP_USER
        msg['To'] = config.EMAIL_SMTP_USER # Send to self/owner as notification receiver
        
        with smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_SMTP_USER, config.EMAIL_SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email: {e}")
        return False

def send_whatsapp_notification(title: str, message: str) -> bool:
    """
    Sends a WhatsApp notification. Currently simulated unless a custom hook is set.
    """
    print(f"[SIMULATED WHATSAPP] Message: *{title}*\n{message}")
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
