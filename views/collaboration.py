import streamlit as st
import pandas as pd
from database import get_db
from models.household import HouseholdMember
from models.auth import User
from models.audit import AuditLog, Notification
from services.auth_service import invite_member_to_household
from utils.helpers import format_date

def show_collaboration(household_id: int):
    """
    Renders the Household Collaboration, Notifications, and Audit Log logs.
    """
    st.markdown("<h1 class='app-title'>Household Collaboration</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Manage family members, view active audit logs, and notification feeds</p>", unsafe_allow_html=True)
    
    tab_mem, tab_notif, tab_audit = st.tabs(["👥 Family Members", "🔔 Notification Feed", "📜 Activity Logs"])
    
    with get_db() as db:
        # ----------------------------------------------------
        # MEMBERS TAB
        # ----------------------------------------------------
        with tab_mem:
            # 1. Invite Form
            role = st.session_state.get("user_role", "viewer")
            if role in ["owner", "partner"]:
                with st.expander("➕ Invite Family Member", expanded=False):
                    with st.form("invite_member_form"):
                        inv_email = st.text_input("Member Email Address").strip()
                        inv_role = st.selectbox("Role Permission", ["partner", "viewer"])
                        
                        submit_inv = st.form_submit_button("Invite Member", type="primary")
                        if submit_inv:
                            res = invite_member_to_household(
                                db, household_id, inv_email, inv_role, st.session_state["user_id"]
                            )
                            if res:
                                st.success("Member added to household successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to add member. Ensure user exists first or contact administrator.")
                                
            # 2. List Members
            st.subheader("Current Household Members")
            members = db.query(HouseholdMember).filter(HouseholdMember.household_id == household_id).all()
            
            mem_rows = []
            for m in members:
                user = db.query(User).filter(User.id == m.user_id).first()
                if user:
                    mem_rows.append({
                        "Name": user.full_name,
                        "Email": user.email,
                        "Household Role": m.role.upper(),
                        "Joined Date": format_date(m.joined_at)
                    })
                    
            st.dataframe(pd.DataFrame(mem_rows), width="stretch", hide_index=True)

        # ----------------------------------------------------
        # NOTIFICATION FEED TAB
        # ----------------------------------------------------
        with tab_notif:
            st.subheader("Recent Notifications")
            notifs = db.query(Notification).filter(
                Notification.household_id == household_id
            ).order_by(Notification.sent_at.desc()).all()
            
            if not notifs:
                st.info("No notifications logged yet.")
            else:
                for n in notifs:
                    # Determine styling color by type
                    style = "good"
                    if n.type == "warning" or n.type == "alert":
                        style = "critical"
                    elif n.type == "success":
                        style = "exceptional"
                        
                    with st.container(border=True):
                        st.markdown(f"**{n.title}** <span class='status-pill {style}'>{n.type}</span>", unsafe_allow_html=True)
                        st.write(n.message)
                        st.caption(f"Sent: {n.sent_at.strftime('%Y-%m-%d %H:%M')} via {n.channel.upper()}")

        # ----------------------------------------------------
        # AUDIT LOG TAB
        # ----------------------------------------------------
        with tab_audit:
            st.subheader("Recent Household Activity Logs")
            
            # Load audit logs related to members of this household
            member_ids = [m.user_id for m in members]
            logs = db.query(AuditLog).filter(
                AuditLog.user_id.in_(member_ids)
            ).order_by(AuditLog.timestamp.desc()).limit(30).all()
            
            if not logs:
                st.info("No activity logs recorded.")
            else:
                log_rows = []
                for l in logs:
                    log_rows.append({
                        "Timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "User": l.user.full_name if l.user else "System",
                        "Action": l.action,
                        "Details": l.details or ""
                    })
                st.dataframe(pd.DataFrame(log_rows), width="stretch", hide_index=True)
                
                # Download audit CSV option
                csv_data = pd.DataFrame(log_rows).to_csv(index=False)
                st.download_button(
                    label="📥 Export Activity Log CSV",
                    data=csv_data,
                    file_name=f"audit_log_{household_id}.csv",
                    mime="text/csv"
                )
