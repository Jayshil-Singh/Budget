import streamlit as st
from database import get_db
from models.auth import User
from services.auth_service import reset_user_password, log_audit
from services.notification_service import send_email_notification
from utils.security import verify_password, hash_password


def show_profile(user_id: int):
    """
    Renders the user's own self-service profile edit page.
    Allows updating name, email, and password.
    """
    st.markdown("<h1 class='app-title'>My Profile</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Manage your account details and security settings</p>", unsafe_allow_html=True)

    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            st.error("User not found.")
            return

        tab_info, tab_pwd = st.tabs(["👤 Profile Information", "🔒 Change Password"])

        # --------------------------------------------------------
        # PROFILE INFORMATION TAB
        # --------------------------------------------------------
        with tab_info:
            with st.container(border=True):
                st.subheader("Account Details")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Email:** {user.email}")
                    st.write(f"**Role:** {user.role.upper()}")
                with col2:
                    st.write(f"**Name:** {user.full_name}")
                    status = "✅ Active" if user.is_active else "❌ Inactive"
                    st.write(f"**Status:** {status}")
                st.write(f"**Member Since:** {user.created_at.strftime('%d %b %Y')}")

            st.write("")
            with st.expander("✏️ Edit Profile Details", expanded=False):
                with st.form("edit_own_profile_form"):
                    new_name = st.text_input("Full Name", value=user.full_name).strip()
                    new_email = st.text_input("Email Address", value=user.email).strip().lower()
                    st.caption("⚠️ If you change your email, you will need to log in again with the new address.")

                    submitted = st.form_submit_button("Save Changes", type="primary")
                    if submitted:
                        changes = []
                        old_email = user.email

                        if new_name and new_name != user.full_name:
                            user.full_name = new_name
                            # Update session display name
                            st.session_state["user_name"] = new_name
                            changes.append(f"Name updated to '{new_name}'")

                        if new_email and new_email != user.email:
                            # Check email not already taken
                            taken = db.query(User).filter(
                                User.email == new_email,
                                User.id != user_id
                            ).first()
                            if taken:
                                st.error(f"Email '{new_email}' is already registered to another account.")
                            else:
                                user.email = new_email
                                changes.append(f"Email updated to '{new_email}'")

                        if changes:
                            db.commit()
                            log_audit(db, user_id, "PROFILE_SELF_UPDATED", "; ".join(changes))

                            # Send notification to both old/new emails
                            subject = "SmartBudget AI – Profile Updated"
                            body = (
                                f"Hello {user.full_name},\n\n"
                                f"Your profile was updated:\n"
                                + "\n".join(f"• {c}" for c in changes)
                                + "\n\nIf you did not make this change, please contact your administrator immediately.\n\n"
                                "Regards,\nSmartBudget AI"
                            )
                            if old_email != user.email:
                                send_email_notification(subject, body, to_email=old_email)
                            send_email_notification(subject, body, to_email=user.email)
                            st.success("✅ Profile updated successfully!")
                            st.rerun()
                        else:
                            st.info("No changes detected.")

        # --------------------------------------------------------
        # CHANGE PASSWORD TAB
        # --------------------------------------------------------
        with tab_pwd:
            with st.form("change_own_password_form"):
                st.subheader("Change Password")
                current_pwd = st.text_input("Current Password", type="password")
                new_pwd = st.text_input("New Password", type="password")
                confirm_pwd = st.text_input("Confirm New Password", type="password")

                pwd_submitted = st.form_submit_button("Update Password", type="primary")
                if pwd_submitted:
                    if not current_pwd or not new_pwd or not confirm_pwd:
                        st.error("Please fill in all fields.")
                    elif not verify_password(current_pwd, user.password_hash):
                        st.error("❌ Current password is incorrect.")
                    elif new_pwd != confirm_pwd:
                        st.error("❌ New passwords do not match.")
                    elif len(new_pwd) < 8:
                        st.error("❌ New password must be at least 8 characters long.")
                    else:
                        reset_user_password(db, user_id, new_pwd, requester_id=user_id)
                        send_email_notification(
                            "SmartBudget AI – Password Changed",
                            f"Hello {user.full_name},\n\nYour account password was changed successfully.\n\n"
                            "If you did not make this change, contact your administrator immediately.\n\n"
                            "Regards,\nSmartBudget AI",
                            to_email=user.email
                        )
                        st.success("✅ Password updated successfully!")
                        log_audit(db, user_id, "PASSWORD_SELF_CHANGED", f"User {user.email} changed own password")
