"""Household membership management."""
from sqlalchemy.orm import Session as DBSession
from models.household import HouseholdMember
from models.auth import User
from services.auth_service import log_audit


def update_member_role(
    db: DBSession,
    household_id: int,
    member_user_id: int,
    new_role: str,
    requester_id: int,
) -> bool:
    requester = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == requester_id,
    ).first()
    if not requester or requester.role != "owner":
        return False
    target = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == member_user_id,
    ).first()
    if not target or target.role == "owner":
        return False
    if new_role not in ("partner", "viewer"):
        return False
    old = target.role
    target.role = new_role
    db.commit()
    log_audit(
        db, requester_id, "MEMBER_ROLE_CHANGED",
        f"Changed member {member_user_id} from {old} to {new_role}",
    )
    return True


def remove_household_member(
    db: DBSession,
    household_id: int,
    member_user_id: int,
    requester_id: int,
) -> bool:
    requester = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == requester_id,
    ).first()
    if not requester or requester.role != "owner":
        return False
    if member_user_id == requester_id:
        return False
    target = db.query(HouseholdMember).filter(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == member_user_id,
    ).first()
    if not target or target.role == "owner":
        return False
    user = db.query(User).filter(User.id == member_user_id).first()
    db.delete(target)
    db.commit()
    log_audit(
        db, requester_id, "MEMBER_REMOVED",
        f"Removed {user.email if user else member_user_id} from household {household_id}",
    )
    return True
