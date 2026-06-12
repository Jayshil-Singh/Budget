import secrets
import bcrypt
import datetime
import re
from sqlalchemy.orm import Session as DBSession
from models.auth import User, Session as UserSession

def hash_password(password: str) -> str:
    """
    Hashes a password using bcrypt.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies a password against its hash.
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_user_session(db: DBSession, user_id: int, ip_address: str = None, user_agent: str = None, duration_days: int = 1) -> UserSession:
    """
    Creates a new user session in the database.
    """
    token = secrets.token_hex(32)
    expires_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(days=duration_days)
    
    session = UserSession(
        user_id=user_id,
        session_token=token,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def validate_user_session(db: DBSession, token: str) -> UserSession | None:
    """
    Validates a session token and returns the session if valid.
    """
    session = db.query(UserSession).filter(UserSession.session_token == token).first()
    if session and session.expires_at > datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None):
        return session
    return None

def destroy_user_session(db: DBSession, token: str) -> bool:
    """
    Removes a session from the database.
    """
    session = db.query(UserSession).filter(UserSession.session_token == token).first()
    if session:
        db.delete(session)
        db.commit()
        return True
    return False


def evaluate_password_strength(password: str) -> dict:
    """
    Evaluates password strength based on:
    - Length >= 8
    - Contains at least one uppercase letter
    - Contains at least one digit
    - Contains at least one special character
    
    Returns a dict with:
    - 'strength': 'Weak' | 'Medium' | 'Strong'
    - 'score': 0..100 (for progress bar)
    - 'color': 'red' | 'orange' | 'green'
    - 'feedback': list of unmet requirements
    """
    if not password:
        return {
            "strength": "Weak",
            "score": 0,
            "color": "red",
            "feedback": ["Password cannot be empty."]
        }
        
    feedback = []
    has_length = len(password) >= 8
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = bool(re.search(r"[^a-zA-Z0-9]", password))
    
    if not has_length:
        feedback.append("At least 8 characters long")
    if not has_upper:
        feedback.append("At least one uppercase letter")
    if not has_digit:
        feedback.append("At least one number/digit")
    if not has_special:
        feedback.append("At least one special character (e.g., @, #, $, etc.)")
        
    if not has_length or not has_upper or not has_digit:
        basic_score = 0
        if has_length: basic_score += 10
        if has_upper: basic_score += 10
        if has_digit: basic_score += 10
        return {
            "strength": "Weak",
            "score": max(15, basic_score),
            "color": "red",
            "feedback": feedback
        }
    elif not has_special:
        return {
            "strength": "Medium",
            "score": 66,
            "color": "orange",
            "feedback": feedback
        }
    else:
        return {
            "strength": "Strong",
            "score": 100,
            "color": "green",
            "feedback": []
        }
