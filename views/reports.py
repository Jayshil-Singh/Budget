import streamlit as st
import datetime
import io
from database import get_db
from models.finance import Income, Expense, ExpenseCategory, PayPeriod
from models.budget import SavingsGoal, Debt, SinkingFund
from models.audit import Notification
from services.report_service import generate_pdf_report, generate_excel_report, generate_csv_export
from utils.helpers import format_currency
from services.finance_service import get_current_pay_period, calculate_income_for_period, calculate_expenses_for_period
from services.dashboard_service import get_period_comparison, get_budget_progress, get_upcoming_bills


def show_reports(household_id: int):
    """
    Renders the Reports & Data Export view.
    Allows generating PDF, Excel, and CSV reports and downloading them directly.
    """
    st.markdown("<h1 class='app-title'>Reports & Data Export</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Generate financial summaries and export your data</p>", unsafe_allow_html=True)

    currency = st.session_state.get("household_currency", "FJD")

    tab_summary, tab_pdf, tab_excel, tab_csv = st.tabs([
        "📝 Plain Summary", "📄 PDF Report", "📊 Excel Workbook", "📁 Raw CSV Export",
    ])

    with get_db() as db:

        with tab_summary:
            period = get_current_pay_period(db, household_id)
            if not period:
                st.info("Set up a pay cycle first to see your summary.")
            else:
                income = calculate_income_for_period(db, household_id, period.start_date, period.end_date)
                expenses = calculate_expenses_for_period(db, household_id, period.start_date, period.end_date)
                left = income - expenses
                cmp = get_period_comparison(db, household_id)
                st.markdown(f"### {period.name}")
                st.write(
                    f"This pay cycle you received **{format_currency(income, currency)}** "
                    f"and spent **{format_currency(expenses, currency)}**."
                )
                if left >= 0:
                    st.success(f"You have {format_currency(left, currency)} left until payday.")
                else:
                    st.error(f"You are {format_currency(abs(left), currency)} over budget this cycle.")
                if cmp and cmp.get("has_prev"):
                    direction = "more" if cmp["delta"] > 0 else "less"
                    st.write(
                        f"That is **{format_currency(abs(cmp['delta']), currency)}** {direction} "
                        f"than last cycle ({cmp['pct']:+.0f}%)."
                    )
                progress = get_budget_progress(db, household_id)
                if progress:
                    st.markdown("**Category highlights**")
                    for row in progress[:5]:
                        status = "on track" if not row["over"] else "over budget"
                        st.write(
                            f"- **{row['category']}**: {format_currency(row['spent'], currency)} "
                            f"of {format_currency(row['limit'], currency)} ({status})"
                        )
                upcoming = get_upcoming_bills(db, household_id, limit=3)
                if upcoming:
                    st.markdown("**Coming up**")
                    for bill in upcoming:
                        st.write(f"- {bill['name']}: {format_currency(bill['amount'], currency)} on {bill['date']}")

        with tab_pdf:
            with st.container(border=True):
                st.subheader("📄 Monthly Financial Summary PDF")
                st.write(
                    "Generates a professionally designed PDF with:\n"
                    "- Executive summary (income, expenses, net balance)\n"
                    "- Spending breakdown by category\n"
                    "- Outstanding debts overview\n"
                    "- Savings goals progress"
                )
                st.write("")
                if st.button("🔄 Generate & Download PDF Report", type="primary", width="stretch"):
                    with st.spinner("Generating your PDF report..."):
                        try:
                            filepath = generate_pdf_report(db, household_id)
                            with open(filepath, "rb") as f:
                                pdf_bytes = f.read()
                            st.download_button(
                                label="⬇️ Download PDF Report",
                                data=pdf_bytes,
                                file_name=f"SmartBudget_Report_{datetime.date.today().isoformat()}.pdf",
                                mime="application/pdf",
                                width="stretch"
                            )
                            st.success("✅ PDF report generated! Click the download button above.")
                        except Exception as e:
                            st.error(f"Failed to generate PDF: {e}")

        # --------------------------------------------------------
        # EXCEL REPORT TAB
        # --------------------------------------------------------
        with tab_excel:
            with st.container(border=True):
                st.subheader("📊 Full Excel Workbook")
                st.write(
                    "Generates a multi-sheet Excel workbook with:\n"
                    "- Financial Summary sheet with auto-calculated totals\n"
                    "- Full Income Register\n"
                    "- Full Expense Register\n"
                )
                st.write("")
                if st.button("🔄 Generate & Download Excel Report", type="primary", width="stretch"):
                    with st.spinner("Generating your Excel workbook..."):
                        try:
                            filepath = generate_excel_report(db, household_id)
                            with open(filepath, "rb") as f:
                                excel_bytes = f.read()
                            st.download_button(
                                label="⬇️ Download Excel Workbook",
                                data=excel_bytes,
                                file_name=f"SmartBudget_Excel_{datetime.date.today().isoformat()}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                width="stretch"
                            )
                            st.success("✅ Excel workbook generated! Click the download button above.")
                        except Exception as e:
                            st.error(f"Failed to generate Excel workbook: {e}")

        # --------------------------------------------------------
        # CSV EXPORT TAB
        # --------------------------------------------------------
        with tab_csv:
            with st.container(border=True):
                st.subheader("📁 Raw Data CSV Export")
                col1, col2 = st.columns(2)

                with col1:
                    st.write("**Export Expenses CSV**")
                    st.caption("Includes: ID, Category, Amount, Date, Merchant, Notes, Tags")
                    if st.button("⬇️ Download Expenses CSV", width="stretch"):
                        with st.spinner("Exporting expenses..."):
                            try:
                                filepath = generate_csv_export(db, household_id, "expenses")
                                with open(filepath, "r", encoding="utf-8") as f:
                                    csv_str = f.read()
                                st.download_button(
                                    label="💾 Save Expenses CSV",
                                    data=csv_str,
                                    file_name=f"expenses_{datetime.date.today().isoformat()}.csv",
                                    mime="text/csv",
                                    width="stretch"
                                )
                            except Exception as e:
                                st.error(f"Export failed: {e}")

                with col2:
                    st.write("**Export Income CSV**")
                    st.caption("Includes: ID, Source, Amount, Date, Recurring, Frequency")
                    if st.button("⬇️ Download Income CSV", width="stretch"):
                        with st.spinner("Exporting income..."):
                            try:
                                filepath = generate_csv_export(db, household_id, "income")
                                with open(filepath, "r", encoding="utf-8") as f:
                                    csv_str = f.read()
                                st.download_button(
                                    label="💾 Save Income CSV",
                                    data=csv_str,
                                    file_name=f"income_{datetime.date.today().isoformat()}.csv",
                                    mime="text/csv",
                                    width="stretch"
                                )
                            except Exception as e:
                                st.error(f"Export failed: {e}")

            # Full data backup
            st.write("")
            with st.container(border=True):
                st.subheader("🗄️ Full Data Backup (All Tables)")
                st.caption("Exports all your household financial data as a combined CSV for archiving.")

                if st.button("⬇️ Download Full Data Backup", type="secondary", width="stretch"):
                    with st.spinner("Preparing full backup..."):
                        try:
                            output = io.StringIO()
                            import csv

                            # Expenses
                            expenses = db.query(Expense).filter(Expense.household_id == household_id).all()
                            incomes = db.query(Income).filter(Income.household_id == household_id).all()
                            goals = db.query(SavingsGoal).filter(SavingsGoal.household_id == household_id).all()
                            debts = db.query(Debt).filter(Debt.household_id == household_id).all()
                            sinking = db.query(SinkingFund).filter(SinkingFund.household_id == household_id).all()

                            writer = csv.writer(output)

                            writer.writerow(["=== EXPENSES ==="])
                            writer.writerow(["ID", "Date", "Category", "Merchant", "Amount", "Recurring", "Notes"])
                            for e in expenses:
                                writer.writerow([e.id, e.date, e.category.name if e.category else "Other",
                                                 e.merchant or "", e.amount, e.is_recurring, e.notes or ""])

                            writer.writerow([])
                            writer.writerow(["=== INCOME ==="])
                            writer.writerow(["ID", "Date", "Source", "Amount", "Recurring", "Frequency"])
                            for i in incomes:
                                writer.writerow([i.id, i.date, i.source, i.amount, i.is_recurring, i.frequency or ""])

                            writer.writerow([])
                            writer.writerow(["=== SAVINGS GOALS ==="])
                            writer.writerow(["ID", "Name", "Target", "Current", "Status", "Target Date"])
                            for g in goals:
                                writer.writerow([g.id, g.name, g.target_amount, g.current_amount, g.status,
                                                 g.target_date.isoformat() if g.target_date else ""])

                            writer.writerow([])
                            writer.writerow(["=== DEBTS ==="])
                            writer.writerow(["ID", "Name", "Type", "Balance", "Interest Rate", "Min Payment"])
                            for d in debts:
                                writer.writerow([d.id, d.name, d.type, d.current_balance,
                                                 d.interest_rate, d.minimum_payment])

                            writer.writerow([])
                            writer.writerow(["=== SINKING FUNDS ==="])
                            writer.writerow(["ID", "Name", "Target", "Current", "Target Date", "Contribution", "Frequency"])
                            for s in sinking:
                                writer.writerow([s.id, s.name, s.target_amount, s.current_amount,
                                                 s.target_date.isoformat() if s.target_date else "",
                                                 s.contribution_amount, s.frequency])

                            st.download_button(
                                label="💾 Save Full Backup CSV",
                                data=output.getvalue(),
                                file_name=f"SmartBudget_FullBackup_{datetime.date.today().isoformat()}.csv",
                                mime="text/csv",
                                width="stretch"
                            )
                            st.success("✅ Full backup ready for download!")
                        except Exception as e:
                            st.error(f"Backup failed: {e}")
