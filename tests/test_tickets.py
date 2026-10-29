"""
tests/test_tickets.py  -  checks the ticket engine and mock data (NO AI, no OpenAI cost).

Run from the project root:
    python tests\\test_tickets.py

It uses its own throw-away database (test_support.db), so your real support.db is never touched.
"""

import os
import sys
from datetime import date, datetime, timedelta

# Make the project root importable, and use a separate test database BEFORE importing core
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["DATABASE_URL"] = "sqlite:///test_support.db"

from sqlalchemy import select  # noqa: E402

from core.db import engine, get_session, init_db  # noqa: E402
from core.models import Base, MockPayment, Ticket, TicketEvent  # noqa: E402
from core.seed import seed_mock_data  # noqa: E402
from core.ticket_service import (  # noqa: E402
    InvalidTransition, create_ticket, get_agent_messages, get_ticket,
    log_agent_message, update_status,
)


def reset():
    """Empty database before every test."""
    Base.metadata.drop_all(engine)
    init_db()


def expect_error(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"Expected {exc_type.__name__} but nothing was raised")


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------
def test_ticket_ids_are_sequential_per_department():
    reset()
    year = datetime.now().year
    assert create_ticket("a", "d", "Accounts")["ticket_id"] == f"ACC-{year}-001"
    assert create_ticket("b", "d", "Accounts")["ticket_id"] == f"ACC-{year}-002"
    assert create_ticket("c", "d", "IT")["ticket_id"] == f"IT-{year}-001"
    assert create_ticket("d", "d", "HR")["ticket_id"] == f"HR-{year}-001"
    assert create_ticket("e", "d", "Compliance")["ticket_id"] == f"CMP-{year}-001"
    assert create_ticket("f", "d", "Admin")["ticket_id"] == f"ADM-{year}-001"


def test_new_ticket_is_open_and_assigned():
    reset()
    t = create_ticket("Vendor payment", "20 days", "Accounts", "Medium")
    assert t["status"] == "OPEN"
    assert t["assigned_to"] == "Accounts_Agent"
    assert get_ticket(t["ticket_id"])["subject"] == "Vendor payment"
    assert get_ticket("NOPE-1") is None


def test_sla_hours_match_priority():
    reset()
    expected = {"Low": 48, "Medium": 24, "High": 8, "Critical": 2}
    for priority, hours in expected.items():
        t = create_ticket("x", "d", "IT", priority)
        fmt = "%Y-%m-%d %H:%M"
        diff = datetime.strptime(t["due_at"], fmt) - datetime.strptime(t["created_at"], fmt)
        assert diff == timedelta(hours=hours), f"{priority}: {diff}"


def test_invalid_input_is_rejected():
    reset()
    expect_error(ValueError, create_ticket, "x", "d", "Cooking")
    expect_error(ValueError, create_ticket, "x", "d", "IT", "Urgent")
    expect_error(ValueError, create_ticket, "   ", "d", "IT")


def test_normal_lifecycle():
    reset()
    tid = create_ticket("x", "d", "Accounts")["ticket_id"]
    assert update_status(tid, "IN PROGRESS", "Accounts_Agent")["status"] == "IN PROGRESS"
    done = update_status(tid, "RESOLVED", "Accounts_Agent", resolution="Fixed the workflow.")
    assert done["status"] == "RESOLVED" and done["resolution"] == "Fixed the workflow."
    with get_session() as s:
        assert s.scalars(select(Ticket).where(Ticket.ticket_id == tid)).first().resolved_at is not None
    assert update_status(tid, "CLOSED", "Admin_Agent")["status"] == "CLOSED"


