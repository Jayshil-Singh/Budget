import streamlit as st
import pandas as pd
from database import get_db
from models.finance import BankTransaction
from services.import_service import (
    parse_bank_csv, reconcile_transaction, import_sms_transaction, reconcile_all_imported,
)
from utils.helpers import format_currency, can_modify

def show_bank_import(household_id: int):
    st.markdown("<h1 class='app-title'>Import & SMS</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='app-subtitle'>Paste an M-PAiSA SMS or upload a bank CSV — fastest way to log spending</p>",
        unsafe_allow_html=True,
    )

    currency = st.session_state.get("household_currency", "FJD")
    role = st.session_state.get("user_role", "viewer")
    can_edit = can_modify(role)

    # SMS first — promoted for mobile users
    with st.container(border=True):
        st.subheader("📱 Paste M-PAiSA / MyCash SMS")
        st.caption("Copy the confirmation SMS from your phone and paste it here.")
        if not can_edit:
            st.info("View only — you cannot import transactions.")
        else:
            sms_input = st.text_area(
                "SMS text",
                placeholder="M-PAiSA: You have paid FJD 15.50 to MH Supermarket on 09/06/2026. Ref: 123456789.",
                height=100,
                key="sms_paste_input",
            )
            if st.button("📲 Import from SMS", type="primary"):
                if not sms_input.strip():
                    st.error("Paste your SMS first.")
                else:
                    with get_db() as db:
                        result = import_sms_transaction(db, household_id, sms_input.strip())
                    if result["status"] == "success":
                        st.success(result["message"])
                        st.rerun()
                    elif result["status"] == "warning":
                        st.warning(result["message"])
                    else:
                        st.error(result["message"])

    st.write("")

    col1, col2 = st.columns([1, 2])

    with col1:
        with st.container(border=True):
            st.subheader("📂 Bank CSV")
            if not can_edit:
                st.info("View only.")
            else:
                bank_choice = st.selectbox(
                    "Bank",
                    ["ANZ Fiji", "BSP Fiji", "Westpac Fiji", "HFC Bank", "Bred Bank", "Generic CSV"],
                )
                uploaded_file = st.file_uploader("CSV file", type="csv")
                if uploaded_file is not None and st.button("Upload & Parse", type="primary", width="stretch"):
                    with get_db() as db:
                        imported, matched, duplicates = parse_bank_csv(
                            db, household_id, bank_choice, uploaded_file.read()
                        )
                    st.success(f"Done: {imported} new, {matched} matched, {duplicates} duplicates skipped")
                    st.rerun()

    with col2:
        with st.container(border=True):
            st.subheader("🔄 Needs review")
            with get_db() as db:
                txs = db.query(BankTransaction).filter(
                    BankTransaction.household_id == household_id,
                    BankTransaction.status == "imported",
                ).order_by(BankTransaction.transaction_date.desc()).all()

                if not txs:
                    st.success("All caught up — nothing waiting to review.")
                else:
                    st.caption(f"{len(txs)} transaction(s) waiting")
                    if can_edit:
                        if st.button("✅ Accept all obvious matches", type="primary"):
                            rec, skip = reconcile_all_imported(db, household_id)
                            st.success(f"Added {rec} to your money log. {skip} need manual review.")
                            st.rerun()

                    for t in txs[:15]:
                        with st.container(border=True):
                            tc1, tc2, tc3 = st.columns([3, 1, 1])
                            with tc1:
                                st.write(f"**{t.description[:60]}**")
                                st.caption(f"{t.transaction_date} · {t.account_bank}")
                            with tc2:
                                st.write(format_currency(t.amount, currency))
                                st.caption(t.category.name if t.category else "Uncategorized")
                            with tc3:
                                if can_edit:
                                    if st.button("✅ Add", key=f"rec_{t.id}"):
                                        if reconcile_transaction(db, household_id, t.id):
                                            st.success("Added!")
                                            st.rerun()
                                    if st.button("Skip", key=f"skip_{t.id}"):
                                        t.status = "duplicate"
                                        db.commit()
                                        st.rerun()
                    if len(txs) > 15:
                        st.caption(f"+ {len(txs) - 15} more in queue")
