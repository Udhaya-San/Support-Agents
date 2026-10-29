"""
core/sla.py  -  SLA engine (plain Python, no AI).

Rule: a ticket that is not RESOLVED/CLOSED and whose deadline (due_at) has passed is escalated:
  1. status becomes ESCALATED (if the status rules allow it)
  2. priority goes up one level (Low -> Medium -> High -> Critical)
  3. a new deadline is set from the NEW priority
  4. Admin_Agent and Supervisor_Agent are notified
  5. every change is written to the ticket history
Run it from the Streamlit SLA page, or:  python -m core.sla
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from core.db import get_session
from core.models import PRIORITIES, SLA_HOURS, Ticket, TicketEvent
from core.notifications import notify
from core.ticket_service import ALLOWED_TRANSITIONS, ticket_to_dict, update_status

ACTIVE_EXCLUDED = ("RESOLVED", "CLOSED")


def time_left(t: dict, now: Optional[datetime] = None) -> str:
    """Human text such as '3h 20m left' or 'OVERDUE by 1h 5m'."""
    now = now or datetime.now()
    due = datetime.strptime(t["due_at"], "%Y-%m-%d %H:%M")
    mins = int((due - now).total_seconds() // 60)
    h, m = divmod(abs(mins), 60)
    return f"{h}h {m}m left" if mins >= 0 else f"OVERDUE by {h}h {m}m"


def find_overdue(now: Optional[datetime] = None) -> list[str]:
    now = now or datetime.now()
    with get_session() as s:
        rows = s.scalars(select(Ticket).where(Ticket.status.notin_(ACTIVE_EXCLUDED),
                                              Ticket.due_at.is_not(None), Ticket.due_at < now)
                         .order_by(Ticket.due_at)).all()
        return [t.ticket_id for t in rows]


def escalate_ticket(ticket_id: str, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    with get_session() as s:
        t = s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
        old_status, old_priority = t.status, t.priority
    if "ESCALATED" in ALLOWED_TRANSITIONS[old_status]:
        update_status(ticket_id, "ESCALATED", by_agent="SLA_Engine",
                      note="SLA deadline missed, ticket escalated automatically")
    new_priority = PRIORITIES[min(PRIORITIES.index(old_priority) + 1, len(PRIORITIES) - 1)]
    with get_session() as s:
        t = s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
        t.priority = new_priority
        t.escalated = True
        t.due_at = now + timedelta(hours=SLA_HOURS[new_priority])
        t.updated_at = now
        s.add(TicketEvent(ticket_id=ticket_id, event_type="priority_change", old_value=old_priority,
                          new_value=new_priority, by_agent="SLA_Engine", created_at=now))
        s.commit()
        result = ticket_to_dict(t)
    text = (f"SLA breached for {ticket_id}: status {old_status} -> {result['status']}, "
            f"priority {old_priority} -> {new_priority}. New deadline {result['due_at']}.")
    for who in ("Admin_Agent", "Supervisor_Agent"):
        notify(ticket_id, text, channel="ui", recipient=who)
    return {"ticket_id": ticket_id, "old_status": old_status, "new_status": result["status"],
            "old_priority": old_priority, "new_priority": new_priority, "new_due_at": result["due_at"]}


def run_sla_check(now: Optional[datetime] = None) -> list[dict]:
    """Escalate every overdue ticket. 'now' can be a future time to simulate time passing (demo)."""
    now = now or datetime.now()
    return [escalate_ticket(tid, now) for tid in find_overdue(now)]


if __name__ == "__main__":
    from core.db import init_db
    init_db()
    done = run_sla_check()
    print(f"{len(done)} ticket(s) escalated")
    for d in done:
        print(d)
