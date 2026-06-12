"""Central navigation menu — labels, sections, and route keys."""

NAV_SECTIONS = [
    ("Overview", "Dashboard & reports"),
    ("Setup", "Income · budget · expenses · recurring"),
    ("Track", "Budget vs actual · sinking · forecast"),
    ("More", "Notifications · plans · import · coach · family"),
]

# (sidebar label, internal route key)
NAV_ITEMS: list[tuple[str, str]] = [
    ("📊 Dashboard", "dashboard"),
    ("💰 Income Setup", "income_setup"),
    ("📅 Pay Schedule", "pay_schedule"),
    ("📋 Budget Setup", "budget_setup"),
    ("💸 Expense Setup", "expense_setup"),
    ("🔁 Recurring Bills", "recurring_bills"),
    ("⚖️ Budget vs Actual", "budget_vs_actual"),
    ("🏺 Sinking Funds", "sinking_funds"),
    ("🔮 Forecast", "forecast"),
    ("🔔 Notifications", "notifications"),
    ("📋 Plans & Bills", "plans_bills"),
    ("📱 Import & SMS", "import_sms"),
    ("🤖 Money Coach", "money_coach"),
    ("👨‍👩‍👧 Family & Sharing", "family"),
    ("📊 Reports", "reports"),
    ("👤 My Profile", "profile"),
]

ADMIN_NAV = ("🛠️ Admin", "admin")
