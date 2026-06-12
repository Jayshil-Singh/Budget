import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from models.base import Base

class PayPeriod(Base):
    __tablename__ = "pay_periods"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    name = Column(String, nullable=False)  # e.g., "Period 24 (Jun 01 - Jun 14)"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="pay_periods")
    income_records = relationship("Income", back_populates="pay_period")
    expense_records = relationship("Expense", back_populates="pay_period")
    budgets = relationship("Budget", back_populates="pay_period")

class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=True) # Null means system category
    name = Column(String, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="categories")
    expense_records = relationship("Expense", back_populates="category")
    budget_items = relationship("BudgetItem", back_populates="category")
    subscriptions = relationship("Subscription", back_populates="category")

class Income(Base):
    __tablename__ = "income"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    source = Column(String, nullable=False)  # Salary, Business, Rental, Side Hustle, etc.
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False)
    is_recurring = Column(Boolean, default=False, nullable=False)
    frequency = Column(String, nullable=True)  # weekly, fortnightly, monthly, custom
    next_date = Column(Date, nullable=True)     # For forecasting
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id", ondelete="SET NULL"), nullable=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="income_records")
    pay_period = relationship("PayPeriod", back_populates="income_records")

class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False)
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id", ondelete="SET NULL"), nullable=True)
    is_recurring = Column(Boolean, default=False, nullable=False)
    frequency = Column(String, nullable=True)  # weekly, fortnightly, monthly
    merchant = Column(String, nullable=True)
    tags = Column(String, nullable=True)  # Comma separated
    notes = Column(String, nullable=True)
    attachment_id = Column(Integer, nullable=True)  # Linked to attachments table
    attachment_note = Column(String, nullable=True)  # Receipt reference or file path
    logged_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="expense_records")
    category = relationship("ExpenseCategory", back_populates="expense_records")
    pay_period = relationship("PayPeriod", back_populates="expense_records")

class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency = Column(String, default="monthly", nullable=False)  # monthly, annual
    next_renewal = Column(Date, nullable=False)
    category_id = Column(Integer, ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String, default="active", nullable=False)  # active, paused, cancelled
    service_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="subscriptions")
    category = relationship("ExpenseCategory", back_populates="subscriptions")

class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    account_bank = Column(String, nullable=False)  # ANZ, BSP, Westpac, HFC, Bred
    account_number = Column(String, nullable=True)
    transaction_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    reference = Column(String, nullable=True)
    status = Column(String, default="imported", nullable=False)  # imported, matched, duplicate
    matched_expense_id = Column(Integer, ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True)
    matched_income_id = Column(Integer, ForeignKey("income.id", ondelete="SET NULL"), nullable=True)
    category_id = Column(Integer, ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="bank_transactions")


class PaymentDueDate(Base):
    __tablename__ = "payment_due_dates"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(Date, nullable=False)
    is_paid = Column(Boolean, default=False, nullable=False)
    email_notified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    household = relationship("Household", back_populates="payment_due_dates")

