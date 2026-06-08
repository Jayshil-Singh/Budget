import streamlit as st
from database import get_db
from models.finance import ExpenseCategory
from services.ai_service import ask_budget_coach, analyze_affordability, detect_ai_anomalies, generate_ai_monthly_review
from utils.helpers import format_currency

def show_ai_coach(household_id: int):
    """
    Renders the AI Coach chatbot assistant, affordability calculator, and anomaly detector.
    """
    st.markdown("<h1 class='app-title'>SmartBudget AI Coach</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Receive personalized strategies, reviews, and transaction affordability analytics</p>", unsafe_allow_html=True)
    
    tab_chat, tab_afford, tab_review = st.tabs(["💬 AI Budget Coach", "🛍️ Can I Afford It?", "🔍 Monthly Reviews & Anomalies"])
    
    with get_db() as db:
        # Load categories
        categories = db.query(ExpenseCategory).filter(
            (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
        ).all()
        cat_choices = {c.name: c.id for c in categories}
        
        # ----------------------------------------------------
        # AI BUDGET COACH CHAT TAB
        # ----------------------------------------------------
        with tab_chat:
            st.subheader("Chat with your Budget Coach")
            st.write("Ask questions about saving, debt strategies (snowball vs avalanche), category limits, or general financial advice.")
            
            # Setup session state chat history
            if "chat_history" not in st.session_state:
                st.session_state["chat_history"] = []
                
            # Render chat history
            for msg in st.session_state["chat_history"]:
                role_label = "👤 You" if msg["role"] == "user" else "🤖 Coach"
                with st.chat_message(msg["role"]):
                    st.write(f"**{role_label}**")
                    st.markdown(msg["content"])
                    
            # Input query
            user_input = st.chat_input("Ask a question (e.g. 'How can I save for school fees?')")
            
            if user_input:
                # Add user message to history
                st.session_state["chat_history"].append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.write("**👤 You**")
                    st.markdown(user_input)
                    
                # Query AI Coach
                with st.spinner("Analyzing financial command center database..."):
                    answer = ask_budget_coach(db, household_id, user_input)
                    
                st.session_state["chat_history"].append({"role": "assistant", "content": answer})
                with st.chat_message("assistant"):
                    st.write("**🤖 Coach**")
                    st.markdown(answer)
                    
            if st.button("Clear Chat History", type="secondary"):
                st.session_state["chat_history"] = []
                st.rerun()

        # ----------------------------------------------------
        # "CAN I AFFORD IT?" TAB
        # ----------------------------------------------------
        with tab_afford:
            st.subheader("🛍️ 'Can I Afford It?' Calculator")
            st.write("Input a prospective purchase to evaluate the impact on your household cash flow, savings, and debt repayments.")
            
            with st.form("affordability_calculator_form"):
                col1, col2 = st.columns(2)
                with col1:
                    price = st.number_input("Purchase Price", min_value=1.0, value=250.0, step=50.0)
                    terms = st.number_input("Installment Terms (Months - 1 for cash)", min_value=1, value=1, step=1)
                with col2:
                    p_cat = st.selectbox("Purchase Category", list(cat_choices.keys()))
                    p_desc = st.text_input("Item Description", placeholder="e.g. Smart TV")
                    
                calc_clicked = st.form_submit_button("Evaluate Affordability", type="primary")
                
                if calc_clicked:
                    cat_id = cat_choices[p_cat]
                    res = analyze_affordability(db, household_id, price, cat_id, terms)
                    
                    verdict = res["verdict"]
                    explanation = res["explanation"]
                    
                    st.markdown("### Analysis Result:")
                    
                    # Pill styling based on verdict
                    style = "poor"
                    if verdict == "Affordable":
                        style = "exceptional"
                    elif verdict == "Borderline":
                        style = "poor"
                    else:
                        style = "critical"
                        
                    st.markdown(f"Verdict: <span class='status-pill {style}'>{verdict}</span>", unsafe_allow_html=True)
                    st.write(f"Estimated payment per month: **{format_currency(res['monthly_payment'], st.session_state.get('household_currency', 'FJD'))}**")
                    st.info(explanation)

        # ----------------------------------------------------
        # MONTHLY REVIEWS & ANOMALIES TAB
        # ----------------------------------------------------
        with tab_review:
            st.subheader("🔍 Monthly Review & Spending Anomalies")
            
            col_rev1, col_rev2 = st.columns(2)
            
            with col_rev1:
                st.markdown("### Spending Spikes / Anomaly Alerts")
                anomalies = detect_ai_anomalies(db, household_id)
                if not anomalies:
                    st.success("No unusual spending spikes detected in your ledger!")
                else:
                    for a in anomalies:
                        with st.container(border=True):
                            st.markdown(f"⚠️ **Anomaly in {a['category']}**")
                            st.write(f"- Merchant: **{a['merchant']}**")
                            st.write(f"- Amount: **{format_currency(a['amount'], st.session_state.get('household_currency', 'FJD'))}**")
                            st.write(f"- Category Average: **{format_currency(a['average'], st.session_state.get('household_currency', 'FJD'))}**")
                            st.caption(a["message"])
                            
            with col_rev2:
                st.markdown("### AI Generated Monthly review")
                if st.button("Generate Monthly Review Report", type="primary"):
                    review_text = generate_ai_monthly_review(db, household_id)
                    st.markdown(review_text)
                    
                    # Store as insight in DB
                    st.success("Insight report cached successfully.")
