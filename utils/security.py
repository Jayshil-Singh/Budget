import secrets
import bcrypt
import datetime
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
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=duration_days)
    
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
    if session and session.expires_at > datetime.datetime.utcnow():
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
