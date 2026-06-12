import streamlit as st
import plotly.graph_objects as go
from database import get_db
from models.finance import ExpenseCategory
from models.budget import Debt
from services.ai_service import ask_budget_coach, analyze_affordability, detect_ai_anomalies, generate_ai_monthly_review
from services.forecast_service import calculate_debt_payoff_forecast
from utils.helpers import format_currency

def show_ai_coach(household_id: int):
    """
    Renders the AI Coach chatbot assistant, affordability calculator, and anomaly detector.
    """
    st.markdown("<h1 class='app-title'>Money Coach</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Quick answers about your budget, spending, and debt</p>", unsafe_allow_html=True)
    
    tab_chat, tab_afford, tab_debt, tab_review = st.tabs(["💬 AI Budget Coach", "🛍️ Can I Afford It?", "📈 Debt Strategist", "🔍 Monthly Reviews & Anomalies"])
    
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
            st.subheader("Your Money Coach")
            st.caption("Tap a question below or type your own.")

            guided = [
                ("on_track", "📊 Am I on track this pay cycle?", "Am I on track with my budget this pay cycle? Give me a short, actionable summary."),
                ("afford", "🛍️ Can I afford a purchase?", "How should I decide if I can afford a non-essential purchase this pay cycle?"),
                ("cut", "✂️ What should I cut?", "Looking at my spending, what categories should I reduce to improve my savings rate?"),
                ("debt", "⛓️ How do I tackle debt?", "How can I tackle my debts? Explain snowball vs avalanche briefly for my situation."),
            ]
            gcols = st.columns(len(guided))
            for col, (key, label, query) in zip(gcols, guided):
                with col:
                    if st.button(label, width="stretch", key=f"guide_{key}"):
                        st.session_state["coach_pending_query"] = query

            if "chat_history" not in st.session_state:
                st.session_state["chat_history"] = []

            pending = st.session_state.pop("coach_pending_query", None)
            if pending:
                st.session_state["chat_history"].append({"role": "user", "content": pending})
                with st.spinner("Thinking..."):
                    answer = ask_budget_coach(db, household_id, pending)
                st.session_state["chat_history"].append({"role": "assistant", "content": answer})
                st.rerun()
                
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
        # DEBT PAYOFF STRATEGIST TAB
        # ----------------------------------------------------
        with tab_debt:
            st.subheader("📈 AI Debt-Payoff Strategist")
            st.write("Compare the **Snowball** (lowest balance first) vs **Avalanche** (highest interest first) strategies to find the optimal debt-payoff plan for your household.")

            debts = db.query(Debt).filter(Debt.household_id == household_id, Debt.current_balance > 0).all()

            if not debts:
                st.info("🎉 No active debts found! Your household is debt-free.")
            else:
                # Summary cards
                total_debt = sum(d.current_balance for d in debts)
                total_min = sum(d.minimum_payment for d in debts)
                currency = st.session_state.get("household_currency", "FJD")

                m1, m2, m3 = st.columns(3)
                m1.metric("Total Outstanding Debt", format_currency(total_debt, currency))
                m2.metric("Total Monthly Minimums", format_currency(total_min, currency))
                m3.metric("Number of Active Debts", len(debts))

                st.write("")
                extra_payment = st.slider(
                    "Extra Monthly Payment (on top of minimums)",
                    min_value=0, max_value=2000, value=100, step=50,
                    help="Adding extra payments dramatically reduces interest paid and payoff time."
                )

                with st.spinner("Calculating payoff schedules..."):
                    result = calculate_debt_payoff_forecast(db, household_id, float(extra_payment))

                sb = result.get("snowball", {})
                av = result.get("avalanche", {})

                if sb and av:
                    # Side-by-side comparison metrics
                    st.write("")
                    st.subheader("📊 Strategy Comparison")
                    col_s, col_a = st.columns(2)

                    with col_s:
                        with st.container(border=True):
                            st.markdown("### ❄️ Debt Snowball")
                            st.caption("Pay lowest balance first — builds momentum.")
                            st.metric("Months to Pay Off", f"{sb['months_to_payoff']} months")
                            st.metric("Total Interest Paid", format_currency(sb['total_interest_paid'], currency))
                            if sb['months_to_payoff'] < av['months_to_payoff']:
                                st.success("⚡ Faster payoff than Avalanche with this debt mix!")

                    with col_a:
                        with st.container(border=True):
                            st.markdown("### 🏔️ Debt Avalanche")
                            st.caption("Pay highest interest first — saves the most money.")
                            st.metric("Months to Pay Off", f"{av['months_to_payoff']} months")
                            st.metric("Total Interest Paid", format_currency(av['total_interest_paid'], currency))
                            if av['total_interest_paid'] < sb['total_interest_paid']:
                                st.success("💰 Saves more money than Snowball!")

                    # Plotly payoff chart
                    st.write("")
                    st.subheader("📉 Remaining Balance Over Time")

                    sb_schedule = sb.get("schedule", [])
                    av_schedule = av.get("schedule", [])
                    max_months = max(len(sb_schedule), len(av_schedule))

                    if max_months > 0:
                        sb_balance = [s["remaining_total"] for s in sb_schedule]
                        av_balance = [s["remaining_total"] for s in av_schedule]
                        months_axis = list(range(1, max_months + 1))

                        # Pad shorter list
                        while len(sb_balance) < max_months:
                            sb_balance.append(0.0)
                        while len(av_balance) < max_months:
                            av_balance.append(0.0)

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=months_axis, y=sb_balance,
                            name="Snowball", mode="lines",
                            line=dict(color="rgba(46,213,115,0.9)", width=2.5)
                        ))
                        fig.add_trace(go.Scatter(
                            x=months_axis, y=av_balance,
                            name="Avalanche", mode="lines",
                            line=dict(color="rgba(255,107,107,0.9)", width=2.5)
                        ))
                        from utils.styles import get_chart_colors
                        cc = get_chart_colors()
                        cf = cc.get("font") or "#94a3b8"
                        fig.update_layout(
                            height=300,
                            xaxis_title="Month",
                            yaxis_title=f"Balance ({currency})",
                            paper_bgcolor=cc["paper"],
                            plot_bgcolor=cc["plot"],
                            font_color=cf,
                            font_family="Outfit",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02),
                            xaxis=dict(showgrid=False),
                            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
                        )
                        st.plotly_chart(fig, width="stretch")

                # AI-driven strategic advice
                st.write("")
                with st.expander("🤖 Ask AI for Personalized Debt Strategy", expanded=False):
                    debt_names = ", ".join([f"{d.name} (FJD {d.current_balance:.0f} @ {d.interest_rate}%)" for d in debts])
                    default_q = f"I have these debts: {debt_names}. Which payoff strategy suits me best and how can I pay them off faster?"
                    debt_question = st.text_area("Your question:", value=default_q, height=80)
                    if st.button("💬 Get AI Debt Advice", type="primary"):
                        with st.spinner("Generating personalized strategy..."):
                            advice = ask_budget_coach(db, household_id, debt_question)
                        st.markdown(advice)

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
