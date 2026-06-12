import streamlit as st
from database import get_db
from services.auth_service import authenticate_user

def show_login_page():
    """
    Renders the secure login interface for SmartBudget AI.
    """
    st.markdown("<div style='text-align: center; margin-bottom: 2rem;'>", unsafe_allow_html=True)
    st.markdown("<h1 class='app-title' style='text-align: center;'>SmartBudget AI</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle' style='text-align: center;'>Your Household Financial Command Center</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.container(border=True):
            st.subheader("Sign In")
            
            email = st.text_input("Email Address", placeholder="name@household.com").strip()
            password = st.text_input("Password", type="password", placeholder="••••••••")
            
            remember_me = st.checkbox("Remember Me")
            
            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                login_clicked = st.button("Log In", width="stretch", type="primary")
            with col_btn2:
                forgot_pwd_clicked = st.button("Forgot Password?", width="stretch")
                
            if login_clicked:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    with get_db() as db:
                        user = authenticate_user(db, email, password)
                        if user:
                            # Resolve user IP and agent
                            try:
                                headers = st.context.headers
                                ip_address = headers.get("x-forwarded-for", "127.0.0.1")
                                user_agent = headers.get("user-agent", "Unknown")
                            except Exception:
                                try:
                                    from streamlit.web.server.websocket_headers import _get_websocket_headers
                                    headers = _get_websocket_headers()
                                    ip_address = headers.get("X-Forwarded-For", "127.0.0.1")
                                    user_agent = headers.get("User-Agent", "Unknown")
                                except Exception:
                                    ip_address = "127.0.0.1"
                                    user_agent = "Unknown"

                            if user_agent and len(user_agent) > 200:
                                user_agent = user_agent[:197] + "..."

                            from utils.security import create_user_session
                            session_days = 30 if remember_me else 1
                            try:
                                s_record = create_user_session(
                                    db, user.id,
                                    ip_address=ip_address,
                                    user_agent=user_agent,
                                    duration_days=session_days,
                                )
                            except Exception as e:
                                print(f"[SESSION CREATE ERROR] {e}")
                                st.error("Login failed: could not create a secure session. Please try again.")
                            else:
                                st.session_state["logged_in"] = True
                                st.session_state["user_id"] = user.id
                                st.session_state["user_email"] = user.email
                                st.session_state["user_name"] = user.full_name
                                st.session_state["user_role"] = user.role
                                st.session_state["system_role"] = user.role
                                st.session_state["session_token"] = s_record.session_token
                                st.session_state["ui_theme"] = getattr(user, "ui_theme", None) or "system"
                                st.session_state["_theme_synced"] = True
                                st.success(f"Welcome back, {user.full_name}!")
                                st.rerun()
                        else:
                            st.error("Invalid email, password, or account is disabled.")
                            
            if forgot_pwd_clicked:
                st.session_state["show_reset_view"] = True
                st.rerun()

def show_password_reset_page():
    """
    Renders the password reset view. Self-service reset is disabled;
    users must contact a platform administrator.
    """
    st.markdown("<h2 class='app-title' style='text-align: center;'>Reset Password</h2>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        with st.container(border=True):
            st.write(
                "For security reasons, password resets must be performed by a "
                "**Platform Administrator**."
            )
            st.info(
                "Please contact your administrator and provide the email address "
                "registered to your account. They can reset your password via "
                "**Admin Portal → User Management**."
            )
            st.caption(
                "If you are testing locally, log in as `admin@smartbudget.local` "
                "and use **Force Reset Password** in the Admin Portal."
            )

            if st.button("Back to Login", type="primary", width="stretch"):
                st.session_state["show_reset_view"] = False
                st.rerun()
