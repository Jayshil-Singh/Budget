"""Shared UX helpers: tours, confirmations, empty states, toasts."""
import json
import time
import streamlit as st
from models.household import Setting


def toast_success(message: str):
    """Non-blocking success feedback."""
    try:
        st.toast(message, icon="✅")
    except Exception:
        st.success(message)


def render_empty_state(icon: str, title: str, message: str, button_label: str = None, button_key: str = None):
    st.markdown(f"### {icon} {title}")
    st.caption(message)
    if button_label and button_key:
        return st.button(button_label, type="primary", key=button_key)
    return False


def confirm_button(key: str, label: str, confirm_label: str, message: str) -> bool:
    """
    Two-step delete/action. Returns True when user confirmed on second click.
  """
    pending_key = f"_confirm_pending_{key}"
    if st.session_state.get(pending_key):
        st.warning(message)
        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"Yes, {confirm_label}", key=f"_yes_{key}", type="primary"):
                del st.session_state[pending_key]
                return True
        with c2:
            if st.button("Cancel", key=f"_no_{key}"):
                del st.session_state[pending_key]
                st.rerun()
        return False
    if st.button(label, key=f"_btn_{key}"):
        st.session_state[pending_key] = True
        st.rerun()
    return False


def get_tour_seen(db, household_id: int, screen: str) -> bool:
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == "ui_tour_seen",
    ).first()
    if not row:
        return False
    try:
        data = json.loads(row.value)
        return bool(data.get(screen, False))
    except Exception:
        return False


def mark_tour_seen(db, household_id: int, screen: str):
    row = db.query(Setting).filter(
        Setting.household_id == household_id,
        Setting.key == "ui_tour_seen",
    ).first()
    data = json.loads(row.value) if row else {}
    data[screen] = True
    if row:
        row.value = json.dumps(data)
    else:
        db.add(Setting(household_id=household_id, key="ui_tour_seen", value=json.dumps(data)))
    db.commit()


def render_screen_tour(db, household_id: int, screen: str, tips: list[str]):
    if get_tour_seen(db, household_id, screen):
        return
    with st.container(border=True):
        st.markdown("**👋 Quick tips**")
        for tip in tips:
            st.markdown(f"- {tip}")
        if st.button("Got it", key=f"tour_dismiss_{screen}"):
            mark_tour_seen(db, household_id, screen)
            st.rerun()


def store_undo(household_id: int, tx_type: str, tx_id: int):
    st.session_state["undo_tx"] = {
        "household_id": household_id,
        "type": tx_type,
        "id": tx_id,
        "expires": time.time() + 30,
    }


def render_undo_bar(db, household_id: int):
    undo = st.session_state.get("undo_tx")
    if not undo or undo.get("household_id") != household_id:
        return
    if time.time() > undo.get("expires", 0):
        del st.session_state["undo_tx"]
        return
    if st.button("↩️ Undo last entry", key="undo_last_tx"):
        from models.finance import Expense, Income
        if undo["type"] == "expense":
            row = db.query(Expense).filter(
                Expense.id == undo["id"], Expense.household_id == household_id
            ).first()
        else:
            row = db.query(Income).filter(
                Income.id == undo["id"], Income.household_id == household_id
            ).first()
        if row:
            db.delete(row)
            db.commit()
            toast_success("Undone!")
        del st.session_state["undo_tx"]
        st.rerun()
