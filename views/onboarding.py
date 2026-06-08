import streamlit as st
import datetime
from database import get_db
from services.auth_service import create_household_for_user
from services.finance_service import generate_pay_periods
from models.finance import Income, Expense, ExpenseCategory
from models.budget import SavingsGoal, Budget, BudgetItem
from config import SUPPORTED_CURRENCIES, BUDGET_METHODS, INCOME_SOURCES, EXPENSE_CATEGORIES

def show_onboarding_wizard():
    """
    Shows the step-by-step wizard to setup household settings on first login.
    """
    st.markdown("<h1 class='app-title'>Set Up Your Household</h1>", unsafe_allow_html=True)
    st.write("Welcome to SmartBudget AI! Let's get your command center configured in a few quick steps.")
    
    # Initialize onboarding step in session state
    if "onboarding_step" not in st.session_state:
        st.session_state["onboarding_step"] = 1
        st.session_state["onboarding_data"] = {}
        
    step = st.session_state["onboarding_step"]
    
    # Simple step indicator
    cols = st.columns(6)
    steps_titles = ["Household", "Pay Cycle", "Income", "Fixed Bills", "Goals", "Finish"]
    for i, title in enumerate(steps_titles):
        col_idx = i
        with cols[col_idx]:
            if step == i + 1:
                st.markdown(f"**🟢 Step {i+1}**\n*{title}*")
            elif step > i + 1:
                st.markdown(f"✅ Step {i+1}\n*{title}*")
            else:
                st.markdown(f"⚪ Step {i+1}\n*{title}*")
                
    st.markdown("---")
    
    data = st.session_state["onboarding_data"]
    
    if step == 1:
        st.subheader("Step 1: Household Name & Currency")
        h_name = st.text_input("Household Name", value=data.get("name", "My Family Hub"), placeholder="e.g. Singh Family Hub")
        currency = st.selectbox("Preferred Currency", options=list(SUPPORTED_CURRENCIES.keys()), 
                                format_func=lambda x: SUPPORTED_CURRENCIES[x], index=0) # Default FJD
        
        col_nav = st.columns([1, 4, 1])
        with col_nav[2]:
            if st.button("Next ➡️", type="primary"):
                data["name"] = h_name
                data["currency"] = currency
                st.session_state["onboarding_step"] = 2
                st.rerun()
                
    elif step == 2:
        st.subheader("Step 2: Payday & Cycle Configuration")
        st.write("Payday-to-Payday budgeting matches your budget cycles directly to when you receive your salary. This is highly recommended for payday-based households.")
        
        budget_method = st.selectbox("Budgeting Method", options=list(BUDGET_METHODS.keys()),
                                     format_func=lambda x: BUDGET_METHODS[x], index=0) # Default payday
                                     
        start_date = st.date_input("When is your next payday?", value=datetime.date.today())
        
        col_nav = st.columns([1, 4, 1])
        with col_nav[0]:
            if st.button("⬅️ Back"):
                st.session_state["onboarding_step"] = 1
                st.rerun()
        with col_nav[2]:
            if st.button("Next ➡️", type="primary"):
                data["budget_method"] = budget_method
                data["start_date"] = start_date
                st.session_state["onboarding_step"] = 3
                st.rerun()
                
    elif step == 3:
        st.subheader("Step 3: Income Configurations")
        st.write("Add your primary source of income (salary, wages, side business, etc.).")
        
        inc_source = st.selectbox("Income Source", options=INCOME_SOURCES)
        inc_amount = st.number_input("Typical Amount (Net Take-home)", min_value=100.0, value=1200.0, step=100.0)
        inc_freq = st.selectbox("Payday Interval", options=["Weekly", "Fortnightly", "Monthly"])
        
        col_nav = st.columns([1, 4, 1])
        with col_nav[0]:
            if st.button("⬅️ Back"):
                st.session_state["onboarding_step"] = 2
                st.rerun()
        with col_nav[2]:
            if st.button("Next ➡️", type="primary"):
                data["income_source"] = inc_source
                data["income_amount"] = inc_amount
                data["income_freq"] = inc_freq
                st.session_state["onboarding_step"] = 4
                st.rerun()
                
    elif step == 4:
        st.subheader("Step 4: Primary Fixed Expenses")
        st.write("Input your major fixed cycle bills (mortgage, rents, basic utilities, loans).")
        
        rent = st.number_input("Rent or Mortgage Payment", min_value=0.0, value=300.0, step=50.0)
        utilities = st.number_input("Average Utilities (EFL/Water/Gas)", min_value=0.0, value=100.0, step=10.0)
        loans = st.number_input("Loan/Credit Repayments", min_value=0.0, value=50.0, step=10.0)
        
        col_nav = st.columns([1, 4, 1])
        with col_nav[0]:
            if st.button("⬅️ Back"):
                st.session_state["onboarding_step"] = 3
                st.rerun()
        with col_nav[2]:
            if st.button("Next ➡️", type="primary"):
                data["rent"] = rent
                data["utilities"] = utilities
                data["loans"] = loans
                st.session_state["onboarding_step"] = 5
                st.rerun()
                
    elif step == 5:
        st.subheader("Step 5: Savings Goals & Emergency Reserve")
        st.write("Configure your initial financial goals. Setting up an emergency buffer is highly recommended.")
        
        emergency_target = st.number_input("Target Emergency Reserve Fund", min_value=100.0, value=5000.0, step=500.0)
        emergency_current = st.number_input("Current Amount Already Saved", min_value=0.0, value=500.0, step=100.0)
        
        col_nav = st.columns([1, 4, 1])
        with col_nav[0]:
            if st.button("⬅️ Back"):
                st.session_state["onboarding_step"] = 4
                st.rerun()
        with col_nav[2]:
            if st.button("Next ➡️", type="primary"):
                data["emergency_target"] = emergency_target
                data["emergency_current"] = emergency_current
                st.session_state["onboarding_step"] = 6
                st.rerun()
                
    elif step == 6:
        st.subheader("Step 6: Confirm and Complete Setup")
        st.write("We are ready to build your command center! Review details below:")
        
        st.markdown(f"""
        - **Household Name**: {data['name']}
        - **Currency**: {data['currency']}
        - **Budget Cycle**: {BUDGET_METHODS.get(data['budget_method'])}
        - **Initial Income**: {data['income_source']} (${data['income_amount']:,.2f} {data['income_freq']})
        - **Fixed expenses**: Rent (${data['rent']:,.2f}), Utilities (${data['utilities']:,.2f}), Loans (${data['loans']:,.2f})
        - **Emergency Goal**: ${data['emergency_target']:,.2f} (Current: ${data['emergency_current']:,.2f})
        """)
        
        col_nav = st.columns([1, 4, 1])
        with col_nav[0]:
            if st.button("⬅️ Back"):
                st.session_state["onboarding_step"] = 5
                st.rerun()
        with col_nav[2]:
            if st.button("Finish 🚀", type="primary"):
                # Write to database
                with get_db() as db:
                    user_id = st.session_state["user_id"]
                    
                    # 1. Create Household & Associate User as Owner
                    h = create_household_for_user(
                        db, user_id, data["name"], data["currency"], data["budget_method"]
                    )
                    
                    # 2. Add System expense categories if not already present
                    for cat_name in EXPENSE_CATEGORIES:
                        exists = db.query(ExpenseCategory).filter(
                            ExpenseCategory.is_system == True,
                            ExpenseCategory.name == cat_name
                        ).first()
                        if not exists:
                            cat = ExpenseCategory(name=cat_name, is_system=True)
                            db.add(cat)
                    db.commit()
                    
                    # 3. Create default income
                    income = Income(
                        household_id=h.id,
                        source=data["income_source"],
                        amount=data["income_amount"],
                        date=data["start_date"],
                        is_recurring=True,
                        frequency=data["income_freq"].lower(),
                        next_date=data["start_date"] + datetime.timedelta(days=14) if data["income_freq"].lower() == "fortnightly" else data["start_date"] + datetime.timedelta(days=7)
                    )
                    db.add(income)
                    
                    # 4. Generate first batch of Pay Periods
                    periods = generate_pay_periods(db, h.id, data["start_date"], num_periods=12)
                    first_period = periods[0] if periods else None
                    
                    # Get category references for writing expenses
                    rent_cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Rent/Mortgage").first()
                    util_cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Utilities").first()
                    loan_cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Loan Payments").first()
                    
                    # 5. Create initial fixed expenses (if configured)
                    if data["rent"] > 0:
                        db.add(Expense(
                            household_id=h.id, category_id=rent_cat.id, amount=data["rent"],
                            date=data["start_date"], pay_period_id=first_period.id if first_period else None,
                            is_recurring=True, frequency="monthly", merchant="Rent/Landlord"
                        ))
                    if data["utilities"] > 0:
                        db.add(Expense(
                            household_id=h.id, category_id=util_cat.id, amount=data["utilities"],
                            date=data["start_date"], pay_period_id=first_period.id if first_period else None,
                            is_recurring=True, frequency="monthly", merchant="EFL / Water Authority"
                        ))
                    if data["loans"] > 0:
                        db.add(Expense(
                            household_id=h.id, category_id=loan_cat.id, amount=data["loans"],
                            date=data["start_date"], pay_period_id=first_period.id if first_period else None,
                            is_recurring=True, frequency="monthly", merchant="Bank Loan"
                        ))
                        
                    # 6. Create Emergency Savings Goal
                    db.add(SavingsGoal(
                        household_id=h.id,
                        name="Emergency Fund",
                        target_amount=data["emergency_target"],
                        current_amount=data["emergency_current"],
                        target_date=datetime.date.today() + datetime.timedelta(days=365),
                        priority="high",
                        status="active"
                    ))
                    
                    # 7. Create default Category Budgets inside a main budget
                    budget = Budget(
                        household_id=h.id,
                        pay_period_id=first_period.id if first_period else None,
                        name=first_period.name if first_period else "Initial Budget",
                        total_limit=data["income_amount"]
                    )
                    db.add(budget)
                    db.commit()
                    db.refresh(budget)
                    
                    # Add item targets
                    if rent_cat:
                        db.add(BudgetItem(budget_id=budget.id, category_id=rent_cat.id, limit_amount=data["rent"] * 1.2))
                    if util_cat:
                        db.add(BudgetItem(budget_id=budget.id, category_id=util_cat.id, limit_amount=data["utilities"] * 1.2))
                    if loan_cat:
                        db.add(BudgetItem(budget_id=budget.id, category_id=loan_cat.id, limit_amount=data["loans"] * 1.1))
                    db.commit()
                    
                # Clean up onboarding state
                del st.session_state["onboarding_step"]
                del st.session_state["onboarding_data"]
                
                st.success("Household initialized successfully! Redirecting...")
                st.rerun()
