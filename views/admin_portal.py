import streamlit as st
import pandas as pd
from database import get_db
from models.auth import User
from models.household import Household
from models.finance import Income, Expense, ExpenseCategory
from models.audit import AuditLog
from services.auth_service import create_new_user, disable_user, reset_user_password
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
        
    tab_users, tab_stats, tab_cats, tab_sys_audit = st.tabs([
        "👤 User Management", "📈 Platform Stats", "🏷️ Custom Categories", "📜 Global System Logs"
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
                            res = create_new_user(db, new_email, new_pwd, new_name, new_role)
                            if res:
                                st.success(f"Registered user {new_name} as {new_role.upper()} successfully!")
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
                
            if st.button("Apply Account Action", type="secondary"):
                target_user = db.query(User).filter(User.id == target_user_id).first()
                if target_user:
                    if action == "Disable/Deactivate Account":
                        target_user.is_active = False
                        st.success("Account deactivated!")
                    elif action == "Enable/Reactivate Account":
                        target_user.is_active = True
                        st.success("Account activated!")
                    elif action == "Force Reset Password":
                        if reset_pwd_val:
                            reset_user_password(db, target_user.id, reset_pwd_val, admin_user_id)
                            st.success("Password updated!")
                        else:
                            st.error("Please provide the reset password value.")
                    db.commit()
                    st.rerun()
                else:
                    st.error("User ID not found.")

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
