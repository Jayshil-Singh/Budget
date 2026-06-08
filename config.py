import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Config
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///smartbudget.db")
if DATABASE_URL.startswith("postgres://"):
    # Fix for SQLAlchemy compatibility with older postgres:// prefixes
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# AI Service Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Security Config
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key-12345")

# Notification Config (Simulated channels if config is missing)
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", "")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
EMAIL_SMTP_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "")

# Platform Defaults
DEFAULT_CURRENCY = "FJD"
SUPPORTED_CURRENCIES = {
    "FJD": "Fijian Dollar ($)",
    "USD": "US Dollar ($)",
    "AUD": "Australian Dollar ($)",
    "NZD": "New Zealand Dollar ($)",
    "GBP": "British Pound (£)"
}

BUDGET_METHODS = {
    "payday": "Payday-to-Payday",
    "weekly": "Weekly",
    "fortnightly": "Fortnightly",
    "monthly": "Monthly"
}

INCOME_SOURCES = ["Salary", "Business", "Rental", "Investment", "Side Hustle", "Other"]
EXPENSE_CATEGORIES = [
    "Rent/Mortgage", 
    "Utilities", 
    "Internet", 
    "Insurance", 
    "School Fees", 
    "Childcare", 
    "Transport", 
    "Subscriptions", 
    "Groceries",
    "Dining Out",
    "Entertainment",
    "Medical",
    "Loan Payments", 
    "Other"
]

DEBT_TYPES = ["Mortgage", "Credit Cards", "Personal Loans", "Vehicle Loans", "Store Credit", "Other"]
SINKING_FUND_TYPES = ["Christmas", "School Fees", "Vehicle Maintenance", "Insurance", "Vacation", "Medical", "Emergency", "Other"]
SAVINGS_GOALS_TYPES = ["House Deposit", "Emergency Fund", "Vacation", "Vehicle Purchase", "Education", "Wedding", "Other"]
