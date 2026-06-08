import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from models.base import Base

class Household(Base):
    __tablename__ = "households"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    currency = Column(String, default="FJD", nullable=False)
    budget_method = Column(String, default="payday", nullable=False)  # weekly, fortnightly, monthly, payday
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    members = relationship("HouseholdMember", back_populates="household", cascade="all, delete-orphan")
    settings = relationship("Setting", back_populates="household", cascade="all, delete-orphan")
    income_records = relationship("Income", back_populates="household", cascade="all, delete-orphan")
    expense_records = relationship("Expense", back_populates="household", cascade="all, delete-orphan")
    categories = relationship("ExpenseCategory", back_populates="household", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="household", cascade="all, delete-orphan")
    sinking_funds = relationship("SinkingFund", back_populates="household", cascade="all, delete-orphan")
    savings_goals = relationship("SavingsGoal", back_populates="household", cascade="all, delete-orphan")
    debts = relationship("Debt", back_populates="household", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="household", cascade="all, delete-orphan")
    bank_transactions = relationship("BankTransaction", back_populates="household", cascade="all, delete-orphan")
    pay_periods = relationship("PayPeriod", back_populates="household", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="household", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="household", cascade="all, delete-orphan")
    financial_scores = relationship("FinancialScore", back_populates="household", cascade="all, delete-orphan")
    ai_insights = relationship("AIInsight", back_populates="household", cascade="all, delete-orphan")

class HouseholdMember(Base):
    __tablename__ = "household_members"
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False, default="viewer")  # owner, partner, viewer
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Unique constraint so a user is only added once per household
    __table_args__ = (UniqueConstraint('household_id', 'user_id', name='_household_user_uc'),)
    
    # Relationships
    household = relationship("Household", back_populates="members")
    user = relationship("User", back_populates="household_memberships")

class Setting(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Unique constraint per household setting key
    __table_args__ = (UniqueConstraint('household_id', 'key', name='_household_setting_key_uc'),)
    
    # Relationships
    household = relationship("Household", back_populates="settings")
