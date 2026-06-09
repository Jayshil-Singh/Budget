import os
import urllib.parse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def _clean_db_url(url_str: str) -> str:
    if not url_str or not (url_str.startswith("postgresql://") or url_str.startswith("postgres://")):
        return url_str
        
    # Find scheme separator
    scheme_idx = url_str.find("://")
    if scheme_idx == -1:
        return url_str
    scheme = url_str[:scheme_idx]
    rest = url_str[scheme_idx + 3:]
    
    # Split authority (host/user) and path/query
    slash_idx = rest.find("/")
    if slash_idx != -1:
        authority = rest[:slash_idx]
        path_query = rest[slash_idx:]
    else:
        authority = rest
        path_query = ""
        
    # Split userinfo and host/port at the last '@'
    at_idx = authority.rfind("@")
    if at_idx == -1:
        return url_str # No '@', so no password or no host info, return as is
        
    userinfo = authority[:at_idx]
    host_port = authority[at_idx + 1:]
    
    # Split username and password at the first ':'
    colon_idx = userinfo.find(":")
    if colon_idx == -1:
        # No password, userinfo is just username
        username = userinfo
        password = ""
    else:
        username = userinfo[:colon_idx]
        password = userinfo[colon_idx + 1:]
        
    # Strip accidental surrounding brackets (e.g. [password]) commonly copied from templates
    if password.startswith("[") and password.endswith("]"):
        password = password[1:-1]
        
    # URL-encode the password if it's not already encoded
    decoded_password = urllib.parse.unquote(password)
    encoded_password = urllib.parse.quote(decoded_password, safe="")
    
    # Reconstruct the URL
    if encoded_password:
        new_authority = f"{username}:{encoded_password}@{host_port}"
    else:
        new_authority = f"{username}@{host_port}"
        
    return f"{scheme}://{new_authority}{path_query}"

# Database Config
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///smartbudget.db")
if DATABASE_URL.startswith("postgres://"):
    # Fix for SQLAlchemy compatibility with older postgres:// prefixes
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
DATABASE_URL = _clean_db_url(DATABASE_URL)

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
