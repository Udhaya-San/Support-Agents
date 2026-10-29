"""
core/ticket_service.py  -  the ticket engine (plain Python, NO AI inside).

Step 8 : create_ticket   (Ticket ID + priority + SLA deadline)
Later  : state machine (step 9), agent messages (step 10) are added to this same file.

Why code and not AI? Ticket IDs, deadlines and rules must be exactly right every time.
The AI agents will CALL these functions as tools.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.db import get_session
from core.models import (DEPARTMENTS, DEPT_PREFIX, PRIORITIES, SLA_HOURS, AgentMessage, Ticket,
                         TicketEvent)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def agent_name_for(department: str) -> str:
    """Accounts -> Accounts_Agent"""
    return f"{department}_Agent"


def ticket_to_dict(t: Ticket) -> dict:
    """Turn a Ticket row into a simple dict (easy to print, show in Streamlit, or give to an agent)."""
    return {
        "ticket_id": t.ticket_id,
        "subject": t.subject,
        "description": t.description,
        "customer_name": t.customer_name,
        "customer_email": t.customer_email,
        "department": t.department,
        "priority": t.priority,
        "status": t.status,
        "assigned_to": t.assigned_to,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
        "due_at": t.due_at.strftime("%Y-%m-%d %H:%M") if t.due_at else None,
        "resolution": t.resolution,
        "escalated": t.escalated,
    }


def _next_ticket_id(session, department: str, year: int) -> str:
    """ACC-2026-001, ACC-2026-002 ... (a separate running number per department per year)."""
    prefix = f"{DEPT_PREFIX[department]}-{year}-"
    existing = session.scalars(select(Ticket.ticket_id).where(Ticket.ticket_id.like(prefix + "%"))).all()
    last = max((int(x.rsplit("-", 1)[1]) for x in existing), default=0)
    return f"{prefix}{last + 1:03d}"


# ----------------------------------------------------------------------------
# Step 8: create_ticket
# ----------------------------------------------------------------------------
def create_ticket(
    subject: str,
    description: str,
    department: str,
    priority: str = "Medium",
    customer_name: str = "Customer",
    customer_email: Optional[str] = None,
) -> dict:
    """Create a support ticket and return its details.

    department: one of Admin, IT, HR, Accounts, Compliance (who owns the ticket)
    priority:   one of Low, Medium, High, Critical (decides the SLA deadline)
    """
    if department not in DEPT_PREFIX:
        raise ValueError(f"Unknown department '{department}'. Use one of: {', '.join(DEPT_PREFIX)}")
    if priority not in PRIORITIES:
        raise ValueError(f"Unknown priority '{priority}'. Use one of: {', '.join(PRIORITIES)}")
    if not subject.strip():
        raise ValueError("Subject cannot be empty")

    now = datetime.now()

    # Retry a few times in the rare case two tickets get the same ID at the same moment.
    for _attempt in range(3):
        with get_session() as s:
            ticket = Ticket(
                ticket_id=_next_ticket_id(s, department, now.year),
                subject=subject.strip()[:200],
                description=description.strip(),
                customer_name=customer_name,
                customer_email=customer_email,
                category=department,
                department=department,
                priority=priority,
                status="OPEN",                                   # as in the assignment example
                assigned_to=agent_name_for(department),
                created_at=now,
                updated_at=now,
                due_at=now + timedelta(hours=SLA_HOURS[priority]),
            )
            s.add(ticket)
            try:
                s.flush()                                        # IntegrityError shows up here if ID clashed
            except IntegrityError:
                s.rollback()
                continue
            s.add(TicketEvent(ticket_id=ticket.ticket_id, event_type="created",
                              new_value="OPEN", by_agent="Admin_Agent", created_at=now))
            s.add(TicketEvent(ticket_id=ticket.ticket_id, event_type="assigned",
                              new_value=ticket.assigned_to, by_agent="Admin_Agent", created_at=now))
            s.commit()
            return ticket_to_dict(ticket)
    raise RuntimeError("Could not create a unique ticket ID, please try again")


def get_ticket(ticket_id: str) -> Optional[dict]:
    """Read one ticket by its ID (returns None if not found)."""
    with get_session() as s:
        t = s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
        return ticket_to_dict(t) if t else None


# ----------------------------------------------------------------------------
# Step 9: status rules (state machine)
# ----------------------------------------------------------------------------
# A ticket can only move from one status to certain other statuses.
# Anything not listed here is refused, whoever asks (AI agent or human).
ALLOWED_TRANSITIONS = {
    "NEW":                  ["OPEN", "ASSIGNED"],
    "OPEN":                 ["ASSIGNED", "IN PROGRESS", "PENDING INFORMATION", "ESCALATED", "RESOLVED"],
    "ASSIGNED":             ["IN PROGRESS", "PENDING INFORMATION", "ESCALATED", "RESOLVED"],
    "IN PROGRESS":          ["PENDING INFORMATION", "WAITING FOR APPROVAL", "ESCALATED", "RESOLVED"],
    "PENDING INFORMATION":  ["IN PROGRESS", "ESCALATED", "CLOSED"],
    "WAITING FOR APPROVAL": ["IN PROGRESS", "ESCALATED", "RESOLVED"],
    "ESCALATED":            ["IN PROGRESS", "PENDING INFORMATION", "WAITING FOR APPROVAL", "RESOLVED"],
    "RESOLVED":             ["CLOSED", "REOPENED"],
    "CLOSED":               ["REOPENED"],
    "REOPENED":             ["ASSIGNED", "IN PROGRESS", "PENDING INFORMATION", "ESCALATED"],
}


class InvalidTransition(ValueError):
    """Raised when a status change is not allowed."""


def allowed_next_statuses(status: str) -> list:
    return ALLOWED_TRANSITIONS.get(status, [])


def update_status(ticket_id: str, new_status: str, by_agent: str = "system",
                  note: Optional[str] = None, resolution: Optional[str] = None) -> dict:
    """Move a ticket to a new status (only if the rules allow it) and record it in the history.

    resolution: the final explanation, saved when the new status is RESOLVED.
    """
    new_status = new_status.strip().upper()
    if new_status not in ALLOWED_TRANSITIONS:
        raise InvalidTransition(f"'{new_status}' is not a valid status.")

    now = datetime.now()
    with get_session() as s:
        t = s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
        if t is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        old = t.status
        if new_status not in ALLOWED_TRANSITIONS[old]:
            raise InvalidTransition(
                f"Cannot move {ticket_id} from {old} to {new_status}. "
                f"Allowed next statuses: {', '.join(ALLOWED_TRANSITIONS[old])}"
            )
        t.status = new_status
        t.updated_at = now
        if new_status == "RESOLVED":
            t.resolved_at = now
            if resolution:
                t.resolution = resolution
        elif new_status == "REOPENED":
            t.resolved_at = None
        elif new_status == "ESCALATED":
            t.escalated = True
            t.escalation_count += 1
        s.add(TicketEvent(ticket_id=ticket_id, event_type="status_change", old_value=old,
                          new_value=new_status, by_agent=by_agent, created_at=now))
        if note:
            s.add(TicketEvent(ticket_id=ticket_id, event_type="note", new_value=note,
                              by_agent=by_agent, created_at=now))
        s.commit()
        return ticket_to_dict(t)


# ----------------------------------------------------------------------------
# Step 13 helpers: assign a ticket to another department, add a note
# ----------------------------------------------------------------------------
def assign_ticket(ticket_id: str, department: str, by_agent: str = "Admin_Agent") -> dict:
    """Give the ticket to a department's agent. Status becomes ASSIGNED when the rules allow it."""
    if department not in DEPT_PREFIX:
        raise ValueError(f"Unknown department '{department}'. Use one of: {', '.join(DEPT_PREFIX)}")
    now = datetime.now()
    with get_session() as s:
        t = s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
        if t is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        old_agent = t.assigned_to
        t.department = department
        t.assigned_to = agent_name_for(department)
        t.updated_at = now
        s.add(TicketEvent(ticket_id=ticket_id, event_type="assigned", old_value=old_agent,
                          new_value=t.assigned_to, by_agent=by_agent, created_at=now))
        if "ASSIGNED" in ALLOWED_TRANSITIONS.get(t.status, []):
            s.add(TicketEvent(ticket_id=ticket_id, event_type="status_change", old_value=t.status,
                              new_value="ASSIGNED", by_agent=by_agent, created_at=now))
            t.status = "ASSIGNED"
        s.commit()
        return ticket_to_dict(t)


