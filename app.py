import streamlit as st
from database import init_db, get_db
from models.household import HouseholdMember
from utils.styles import inject_custom_css
from views.login import show_login_page, show_password_reset_page
from views.onboarding import show_onboarding_wizard
from views.dashboard import show_dashboard
from views.calendar_view import show_calendar
from views.transaction_entry import show_transaction_ledger
from views.budgeting import show_budgeting
from views.savings_debt import show_savings_debt
from views.subscription_view import show_subscriptions
from views.bank_import import show_bank_import
from views.collaboration import show_collaboration
from views.ai_coach import show_ai_coach
from views.admin_portal import show_admin_portal
from views.profile import show_profile
from views.reports import show_reports


# Configure Streamlit page
st.set_page_config(
    page_title="SmartBudget AI",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database tables
init_db()

# Inject modern custom stylesheet
inject_custom_css()

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "show_reset_view" not in st.session_state:
    st.session_state["show_reset_view"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "household_id" not in st.session_state:
    st.session_state["household_id"] = None
if "real_admin_user_id" not in st.session_state:
    st.session_state["real_admin_user_id"] = None
if "session_token" not in st.session_state:
    st.session_state["session_token"] = None
    
# ----------------------------------------------------
# AUTHENTICATION ROUTER
# ----------------------------------------------------
if not st.session_state["logged_in"]:
    if st.session_state["show_reset_view"]:
        show_password_reset_page()
    else:
        show_login_page()
else:
    # Validate session token in DB if it exists
    token = st.session_state.get("session_token")
    is_valid = True
    if token:
        from utils.security import validate_user_session
        with get_db() as db:
            session = validate_user_session(db, token)
            if not session:
                is_valid = False
                
    if not is_valid:
        st.session_state["logged_in"] = False
        st.session_state["user_id"] = None
        st.session_state["user_name"] = None
        st.session_state["user_role"] = None
        st.session_state["household_id"] = None
        st.session_state["real_admin_user_id"] = None
        st.session_state["session_token"] = None
        st.error("Your session has been revoked or expired. Please log in again.")
        st.rerun()

    # Check household association
    user_id = st.session_state["user_id"]
    
    with get_db() as db:
        membership = db.query(HouseholdMember).filter(HouseholdMember.user_id == user_id).first()
        
        if membership:
            st.session_state["household_id"] = membership.household_id
            st.session_state["household_name"] = membership.household.name
            st.session_state["household_currency"] = membership.household.currency
            st.session_state["user_role"] = membership.role # Override user role with household specific permissions
            
            # Run recurring transaction auto-posting check
            from services.recurring_service import post_recurring_transactions
            try:
                post_recurring_transactions(db, membership.household_id)
            except Exception as e:
                print(f"[RECURRING POST ERROR]: {e}")

            # Run payment due dates email check
            from services.notification_service import check_due_date_email_notifications
            try:
                check_due_date_email_notifications(db, membership.household_id)
            except Exception as e:
                print(f"[DUE DATE NOTIFICATION ERROR]: {e}")


            # Proactive overdraft & burn-rate alert check
            from services.forecast_service import get_bill_overdraft_warnings
            from services.notification_service import create_notification
            from models.audit import Notification
            try:
                overdraft_warnings = get_bill_overdraft_warnings(db, membership.household_id)
                if overdraft_warnings:
                    w = overdraft_warnings[0]
                    warn_title = "⚠️ Cash Shortfall Predicted"
                    warn_msg = (
                        f"Your projected balance may drop to "
                        f"{membership.household.currency} {w['balance']:.2f} "
                        f"on {w['date'].strftime('%d %b %Y')}."
                    )
                    if w["events_that_day"]:
                        warn_msg += f" Upcoming charges: {w['events_that_day']}."
                    # Only create new notification if one doesn't already exist for today
                    today_str = __import__("datetime").date.today().isoformat()
                    duplicate = db.query(Notification).filter(
                        Notification.household_id == membership.household_id,
                        Notification.title == warn_title,
                        Notification.is_read == False
                    ).first()
                    if not duplicate:
                        create_notification(
                            db, membership.household_id,
                            warn_title, warn_msg,
                            msg_type="warning", channel="in_app"
                        )
            except Exception as e:
                print(f"[OVERDRAFT ALERT ERROR]: {e}")
        else:
            st.session_state["household_id"] = None
            
    # If no household found and not platform admin, redirect to onboarding wizard
    if st.session_state["household_id"] is None and st.session_state["user_role"] != "admin":
        show_onboarding_wizard()
    else:
        # User is authenticated and has household or is Admin
        # ----------------------------------------------------
        # SIDEBAR NAVIGATION
        # ----------------------------------------------------
        st.sidebar.markdown(f"### SmartBudget AI")
        
        # Ghost Mode Banner (Must be above user role)
        if st.session_state.get("real_admin_user_id") is not None:
            st.sidebar.error("🎭 **GHOST MODE ACTIVE**\n\nViewing as another user")
            if st.sidebar.button("🔴 Exit Ghost Mode", type="primary", use_container_width=True):
                real_admin_id = st.session_state["real_admin_user_id"]
                with get_db() as db:
                    from services.auth_service import log_audit
                    from models.auth import User
                    admin_user = db.query(User).filter(User.id == real_admin_id).first()
                    impersonated_user = db.query(User).filter(User.id == st.session_state["user_id"]).first()
                    log_audit(db, real_admin_id, "ADMIN_GHOST_MODE_EXIT", f"Admin {admin_user.full_name if admin_user else real_admin_id} exited impersonation of user {impersonated_user.email if impersonated_user else st.session_state['user_id']}")
                    
                    st.session_state["user_id"] = real_admin_id
                    st.session_state["real_admin_user_id"] = None
                    if admin_user:
                        st.session_state["user_email"] = admin_user.email
                        st.session_state["user_name"] = admin_user.full_name
                        st.session_state["user_role"] = admin_user.role
                    membership = db.query(HouseholdMember).filter(HouseholdMember.user_id == real_admin_id).first()
                    if membership:
                        st.session_state["household_id"] = membership.household_id
                        st.session_state["household_name"] = membership.household.name
                        st.session_state["household_currency"] = membership.household.currency
                        st.session_state["user_role"] = membership.role
                    else:
                        st.session_state["household_id"] = None
                        if "household_name" in st.session_state:
                            del st.session_state["household_name"]
                        if "household_currency" in st.session_state:
                            del st.session_state["household_currency"]
                st.success("Exited Ghost Mode.")
                st.rerun()

        st.sidebar.markdown(f"👤 User: **{st.session_state.get('user_name', 'Member')}**")
        st.sidebar.markdown(f"🛡️ Role: **{st.session_state.get('user_role', 'viewer').upper()}**")
        if st.session_state.get("household_id"):
            st.sidebar.markdown(f"🏠 Hub: **{st.session_state.get('household_name')}**")
            
            # Sidebar notification bell query
            from models.audit import Notification
            with get_db() as db:
                unread_count = db.query(Notification).filter(
                    Notification.household_id == st.session_state["household_id"],
                    Notification.is_read == False
                ).count()
            if unread_count > 0:
                st.sidebar.markdown(f"🔔 **{unread_count} Unread Notifications**")
            else:
                st.sidebar.markdown("🔔 No new notifications")
        st.sidebar.markdown("---")
        
        # Build Navigation items
        nav_options = [
            "Dashboard", 
            "Financial Ledger", 
            "Budgets & Sinking Funds",
            "Savings & Debts", 
            "Subscriptions Tracker", 
            "Bank Import Portal", 
            "Reports & Export",
            "Collaboration & Invites",
            "Financial Calendar",
            "AI Budget Coach",
            "My Profile"
        ]
            
        if st.session_state["user_role"] == "admin" or st.session_state.get("real_admin_user_id") is not None:
            nav_options.append("Admin Portal")
            
        choice = st.sidebar.radio("Navigation Menu", nav_options)
        
        st.sidebar.markdown("---")
        if st.sidebar.button("Log Out", use_container_width=True, type="secondary"):
            token = st.session_state.get("session_token")
            if token:
                from utils.security import destroy_user_session
                with get_db() as db:
                    destroy_user_session(db, token)
                    
            st.session_state["logged_in"] = False
            st.session_state["user_id"] = None
            st.session_state["user_name"] = None
            st.session_state["user_role"] = None
            st.session_state["household_id"] = None
            st.session_state["real_admin_user_id"] = None
            st.session_state["session_token"] = None
            st.success("Logged out successfully.")
            st.rerun()
            
        # Dispatch to view
        household_id = st.session_state["household_id"]
        
        # Display system banner if active
        try:
            import json
            import os
            if os.path.exists("system_banner.json"):
                with open("system_banner.json", "r") as f:
                    banner = json.load(f)
                if banner.get("active") and banner.get("text"):
                    b_type = banner.get("type", "info")
                    b_text = banner.get("text")
                    if b_type == "info":
                        st.info(b_text)
                    elif b_type == "warning":
                        st.warning(b_text)
                    elif b_type == "error":
                        st.error(b_text)
                    elif b_type == "success":
                        st.success(b_text)
        except Exception as e:
            print(f"[SYSTEM BANNER ERROR]: {e}")
            
        if choice == "Dashboard":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To view the Dashboard, please join or create a household first via Collaboration & Invites or profile configuration.")
            else:
                show_dashboard(household_id)
        elif choice == "Financial Ledger":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To view the Ledger, please join or create a household first.")
            else:
                show_transaction_ledger(household_id)
        elif choice == "Budgets & Sinking Funds":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To view Budgets, please join or create a household first.")
            else:
                show_budgeting(household_id)
        elif choice == "Savings & Debts":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To view Savings & Debts, please join or create a household first.")
            else:
                show_savings_debt(household_id)
        elif choice == "Subscriptions Tracker":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To track Subscriptions, please join or create a household first.")
            else:
                show_subscriptions(household_id)
        elif choice == "Bank Import Portal":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To import bank statements, please join or create a household first.")
            else:
                show_bank_import(household_id)
        elif choice == "Reports & Export":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To view Reports, please join or create a household first.")
            else:
                show_reports(household_id)
        elif choice == "Collaboration & Invites":
            if not household_id:
                st.warning("⚠️ **No Active Household**: Please enter a household context first.")
                # We can still allow collaboration / invitations view or profile configuration to associate a household
                show_collaboration(household_id)
            else:
                show_collaboration(household_id)
        elif choice == "Financial Calendar":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To view the Financial Calendar, please join or create a household first.")
            else:
                show_calendar(household_id)
        elif choice == "AI Budget Coach":
            if not household_id:
                st.warning("⚠️ **No Active Household**: To talk with the AI Coach, please join or create a household first.")
            else:
                show_ai_coach(household_id)
        elif choice == "My Profile":
            show_profile(st.session_state["user_id"])
        elif choice == "Admin Portal":
            if st.session_state.get("real_admin_user_id") is not None:
                # Auto-exit Ghost Mode
                real_admin_id = st.session_state["real_admin_user_id"]
                with get_db() as db:
                    from services.auth_service import log_audit
                    from models.auth import User
                    admin_user = db.query(User).filter(User.id == real_admin_id).first()
                    impersonated_user = db.query(User).filter(User.id == st.session_state["user_id"]).first()
                    log_audit(db, real_admin_id, "ADMIN_GHOST_MODE_EXIT", f"Admin {admin_user.full_name if admin_user else real_admin_id} exited impersonation of user {impersonated_user.email if impersonated_user else st.session_state['user_id']}")
                    
                    st.session_state["user_id"] = real_admin_id
                    st.session_state["real_admin_user_id"] = None
                    if admin_user:
                        st.session_state["user_email"] = admin_user.email
                        st.session_state["user_name"] = admin_user.full_name
                        st.session_state["user_role"] = admin_user.role
                    membership = db.query(HouseholdMember).filter(HouseholdMember.user_id == real_admin_id).first()
                    if membership:
                        st.session_state["household_id"] = membership.household_id
                        st.session_state["household_name"] = membership.household.name
                        st.session_state["household_currency"] = membership.household.currency
                        st.session_state["user_role"] = membership.role
                    else:
                        st.session_state["household_id"] = None
                        if "household_name" in st.session_state:
                            del st.session_state["household_name"]
                        if "household_currency" in st.session_state:
                            del st.session_state["household_currency"]
                st.info("Exited Ghost Mode to access Admin Portal.")
                st.rerun()
            else:
                show_admin_portal(st.session_state["user_id"])
