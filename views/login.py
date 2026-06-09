import streamlit as st
from database import get_db
from services.auth_service import authenticate_user, reset_user_password
from models.auth import User

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
                            st.session_state["logged_in"] = True
                            st.session_state["user_id"] = user.id
                            st.session_state["user_email"] = user.email
                            st.session_state["user_name"] = user.full_name
                            st.session_state["user_role"] = user.role # admin, owner, partner, viewer
                            
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
                            try:
                                s_record = create_user_session(db, user.id, ip_address=ip_address, user_agent=user_agent)
                                st.session_state["session_token"] = s_record.session_token
                            except Exception as e:
                                print(f"[SESSION CREATE ERROR] {e}")
                                
                            st.success(f"Welcome back, {user.full_name}!")
                            st.rerun()
                        else:
                            st.error("Invalid email, password, or account is disabled.")
                            
            if forgot_pwd_clicked:
                st.session_state["show_reset_view"] = True
                st.rerun()

def show_password_reset_page():
    """
    Renders the password reset view.
    """
    st.markdown("<h2 class='app-title' style='text-align: center;'>Reset Password</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.container(border=True):
            st.write("For security reasons, please contact your Platform Administrator to reset your password.")
            st.info("If you are testing the platform locally, you can use the Administrator account to reset any password via the Admin Portal.")
            
            email = st.text_input("Verify Your Email Address").strip()
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                if st.button("Request Reset", type="primary", width="stretch"):
                    if new_password != confirm_password:
                        st.error("Passwords do not match.")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        with get_db() as db:
                            user = db.query(User).filter(User.email == email.lower()).first()
                            if user:
                                reset_user_password(db, user.id, new_password, user.id)
                                st.success("Password updated successfully! Please log in.")
                                st.session_state["show_reset_view"] = False
                                st.rerun()
                            else:
                                st.error("Email not found in our database.")
                                
            with col_r2:
                if st.button("Back to Login", width="stretch"):
                    st.session_state["show_reset_view"] = False
                    st.rerun()
