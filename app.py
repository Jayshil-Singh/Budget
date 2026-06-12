import streamlit as st

from database import init_db, get_db

from models.household import HouseholdMember

from utils.styles import inject_custom_css, init_theme_state, sync_theme_from_user, render_theme_toggle

from views.login import show_login_page, show_password_reset_page

from views.onboarding import show_onboarding_wizard

from views.dashboard import show_dashboard

from views.transaction_entry import show_transaction_ledger, show_income_setup, show_expense_setup

from views.budgeting import show_budgeting

from views.budget_setup import show_budget_setup

from views.bank_import import show_bank_import

from views.collaboration import show_collaboration

from views.ai_coach import show_ai_coach

from views.admin_portal import show_admin_portal

from views.profile import show_profile

from views.reports import show_reports

from views.plans_bills import show_plans_bills

from views.recurring_expenses import show_recurring_expenses

from views.income_schedule import show_income_schedule

from views.force_password_change import show_force_password_change

from views.notifications import show_notifications

from utils.navigation import NAV_SECTIONS, NAV_ITEMS, ADMIN_NAV

from utils.helpers import get_role_label





st.set_page_config(

    page_title="SmartBudget AI",

    page_icon="💰",

    layout="wide",

    initial_sidebar_state="expanded",

)



init_db()



init_theme_state()

if st.session_state.get("logged_in") and st.session_state.get("user_id"):

    sync_theme_from_user(st.session_state["user_id"])

inject_custom_css()



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

if "system_role" not in st.session_state:

    st.session_state["system_role"] = None

if "selected_household_id" not in st.session_state:

    st.session_state["selected_household_id"] = None



if not st.session_state["logged_in"]:

    if st.session_state["show_reset_view"]:

        show_password_reset_page()

    else:

        show_login_page()

    render_theme_toggle(use_sidebar=False)

