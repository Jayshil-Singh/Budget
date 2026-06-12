"""Category budget limits for the current pay period."""
import streamlit as st
from sqlalchemy.orm import Session as DBSession
from models.finance import ExpenseCategory, PayPeriod
from models.budget import Budget, BudgetItem
from services.finance_service import get_current_pay_period
from utils.helpers import format_currency, can_modify


def render_budget_limits_editor(db: DBSession, household_id: int, role: str, currency: str):
    """UI to set per-category limits for the active pay period."""
    st.markdown("---")
    st.subheader("📊 Category Budget Limits")
    st.caption("Set how much you plan to spend in each category for the **current pay cycle**.")

    period = get_current_pay_period(db, household_id)
    if not period:
        st.info("Generate pay periods under **Pay & Budget Cycle** above, then set limits here.")
        return

    categories = db.query(ExpenseCategory).filter(
        (ExpenseCategory.household_id == household_id) | (ExpenseCategory.is_system == True)
    ).all()
    cat_choices = {c.name: c.id for c in categories}

    budget = db.query(Budget).filter(
        Budget.household_id == household_id,
        Budget.pay_period_id == period.id,
    ).first()

    if not budget:
        st.info(f"No budget yet for **{period.name}**.")
        if can_modify(role) and st.button("Create budget for this period", type="primary", key="bs_create_bud"):
            budget = Budget(
                household_id=household_id,
                pay_period_id=period.id,
                name=f"Budget for {period.name}",
                total_limit=0.0,
            )
            db.add(budget)
            db.commit()
            st.rerun()
        return

    st.write(f"**Period:** {period.name}")

    if not can_modify(role):
        st.info("Read-only — viewers cannot edit limits.")
        items = db.query(BudgetItem).filter(BudgetItem.budget_id == budget.id).all()
        for item in items:
            if item.limit_amount > 0 and item.category:
                st.write(f"• {item.category.name}: {format_currency(item.limit_amount, currency)}")
        return

    with st.form("budget_setup_limits_form"):
        item_inputs = {}
        for cat_name, cat_id in cat_choices.items():
            item = db.query(BudgetItem).filter(
                BudgetItem.budget_id == budget.id,
                BudgetItem.category_id == cat_id,
            ).first()
            existing = item.limit_amount if item else 0.0
            item_inputs[cat_id] = st.number_input(
                f"{cat_name}", min_value=0.0, value=float(existing), step=10.0,
            )
        if st.form_submit_button("Save category limits", type="primary"):
            total = 0.0
            for cat_id, limit_val in item_inputs.items():
                total += limit_val
                item = db.query(BudgetItem).filter(
                    BudgetItem.budget_id == budget.id,
                    BudgetItem.category_id == cat_id,
                ).first()
                if item:
                    item.limit_amount = limit_val
                elif limit_val > 0:
                    db.add(BudgetItem(budget_id=budget.id, category_id=cat_id, limit_amount=limit_val))
            budget.total_limit = total
            db.commit()
            st.success("Category limits saved!")
            st.rerun()
