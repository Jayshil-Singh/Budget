import streamlit as st
import pandas as pd
from database import get_db
from models.household import HouseholdMember
from models.auth import User
from models.audit import AuditLog, Notification
from services.auth_service import invite_member_to_household
from services.household_service import update_member_role, remove_household_member
from utils.helpers import format_date, get_role_label
from utils.ux import toast_success, confirm_button

def show_collaboration(household_id: int | None):
    """
    Renders the Household Collaboration, Notifications, and Audit Log logs.
    """
    st.markdown("<h1 class='app-title'>Household Collaboration</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Manage family members, view active audit logs, and notification feeds</p>", unsafe_allow_html=True)

    if household_id is None:
        st.warning(
            "You are not linked to a household yet. Complete the **onboarding wizard** "
            "to create one, or ask a household owner to invite your email address."
        )
        st.info(
            "If you were invited, ensure you log in with the same email address "
            "the invitation was sent to, then refresh this page."
        )
        return

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
                    st.caption(
                        "New members receive an email with a temporary password. "
                        "They must set a new password on first login."
                    )
                    with st.form("invite_member_form"):
                        inv_email = st.text_input("Member email").strip()
                        inv_role = st.selectbox(
                            "Access level",
                            ["partner", "viewer"],
                            format_func=lambda r: get_role_label(r),
                        )
                        submit_inv = st.form_submit_button("Send invite", type="primary")
                        if submit_inv:
                            if not inv_email or "@" not in inv_email:
                                st.error("Enter a valid email address.")
                            else:
                                member, temp_pwd = invite_member_to_household(
                                    db, household_id, inv_email, inv_role, st.session_state["user_id"],
                                )
                                if member:
                                    if temp_pwd:
                                        toast_success(f"Invite sent to {inv_email}")
                                        st.info(
                                            "If email delivery is not configured, share the temporary "
                                            "password from server logs with the invitee."
                                        )
                                    else:
                                        toast_success(f"{inv_email} added to your household")
                                    st.rerun()
                                else:
                                    st.error("Could not invite member. Check permissions and email.")
                                
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

            if role == "owner":
                st.subheader("Manage members")
                for m in members:
                    user = db.query(User).filter(User.id == m.user_id).first()
                    if not user or m.role == "owner":
                        continue
                    mc1, mc2, mc3 = st.columns([3, 2, 1])
                    with mc1:
                        st.write(f"**{user.full_name}** ({user.email})")
                    with mc2:
                        new_role = st.selectbox(
                            "Role", ["partner", "viewer"],
                            index=0 if m.role == "partner" else 1,
                            key=f"mem_role_{m.user_id}",
                            format_func=get_role_label,
                        )
                        if new_role != m.role and st.button("Update role", key=f"role_up_{m.user_id}"):
                            if update_member_role(db, household_id, m.user_id, new_role, st.session_state["user_id"]):
                                toast_success("Role updated")
                                st.rerun()
                    with mc3:
                        if confirm_button(
                            f"rm_mem_{m.user_id}", "Remove", "remove",
                            f"Remove **{user.full_name}** from this household?",
                        ):
                            if remove_household_member(db, household_id, m.user_id, st.session_state["user_id"]):
                                toast_success("Member removed")
                                st.rerun()

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
                        if not n.is_read and st.button("Mark read", key=f"collab_read_{n.id}"):
                            from services.notification_service import mark_notification_read
                            mark_notification_read(db, n.id)
                            st.rerun()

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
