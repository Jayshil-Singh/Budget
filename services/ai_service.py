import datetime
import openai
from sqlalchemy.orm import Session as DBSession
from models.finance import Income, Expense, ExpenseCategory, Subscription
from models.budget import Budget, SavingsGoal, Debt, SinkingFund
from models.audit import AIInsight
import config
from utils.helpers import format_currency

def auto_tag_category(merchant: str, categories: list) -> str:
    """
    Suggests the best matching expense category based on the merchant/description name
    using keyword matching. Returns the category name string.
    """
    merchant_lower = merchant.lower().strip()

    # Keyword mapping for common Fiji/Pacific merchants and categories
    keyword_map = {
        "groceries": ["supermarket", "mh", "foodtown", "new world", "price right", "lotus", "jacks", "mom's", "grocery"],
        "fuel": ["shell", "mobil", "bp", "pacific energy", "petrol", "fuel", "gas"],
        "utilities": ["flf", "fiji electricity", "awt", "water", "power", "electricity", "utility", "telecom", "water authority"],
        "transport": ["bus", "taxi", "uber", "transport", "cab", "ferry", "pacific transport", "fijibus"],
        "healthcare": ["cwr", "colonialwar", "hospita", "clinic", "pharma", "chemist", "medical", "doctor", "dental", "health"],
        "education": ["university", "school", "college", "fnu", "usp", "fees", "tuition", "books", "stationary"],
        "dining": ["restaurant", "cafe", "pizza", "mcdonald", "kfc", "burger", "food court", "eatery", "dine"],
        "entertainment": ["cinema", "fiji cinema", "netflix", "spotify", "disney", "game", "entertainment"],
        "insurance": ["colonial", "anz insurance", "qbe", "sun insurance", "tower", "insurance", "life"],
        "rent": ["rent", "lease", "apartment", "landlord", "accommodation", "housing"],
        "internet": ["connect", "inkk", "digicel", "vodafone", "internet", "broadband", "data"],
        "clothing": ["jacks of fiji", "rups", "court", "clothing", "fashion", "shoes", "apparel"],
    }

    for cat_keyword, keywords in keyword_map.items():
        for kw in keywords:
            if kw in merchant_lower:
                # Find closest matching category from provided list
                for cat_name in categories:
                    if cat_keyword in cat_name.lower():
                        return cat_name
                break

    return ""  # No suggestion found


def get_financial_context(db: DBSession, household_id: int) -> dict:

    """
    Assembles a dictionary representation of the household's financial health
    to inject into the AI context.
    """
    incomes = db.query(Income).filter(Income.household_id == household_id).all()
    expenses = db.query(Expense).filter(Expense.household_id == household_id).all()
    debts = db.query(Debt).filter(Debt.household_id == household_id).all()
    goals = db.query(SavingsGoal).filter(SavingsGoal.household_id == household_id).all()
    funds = db.query(SinkingFund).filter(SinkingFund.household_id == household_id).all()
    subs = db.query(Subscription).filter(Subscription.household_id == household_id, Subscription.status == "active").all()
    
    total_income = sum(i.amount for i in incomes)
    total_expense = sum(e.amount for e in expenses)
    remaining_balance = total_income - total_expense
    
    # Calculate category breakdowns
    category_summary = {}
    for exp in expenses:
        cat_name = exp.category.name if exp.category else "Other"
        category_summary[cat_name] = category_summary.get(cat_name, 0.0) + exp.amount
        
    debt_details = [{"name": d.name, "balance": d.current_balance, "interest": d.interest_rate} for d in debts]
    goal_details = [{"name": g.name, "target": g.target_amount, "current": g.current_amount} for g in goals]
    fund_details = [{"name": f.name, "target": f.target_amount, "current": f.current_amount} for f in funds]
    sub_details = [{"name": s.name, "amount": s.amount, "freq": s.frequency} for s in subs]
    
    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "remaining_balance": remaining_balance,
        "categories": category_summary,
        "debts": debt_details,
        "goals": goal_details,
        "sinking_funds": fund_details,
        "subscriptions": sub_details
    }

