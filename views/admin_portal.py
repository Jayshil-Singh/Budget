import streamlit as st
import pandas as pd
from database import get_db
from models.auth import User
from models.household import Household
from models.finance import Income, Expense, ExpenseCategory
from models.audit import AuditLog, EmailLog
from services.auth_service import create_new_user, disable_user, reset_user_password
from services.notification_service import send_email_notification
from config import EXPENSE_CATEGORIES

def show_admin_portal(admin_user_id: int):
    """
    Renders the platform administration dashboard.
    Exclusive to the 'admin' system role.
    """
    st.markdown("<h1 class='app-title'>Platform Admin Portal</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Manage global accounts, review system audits, and manage global settings</p>", unsafe_allow_html=True)
    
    # Verify Admin Role
    if st.session_state.get("user_role") != "admin":
        st.error("Access Denied: You do not have permission to view the Admin Portal.")
        return
        
    tab_users, tab_stats, tab_cats, tab_emails, tab_sys_audit = st.tabs([
        "👤 User Management", "📈 Platform Stats", "🏷️ Custom Categories", "✉️ Email Logs", "📜 Global System Logs"
    ])
    
    with get_db() as db:
        # ----------------------------------------------------
        # USER MANAGEMENT TAB
        # ----------------------------------------------------
        with tab_users:
            st.subheader("Manage Accounts")
            
            # Form to create user
            with st.expander("➕ Create New User Account", expanded=False):
                with st.form("create_user_admin_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        new_email = st.text_input("Email Address").strip()
                        new_name = st.text_input("Full Name").strip()
                    with col2:
                        new_pwd = st.text_input("Default Password", type="password")
                        new_role = st.selectbox("System Role Permission", ["owner", "partner", "viewer", "admin"])
                        
                    submit_user = st.form_submit_button("Register User", type="primary")
                    if submit_user:
                        if not new_email or not new_name or not new_pwd:
                            st.error("Please fill in all fields.")
                        else:
                            from utils.security import evaluate_password_strength
                            strength_info = evaluate_password_strength(new_pwd)
                            if strength_info["strength"] == "Weak":
                                st.error("❌ Password is too weak. It must meet the following criteria:")
                                for fb in strength_info["feedback"]:
                                    st.markdown(f"- {fb}")
                            else:
                                res = create_new_user(db, new_email, new_pwd, new_name, new_role)
                                if res:
                                    email_subject = "Your SmartBudget AI Account Credentials"
                                    email_body = (
                                        f"Hello {new_name},\n\n"
                                        f"An administrator has created a SmartBudget AI account for you.\n\n"
                                        f"Here are your login credentials:\n"
                                        f"Email: {new_email}\n"
                                        f"Password: {new_pwd}\n\n"
                                        f"You can access the application here:\n"
                                        f"https://smart-budget.streamlit.app/\n\n"
                                        f"Regards,\n"
                                        f"SmartBudget AI Team"
                                    )
                                    send_email_notification(email_subject, email_body, to_email=new_email)
                                    st.success(f"Registered user {new_name} as {new_role.upper()} successfully and sent credentials email!")
                                    st.rerun()
                                else:
                                    st.error("Email is already registered.")
                                
            # List users
            users = db.query(User).all()
            user_rows = []
            for u in users:
                user_rows.append({
                    "ID": u.id,
                    "Name": u.full_name,
                    "Email": u.email,
                    "Role": u.role.upper(),
                    "Active": "Yes" if u.is_active else "No"
                })
            df_users = pd.DataFrame(user_rows)
            st.dataframe(df_users, width="stretch", hide_index=True)
            
            # Disable / Enable / Password reset actions
            st.write("")
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                target_user_id = st.number_input("Target User ID to manage", min_value=0, step=1)
            with col_act2:
                action = st.selectbox("Action", ["Disable/Deactivate Account", "Enable/Reactivate Account", "Force Reset Password"])
                
            if action == "Force Reset Password":
                reset_pwd_val = st.text_input("New Force Reset Password", type="password", key="reset_val_pwd")
            else:
                reset_pwd_val = None
                
            action_purpose = st.text_area("Purpose of Action (This will be emailed to the user)", placeholder="Provide reason for deactivation, reactivation, or password reset...", key="action_purpose_val")
            
            if st.button("Apply Account Action", type="secondary"):
                if not action_purpose.strip():
                    st.error("Please provide the purpose/reason of the action.")
                else:
                    target_user = db.query(User).filter(User.id == target_user_id).first()
                    if target_user:
                        if action == "Disable/Deactivate Account":
                            target_user.is_active = False
                            db.commit()
                            email_subject = "Your SmartBudget AI Account Status Update"
                            email_body = (
                                f"Hello {target_user.full_name},\n\n"
                                f"Your SmartBudget AI account has been deactivated by the platform administrator.\n\n"
                                f"Reason/Purpose: {action_purpose}\n\n"
                                f"If you believe this is an error, please contact support.\n\n"
                                f"Regards,\n"
                                f"SmartBudget AI Team"
                            )
                            send_email_notification(email_subject, email_body, to_email=target_user.email)
                            st.success("Account deactivated and user notified via email!")
                            st.rerun()
                        elif action == "Enable/Reactivate Account":
                            target_user.is_active = True
                            db.commit()
                            email_subject = "Your SmartBudget AI Account Status Update"
                            email_body = (
                                f"Hello {target_user.full_name},\n\n"
                                f"Your SmartBudget AI account has been reactivated by the platform administrator.\n\n"
                                f"Reason/Purpose: {action_purpose}\n\n"
                                f"You can now log in at: https://smart-budget.streamlit.app/\n\n"
                                f"Regards,\n"
                                f"SmartBudget AI Team"
                            )
                            send_email_notification(email_subject, email_body, to_email=target_user.email)
                            st.success("Account activated and user notified via email!")
                            st.rerun()
                        elif action == "Force Reset Password":
                            if reset_pwd_val:
                                from utils.security import evaluate_password_strength
                                strength_info = evaluate_password_strength(reset_pwd_val)
                                if strength_info["strength"] == "Weak":
                                    st.error("❌ Password is too weak. It must meet the following criteria:")
                                    for fb in strength_info["feedback"]:
                                        st.markdown(f"- {fb}")
                                else:
                                    reset_user_password(db, target_user.id, reset_pwd_val, admin_user_id)
                                    email_subject = "Your SmartBudget AI Password Reset"
                                    email_body = (
                                        f"Hello {target_user.full_name},\n\n"
                                        f"Your password has been reset by the platform administrator.\n\n"
                                        f"New Password: {reset_pwd_val}\n"
                                        f"Reason/Purpose: {action_purpose}\n\n"
                                        f"Please log in at https://smart-budget.streamlit.app/ and update your password.\n\n"
                                        f"Regards,\n"
                                        f"SmartBudget AI Team"
                                    )
                                    send_email_notification(email_subject, email_body, to_email=target_user.email)
                                    st.success("Password updated and user notified via email!")
                                    st.rerun()
                            else:
                                st.error("Please provide the reset password value.")
                    else:
                        st.error("User ID not found.")

            # Edit User Profile expander
            st.write("")
            with st.expander("📝 Edit User Profile (Role, Email, Name)", expanded=False):
                with st.form("edit_user_profile_form"):
                    edit_user_id = st.number_input("User ID to Edit", min_value=1, step=1)
                    edit_name = st.text_input("New Full Name (Leave blank to keep current)").strip()
                    edit_email = st.text_input("New Email Address (Leave blank to keep current)").strip()
                    edit_role = st.selectbox("New System Role Permission", ["No Change", "owner", "partner", "viewer", "admin"])
                    edit_purpose = st.text_area("Purpose of Profile Change (This will be emailed to the user)", placeholder="Provide reason for updating name, email, or role...")
                    
                    submit_edit = st.form_submit_button("Update Profile", type="primary")
                    if submit_edit:
                        target_user = db.query(User).filter(User.id == edit_user_id).first()
                        if not target_user:
                            st.error("User ID not found.")
                        elif not edit_purpose.strip():
                            st.error("Please provide the purpose of the change.")
                        else:
                            changes = []
                            old_email = target_user.email
                            old_name = target_user.full_name
                            old_role = target_user.role
                            
                            if edit_name and edit_name != old_name:
                                target_user.full_name = edit_name
                                changes.append(f"Name: '{old_name}' -> '{edit_name}'")
                            if edit_email and edit_email.lower() != old_email:
                                email_exists = db.query(User).filter(User.email == edit_email.lower()).first()
                                if email_exists:
                                    st.error(f"Email {edit_email} is already registered to another user.")
                                    target_user = None
                                else:
                                    target_user.email = edit_email.lower()
                                    changes.append(f"Email: '{old_email}' -> '{edit_email.lower()}'")
                            if edit_role != "No Change" and edit_role != old_role:
                                target_user.role = edit_role
                                changes.append(f"Role: '{old_role.upper()}' -> '{edit_role.upper()}'")
                                
                            if target_user and changes:
                                db.commit()
                                
                                changes_str = "\n".join(f"- {c}" for c in changes)
                                email_subject = "Your SmartBudget AI Account Profile Has Been Updated"
                                email_body = (
                                    f"Hello {target_user.full_name},\n\n"
                                    f"Your SmartBudget AI account profile details have been updated by the platform administrator.\n\n"
                                    f"The following changes were made:\n"
                                    f"{changes_str}\n\n"
                                    f"Reason/Purpose for change:\n"
                                    f"{edit_purpose}\n\n"
                                    f"You can log in and access the application here:\n"
                                    f"https://smart-budget.streamlit.app/\n\n"
                                    f"Regards,\n"
                                    f"SmartBudget AI Team"
                                )
                                
                                if old_email != target_user.email:
                                    send_email_notification(email_subject, email_body, to_email=old_email)
                                send_email_notification(email_subject, email_body, to_email=target_user.email)
                                
                                st.success(f"Successfully updated profile for user ID {edit_user_id} and notified the user!")
                                st.rerun()
                            elif target_user and not changes:
                                st.warning("No changes detected.")

        # ----------------------------------------------------
        # STATS TAB
        # ----------------------------------------------------
        with tab_stats:
            st.subheader("Platform Telemetry & Analytics")
            
            total_households = db.query(Household).count()
            total_users = db.query(User).count()
            total_inc_amount = db.query(Income).sum_amount = sum(i.amount for i in db.query(Income).all())
            total_exp_amount = sum(e.amount for e in db.query(Expense).all())
            
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            col_k1.metric("Total Households", total_households)
            col_k2.metric("Total Platform Users", total_users)
            col_k3.metric("Platform Total Income", f"${total_inc_amount:,.2f}")
            col_k4.metric("Platform Total Expenses", f"${total_exp_amount:,.2f}")
            
            # List Households
            st.write("")
            st.write("### Active Households Register")
            households = db.query(Household).all()
            h_rows = []
            for h in households:
                h_rows.append({
                    "ID": h.id,
                    "Name": h.name,
                    "Currency": h.currency,
                    "Budget Method": h.budget_method.upper(),
                    "Created At": h.created_at.strftime("%Y-%m-%d")
                })
            st.dataframe(pd.DataFrame(h_rows), width="stretch", hide_index=True)

        # ----------------------------------------------------
        # CATEGORIES TAB
        # ----------------------------------------------------
        with tab_cats:
            st.subheader("Manage System-wide Categories")
            
            # Add System Category
            new_cat_name = st.text_input("New System Category Name", placeholder="e.g. Vacation Extra")
            if st.button("Add Global Category", type="primary"):
                if not new_cat_name:
                    st.error("Please enter a category name.")
                else:
                    exists = db.query(ExpenseCategory).filter(
                        ExpenseCategory.is_system == True,
                        ExpenseCategory.name == new_cat_name
                    ).first()
                    if exists:
                        st.error("Category name already exists.")
                    else:
                        db.add(ExpenseCategory(name=new_cat_name, is_system=True))
                        db.commit()
                        st.success(f"Category '{new_cat_name}' added to global categories!")
                        st.rerun()
                        
            # List Global Categories
            st.write("")
            st.write("### System Categories List")
            system_cats = db.query(ExpenseCategory).filter(ExpenseCategory.is_system == True).all()
            for c in system_cats:
                st.write(f"- 🏷️ {c.name}")

        # ----------------------------------------------------
        # EMAIL LOGS TAB
        # ----------------------------------------------------
        with tab_emails:
            st.subheader("System Email Logs")
            st.write("Track the status of all automated emails sent by the platform:")
            
            emails = db.query(EmailLog).order_by(EmailLog.timestamp.desc()).all()
            if not emails:
                st.info("No email logs found.")
            else:
                email_rows = []
                for e in emails:
                    email_rows.append({
                        "ID": e.id,
                        "Timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "Recipient": e.recipient,
                        "Subject": e.subject,
                        "Status": e.status,
                        "Content Snippet": e.body[:100] + "..." if len(e.body) > 100 else e.body
                    })
                st.dataframe(pd.DataFrame(email_rows), width="stretch", hide_index=True)

        # ----------------------------------------------------
        # GLOBAL SYSTEM LOGS TAB
        # ----------------------------------------------------
        with tab_sys_audit:
            st.subheader("Global Security Audit Stream")
            
            global_logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100).all()
            
            if not global_logs:
                st.info("No audit logs found.")
            else:
                g_log_rows = []
                for l in global_logs:
                    g_log_rows.append({
                        "ID": l.id,
                        "Timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "User": l.user.email if l.user else "Anonymous/Failed Login",
                        "Action": l.action,
                        "Details": l.details or ""
                    })
                st.dataframe(pd.DataFrame(g_log_rows), width="stretch", hide_index=True)
                
                # Clear Logs button
                if st.button("Clear System Audit Logs", type="secondary"):
                    db.query(AuditLog).delete()
                    db.commit()
                    st.success("Audit logs cleared successfully!")
                    st.rerun()