else:

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

        st.session_state["system_role"] = None

        st.session_state["household_id"] = None

        st.session_state["selected_household_id"] = None

        st.session_state["real_admin_user_id"] = None

        st.session_state["session_token"] = None

        st.error("Your session has been revoked or expired. Please log in again.")

        st.rerun()



    user_id = st.session_state["user_id"]



    with get_db() as db:

        from models.auth import User

        user_record = db.query(User).filter(User.id == user_id).first()

        if user_record:

            st.session_state["system_role"] = user_record.role



        memberships = db.query(HouseholdMember).filter(

            HouseholdMember.user_id == user_id

        ).all()



        if memberships:

            st.session_state["household_memberships"] = [

                (m.household_id, m.household.name) for m in memberships

            ]

            selected_id = st.session_state.get("selected_household_id")

            membership = next(

                (m for m in memberships if m.household_id == selected_id),

                memberships[0],

            )

            st.session_state["selected_household_id"] = membership.household_id

            st.session_state["household_id"] = membership.household_id

            st.session_state["household_name"] = membership.household.name

            st.session_state["household_currency"] = membership.household.currency

            st.session_state["user_role"] = membership.role



            import datetime as _dt

            bg_key = f"bg_jobs_{membership.household_id}_{_dt.date.today().isoformat()}"

            if bg_key not in st.session_state:

                from services.recurring_service import post_recurring_transactions

                try:

                    post_recurring_transactions(db, membership.household_id)

                except Exception as e:

                    print(f"[RECURRING POST ERROR]: {e}")



                from services.notification_service import check_due_date_email_notifications

                try:

                    check_due_date_email_notifications(db, membership.household_id)

                except Exception as e:

                    print(f"[DUE DATE NOTIFICATION ERROR]: {e}")



                from services.budget_alert_service import check_budget_threshold_alerts

                try:

                    check_budget_threshold_alerts(db, membership.household_id)

                except Exception as e:

                    print(f"[BUDGET ALERT ERROR]: {e}")



                from services.goal_alert_service import check_goal_threshold_alerts

                try:

                    check_goal_threshold_alerts(db, membership.household_id)

                except Exception as e:

                    print(f"[GOAL ALERT ERROR]: {e}")



                try:

                    from services.forecast_service import get_bill_overdraft_warnings

                    from services.notification_service import create_notification

                    from models.audit import Notification

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

                        today_start = _dt.datetime.combine(_dt.date.today(), _dt.time.min)

                        duplicate = db.query(Notification).filter(

                            Notification.household_id == membership.household_id,

                            Notification.title == warn_title,

                            Notification.sent_at >= today_start,

                        ).first()

                        if not duplicate:

                            create_notification(

                                db, membership.household_id,

                                warn_title, warn_msg,

                                msg_type="warning", channel="in_app",

                            )

                except Exception as e:

                    print(f"[OVERDRAFT ALERT ERROR]: {e}")



                st.session_state[bg_key] = True

        else:

            st.session_state["household_id"] = None

            st.session_state["household_memberships"] = []



    must_change = False

    with get_db() as db:

        from models.auth import User

        u = db.query(User).filter(User.id == user_id).first()

        must_change = bool(u and u.must_change_password)



    if must_change:

        show_force_password_change(user_id)

    elif st.session_state["household_id"] is None and st.session_state.get("system_role") != "admin":

        show_onboarding_wizard()

    else:

        st.sidebar.markdown("### SmartBudget AI")



        if st.session_state.get("real_admin_user_id") is not None:

            st.sidebar.error("🎭 **GHOST MODE ACTIVE**\n\nViewing as another user")

            if st.sidebar.button("🔴 Exit Ghost Mode", type="primary", width="stretch"):

                real_admin_id = st.session_state["real_admin_user_id"]

                with get_db() as db:

                    from services.auth_service import log_audit

                    from models.auth import User

                    admin_user = db.query(User).filter(User.id == real_admin_id).first()

                    impersonated_user = db.query(User).filter(User.id == st.session_state["user_id"]).first()

                    log_audit(db, real_admin_id, "ADMIN_GHOST_MODE_EXIT", f"Admin exited impersonation of {impersonated_user.email if impersonated_user else st.session_state['user_id']}")

                    st.session_state["user_id"] = real_admin_id

                    st.session_state["real_admin_user_id"] = None

                    if admin_user:

                        st.session_state["user_email"] = admin_user.email

                        st.session_state["user_name"] = admin_user.full_name

                        st.session_state["system_role"] = admin_user.role

                        st.session_state["user_role"] = admin_user.role

                    membership = db.query(HouseholdMember).filter(HouseholdMember.user_id == real_admin_id).first()

                    if membership:

                        st.session_state["household_id"] = membership.household_id

                        st.session_state["household_name"] = membership.household.name

                        st.session_state["household_currency"] = membership.household.currency

                        st.session_state["user_role"] = membership.role

                        st.session_state["selected_household_id"] = membership.household_id

                    else:

                        st.session_state["household_id"] = None

                        st.session_state["selected_household_id"] = None

                st.success("Exited Ghost Mode.")

                st.rerun()



        st.sidebar.markdown(f"👤 User: **{st.session_state.get('user_name', 'Member')}**")

        household_role = st.session_state.get("user_role", "viewer")

        system_role = st.session_state.get("system_role")

        display_role = household_role if st.session_state.get("household_id") else (system_role or "viewer")

        st.sidebar.markdown(f"🛡️ Access: **{get_role_label(display_role)}**")



        if len(st.session_state.get("household_memberships", [])) > 1:

            hh_options = {name: hid for hid, name in st.session_state["household_memberships"]}

            current_name = st.session_state.get("household_name", "")

            names = list(hh_options.keys())

            picked = st.sidebar.selectbox(

                "🏠 Active Household",

                names,

                index=names.index(current_name) if current_name in names else 0,

            )

            if hh_options[picked] != st.session_state.get("selected_household_id"):

                st.session_state["selected_household_id"] = hh_options[picked]

                st.rerun()

        elif st.session_state.get("household_id"):

            st.sidebar.markdown(f"🏠 Hub: **{st.session_state.get('household_name')}**")

            from models.audit import Notification

            hid = st.session_state["household_id"]
            unread_count = 0
            with get_db() as db:
                unread_count = db.query(Notification).filter(
                    Notification.household_id == hid, Notification.is_read == False,
                ).count()

            bell_label = f"🔔 Notifications ({unread_count})" if unread_count else "🔔 Notifications"
            if st.sidebar.button(bell_label, key="sidebar_open_notifications", width="stretch"):
                st.session_state["nav_route"] = "notifications"
                st.session_state["notif_selected_id"] = None
                st.rerun()



        st.sidebar.markdown("---")



        for section_title, section_hint in NAV_SECTIONS:
            st.sidebar.markdown(f"**{section_title}**")
            st.sidebar.caption(section_hint)

        nav_labels = [label for label, _ in NAV_ITEMS]
        nav_routes = {label: key for label, key in NAV_ITEMS}

        if st.session_state.get("system_role") == "admin" or st.session_state.get("real_admin_user_id") is not None:
            nav_labels.append(ADMIN_NAV[0])
            nav_routes[ADMIN_NAV[0]] = ADMIN_NAV[1]

        pending_route = st.session_state.pop("nav_route", None)
        if pending_route:
            for label, key in NAV_ITEMS + ([ADMIN_NAV] if ADMIN_NAV[0] in nav_labels else []):
                if key == pending_route:
                    st.session_state["main_nav"] = label
                    break

        choice = st.sidebar.radio("Navigation Menu", nav_labels, key="main_nav")
        route = nav_routes.get(choice, "dashboard")



        st.sidebar.markdown("---")

        render_theme_toggle(persist_user_id=user_id, use_sidebar=True)

        st.sidebar.markdown("---")

        if st.sidebar.button("Log Out", width="stretch", type="secondary"):

            token = st.session_state.get("session_token")

            if token:

                from utils.security import destroy_user_session

                with get_db() as db:

                    destroy_user_session(db, token)

            st.session_state["logged_in"] = False

            st.session_state["user_id"] = None

            st.session_state["user_name"] = None

            st.session_state["user_role"] = None

            st.session_state["system_role"] = None

            st.session_state["household_id"] = None

            st.session_state["selected_household_id"] = None

            st.session_state["real_admin_user_id"] = None

            st.session_state["session_token"] = None

            st.success("Logged out successfully.")

            st.rerun()



        household_id = st.session_state["household_id"]



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



        def _need_household(view_name: str):

            st.warning(f"Join or create a household first to use {view_name}.")



        _ROUTES = {
            "dashboard": ("Dashboard", show_dashboard),
            "income_setup": ("Income Setup", show_income_setup),
            "pay_schedule": ("Pay Schedule", show_income_schedule),
            "budget_setup": ("Budget Setup", show_budget_setup),
            "expense_setup": ("Expense Setup", show_expense_setup),
            "recurring_bills": ("Recurring Bills", show_recurring_expenses),
            "budget_vs_actual": ("Budget vs Actual", lambda h: show_budgeting(h, page="vs_actual")),
            "sinking_funds": ("Sinking Funds", lambda h: show_budgeting(h, page="sinking")),
            "forecast": ("Forecast", lambda h: show_budgeting(h, page="forecast")),
            "notifications": ("Notifications", show_notifications),
            "plans_bills": ("Plans & Bills", show_plans_bills),
            "import_sms": ("Import & SMS", show_bank_import),
            "money_coach": ("Money Coach", show_ai_coach),
            "family": ("Family & Sharing", show_collaboration),
            "reports": ("Reports", show_reports),
            "profile": ("My Profile", None),
            "admin": ("Admin", None),
        }

        if route == "profile":
            show_profile(st.session_state["user_id"])
        elif route == "admin":
            if st.session_state.get("real_admin_user_id") is not None:
                st.info("Exit Ghost Mode to access Admin tools.")
            else:
                show_admin_portal(st.session_state["user_id"], "🛠️ Admin")
        elif route == "family":
            show_collaboration(household_id)
        elif route in _ROUTES:
            label, handler = _ROUTES[route]
            if household_id:
                handler(household_id)
            else:
                _need_household(label)