def test_illegal_status_moves_are_blocked():
    reset()
    tid = create_ticket("x", "d", "IT")["ticket_id"]
    expect_error(InvalidTransition, update_status, tid, "CLOSED")          # OPEN -> CLOSED not allowed
    expect_error(InvalidTransition, update_status, tid, "FLYING")          # not a status at all
    update_status(tid, "RESOLVED")
    expect_error(InvalidTransition, update_status, tid, "IN PROGRESS")     # RESOLVED -> IN PROGRESS
    update_status(tid, "CLOSED")
    expect_error(InvalidTransition, update_status, tid, "IN PROGRESS")     # CLOSED -> IN PROGRESS
    expect_error(ValueError, update_status, "NOPE-1", "OPEN")              # unknown ticket


def test_reopen_and_escalate():
    reset()
    tid = create_ticket("x", "d", "HR")["ticket_id"]
    update_status(tid, "RESOLVED")
    update_status(tid, "CLOSED")
    assert update_status(tid, "REOPENED")["status"] == "REOPENED"
    with get_session() as s:
        assert s.scalars(select(Ticket).where(Ticket.ticket_id == tid)).first().resolved_at is None
    t = update_status(tid, "ESCALATED", "system")
    assert t["escalated"] is True
    with get_session() as s:
        assert s.scalars(select(Ticket).where(Ticket.ticket_id == tid)).first().escalation_count == 1


def test_history_events_are_recorded():
    reset()
    tid = create_ticket("x", "d", "IT")["ticket_id"]
    update_status(tid, "IN PROGRESS", "IT_Agent", note="Checking the laptop")
    with get_session() as s:
        events = s.scalars(select(TicketEvent).where(TicketEvent.ticket_id == tid).order_by(TicketEvent.id)).all()
    kinds = [e.event_type for e in events]
    assert kinds == ["created", "assigned", "status_change", "note"], kinds
    assert (events[2].old_value, events[2].new_value) == ("OPEN", "IN PROGRESS")


def test_agent_messages_format_and_validation():
    reset()
    tid = create_ticket("x", "d", "Accounts")["ticket_id"]
    m = log_agent_message(tid, "Accounts Agent", "Compliance_Agent", "Please verify approval status.")
    assert list(m.keys()) == ["ticket_id", "from_agent", "to_agent", "message", "timestamp"]
    assert m["from_agent"] == "Accounts_Agent"                         # space fixed to underscore
    datetime.strptime(m["timestamp"], "%Y-%m-%d %I:%M %p")             # format like 2026-01-15 10:30 AM
    log_agent_message(tid, "Compliance_Agent", "Accounts_Agent", "Approval verified.")
    msgs = get_agent_messages(tid)
    assert [x["from_agent"] for x in msgs] == ["Accounts_Agent", "Compliance_Agent"]
    expect_error(ValueError, log_agent_message, tid, "Accounts_Agent", "Chef_Agent", "hi")
    expect_error(ValueError, log_agent_message, tid, "Accounts_Agent", "HR_Agent", "  ")
    expect_error(ValueError, log_agent_message, "NOPE-1", "Accounts_Agent", "HR_Agent", "hi")


def test_mock_data_matches_the_assignment_example():
    reset()
    counts = seed_mock_data()
    assert counts == {"payments": 5, "approvals": 5, "employees": 4, "it_accounts": 4}
    seed_mock_data()                                                   # running twice must not duplicate
    with get_session() as s:
        p = s.scalars(select(MockPayment).where(MockPayment.invoice_no == "INV-1001")).first()
        assert p.status == "PENDING" and p.approval_status == "INCOMPLETE"
        assert (date.today() - p.due_date).days == 20
        assert len(s.scalars(select(MockPayment)).all()) == 5


# ----------------------------------------------------------------------------
# Tiny test runner (also works with pytest)
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    tests.sort(key=lambda x: x[1].__code__.co_firstlineno)
    failed = 0
    for name, func in tests:
        try:
            func()
            print("PASS ", name)
        except Exception as e:                                         # noqa: BLE001
            failed += 1
            print("FAIL ", name, "->", repr(e))
    engine.dispose()
    if os.path.exists("test_support.db"):
        os.remove("test_support.db")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
