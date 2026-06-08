import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from models.base import Base

class Budget(Base):
    __tablename__ = "budgets"
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id", ondelete="CASCADE"), nullable=True) # Payday cycle budget
    month = Column(Integer, nullable=True)  # Calendar month (1-12)
    year = Column(Integer, nullable=True)   # Calendar year
    name = Column(String, nullable=False)   # e.g., "June 2026 Budget" or "Period 24 Budget"
    total_limit = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="budgets")
    pay_period = relationship("PayPeriod", back_populates="budgets")
    items = relationship("BudgetItem", back_populates="budget", cascade="all, delete-orphan")

class BudgetItem(Base):
    __tablename__ = "budget_items"
    
    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("expense_categories.id", ondelete="CASCADE"), nullable=False)
    limit_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    budget = relationship("Budget", back_populates="items")
    category = relationship("ExpenseCategory", back_populates="budget_items")

class SinkingFund(Base):
    __tablename__ = "sinking_funds"
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, nullable=False, default=0.0)
    target_date = Column(Date, nullable=False)
    contribution_amount = Column(Float, nullable=False)  # cycle/monthly contribution amount
    frequency = Column(String, default="payday", nullable=False)  # weekly, fortnightly, monthly, payday
    last_contribution = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="sinking_funds")

class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, nullable=False, default=0.0)
    target_date = Column(Date, nullable=False)
    priority = Column(String, default="medium", nullable=False)  # low, medium, high
    status = Column(String, default="active", nullable=False)    # active, achieved, paused
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="savings_goals")

class Debt(Base):
    __tablename__ = "debts"
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # Mortgage, Credit Card, Personal Loan, Vehicle Loan, Store Credit, Other
    current_balance = Column(Float, nullable=False)
    original_balance = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)  # percentage, e.g. 5.5
    minimum_payment = Column(Float, nullable=False)
    payment_frequency = Column(String, default="monthly", nullable=False)  # weekly, fortnightly, monthly
    start_date = Column(Date, nullable=False)
    target_payoff_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="debts")
