"""
core/notifications.py  -  tell the customer / supervisor what happened to a ticket.

For now a notification is saved in the database and shown in the Streamlit page (channel "ui").
Email and Slack/Teams sending are added later (Phase 6) inside notify(), without changing callers.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from core.db import get_session
from core.models import Notification, Ticket


def notify(ticket_id: str, text: str, channel: str = "ui", recipient: Optional[str] = None) -> dict:
    if not text.strip():
        raise ValueError("Notification text cannot be empty")
    with get_session() as s:
        t = s.scalars(select(Ticket).where(Ticket.ticket_id == ticket_id)).first()
        if t is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        who = recipient or t.customer_email or t.customer_name
        n = Notification(ticket_id=ticket_id, channel=channel, recipient=who,
                         text=text.strip(), sent_at=datetime.now(), status="sent")
        s.add(n)
        s.commit()
        return {"ticket_id": ticket_id, "channel": channel, "recipient": who,
                "text": n.text, "sent_at": n.sent_at.strftime("%Y-%m-%d %I:%M %p")}


def get_notifications(ticket_id: str) -> list:
    with get_session() as s:
        rows = s.scalars(select(Notification).where(Notification.ticket_id == ticket_id)
                         .order_by(Notification.id)).all()
        return [{"ticket_id": n.ticket_id, "channel": n.channel, "recipient": n.recipient,
                 "text": n.text, "sent_at": n.sent_at.strftime("%Y-%m-%d %I:%M %p")} for n in rows]
