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
    
# ----------------------------------------------------
# AUTHENTICATION ROUTER
# ----------------------------------------------------
if not st.session_state["logged_in"]:
    if st.session_state["show_reset_view"]:
        show_password_reset_page()
    else:
        show_login_page()
else:
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
        nav_options = []
        if st.session_state["household_id"]:
            nav_options.extend([
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
            ])
            
        if st.session_state["user_role"] == "admin":
            nav_options.append("Admin Portal")
            
        choice = st.sidebar.radio("Navigation Menu", nav_options)
        
        st.sidebar.markdown("---")
        if st.sidebar.button("Log Out", use_container_width=True, type="secondary"):
            st.session_state["logged_in"] = False
            st.session_state["user_id"] = None
            st.session_state["user_name"] = None
            st.session_state["user_role"] = None
            st.session_state["household_id"] = None
            st.success("Logged out successfully.")
            st.rerun()
            
        # Dispatch to view
        household_id = st.session_state["household_id"]
        
        if choice == "Dashboard":
            show_dashboard(household_id)
        elif choice == "Financial Ledger":
            show_transaction_ledger(household_id)
        elif choice == "Budgets & Sinking Funds":
            show_budgeting(household_id)
        elif choice == "Savings & Debts":
            show_savings_debt(household_id)
        elif choice == "Subscriptions Tracker":
            show_subscriptions(household_id)
        elif choice == "Bank Import Portal":
            show_bank_import(household_id)
        elif choice == "Reports & Export":
            show_reports(household_id)
        elif choice == "Collaboration & Invites":
            show_collaboration(household_id)
        elif choice == "Financial Calendar":
            show_calendar(household_id)
        elif choice == "AI Budget Coach":
            show_ai_coach(household_id)
        elif choice == "My Profile":
            show_profile(st.session_state["user_id"])
        elif choice == "Admin Portal":
            show_admin_portal(st.session_state["user_id"])