def add_note(ticket_id: str, note: str, by_agent: str = "system") -> dict:
    """Write a note (diagnosis, resolution step, escalation note...) into the ticket history."""
    if not note.strip():
        raise ValueError("Note cannot be empty")
    with get_session() as s:
        if s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first() is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        s.add(TicketEvent(ticket_id=ticket_id, event_type="note", new_value=note.strip(),
                          by_agent=by_agent, created_at=datetime.now()))
        s.commit()
    return {"ticket_id": ticket_id, "by_agent": by_agent, "note": note.strip()}


# ----------------------------------------------------------------------------
# Step 10: structured messages between agents (format from the assignment)
# ----------------------------------------------------------------------------
VALID_AGENTS = [f"{d}_Agent" for d in DEPARTMENTS] + ["Supervisor_Agent"]


def _message_to_dict(m: AgentMessage) -> dict:
    """The exact JSON shape required by the assignment."""
    return {
        "ticket_id": m.ticket_id,
        "from_agent": m.from_agent,
        "to_agent": m.to_agent,
        "message": m.message,
        "timestamp": m.timestamp.strftime("%Y-%m-%d %I:%M %p"),   # e.g. 2026-01-15 10:30 AM
    }


def log_agent_message(ticket_id: str, from_agent: str, to_agent: str, message: str) -> dict:
    """Save one agent-to-agent message and return it in the assignment's JSON format."""
    from_agent = from_agent.strip().replace(" ", "_")     # "Accounts Agent" -> "Accounts_Agent"
    to_agent = to_agent.strip().replace(" ", "_")
    for name in (from_agent, to_agent):
        if name not in VALID_AGENTS:
            raise ValueError(f"Unknown agent '{name}'. Use one of: {', '.join(VALID_AGENTS)}")
    if not message.strip():
        raise ValueError("Message cannot be empty")
    with get_session() as s:
        if s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first() is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        m = AgentMessage(ticket_id=ticket_id, from_agent=from_agent, to_agent=to_agent,
                         message=message.strip(), timestamp=datetime.now())
        s.add(m)
        s.commit()
        return _message_to_dict(m)


