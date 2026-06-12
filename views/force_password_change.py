"""Gate screen when user must set a new password after invite."""
import streamlit as st
from database import get_db
from models.auth import User
from services.auth_service import reset_user_password, log_audit
from utils.security import evaluate_password_strength


def show_force_password_change(user_id: int) -> bool:
    """
    Returns True when password was changed and caller may continue.
    """
    st.markdown("<h1 class='app-title'>Set Your Password</h1>", unsafe_allow_html=True)
    st.info(
        "Your account was created by a household invite. "
        "Please choose a new password before continuing."
    )

    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            st.error("User not found.")
            return False

        with st.form("force_pwd_form"):
            new_pwd = st.text_input("New password", type="password")
            confirm_pwd = st.text_input("Confirm new password", type="password")
            submitted = st.form_submit_button("Save & Continue", type="primary")

            if submitted:
                if not new_pwd or not confirm_pwd:
                    st.error("Please fill in all fields.")
                elif new_pwd != confirm_pwd:
                    st.error("New passwords do not match.")
                else:
                    info = evaluate_password_strength(new_pwd)
                    if info["strength"] == "Weak":
                        st.error("Password is too weak. Please choose a stronger password.")
                        for fb in info["feedback"]:
                            st.markdown(f"- {fb}")
                    else:
                        reset_user_password(db, user_id, new_pwd, requester_id=user_id)
                        user.must_change_password = False
                        db.commit()
                        log_audit(db, user_id, "PASSWORD_FORCED_CHANGE", f"User {user.email} completed invite password setup")
                        st.success("Password updated! Redirecting…")
                        st.rerun()
    return False
