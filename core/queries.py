"""Read-only helpers used by the Streamlit pages (lists, history)."""
from sqlalchemy import select

from core.db import get_session
from core.models import Ticket, TicketEvent
from core.ticket_service import ticket_to_dict


def list_tickets(limit: int = 100, status: str | None = None, department: str | None = None) -> list[dict]:
    """Newest first. Optional filters."""
    with get_session() as s:
        q = select(Ticket).order_by(Ticket.id.desc()).limit(limit)
        if status:
            q = q.where(Ticket.status == status)
        if department:
            q = q.where(Ticket.department == department)
        return [ticket_to_dict(t) for t in s.scalars(q).all()]


def get_events(ticket_id: str) -> list[dict]:
    """Full history of one ticket, oldest first."""
    with get_session() as s:
        rows = s.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket_id)
                         .order_by(TicketEvent.id)).all()
        return [{"time": e.created_at.strftime("%Y-%m-%d %H:%M:%S"), "event": e.event_type,
                 "from": e.old_value, "to": e.new_value, "by": e.by_agent} for e in rows]
