import streamlit as st
import datetime
import json
from database import get_db
from services.auth_service import create_household_for_user
from services.finance_service import generate_pay_periods
from models.finance import Income, Expense, ExpenseCategory
from models.budget import SavingsGoal, Budget, BudgetItem
from models.household import Setting
from config import SUPPORTED_CURRENCIES, BUDGET_METHODS, INCOME_SOURCES, EXPENSE_CATEGORIES


def show_onboarding_wizard():
    """Three-step household setup."""
    st.markdown("<h1 class='app-title'>Set Up Your Household</h1>", unsafe_allow_html=True)
    st.write("Welcome! We'll have you ready in about 2 minutes.")

    if "onboarding_step" not in st.session_state:
        st.session_state["onboarding_step"] = 1
        st.session_state["onboarding_data"] = {}

    step = st.session_state["onboarding_step"]
    cols = st.columns(3)
    steps_titles = ["Basics", "Money In & Bills", "Finish"]
    for i, title in enumerate(steps_titles):
        with cols[i]:
            if step == i + 1:
                st.markdown(f"**🟢 Step {i + 1}**\n*{title}*")
            elif step > i + 1:
                st.markdown(f"✅ Step {i + 1}\n*{title}*")
            else:
                st.markdown(f"⚪ Step {i + 1}\n*{title}*")

    st.markdown("---")
    data = st.session_state["onboarding_data"]

    if step == 1:
        st.subheader("Household & pay cycle")
        data["name"] = st.text_input("Household name", value=data.get("name", "My Family Hub"))
        data["currency"] = st.selectbox(
            "Currency", options=list(SUPPORTED_CURRENCIES.keys()),
            format_func=lambda x: SUPPORTED_CURRENCIES[x], index=0,
        )
        data["budget_method"] = st.selectbox(
            "Budget method", options=list(BUDGET_METHODS.keys()),
            format_func=lambda x: BUDGET_METHODS[x], index=0,
        )
        data["start_date"] = st.date_input("Next payday", value=data.get("start_date", datetime.date.today()))

        c1, _, c2 = st.columns([1, 4, 1])
        with c2:
            if st.button("Next ➡️", type="primary"):
                st.session_state["onboarding_step"] = 2
                st.rerun()

    elif step == 2:
        st.subheader("Income & fixed bills")
        data["income_source"] = st.selectbox("Main income", INCOME_SOURCES, index=0)
        data["income_amount"] = st.number_input("Typical take-home pay", min_value=100.0, value=1200.0, step=100.0)
        data["income_freq"] = st.selectbox("Pay interval", ["Weekly", "Fortnightly", "Monthly"])
        st.markdown("**Fixed bills each cycle**")
        b1, b2, b3 = st.columns(3)
        with b1:
            data["rent"] = st.number_input("Rent / mortgage", min_value=0.0, value=300.0, step=50.0)
        with b2:
            data["utilities"] = st.number_input("Utilities", min_value=0.0, value=100.0, step=10.0)
        with b3:
            data["loans"] = st.number_input("Loans", min_value=0.0, value=50.0, step=10.0)

        c1, _, c2 = st.columns([1, 4, 1])
        with c1:
            if st.button("⬅️ Back"):
                st.session_state["onboarding_step"] = 1
                st.rerun()
        with c2:
            if st.button("Next ➡️", type="primary"):
                st.session_state["onboarding_step"] = 3
                st.rerun()

    elif step == 3:
        st.subheader("Review & launch")
        with st.expander("Optional: emergency savings goal", expanded=False):
            data["emergency_target"] = st.number_input(
                "Target emergency fund", min_value=0.0, value=data.get("emergency_target", 5000.0), step=500.0,
            )
            data["emergency_current"] = st.number_input(
                "Already saved", min_value=0.0, value=data.get("emergency_current", 500.0), step=100.0,
            )

        st.markdown(f"""
        - **{data['name']}** · {data['currency']}
        - **Pay cycle:** {BUDGET_METHODS.get(data['budget_method'])} from {data['start_date']}
        - **Income:** {data['income_source']} — ${data['income_amount']:,.2f} ({data['income_freq']})
        - **Fixed bills:** rent ${data['rent']:,.2f}, utilities ${data['utilities']:,.2f}, loans ${data['loans']:,.2f}
        """)

        c1, _, c2 = st.columns([1, 4, 1])
        with c1:
            if st.button("⬅️ Back"):
                st.session_state["onboarding_step"] = 2
                st.rerun()
        with c2:
            if st.button("Finish 🚀", type="primary"):
                _complete_onboarding(data)
                del st.session_state["onboarding_step"]
                del st.session_state["onboarding_data"]
                st.success("Household ready! Redirecting…")
                st.rerun()