def get_agent_messages(ticket_id: str) -> list:
    """All messages of a ticket, oldest first (used for the conversation view in Streamlit)."""
    with get_session() as s:
        rows = s.scalars(select(AgentMessage).where(AgentMessage.ticket_id == ticket_id)
                         .order_by(AgentMessage.id)).all()
        return [_message_to_dict(m) for m in rows]


# ----------------------------------------------------------------------------
# Quick demo:  python -m core.ticket_service
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    from core.db import init_db

    init_db()
    a = create_ticket("Vendor payment delayed", "Vendor payment has not been processed for 20 days.",
                      "Accounts", "Medium", customer_name="Ravi")
    b = create_ticket("Second payment query", "Invoice INV-1002 refund.", "Accounts", "High")
    c = create_ticket("Laptop password reset", "I forgot my laptop password.", "IT", "Critical")
    for t in (a, b, c):
        print(t["ticket_id"], "|", t["department"], "|", t["priority"], "|", t["status"],
              "|", t["assigned_to"], "| due:", t["due_at"])
    try:
        create_ticket("x", "y", "Cooking")
    except ValueError as e:
        print("Rejected as expected:", e)

    # ---- Step 9 demo: status rules ----
    print("\n--- Status rules demo ---")
    tid = a["ticket_id"]
    for new in ["IN PROGRESS", "RESOLVED"]:
        t = update_status(tid, new, by_agent="Accounts_Agent",
                          resolution="Approval workflow fixed, payment processed." if new == "RESOLVED" else None)
        print(tid, "->", t["status"])
    for bad in ["IN PROGRESS", "OPEN"]:
        try:
            update_status(tid, bad)
        except InvalidTransition as e:
            print("Rejected as expected:", e)
    print(tid, "->", update_status(tid, "CLOSED", by_agent="Admin_Agent")["status"])
    try:
        update_status(tid, "IN PROGRESS")
    except InvalidTransition as e:
        print("Rejected as expected:", e)
    print(tid, "->", update_status(tid, "REOPENED", by_agent="Admin_Agent")["status"])

    # ---- Step 10 demo: agent messages ----
    print("\n--- Agent messages demo ---")
    m1 = log_agent_message(tid, "Accounts Agent", "Compliance_Agent", "Please verify approval status.")
    log_agent_message(tid, "Compliance_Agent", "Accounts_Agent", "Approval verified. Payment is compliant.")
    print(json.dumps(m1, indent=2))
    print("Messages on this ticket:", len(get_agent_messages(tid)))
    try:
        log_agent_message(tid, "Accounts_Agent", "Chef_Agent", "hello")
    except ValueError as e:
        print("Rejected as expected:", e)
