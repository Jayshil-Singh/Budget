import streamlit as st
import pandas as pd
import datetime
import os
import json
from database import get_db
from models.auth import User, Session as UserSession
from models.household import Household, HouseholdMember
from models.finance import Income, Expense, ExpenseCategory
from models.audit import AuditLog, EmailLog
from services.auth_service import create_new_user, disable_user, reset_user_password
from services.notification_service import send_email_notification
from config import EXPENSE_CATEGORIES

def show_admin_portal(admin_user_id: int, active_choice: str):
    """
    Renders the platform administration dashboard views based on sidebar choice.
    Exclusive to the 'admin' system role.
    """
    # Verify Admin Role
    if st.session_state.get("system_role") != "admin":
        st.error("Access Denied: You do not have permission to view the Admin Portal.")
        return
        
    ADMIN_SECTIONS = [
        "👤 User Management",
        "📈 Platform Stats",
        "🏷️ Custom Categories",
        "✉️ Email Logs",
        "📜 Global System Logs",
        "🛡️ Active Sessions",
        "📢 Broadcast & Alerts",
        "🗄️ Maintenance",
    ]
    if active_choice == "🛠️ Admin":
        st.markdown("<h1 class='app-title'>🛠️ Admin Portal</h1>", unsafe_allow_html=True)
        active_choice = st.selectbox("Admin section", ADMIN_SECTIONS)

    with get_db() as db:
        if active_choice == "👤 User Management":
            st.markdown("<h1 class='app-title'>👤 User Management</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>Manage global user accounts, deactivate accounts, and update permissions</p>", unsafe_allow_html=True)
            
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
                                    email_subject = "Your SmartBudget AI Account Has Been Created"
                                    email_body = (
                                        f"Hello {new_name},\n\n"
                                        f"An administrator has created a SmartBudget AI account for you.\n\n"
                                        f"Email: {new_email}\n\n"
                                        f"Your temporary password was set by the administrator. "
                                        f"Please log in and change it immediately via **My Profile → Change Password**.\n\n"
                                        f"For security, passwords are never sent by email. "
                                        f"Contact your administrator if you need your credentials resent in person.\n\n"
                                        f"You can access the application here:\n"
                                        f"https://smart-budget.streamlit.app/\n\n"
                                        f"Regards,\n"
                                        f"SmartBudget AI Team"
                                    )
                                    send_email_notification(email_subject, email_body, to_email=new_email)
                                    st.success(
                                        f"Registered user {new_name} as {new_role.upper()} successfully. "
                                        f"Share the temporary password with them securely (not via email)."
                                    )
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
            
            if st.button("Apply Account Action", type="secondary", width="stretch"):
                if not action_purpose.strip():
                    st.error("Please provide the purpose/reason of the action.")
                else:
                    target_user = db.query(User).filter(User.id == target_user_id).first()
                    if target_user:
                        if action == "Disable/Deactivate Account":
                            target_user.is_active = False
                            db.commit()
                            from services.auth_service import log_audit
                            log_audit(
                                db, admin_user_id, "USER_DISABLED",
                                f"Disabled user {target_user.email}. Reason: {action_purpose}"
                            )
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
                            from services.auth_service import log_audit
                            log_audit(
                                db, admin_user_id, "USER_REACTIVATED",
                                f"Reactivated user {target_user.email}. Reason: {action_purpose}"
                            )
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
                                        f"Reason/Purpose: {action_purpose}\n\n"
                                        f"Your new temporary password was communicated to you separately "
                                        f"by the administrator. Please log in at "
                                        f"https://smart-budget.streamlit.app/ and change it immediately "
                                        f"via **My Profile → Change Password**.\n\n"
                                        f"Regards,\n"
                                        f"SmartBudget AI Team"
                                    )
                                    send_email_notification(email_subject, email_body, to_email=target_user.email)
                                    st.success(
                                        "Password updated. Share the new password with the user "
                                        "through a secure channel (not email)."
                                    )
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
        # STATS VIEW
        # ----------------------------------------------------
        elif active_choice == "📈 Platform Stats":
            st.markdown("<h1 class='app-title'>📈 Platform Stats</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>Monitor platform activity, households statistics, and total financial values</p>", unsafe_allow_html=True)
            
            st.subheader("Platform Telemetry & Analytics")
            
            total_households = db.query(Household).count()
            total_users = db.query(User).count()
            total_inc_amount = sum(i.amount for i in db.query(Income).all())
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
        # CATEGORIES VIEW
        # ----------------------------------------------------
        elif active_choice == "🏷️ Custom Categories":
            st.markdown("<h1 class='app-title'>🏷️ Custom Categories</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>Create and manage global expense categories</p>", unsafe_allow_html=True)
            
            st.subheader("Manage System-wide Categories")
            
            # Add System Category
            new_cat_name = st.text_input("New System Category Name", placeholder="e.g. Vacation Extra")
            if st.button("Add Global Category", type="primary", width="stretch"):
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
        # EMAIL LOGS VIEW
        # ----------------------------------------------------
        elif active_choice == "✉️ Email Logs":
            st.markdown("<h1 class='app-title'>✉️ Email Logs</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>Review and track automated email notifications sent by the system</p>", unsafe_allow_html=True)
            
            st.subheader("System Email Logs")
            st.write("Search, filter, and export the automated emails sent by the platform:")
            
            # Filters in columns
            col_ef1, col_ef2, col_ef3 = st.columns(3)
            with col_ef1:
                email_search = st.text_input("Search Recipient Email", key="email_search_val").strip()
            with col_ef2:
                status_filter = st.selectbox("Filter Status", ["All", "Success", "Failed", "Simulated", "Pending"], key="email_status_filter")
            with col_ef3:
                # Date Range Input
                today_dt = datetime.date.today()
                start_dt = today_dt - datetime.timedelta(days=90)
                email_date_range = st.date_input("Date Range", value=(start_dt, today_dt), key="email_date_range")
                
            # Construct Query
            query = db.query(EmailLog)
            if email_search:
                query = query.filter(EmailLog.recipient.contains(email_search.lower()))
            if status_filter != "All":
                query = query.filter(EmailLog.status.contains(status_filter))
            if isinstance(email_date_range, tuple) and len(email_date_range) == 2:
                s_date, e_date = email_date_range
                s_dt = datetime.datetime.combine(s_date, datetime.time.min)
                e_dt = datetime.datetime.combine(e_date, datetime.time.max)
                query = query.filter(EmailLog.timestamp.between(s_dt, e_dt))
                
            emails = query.order_by(EmailLog.timestamp.desc()).all()
            
            if not emails:
                st.info("No matching email logs found.")
            else:
                email_rows = []
                for e in emails:
                    email_rows.append({
                        "ID": e.id,
                        "Timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "Recipient": e.recipient,
                        "Subject": e.subject,
                        "Status": e.status,
                        "Body": e.body
                    })
                df_emails = pd.DataFrame(email_rows)
                
                # We show content snippet but keep full body in df for export
                display_rows = []
                for e in emails:
                    display_rows.append({
                        "ID": e.id,
                        "Timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "Recipient": e.recipient,
                        "Subject": e.subject,
                        "Status": e.status,
                        "Content Snippet": e.body[:100] + "..." if len(e.body) > 100 else e.body
                    })
                st.dataframe(pd.DataFrame(display_rows), width="stretch", hide_index=True)
                
                # Export Buttons in column layout
                st.write("")
                col_eex1, col_eex2 = st.columns(2)
                with col_eex1:
                    csv_data = df_emails.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Export Filtered Emails to CSV",
                        data=csv_data,
                        file_name=f"email_logs_{datetime.date.today()}.csv",
                        mime="text/csv",
                        width="stretch"
                    )
                with col_eex2:
                    json_data = df_emails.to_json(orient="records", date_format="iso").encode('utf-8')
                    st.download_button(
                        label="📥 Export Filtered Emails to JSON",
                        data=json_data,
                        file_name=f"email_logs_{datetime.date.today()}.json",
                        mime="application/json",
                        width="stretch"
                    )

        # ----------------------------------------------------
        # GLOBAL SYSTEM LOGS VIEW
        # ----------------------------------------------------
        elif active_choice == "📜 Global System Logs":
            st.markdown("<h1 class='app-title'>📜 Global System Logs</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>Search and export security audit trails and log streams</p>", unsafe_allow_html=True)
            
            st.subheader("Global Security Audit Stream")
            st.write("Search, filter, and export administrative audit logs:")
            
            col_as1, col_as2, col_as3 = st.columns(3)
            with col_as1:
                action_filter = st.text_input("Filter Action Keyword (e.g. USER_LOGIN)", key="audit_action_val").strip()
            with col_as2:
                user_id_filter = st.number_input("Filter User ID (0 for all)", min_value=0, step=1, key="audit_uid_val")
            with col_as3:
                # Date Range Input
                today_dt = datetime.date.today()
                start_dt = today_dt - datetime.timedelta(days=90)
                audit_date_range = st.date_input("Date Range", value=(start_dt, today_dt), key="audit_date_range")
                
            query = db.query(AuditLog)
            if action_filter:
                query = query.filter(AuditLog.action.contains(action_filter.upper()))
            if user_id_filter > 0:
                query = query.filter(AuditLog.user_id == user_id_filter)
            if isinstance(audit_date_range, tuple) and len(audit_date_range) == 2:
                s_date, e_date = audit_date_range
                s_dt = datetime.datetime.combine(s_date, datetime.time.min)
                e_dt = datetime.datetime.combine(e_date, datetime.time.max)
                query = query.filter(AuditLog.timestamp.between(s_dt, e_dt))
                
            global_logs = query.order_by(AuditLog.timestamp.desc()).all()
            
            if not global_logs:
                st.info("No matching audit logs found.")
            else:
                g_log_rows = []
                for l in global_logs:
                    g_log_rows.append({
                        "ID": l.id,
                        "Timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "User ID": l.user_id or "System",
                        "User Email": l.user.email if l.user else "Anonymous/Failed Login",
                        "Action": l.action,
                        "Details": l.details or ""
                    })
                df_audit = pd.DataFrame(g_log_rows)
                st.dataframe(df_audit, width="stretch", hide_index=True)
                
                # Export and Clear Buttons
                st.write("")
                col_aud1, col_aud2 = st.columns(2)
                with col_aud1:
                    csv_data_aud = df_audit.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Export Filtered Audits to CSV",
                        data=csv_data_aud,
                        file_name=f"audit_logs_{datetime.date.today()}.csv",
                        mime="text/csv",
                        width="stretch"
                    )
                with col_aud2:
                    json_data_aud = df_audit.to_json(orient="records", date_format="iso").encode('utf-8')
                    st.download_button(
                        label="📥 Export Filtered Audits to JSON",
                        data=json_data_aud,
                        file_name=f"audit_logs_{datetime.date.today()}.json",
                        mime="application/json",
                        width="stretch"
                    )
                
                st.write("")
                if st.button("Clear System Audit Logs", type="secondary", width="stretch"):
                    db.query(AuditLog).delete()
                    db.commit()
                    st.success("Audit logs cleared successfully!")
                    st.rerun()

        # ----------------------------------------------------
        # ACTIVE SESSIONS VIEW
        # ----------------------------------------------------
        elif active_choice == "🛡️ Active Sessions":
            st.markdown("<h1 class='app-title'>🛡️ Active Sessions</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>View active database sessions, revoke sessions, or enter ghost mode impersonation</p>", unsafe_allow_html=True)
            
            st.subheader("🛡️ Active Sessions & Security Diagnostics")
            st.write("Live listing of active user database sessions. You can revoke any session to force-logout that user.")
            
            sessions = db.query(UserSession).order_by(UserSession.created_at.desc()).all()
            if not sessions:
                st.info("No active sessions found.")
            else:
                session_data = []
                for s in sessions:
                    is_active = s.expires_at > datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    session_data.append({
                        "Session ID": s.id,
                        "User Email": s.user.email if s.user else f"User ID {s.user_id}",
                        "IP Address": s.ip_address or "Unknown",
                        "User Agent": s.user_agent or "Unknown",
                        "Created At": s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "Expires At": s.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "Token Snippet": s.session_token[:8] + "...",
                        "Token": s.session_token,
                        "Status": "Active" if is_active else "Expired"
                    })
                df_sessions = pd.DataFrame(session_data)
                
                # Display subset of columns for readability
                display_cols = ["Session ID", "User Email", "IP Address", "Created At", "Expires At", "Token Snippet", "Status"]
                st.dataframe(df_sessions[display_cols], width="stretch", hide_index=True)
                
                # Revoke Section
                st.write("")
                col_rev1, col_rev2 = st.columns([2, 1])
                with col_rev1:
                    session_to_revoke_id = st.selectbox(
                        "Select Session to Revoke",
                        options=df_sessions["Session ID"].tolist(),
                        format_func=lambda sid: (
                            f"{df_sessions[df_sessions['Session ID']==sid]['User Email'].values[0]} "
                            f"({df_sessions[df_sessions['Session ID']==sid]['Token Snippet'].values[0]})"
                        )
                    )
                with col_rev2:
                    st.write("") # vertical offset
                    if st.button("🚫 Revoke Selected Session", type="primary", width="stretch"):
                        from utils.security import destroy_user_session
                        from services.auth_service import log_audit
                        rev_s = db.query(UserSession).filter(UserSession.id == session_to_revoke_id).first()
                        session_to_revoke_token = rev_s.session_token if rev_s else None
                        rev_email = rev_s.user.email if (rev_s and rev_s.user) else "Unknown"
                        
                        success = destroy_user_session(db, session_to_revoke_token) if session_to_revoke_token else False
                        if success:
                            log_audit(db, admin_user_id, "ADMIN_SESSION_REVOKED", f"Admin revoked session for user {rev_email}")
                            st.success(f"Session for user {rev_email} successfully revoked.")
                            st.rerun()
                        else:
                            st.error("Failed to revoke session.")
            
            # Impersonation Section
            st.write("---")
            st.subheader("👥 Session Impersonation ('Ghost Mode')")
            st.write("Temporarily view the household as a specific user to help troubleshoot. Impersonation of other admins is blocked for safety.")
            
            # Select user to impersonate
            users_list = db.query(User).all()
            user_opts = [u for u in users_list if u.id != admin_user_id]
            
            if not user_opts:
                st.info("No other users available for impersonation.")
            else:
                col_imp1, col_imp2 = st.columns([2, 1])
                with col_imp1:
                    target_imp_user = st.selectbox(
                        "Select User to Impersonate",
                        options=user_opts,
                        format_func=lambda u: f"{u.full_name} ({u.email}) - Role: {u.role.upper()}"
                    )
                with col_imp2:
                    st.write("") # spacing
                    if st.button("🎭 Start Impersonating", type="secondary", width="stretch"):
                        if target_imp_user.role == "admin":
                            st.error("Safety Guard: Impersonating other administrators is not allowed.")
                        else:
                            from services.auth_service import log_audit
                            log_audit(db, admin_user_id, "ADMIN_GHOST_MODE_ENTER", f"Admin entered impersonation of user {target_imp_user.email}")
                            
                            st.session_state["real_admin_user_id"] = admin_user_id
                            st.session_state["user_id"] = target_imp_user.id
                            st.session_state["user_email"] = target_imp_user.email
                            st.session_state["user_name"] = target_imp_user.full_name
                            st.session_state["user_role"] = target_imp_user.role
                            
                            st.success(f"Impersonating {target_imp_user.full_name}...")
                            st.rerun()

        # ----------------------------------------------------
        # BROADCAST & ALERTS VIEW
        # ----------------------------------------------------
        elif active_choice == "📢 Broadcast & Alerts":
            st.markdown("<h1 class='app-title'>📢 Broadcast & Alerts</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>Configure global warning banners and dispatch email broadcasts</p>", unsafe_allow_html=True)
            
            st.subheader("📢 Global System Broadcast Alerts & Banners")
            st.write("Configure a banner visible to all users at the top of every page of the application.")
            
            # Load current banner settings
            current_banner = {"text": "", "type": "info", "active": False}
            if os.path.exists("system_banner.json"):
                try:
                    with open("system_banner.json", "r") as f:
                        current_banner = json.load(f)
                except Exception:
                    pass
            
            with st.form("broadcast_banner_form"):
                banner_text = st.text_area("Banner Message Text", value=current_banner.get("text", ""), placeholder="e.g. System maintenance scheduled for Sunday at 2 AM.")
                banner_type = st.selectbox("Alert Style Level", ["info", "warning", "error", "success"], index=["info", "warning", "error", "success"].index(current_banner.get("type", "info")))
                banner_active = st.checkbox("Enable / Display Banner", value=current_banner.get("active", False))
                
                btn_save_banner = st.form_submit_button("Publish Global Banner", type="primary")
                if btn_save_banner:
                    try:
                        with open("system_banner.json", "w") as f:
                            json.dump({"text": banner_text, "type": banner_type, "active": banner_active}, f)
                        st.success("Global banner settings saved and published!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save banner settings: {e}")
                        
            st.write("---")
            st.subheader("✉️ Mass Broadcast Email Blast")
            st.write("Send an email notification to all active platform users. This uses the system email settings and logs audit footprints.")
            
            with st.form("broadcast_email_form"):
                email_subject = st.text_input("Email Subject Line", placeholder="e.g. Important SmartBudget Account Update")
                email_body = st.text_area("Email Content Body", placeholder="Write email message here...")
                
                btn_send_email = st.form_submit_button("🚀 Dispatch Broadcast Email to All Users", type="secondary")
                if btn_send_email:
                    if not email_subject or not email_body:
                        st.error("Please provide both subject and body message.")
                    else:
                        active_users = db.query(User).filter(User.is_active == True).all()
                        if not active_users:
                            st.warning("No active users found to email.")
                        else:
                            count = 0
                            for u in active_users:
                                success = send_email_notification(email_subject, email_body, to_email=u.email)
                                if success:
                                    count += 1
                            
                            from services.auth_service import log_audit
                            log_audit(db, admin_user_id, "ADMIN_EMAIL_BROADCAST", f"Admin sent broadcast email: '{email_subject}' to {count} users")
                            st.success(f"Successfully sent broadcast email to {count} active users!")

        # ----------------------------------------------------
        # MAINTENANCE VIEW
        # ----------------------------------------------------
        elif active_choice == "🗄️ Maintenance":
            st.markdown("<h1 class='app-title'>🗄️ Maintenance</h1>", unsafe_allow_html=True)
            st.markdown("<p class='app-subtitle'>Database backup downloads, index optimization vacuum, and storage log pruning</p>", unsafe_allow_html=True)
            
            st.subheader("🗄️ Database Backup, Vacuum & Log Pruning")
            st.write("Administrative utilities for system upkeep and diagnostic optimization.")
            
            # DB Backup Download
            st.write("### 1. Database Backup")
            st.write("Download the live SQLite database file. Useful for manual snapshots and offline testing.")
            try:
                import config
                db_file_path = config.DATABASE_URL.replace("sqlite:///", "")
                if os.path.exists(db_file_path):
                    with open(db_file_path, "rb") as f:
                        db_bytes = f.read()
                    st.download_button(
                        label="📥 Download Database Backup (sqlite)",
                        data=db_bytes,
                        file_name=f"smartbudget_backup_{datetime.date.today()}.db",
                        mime="application/x-sqlite3",
                        width="stretch"
                    )
                else:
                    st.error("Database file 'smartbudget.db' not found in root directory.")
            except Exception as e:
                st.error(f"Error reading database file: {e}")
                
            st.write("---")
            
            # SQL VACUUM
            st.write("### 2. Run Database Vacuum")
            st.write("Cleans unused database space, rebuilds the index, and reduces SQLite file size.")
            if st.button("🧹 Optimize & Run SQL VACUUM", type="primary", width="stretch"):
                try:
                    from database import engine
                    with engine.raw_connection() as raw_conn:
                        raw_conn.isolation_level = None
                        cursor = raw_conn.cursor()
                        cursor.execute("VACUUM")
                    
                    from services.auth_service import log_audit
                    log_audit(db, admin_user_id, "ADMIN_DB_VACUUM", "Admin executed SQL VACUUM on database")
                    st.success("SQL VACUUM executed successfully! Database defragmented.")
                except Exception as e:
                    st.error(f"Failed to run VACUUM command: {e}")
                    
            st.write("---")
            
            # Prune Logs
            st.write("### 3. Database Maintenance: Prune Logs")
            st.write("Bulk delete historical email and audit records to conserve storage space.")
            days_to_keep = st.number_input("Days of logs to keep", min_value=1, value=30, step=1)
            if st.button("🔥 Prune Historical Logs", type="secondary", width="stretch"):
                try:
                    prune_date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days_to_keep)
                    
                    # Log count before deletion
                    num_audits_deleted = db.query(AuditLog).filter(AuditLog.timestamp < prune_date).delete()
                    num_emails_deleted = db.query(EmailLog).filter(EmailLog.timestamp < prune_date).delete()
                    db.commit()
                    
                    from services.auth_service import log_audit
                    log_audit(db, admin_user_id, "ADMIN_LOGS_PRUNED", f"Admin pruned audit/email logs older than {days_to_keep} days. Deleted {num_audits_deleted} audit and {num_emails_deleted} email records.")
                    st.success(f"Logs successfully pruned! Deleted {num_audits_deleted} audit logs and {num_emails_deleted} email logs older than {days_to_keep} days.")
                except Exception as e:
                    st.error(f"Failed to prune logs: {e}")