def ask_budget_coach(db: DBSession, household_id: int, user_query: str) -> str:
    """
    Sends a query to the OpenAI API pre-seeded with the household's financial context.
    If the OpenAI API key is missing or invalid, falls back to a rules-based response engine.
    """
    ctx = get_financial_context(db, household_id)
    
    # Build System Prompt
    system_prompt = f"""
    You are Antigravity AI, the Budget Coach for "SmartBudget AI". 
    You are an expert financial consultant helping a household in Fiji manage their finances.
    
    Here is their current financial context:
    - Currency: FJD (default) or FJD equivalents
    - Current Income Total: {ctx['total_income']:.2f}
    - Current Expenses Total: {ctx['total_expense']:.2f}
    - Cash Balance: {ctx['remaining_balance']:.2f}
    
    Active Subscriptions:
    {', '.join([f"{s['name']} ({s['amount']}/{s['freq']})" for s in ctx['subscriptions']]) if ctx['subscriptions'] else 'None'}
    
    Active Debts:
    {', '.join([f"{d['name']} (Balance: {d['balance']:.2f}, Interest: {d['interest']}%" for d in ctx['debts']]) if ctx['debts'] else 'None'}
    
    Active Savings Goals:
    {', '.join([f"{g['name']} (Saved: {g['current']:.2f}/{g['target']:.2f})" for g in ctx['goals']]) if ctx['goals'] else 'None'}
    
    Sinking Funds:
    {', '.join([f"{f['name']} (Saved: {f['current']:.2f}/{f['target']:.2f})" for f in ctx['sinking_funds']]) if ctx['sinking_funds'] else 'None'}
    
    Spending by Category:
    {', '.join([f"{k}: {v:.2f}" for k, v in ctx['categories'].items()]) if ctx['categories'] else 'No transaction data yet.'}
    
    Provide helpful, professional, SaaS-quality, and empathetic financial coaching. Explain snowball vs avalanche for debt, how to save for sinking funds (school fees, Christmas, vehicle), and guide them in Fiji dollar contexts. Keep answers concise, actionable, and formatted in clean markdown.
    """
    
    # Check if OpenAI is configured
    if not config.OPENAI_API_KEY:
        # Fallback rules engine
        return get_local_fallback_advice(user_query, ctx)
        
    try:
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.7,
            max_tokens=600
        )
        answer = response.choices[0].message.content
        
        # Save to DB cache
        insight = AIInsight(
            household_id=household_id,
            type="coach_chat",
            query=user_query,
            prompt=system_prompt[:1000],
            response=answer
        )
        db.add(insight)
        db.commit()
        return answer
    except Exception as e:
        print(f"[AI ERROR] Failed to connect to OpenAI: {e}")
        return get_local_fallback_advice(user_query, ctx) + "\n\n*(Note: Running in offline local fallback mode due to connection error)*"

def get_local_fallback_advice(query: str, ctx: dict) -> str:
    """
    A rule-based local financial engine that responds when the AI API is offline.
    """
    query_lower = query.lower()
    
    if "debt" in query_lower:
        if not ctx["debts"]:
            return "### SmartBudget AI Coach\n\nYou currently don't have any registered debts! That's a great position. Focus on building your **Emergency Fund** (aim for 3-6 months of essential expenses) and contributing to **Sinking Funds** for upcoming bills."
        
        debt_list = "\n".join([f"- **{d['name']}**: ${d['balance']:,.2f} at {d['interest']}% interest" for d in ctx["debts"]])
        return f"""### SmartBudget AI Coach - Debt Strategy

You currently have the following debts:
{debt_list}

**Strategy Recommendation:**
1. **Debt Snowball**: Pay off the smallest balance first (quick psychological wins), while making minimum payments on others.
2. **Debt Avalanche**: Pay off the highest interest rate first (saves the most money mathematically). In your case, focus extra payments on the debt with the highest percentage rate.
"""

    elif "save" in query_lower or "savings" in query_lower:
        if not ctx["goals"]:
            return "### SmartBudget AI Coach\n\nYou haven't created any savings goals yet. Navigate to the **Savings & Debt** tab and create a goal (e.g., 'Emergency Fund' or 'House Deposit') to track your savings progress!"
            
        goals_list = "\n".join([f"- **{g['name']}**: ${g['current']:,.2f} of ${g['target']:,.2f}" for g in ctx["goals"]])
        return f"""### SmartBudget AI Coach - Savings Progress

Here is your current savings progress:
{goals_list}

**Action Plan:**
- Try to save at least **20%** of your income.
- Set up automatic bank transfers to your savings account right on paydays.
- Use **Sinking Funds** for expected large expenses (like school terms or car maintenance) so you don't break your regular savings goals.
"""

    elif "budget" in query_lower:
        if ctx["total_income"] == 0:
            return "### SmartBudget AI Coach\n\nPlease add some income sources under the **Ledger** page first so we can help structure your budget limits."
            
        savings_pct = ((ctx["total_income"] - ctx["total_expense"]) / ctx["total_income"]) * 100 if ctx["total_income"] > 0 else 0
        return f"""### SmartBudget AI Coach - Budget Analysis

- **Total Monthly Income**: ${ctx['total_income']:,.2f}
- **Total Expenses**: ${ctx['total_expense']:,.2f}
- **Savings Rate**: {savings_pct:.1f}%

**Recommendations:**
- If your savings rate is below **10%**, review non-essential expenses like Dining Out and Entertainment.
- Keep fixed costs (Rent, Loans, Utilities) below **50%** of your net income.
- Ensure paydays allocate money straight to fixed expenses before any discretionary spending.
"""
        
    return f"""### SmartBudget AI Coach - Welcome!

I am your SmartBudget AI Coach. How can I help you today?

**Try asking me about:**
1. *"How can I tackle my debts?"*
2. *"Are my savings on track?"*
3. *"How can I improve my budget?"*
4. Use the **Affordability Calculator** below to analyze individual purchases.
"""

