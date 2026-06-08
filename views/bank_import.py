import streamlit as st
import pandas as pd
from database import get_db
from models.finance import BankTransaction
from services.import_service import parse_bank_csv, reconcile_transaction
from utils.helpers import format_currency

def show_bank_import(household_id: int):
    """
    Renders the Bank Statement Import panel.
    Allows CSV file uploads for ANZ, BSP, Westpac, HFC, Bred, and reconciles entries.
    """
    st.markdown("<h1 class='app-title'>Bank Import Portal</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Upload statements from major Fijian banks to automatically sync records</p>", unsafe_allow_html=True)
    
    currency = st.session_state.get("household_currency", "FJD")
    
    col1, col2 = st.columns([1, 2])
    
    role = st.session_state.get("user_role", "viewer")
    
    with col1:
        with st.container(border=True):
            st.subheader("Upload Statement")
            
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
                    
                    if st.button("Parse and Load Transactions", type="primary", width="stretch"):
                        with get_db() as db:
                            imported, matched, duplicates = parse_bank_csv(
                                db, household_id, bank_choice, file_bytes
                            )
                            
                            st.success(f"Parsing complete!")
                            st.write(f"- Imported: **{imported}** new records")
                            st.write(f"- Duplicates skipped: **{duplicates}** matches")
                            st.rerun()
                        
    with col2:
        with st.container(border=True):
            st.subheader("Statement Reconciliation Queue")
            st.write("Review imported transactions and save them directly to your budget ledger:")
            
            with get_db() as db:
                # Load imported (unreconciled) transactions
                txs = db.query(BankTransaction).filter(
                    BankTransaction.household_id == household_id,
                    BankTransaction.status == "imported"
                ).order_by(BankTransaction.transaction_date.desc()).all()
                
                if not txs:
                    st.info("Reconciliation queue is empty. Upload a statement to begin.")
                else:
                    tx_rows = []
                    for t in txs:
                        tx_rows.append({
                            "ID": t.id,
                            "Date": t.transaction_date,
                            "Description": t.description,
                            "Amount": format_currency(t.amount, currency),
                            "Auto Category": t.category.name if t.category else "Uncategorized"
                        })
                        
                    st.dataframe(pd.DataFrame(tx_rows), width="stretch", hide_index=True)
                    
                    if role != "viewer":
                        st.write("")
                        reconcile_id = st.number_input("Enter Transaction ID to Reconcile", min_value=0, step=1)
                        
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if st.button("Approve & Sync to Ledger", type="primary", width="stretch"):
                                if reconcile_transaction(db, household_id, reconcile_id):
                                    st.success("Transaction reconciled!")
                                    st.rerun()
                                else:
                                    st.error("Failed to reconcile. Check transaction ID.")
                                    
                        with col_b2:
                            if st.button("Ignore / Dismiss", width="stretch"):
                                target = db.query(BankTransaction).filter(
                                    BankTransaction.id == reconcile_id,
                                    BankTransaction.household_id == household_id
                                ).first()
                                if target:
                                    target.status = "duplicate" # Set status to hide from queue
                                    db.commit()
                                    st.success("Transaction dismissed.")
                                    st.rerun()
                                else:
                                    st.error("Failed to dismiss. Check ID.")
