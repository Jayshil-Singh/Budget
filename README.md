# 🇫🇯 SmartBudget AI — Household Financial Management Command Center

SmartBudget AI is a Streamlit household budgeting app tailored for Fiji — **payday-to-payday** tracking, local bank CSV import, AI coaching, collaboration, and bill reminders.

---

## 🚀 Key Features

* **Specialized navigation:** Dashboard, Income Setup, Pay Schedule, Budget Setup, Expense Setup, Recurring Bills, Budget vs Actual, Sinking Funds, Forecast, Plans & Bills, and more.
* **Payday-to-payday budgeting:** Pay periods, category limits, and variance tracking.
* **Day-before email digest:** Bills, subscriptions, recurring expenses, debt, sinking funds, and goals — with budget context.
* **Mark paid:** Recurring bills and subscriptions log payment and update schedules.
* **AI Financial Coach:** OpenAI with rule-based fallback.
* **Fiji Bank Import:** ANZ, BSP, Westpac, HFC, BRED CSV + SMS paste; fuzzy auto-match to Money Log.
* **Debt payoff, subscriptions, sinking funds, calendar, budget/goal alerts.**
* **JSON household export** from Profile.
* **Light / dark / system theme** per user.

---

## 🛠️ Tech Stack

- **Frontend:** Streamlit + custom CSS
- **Database:** SQLite + SQLAlchemy
- **Charts:** Plotly
- **Calendar:** Native month grid (works in nested tabs)

---

## 📦 Getting Started

```powershell
.\venv\Scripts\activate
python -m pip install -r requirements.txt
```

Create `.env` from `.env.example` (SMTP for real emails):

```env
DATABASE_URL=sqlite:///smartbudget.db
OPENAI_API_KEY=your-key
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=you@example.com
EMAIL_SMTP_PASSWORD=your-app-password
```

```powershell
streamlit run app.py
pytest tests/ -v
```

### Scheduled reminders (hourly, without opening the app)

```powershell
python scripts/run_background_jobs.py
```

Schedule in **Windows Task Scheduler** or cron **every hour**. Payment reminders start one day before due dates and repeat hourly until you confirm in the app (or update your bills). The next reminder is sent one day before the next upcoming payment.

> `smartbudget.db` is gitignored — do not commit live household data.

---

## 🔑 Demo Credentials

| Role | Email | Password |
| :--- | :--- | :--- |
| **Admin** | `admin@smartbudget.local` | `AdminPass123!` |
| **Owner** | `owner@smartbudget.local` | `OwnerPass123!` |
| **Partner** | `partner@smartbudget.local` | `PartnerPass123!` |
| **Viewer** | `viewer@smartbudget.local` | `ViewerPass123!` |

---

## 📂 Navigation map

| Sidebar | Purpose |
| :--- | :--- |
| Dashboard | Overview, quick links, upcoming bills |
| Income Setup | One-off & recurring income log |
| Pay Schedule | Recurring pay templates |
| Budget Setup | Pay cycle, periods, **category limits**, reminders |
| Expense Setup | One-off expenses + receipts |
| Recurring Bills | Fixed repeating bills |
| Budget vs Actual | Limits vs spending this cycle |
| Sinking Funds / Forecast | Savings pots & cashflow tool |
| Plans & Bills | Subscriptions, goals, debts, calendar |

---

## 📂 Project Structure

- `app.py` — routing & navigation (`utils/navigation.py`)
- `scripts/run_background_jobs.py` — hourly reminders & auto-post
- `services/` — business logic
- `views/` — Streamlit pages
- `tests/` — pytest suite
