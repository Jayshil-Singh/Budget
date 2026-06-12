import streamlit as st
import datetime
import pandas as pd
from database import get_db
from models.finance import Subscription, ExpenseCategory
from utils.helpers import format_currency, can_modify, can_delete
from services.mark_paid_service import mark_subscription_paid
from utils.ux import confirm_button, toast_success, render_empty_state

def show_subscriptions(household_id: int, embedded: bool = False):
    """
    Renders the Subscription Tracker panel.
    Calculates monthly/annual totals and enables subscription management.
    """
    if not embedded:
        st.markdown("<h1 class='app-title'>Subscriptions Tracker</h1>", unsafe_allow_html=True)
        st.markdown("<p class='app-subtitle'>Monitor software services, streaming plans, and renewals</p>", unsafe_allow_html=True)
    
    currency = st.session_state.get("household_currency", "FJD")
    
    with get_db() as db:
        # Load categories
        categories = db.query(ExpenseCategory).filter(
            (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
        ).all()
        cat_choices = {c.name: c.id for c in categories}
        
        role = st.session_state.get("user_role", "viewer")
        
        # 1. Add Subscription Form
        if not can_modify(role):
            st.info("View only — you cannot add subscriptions.")
        else:
            with st.expander("➕ Track New Subscription", expanded=False):
                with st.form("add_subscription_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        sub_name = st.text_input("Service Name", placeholder="e.g. Netflix Premium")
                        sub_amount = st.number_input("Billing Amount", min_value=1.0, value=15.0, step=5.0)
                        sub_freq = st.selectbox("Billing Cycle", ["Monthly", "Annual"])
                    with col2:
                        sub_renewal = st.date_input("Next Renewal Date", datetime.date.today() + datetime.timedelta(days=30))
                        sub_cat = st.selectbox("Assign Expense Category", list(cat_choices.keys()), 
                                               index=list(cat_choices.keys()).index("Subscriptions") if "Subscriptions" in cat_choices else 0)
                        sub_url = st.text_input("Cancellation Link (Optional)", placeholder="https://netflix.com/cancel")
                        
                    submit_sub = st.form_submit_button("Track Service", type="primary")
                    if submit_sub:
                        db.add(Subscription(
                            household_id=household_id,
                            name=sub_name,
                            amount=sub_amount,
                            frequency=sub_freq.lower(),
                            next_renewal=sub_renewal,
                            category_id=cat_choices[sub_cat],
                            service_url=sub_url,
                            status="active"
                        ))
                        db.commit()
                        st.success("Subscription saved!")
                        st.rerun()
                    
        # 2. Fetch active subs
        subs = db.query(Subscription).filter(Subscription.household_id == household_id).all()
        
        if not subs:
            render_empty_state(
                "📺", "No subscriptions yet",
                "Track Netflix, phone plans, and other recurring services above.",
            )
        else:
            # Calculations
            monthly_total = 0.0
            annual_total = 0.0
            
            for s in subs:
                if s.status == "active":
                    m_cost = s.amount if s.frequency == "monthly" else (s.amount / 12)
                    monthly_total += m_cost
                    annual_total += m_cost * 12
                    
            st.markdown("### Total Subscriptions Run Rate")
            col_m1, col_m2 = st.columns(2)
            col_m1.metric("Monthly Aggregate Cost", format_currency(monthly_total, currency))
            col_m2.metric("Annualized Cost", format_currency(annual_total, currency))
            
            st.markdown("---")
            
            # List details
            st.subheader("Your Subscriptions")
            sub_rows = []
            for s in subs:
                sub_rows.append({
                    "ID": s.id,
                    "Service": s.name,
                    "Amount": format_currency(s.amount, currency),
                    "Frequency": s.frequency.upper(),
                    "Next Renewal": s.next_renewal,
                    "Status": s.status.upper(),
                    "Cancellation Page": s.service_url or "None"
                })
                
            st.dataframe(pd.DataFrame(sub_rows), width="stretch", hide_index=True)

            if can_modify(role):
                st.subheader("Manage")
                for s in subs:
                    sc1, sc2, sc3, sc4, sc5 = st.columns([3, 1, 1, 1, 1])
                    with sc1:
                        st.write(f"**{s.name}** · {format_currency(s.amount, currency)} · renews {s.next_renewal}")
                        st.caption(s.status.upper())
                    with sc2:
                        if s.status == "active" and st.button("✅ Paid", key=f"sub_paid_{s.id}"):
                            if mark_subscription_paid(db, household_id, s):
                                toast_success(f"Logged {s.name} payment")
                            else:
                                st.info("Already logged.")
                            st.rerun()
                    with sc3:
                        if s.status != "active" and st.button("Resume", key=f"sub_resume_{s.id}"):
                            s.status = "active"
                            db.commit()
                            toast_success(f"{s.name} marked active")
                            st.rerun()
                    with sc4:
                        if s.status == "active" and st.button("Pause", key=f"sub_pause_{s.id}"):
                            s.status = "paused"
                            db.commit()
                            toast_success(f"{s.name} paused")
                            st.rerun()
                    with sc5:
                        if can_delete(role) and confirm_button(
                            f"sub_del_{s.id}", "Delete", "delete",
                            f"Remove **{s.name}** from your subscription list?",
                        ):
                            db.delete(s)
                            db.commit()
                            toast_success("Subscription removed")
                            st.rerun()
