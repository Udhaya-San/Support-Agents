"""
core/models.py  -  the database tables (one Python class = one table).

Uses SQLAlchemy, so the same code works on SQLite now and PostgreSQL later.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ----------------------------------------------------------------------------
# Fixed values used all over the project (kept here so there is ONE place to change)
# ----------------------------------------------------------------------------
STATUSES = [
    "NEW", "OPEN", "ASSIGNED", "IN PROGRESS", "PENDING INFORMATION",
    "WAITING FOR APPROVAL", "ESCALATED", "RESOLVED", "CLOSED", "REOPENED",
]

PRIORITIES = ["Low", "Medium", "High", "Critical"]          # lowest to highest

SLA_HOURS = {"Low": 48, "Medium": 24, "High": 8, "Critical": 2}   # from the assignment

DEPARTMENTS = ["Admin", "IT", "HR", "Accounts", "Compliance"]

# Ticket ID prefix per department, e.g. ACC-2026-001
DEPT_PREFIX = {"Admin": "ADM", "IT": "IT", "HR": "HR", "Accounts": "ACC", "Compliance": "CMP"}


class Base(DeclarativeBase):
    pass


# ----------------------------------------------------------------------------
# Table 1: tickets  (one row per ticket)
# ----------------------------------------------------------------------------
class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)   # ACC-2026-001
    customer_name: Mapped[str] = mapped_column(String(100), default="Customer")
    customer_email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="Admin")            # what kind of issue
    department: Mapped[str] = mapped_column(String(30), default="Admin")          # who owns it
    priority: Mapped[str] = mapped_column(String(10), default="Medium")
    status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # e.g. Accounts_Agent
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)   # SLA deadline
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0)


# ----------------------------------------------------------------------------
# Table 2: ticket_events  (history: every change is one row)
# ----------------------------------------------------------------------------
class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(20), index=True)
    event_type: Mapped[str] = mapped_column(String(30))        # created, status_change, assigned, escalated, note
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    by_agent: Mapped[str] = mapped_column(String(50), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ----------------------------------------------------------------------------
# Table 3: agent_messages  (the structured agent-to-agent messages from the assignment)
# ----------------------------------------------------------------------------
class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(20), index=True)
    from_agent: Mapped[str] = mapped_column(String(50))
    to_agent: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ----------------------------------------------------------------------------
# Table 4: notifications  (what the customer / supervisor were told)
# ----------------------------------------------------------------------------
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(20), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="ui")    # ui, email, slack, sms
    recipient: Mapped[str] = mapped_column(String(150))
    text: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(20), default="sent")


# ============================================================================
# MOCK COMPANY DATA (fake data the agents look up; filled by core/seed.py)
# In a real company these would be the finance, HR, IT and compliance systems.
# ============================================================================
class MockPayment(Base):
    """Accounts Agent looks here: vendor invoices and payment status."""
    __tablename__ = "mock_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(String(20), unique=True, index=True)   # INV-1001
    vendor: Mapped[str] = mapped_column(String(100))
    amount: Mapped[int] = mapped_column(Integer)                                   # in rupees
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))                # PENDING, PAID, REFUNDED
    approval_status: Mapped[str] = mapped_column(String(20))       # COMPLETE, INCOMPLETE, PENDING
    paid_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class MockApproval(Base):
    """Compliance Agent looks here: who approved what, and the compliance check result."""
    __tablename__ = "mock_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref: Mapped[str] = mapped_column(String(30), unique=True)      # APR-1001-L1
    invoice_no: Mapped[str] = mapped_column(String(20), index=True)
    level: Mapped[str] = mapped_column(String(5))                  # L1, L2
    approver: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))                # APPROVED, PENDING, REJECTED
    compliance_check: Mapped[str] = mapped_column(String(20))      # COMPLIANT, NOT CHECKED, NON-COMPLIANT
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class MockEmployee(Base):
    """HR Agent looks here: leave balance and shift."""
    __tablename__ = "mock_employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(10), unique=True, index=True)  # EMP001
    name: Mapped[str] = mapped_column(String(100))
    department: Mapped[str] = mapped_column(String(50))
    casual_leave: Mapped[int] = mapped_column(Integer)
    sick_leave: Mapped[int] = mapped_column(Integer)
    earned_leave: Mapped[int] = mapped_column(Integer)
    shift: Mapped[str] = mapped_column(String(30))


class MockITAccount(Base):
    """IT Agent looks here: user accounts, lock status and software access."""
    __tablename__ = "mock_it_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)     # ravi.kumar
    employee_id: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))                # ACTIVE, LOCKED
    last_password_reset: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    software_access: Mapped[str] = mapped_column(String(200))      # comma separated list