def analyze_affordability(
    db: DBSession, 
    household_id: int, 
    price: float, 
    category_id: int, 
    terms_months: int = 1
) -> dict:
    """
    Computes if a household can afford a purchase based on cashflow, debts, and savings.
    """
    ctx = get_financial_context(db, household_id)
    monthly_payment = price / terms_months if terms_months > 0 else price
    
    # Determine essential balance threshold
    balance = ctx["remaining_balance"]
    income = ctx["total_income"]
    
    # Decision metrics
    if balance < monthly_payment:
        verdict = "Not Recommended"
        explanation = f"Your current net savings balance (${balance:,.2f}) is lower than the required purchase payment (${monthly_payment:,.2f}). Making this purchase may push you into overdraft or force you to dip into critical emergency reserves."
    elif monthly_payment > (income * 0.15):
        verdict = "Not Recommended"
        explanation = f"This purchase payment represents {((monthly_payment/income)*100):.1f}% of your total income. Financial coaches recommend keeping individual non-essential purchases below 10% of monthly income to avoid cashflow strain."
    elif balance > price:
        verdict = "Affordable"
        explanation = f"You can afford to pay this in full immediately with your current surplus cash of ${balance:,.2f}. This will not impact your active loan obligations, provided you keep your non-essential spending minimal this cycle."
    else:
        verdict = "Borderline"
        explanation = f"While you have enough cash to handle the immediate monthly installment of ${monthly_payment:,.2f}, buying this on terms will reduce your monthly savings buffer for the next {terms_months} months. Ensure your sinking funds are fully funded first."
        
    return {
        "verdict": verdict,
        "monthly_payment": monthly_payment,
        "explanation": explanation
    }

def detect_ai_anomalies(db: DBSession, household_id: int) -> list[dict]:
    """
    Identifies transactions that are spending spikes or unusual category additions.
    """
    expenses = db.query(Expense).filter(Expense.household_id == household_id).all()
    if len(expenses) < 5:
        return []
        
    # Group by category
    cat_expenses = {}
    for exp in expenses:
        cat_expenses.setdefault(exp.category_id, []).append(exp.amount)
        
    anomalies = []
    
    for exp in expenses:
        amounts = cat_expenses[exp.category_id]
        if len(amounts) < 3:
            continue
            
        avg = sum(amounts) / len(amounts)
        # Anomaly if amount is 3x the category average and amount is > $50 (ignoring tiny differences)
        if exp.amount > (avg * 2.5) and exp.amount > 50.0:
            anomalies.append({
                "date": exp.date,
                "merchant": exp.merchant or "Unknown Merchant",
                "amount": exp.amount,
                "category": exp.category.name if exp.category else "Other",
                "average": avg,
                "message": f"Spending spike: ${exp.amount:,.2f} is significantly higher than your category average of ${avg:,.2f}."
            })
            
    return anomalies

def generate_ai_monthly_review(db: DBSession, household_id: int) -> str:
    """
    Generates a full AI monthly summary report.
    """
    ctx = get_financial_context(db, household_id)
    savings_pct = ((ctx["total_income"] - ctx["total_expense"]) / ctx["total_income"]) * 100 if ctx["total_income"] > 0 else 0
    
    debt_warning = ""
    if ctx["debts"]:
        total_debt = sum(d["balance"] for d in ctx["debts"])
        debt_warning = f"Your total outstanding debt is **${total_debt:,.2f}**. Consider allocating any extra payday surplus to clear the smallest balance first."
        
    review = f"""### AI Monthly Financial Review

#### 1. Performance Summary
- **Net Income**: ${ctx['total_income']:,.2f}
- **Expenses**: ${ctx['total_expense']:,.2f}
- **Savings Rate**: {savings_pct:.1f}%

#### 2. Key Insights
- **Savings Buffer**: Your current cycle net cash flow is **${ctx['remaining_balance']:,.2f}**. 
- **Debt Status**: {debt_warning if debt_warning else 'No outstanding debts detected. Keep it up!'}
- **Subscriptions**: You are spending **${sum(s['amount'] for s in ctx['subscriptions']):,.2f}** monthly across active subscriptions. Ensure you are utilizing these services.

#### 3. Action Plan for Next Cycle
1. Target reducing discretionary expenses (like Dining Out or Entertainment) by 10% to boost your savings rate to 20%.
2. Allocate at least $100 on your next payday directly to your **Sinking Funds** to prepare for upcoming bills.
"""
    return review
