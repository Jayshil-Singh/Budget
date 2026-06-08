import datetime
from database import init_db, get_db
from models.auth import User
from models.household import Household, HouseholdMember
from models.finance import Income, Expense, ExpenseCategory
from models.budget import SavingsGoal, Debt, SinkingFund, Budget, BudgetItem
from models.audit import AuditLog, Notification
from utils.security import hash_password
from services.finance_service import generate_pay_periods
from config import EXPENSE_CATEGORIES

def seed_data():
    """
    Seeds database with initial system configurations and demo data.
    """
    print("Initializing database...")
    init_db()
    
    with get_db() as db:
        # Check if already seeded
        admin_exists = db.query(User).filter(User.email == "admin@smartbudget.local").first()
        if admin_exists:
            print("Database already contains seed data. Skipping seeding.")
            return
            
        print("Seeding Users...")
        # 1. Create Users
        admin_user = User(
            email="admin@smartbudget.local",
            password_hash=hash_password("AdminPass123!"),
            full_name="Platform Administrator",
            role="admin",
            is_active=True
        )
        owner_user = User(
            email="owner@smartbudget.local",
            password_hash=hash_password("OwnerPass123!"),
            full_name="Jayshil Singh",
            role="owner",
            is_active=True
        )
        partner_user = User(
            email="partner@smartbudget.local",
            password_hash=hash_password("PartnerPass123!"),
            full_name="Priya Singh",
            role="partner",
            is_active=True
        )
        viewer_user = User(
            email="viewer@smartbudget.local",
            password_hash=hash_password("ViewerPass123!"),
            full_name="Adarsh Singh",
            role="viewer",
            is_active=True
        )
        
        db.add_all([admin_user, owner_user, partner_user, viewer_user])
        db.commit()
        db.refresh(owner_user)
        db.refresh(partner_user)
        db.refresh(viewer_user)
        
        # 2. Create System Categories
        print("Seeding expense categories...")
        category_map = {}
        for cat_name in EXPENSE_CATEGORIES:
            cat = ExpenseCategory(name=cat_name, is_system=True)
            db.add(cat)
            db.commit()
            db.refresh(cat)
            category_map[cat_name] = cat.id
            
        # 3. Create Household
        print("Seeding Household...")
        household = Household(
            name="Singh Family Hub",
            currency="FJD",
            budget_method="payday"
        )
        db.add(household)
        db.commit()
        db.refresh(household)
        
        # 4. Associate Household Members
        m1 = HouseholdMember(household_id=household.id, user_id=owner_user.id, role="owner")
        m2 = HouseholdMember(household_id=household.id, user_id=partner_user.id, role="partner")
        m3 = HouseholdMember(household_id=household.id, user_id=viewer_user.id, role="viewer")
        db.add_all([m1, m2, m3])
        db.commit()
        
        # 5. Generate Pay Periods
        print("Generating pay periods...")
        start_date = datetime.date(2026, 6, 1)
        periods = generate_pay_periods(db, household.id, start_date, num_periods=12)
        first_period = periods[0]
        
        # 6. Seed Incomes
        print("Seeding income sources...")
        db.add(Income(
            household_id=household.id,
            source="Salary (Jayshil)",
            amount=1800.0,
            date=datetime.date(2026, 6, 1),
            is_recurring=True,
            frequency="fortnightly",
            next_date=datetime.date(2026, 6, 15),
            pay_period_id=first_period.id
        ))
        db.add(Income(
            household_id=household.id,
            source="Rental Income",
            amount=400.0,
            date=datetime.date(2026, 6, 3),
            is_recurring=True,
            frequency="monthly",
            next_date=datetime.date(2026, 7, 3),
            pay_period_id=first_period.id
        ))
        db.commit()
        
        # 7. Seed Fixed & Varied Expenses
        print("Seeding expenses...")
        db.add(Expense(
            household_id=household.id,
            category_id=category_map["Rent/Mortgage"],
            amount=450.0,
            date=datetime.date(2026, 6, 1),
            pay_period_id=first_period.id,
            is_recurring=True,
            frequency="monthly",
            merchant="Landlord",
            notes="Monthly Flat Rental"
        ))
        db.add(Expense(
            household_id=household.id,
            category_id=category_map["Utilities"],
            amount=120.0,
            date=datetime.date(2026, 6, 2),
            pay_period_id=first_period.id,
            is_recurring=True,
            frequency="monthly",
            merchant="EFL Electricity",
            notes="Electricity bill"
        ))
        db.add(Expense(
            household_id=household.id,
            category_id=category_map["Groceries"],
            amount=180.0,
            date=datetime.date(2026, 6, 4),
            pay_period_id=first_period.id,
            merchant="RB Patel",
            notes="Weekly grocery run"
        ))
        db.add(Expense(
            household_id=household.id,
            category_id=category_map["Dining Out"],
            amount=45.0,
            date=datetime.date(2026, 6, 5),
            pay_period_id=first_period.id,
            merchant="Lovo Express",
            notes="Friday Lovos"
        ))
        db.commit()
        
        # 8. Seed Savings Goals
        print("Seeding goals...")
        db.add(SavingsGoal(
            household_id=household.id,
            name="Emergency Fund",
            target_amount=6000.0,
            current_amount=1200.0,
            target_date=datetime.date(2026, 12, 31),
            priority="high",
            status="active"
        ))
        db.add(SavingsGoal(
            household_id=household.id,
            name="House Deposit",
            target_amount=30000.0,
            current_amount=1500.0,
            target_date=datetime.date(2028, 6, 1),
            priority="medium",
            status="active"
        ))
        
        # 9. Seed Sinking Funds
        print("Seeding sinking funds...")
        db.add(SinkingFund(
            household_id=household.id,
            name="Christmas Shopping",
            target_amount=1200.0,
            current_amount=300.0,
            target_date=datetime.date(2026, 12, 15),
            contribution_amount=75.0,
            frequency="fortnightly"
        ))
        db.add(SinkingFund(
            household_id=household.id,
            name="School Fees Term 3",
            target_amount=800.0,
            current_amount=200.0,
            target_date=datetime.date(2026, 8, 30),
            contribution_amount=100.0,
            frequency="monthly"
        ))
        
        # 10. Seed Debts
        print("Seeding debts...")
        db.add(Debt(
            household_id=household.id,
            name="BSP Personal Loan",
            type="Personal Loans",
            current_balance=4500.0,
            original_balance=6000.0,
            interest_rate=8.5,
            minimum_payment=250.0,
            payment_frequency="monthly",
            start_date=datetime.date(2026, 1, 15)
        ))
        db.add(Debt(
            household_id=household.id,
            name="Westpac Credit Card",
            type="Credit Cards",
            current_balance=850.0,
            original_balance=1500.0,
            interest_rate=14.9,
            minimum_payment=90.0,
            payment_frequency="monthly",
            start_date=datetime.date(2025, 12, 1)
        ))
        
        # 11. Seed Audit Logs & Notifications
        print("Logging audit activities...")
        db.add(AuditLog(user_id=owner_user.id, action="HOUSEHOLD_CREATED", details="Created Singh Family Hub"))
        db.add(Notification(
            household_id=household.id,
            title="Welcome to SmartBudget AI",
            message="Your household financial center is ready. Sync bank accounts or edit budget categories to begin.",
            type="success",
            channel="in_app"
        ))
        db.commit()
        
        # 12. Set up default budget
        budget = Budget(
            household_id=household.id,
            pay_period_id=first_period.id,
            name=first_period.name,
            total_limit=1200.0
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)
        
        db.add(BudgetItem(budget_id=budget.id, category_id=category_map["Rent/Mortgage"], limit_amount=450.0))
        db.add(BudgetItem(budget_id=budget.id, category_id=category_map["Utilities"], limit_amount=150.0))
        db.add(BudgetItem(budget_id=budget.id, category_id=category_map["Groceries"], limit_amount=400.0))
        db.add(BudgetItem(budget_id=budget.id, category_id=category_map["Dining Out"], limit_amount=200.0))
        db.commit()
        
    print("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_data()
