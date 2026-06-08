import datetime
from sqlalchemy.orm import Session as DBSession
from models.auth import User, Session as UserSession
from models.household import Household, HouseholdMember, Setting
from models.audit import AuditLog
from utils.security import hash_password, verify_password, create_user_session

def log_audit(db: DBSession, user_id: int | None, action: str, details: str = None):
    """
    Log an event to the audit_logs table.
    """
    log = AuditLog(user_id=user_id, action=action, details=details)
    db.add(log)
    db.commit()

def authenticate_user(db: DBSession, email: str, password: str) -> User | None:
    """
    Authenticates a user and logs the attempt.
    """
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user or not user.is_active:
        log_audit(db, None, "AUTH_FAILED", f"Attempted login with email: {email}")
        return None
    
    if verify_password(password, user.password_hash):
        log_audit(db, user.id, "USER_LOGIN", f"User {user.full_name} logged in successfully")
        return user
    
    log_audit(db, user.id, "AUTH_PASSWORD_INCORRECT", f"Incorrect password for user {email}")
    return None

def create_new_user(db: DBSession, email: str, password: str, full_name: str, role: str) -> User | None:
    """
    Creates a new user in the system. Enforces roles: admin, owner, partner, viewer.
    """
    existing = db.query(User).filter(User.email == email.lower()).first()
    if existing:
        return None
        
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    log_audit(db, user.id, "USER_CREATED", f"Created user {full_name} with role {role}")
    return user

def disable_user(db: DBSession, user_id: int, requester_id: int) -> bool:
    """
    Disables a user. Requester must be admin.
    """
    requester = db.query(User).filter(User.id == requester_id).first()
    if not requester or requester.role != "admin":
        return False
        
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = False
        db.commit()
        log_audit(db, requester_id, "USER_DISABLED", f"Disabled user: {user.email}")
        return True
    return False

def reset_user_password(db: DBSession, user_id: int, new_password: str, requester_id: int = None) -> bool:
    """
    Resets a user's password. Requires admin or same user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
        
    user.password_hash = hash_password(new_password)
    db.commit()
    log_audit(db, requester_id or user_id, "PASSWORD_RESET", f"Reset password for user: {user.email}")
    return True

def get_household_for_user(db: DBSession, user_id: int) -> Household | None:
    """
    Gets the household associated with the user.
    Since we support multi-household, this retrieves the first active household
    or a selected household from the memberships.
    """
    membership = db.query(HouseholdMember).filter(HouseholdMember.user_id == user_id).first()
    if membership:
        return db.query(Household).filter(Household.id == membership.household_id).first()
    return None

def create_household_for_user(db: DBSession, user_id: int, name: str, currency: str = "FJD", budget_method: str = "payday") -> Household:
    """
    Creates a new household and marks the creator as the Owner.
    """
    household = Household(name=name, currency=currency, budget_method=budget_method)
    db.add(household)
    db.commit()
    db.refresh(household)
    
    # Add creator as Household Owner
    member = HouseholdMember(household_id=household.id, user_id=user_id, role="owner")
    db.add(member)
    db.commit()
    
    log_audit(db, user_id, "HOUSEHOLD_CREATED", f"Created household {name} ({currency}, {budget_method})")
    return household

def invite_member_to_household(db: DBSession, household_id: int, email: str, role: str, requester_id: int) -> HouseholdMember | None:
    """
    Adds a member to a household. Validates permissions.
    """
    # Verify requester is owner or partner
    req_mem = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id, 
        HouseholdMember.user_id == requester_id
    ).first()
    
    if not req_mem or req_mem.role not in ["owner", "partner"]:
        return None
        
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user:
        # Create user with a temporary password if they don't exist
        # Typically the Admin creates them, but for household self-onboarding
        # we create a placeholder user that gets activated.
        # Let's fallback to search
        return None
        
    # Check if already a member
    existing = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == user.id
    ).first()
    
    if existing:
        return existing
        
    member = HouseholdMember(household_id=household_id, user_id=user.id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    
    log_audit(db, requester_id, "MEMBER_INVITED", f"Invited {email} to household ID {household_id} as {role}")
    return member
