import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from models.base import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)  # e.g., "USER_LOGIN", "EXPENSE_CREATED"
    details = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    type = Column(String, default="info", nullable=False)  # warning, info, alert, success
    is_read = Column(Boolean, default=False, nullable=False)
    channel = Column(String, default="in_app", nullable=False)  # in_app, email
    sent_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    household = relationship("Household", back_populates="notifications")

class Report(Base):
    __tablename__ = "reports"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # PDF, Excel, CSV
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    household = relationship("Household", back_populates="reports")

class FinancialScore(Base):
    __tablename__ = "financial_scores"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    score = Column(Float, nullable=False)  # 0-100
    date = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    details = Column(Text, nullable=True)  # JSON-formatted breakups
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    household = relationship("Household", back_populates="financial_scores")

class AIInsight(Base):
    __tablename__ = "ai_insights"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # coach_chat, affordability, monthly_review, anomaly
    query = Column(Text, nullable=True)
    prompt = Column(Text, nullable=True)
    response = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Relationships
    household = relationship("Household", back_populates="ai_insights")

class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    content_type = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class EmailLog(Base):
    __tablename__ = "email_logs"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False)  # Success, Simulated, Failed: <error>
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
