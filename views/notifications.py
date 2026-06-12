"""Dedicated notifications page — list all alerts and view full details."""
import streamlit as st
from database import get_db
from models.audit import Notification
from services.notification_service import mark_notification_read
from services.due_reminder_service import acknowledge_payment_reminder, parse_reminder_due_date
from utils.ux import toast_success


def _type_style(msg_type: str) -> str:
    if msg_type in ("warning", "alert"):
        return "critical"
    if msg_type == "success":
        return "exceptional"
    return "good"


def _render_detail(db, household_id: int, notification: Notification):
    style = _type_style(notification.type)
    read_label = "Read" if notification.is_read else "Unread"
    read_style = "good" if notification.is_read else "critical"

    st.markdown(
        f"<span class='status-pill {style}'>{notification.type}</span> "
        f"<span class='status-pill {read_style}'>{read_label}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"### {notification.title}")
    st.caption(
        f"Sent {notification.sent_at.strftime('%A, %d %b %Y at %H:%M')} · "
        f"via {notification.channel.replace('_', ' ')}"
    )

    st.markdown("#### Message")
    st.text(notification.message)

    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        if not notification.is_read and st.button("Mark as read", key="notif_detail_read", type="primary"):
            mark_notification_read(db, notification.id)
            toast_success("Notification marked as read.")
            st.rerun()
    with ac2:
        if notification.title.startswith("📅 Payment reminder"):
            if st.button(
                "Stop reminders",
                key="notif_detail_stop",
                help="I've updated my bills — stop hourly emails for this due date",
            ):
                due_d = parse_reminder_due_date(notification.title)
                if due_d:
                    acknowledge_payment_reminder(db, household_id, due_d)
                mark_notification_read(db, notification.id)
                toast_success("Reminders stopped for this due date.")
                st.rerun()
    with ac3:
        if st.button("← Back to all", key="notif_detail_back"):
            st.session_state["notif_selected_id"] = None
            st.rerun()


def show_notifications(household_id: int):
    if "notif_selected_id" not in st.session_state:
        st.session_state["notif_selected_id"] = None

    with get_db() as db:
        st.markdown("<h1 class='app-title'>Notifications</h1>", unsafe_allow_html=True)
        st.markdown(
            "<p class='app-subtitle'>All household alerts, bill reminders, and system updates</p>",
            unsafe_allow_html=True,
        )

        unread_count = db.query(Notification).filter(
            Notification.household_id == household_id,
            Notification.is_read == False,
        ).count()

        selected_id = st.session_state.get("notif_selected_id")
        if selected_id:
            selected = db.query(Notification).filter(
                Notification.id == selected_id,
                Notification.household_id == household_id,
            ).first()
            if not selected:
                st.session_state["notif_selected_id"] = None
                st.rerun()
            _render_detail(db, household_id, selected)
            return

        hc1, hc2, hc3 = st.columns([2, 2, 2])
        with hc1:
            st.metric("Unread", unread_count)
        with hc2:
            total = db.query(Notification).filter(
                Notification.household_id == household_id,
            ).count()
            st.metric("Total", total)
        with hc3:
            if unread_count and st.button("Mark all as read", key="notif_mark_all", width="stretch"):
                pending = db.query(Notification).filter(
                    Notification.household_id == household_id,
                    Notification.is_read == False,
                ).all()
                for n in pending:
                    mark_notification_read(db, n.id)
                toast_success("All notifications marked as read.")
                st.rerun()

        st.write("")
        show_filter = st.radio("Show", ["All", "Unread only"], horizontal=True, key="notif_filter")

        query = db.query(Notification).filter(Notification.household_id == household_id)
        if show_filter == "Unread only":
            query = query.filter(Notification.is_read == False)
        notifs = query.order_by(Notification.sent_at.desc()).all()

        if not notifs:
            st.info("No notifications yet. Bill reminders and budget alerts will appear here.")
            return

        for n in notifs:
            style = _type_style(n.type)
            preview = n.message.replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:120] + "…"

            with st.container(border=True):
                row1, row2 = st.columns([5, 1])
                with row1:
                    unread_dot = "🔵 " if not n.is_read else ""
                    st.markdown(
                        f"{unread_dot}**{n.title}** "
                        f"<span class='status-pill {style}'>{n.type}</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(preview)
                    st.caption(
                        f"{n.sent_at.strftime('%d %b %Y, %H:%M')} · "
                        f"{n.channel.replace('_', ' ')}"
                    )
                with row2:
                    if st.button("View details", key=f"notif_view_{n.id}", width="stretch"):
                        st.session_state["notif_selected_id"] = n.id
                        st.rerun()