def _complete_onboarding(data: dict):
    with get_db() as db:
        user_id = st.session_state["user_id"]
        h = create_household_for_user(
            db, user_id, data["name"], data["currency"], data["budget_method"],
        )

        for cat_name in EXPENSE_CATEGORIES:
            exists = db.query(ExpenseCategory).filter(
                ExpenseCategory.is_system == True,
                ExpenseCategory.name == cat_name,
            ).first()
            if not exists:
                db.add(ExpenseCategory(name=cat_name, is_system=True))
        db.commit()

        from services.finance_service import generate_pay_periods
        inc_freq = data["income_freq"].lower()
        income = Income(
            household_id=h.id,
            source=data["income_source"],
            amount=data["income_amount"],
            date=data["start_date"],
            is_recurring=True,
            frequency=inc_freq,
            next_date=data["start_date"],
        )
        db.add(income)

        periods = generate_pay_periods(db, h.id, data["start_date"], num_periods=12)
        first_period = periods[0] if periods else None

        rent_cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Rent/Mortgage").first()
        util_cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Utilities").first()
        loan_cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Loan Payments").first()

        for amount, cat, merchant in [
            (data["rent"], rent_cat, "Rent/Landlord"),
            (data["utilities"], util_cat, "EFL / Water Authority"),
            (data["loans"], loan_cat, "Bank Loan"),
        ]:
            if amount > 0 and cat:
                db.add(Expense(
                    household_id=h.id, category_id=cat.id, amount=amount,
                    date=data["start_date"], pay_period_id=first_period.id if first_period else None,
                    is_recurring=True, frequency="monthly", merchant=merchant,
                ))

        emergency_target = data.get("emergency_target", 5000.0)
        emergency_current = data.get("emergency_current", 500.0)
        if emergency_target > 0:
            db.add(SavingsGoal(
                household_id=h.id,
                name="Emergency Fund",
                target_amount=emergency_target,
                current_amount=emergency_current,
                target_date=datetime.date.today() + datetime.timedelta(days=365),
                priority="high",
                status="active",
            ))

        budget = Budget(
            household_id=h.id,
            pay_period_id=first_period.id if first_period else None,
            name=first_period.name if first_period else "Initial Budget",
            total_limit=data["income_amount"],
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)

        groceries_cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Groceries").first()
        fixed_total = data["rent"] + data["utilities"] + data["loans"]
        discretionary = max(0.0, data["income_amount"] - fixed_total)
        if rent_cat:
            db.add(BudgetItem(budget_id=budget.id, category_id=rent_cat.id, limit_amount=data["rent"]))
        if util_cat:
            db.add(BudgetItem(budget_id=budget.id, category_id=util_cat.id, limit_amount=data["utilities"]))
        if loan_cat:
            db.add(BudgetItem(budget_id=budget.id, category_id=loan_cat.id, limit_amount=data["loans"]))
        if groceries_cat and discretionary > 0:
            db.add(BudgetItem(
                budget_id=budget.id, category_id=groceries_cat.id,
                limit_amount=round(discretionary * 0.5, 2),
            ))
        budget.total_limit = data["income_amount"]
        db.add(Setting(
            household_id=h.id,
            key="quick_start_progress",
            value=json.dumps({"has_pay_period": True, "has_income": True, "has_fixed_bill": True}),
        ))
        db.commit()
