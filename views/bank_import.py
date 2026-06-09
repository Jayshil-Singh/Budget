import streamlit as st
import pandas as pd
from database import get_db
from models.finance import BankTransaction
from services.import_service import parse_bank_csv, reconcile_transaction, import_sms_transaction
from utils.helpers import format_currency

def show_bank_import(household_id: int):
    """
    Renders the Bank Statement Import portal.
    Allows CSV file uploads for ANZ, BSP, Westpac, HFC, Bred, MyCash/M-PAiSA SMS paste, and reconciles entries.
    """
    st.markdown("<h1 class='app-title'>Bank Import Portal</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Import statements from major Fijian banks or paste M-PAiSA / MyCash SMS confirmations</p>", unsafe_allow_html=True)

    currency = st.session_state.get("household_currency", "FJD")
    role = st.session_state.get("user_role", "viewer")

    # -------------------------------------------------------
    # SMS IMPORTER PANEL
    # -------------------------------------------------------
    with st.expander("📱 M-PAiSA / MyCash SMS Importer", expanded=False):
        st.write("Paste your M-PAiSA or MyCash transaction confirmation SMS below to instantly import it.")
        st.caption("Supported formats: payment sent, payment received, and bill-pay confirmations.")

        if role == "viewer":
            st.info("ℹ️ Read-Only Mode: Viewers cannot import transactions.")
        else:
            sms_example = (
                "Example:\n"
                "Receipt No: 987654321. Paid to Vodafone Fiji of FJD 50.00 on 09/06/2026 13:45.\n"
                "  — or —\n"
                "M-PAiSA: You have paid FJD 15.50 to MH Supermarket on 09/06/2026. Ref: 123456789.\n"
                "  — or —\n"
                "Receipt No: 456789012. You have received FJD 100.00 from John Doe on 09/06/2026 10:30."
            )
            sms_input = st.text_area(
                "Paste SMS Confirmation Text",
                placeholder=sms_example,
                height=130,
                key="sms_paste_input"
            )
            if st.button("📲 Parse & Import SMS Transaction", type="primary"):
                if not sms_input.strip():
                    st.error("Please paste your SMS confirmation text first.")
                else:
                    with get_db() as db:
                        result = import_sms_transaction(db, household_id, sms_input.strip())
                    if result["status"] == "success":
                        st.success(f"✅ {result['message']}")
                        st.rerun()
                    elif result["status"] == "warning":
                        st.warning(f"⚠️ {result['message']}")
                    else:
                        st.error(f"❌ {result['message']}")
                        st.info(
                            "Tip: Ensure the SMS includes the merchant name, amount (FJD), "
                            "and transaction date. Copy the full SMS without editing it."
                        )

    st.write("")

    col1, col2 = st.columns([1, 2])

    with col1:
        with st.container(border=True):
            st.subheader("📂 Upload Bank Statement CSV")

            if role == "viewer":
                st.info("ℹ️ Read-Only Mode: Viewers cannot upload or import statement files.")
            else:
                bank_choice = st.selectbox(
                    "Select Bank",
                    ["ANZ Fiji", "BSP Fiji", "Westpac Fiji", "HFC Bank", "Bred Bank", "Generic CSV"]
                )

                uploaded_file = st.file_uploader("Choose CSV File", type="csv")

                if uploaded_file is not None:
                    file_bytes = uploaded_file.read()

                    if st.button("Parse and Load Transactions", type="primary", use_container_width=True):
                        with get_db() as db:
                            imported, matched, duplicates = parse_bank_csv(
                                db, household_id, bank_choice, file_bytes
                            )

                        st.success("Parsing complete!")
                        st.write(f"- Imported: **{imported}** new records")
                        st.write(f"- Duplicates skipped: **{duplicates}** matches")
                        st.rerun()

    with col2:
        with st.container(border=True):
            st.subheader("🔄 Statement Reconciliation Queue")
            st.write("Review imported transactions and save them directly to your budget ledger:")

            with get_db() as db:
                txs = db.query(BankTransaction).filter(
                    BankTransaction.household_id == household_id,
                    BankTransaction.status == "imported"
                ).order_by(BankTransaction.transaction_date.desc()).all()

                if not txs:
                    st.info("Reconciliation queue is empty. Upload a statement or import an SMS to begin.")
                else:
                    tx_rows = []
                    for t in txs:
                        tx_rows.append({
                            "ID": t.id,
                            "Source": t.account_bank,
                            "Date": t.transaction_date,
                            "Description": t.description,
                            "Amount": format_currency(t.amount, currency),
                            "Auto Category": t.category.name if t.category else "Uncategorized"
                        })

                    st.dataframe(pd.DataFrame(tx_rows), use_container_width=True, hide_index=True)

                    if role != "viewer":
                        st.write("")
                        reconcile_id = st.number_input("Enter Transaction ID to Reconcile", min_value=0, step=1)

                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("✅ Approve & Sync to Ledger", type="primary", use_container_width=True):
                                if reconcile_transaction(db, household_id, reconcile_id):
                                    st.success("Transaction reconciled and added to ledger!")
                                    st.rerun()
                                else:
                                    st.error("Failed to reconcile. Check the transaction ID.")

                        with col_b2:
                            if st.button("🗑️ Ignore / Dismiss", use_container_width=True):
                                target = db.query(BankTransaction).filter(
                                    BankTransaction.id == reconcile_id,
                                    BankTransaction.household_id == household_id
                                ).first()
                                if target:
                                    target.status = "duplicate"
                                    db.commit()
                                    st.success("Transaction dismissed.")
                                    st.rerun()
                                else:
                                    st.error("Failed to dismiss. Check ID.")
