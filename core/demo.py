"""Demo data: ~40 tickets spread over 30 days so the dashboard has something to show.
Run:  python -m core.demo      (adds tickets; run python -m core.seed separately for mock invoices)"""
import random
from datetime import datetime, timedelta

from sqlalchemy import select

from core.db import get_session, init_db
from core.models import PRIORITIES, SLA_HOURS, Ticket, TicketEvent
from core.ticket_service import create_ticket

SUBJECTS = {
    "IT": ["Password reset", "VPN not working", "Laptop slow", "Software access request", "Email not syncing"],
    "HR": ["Leave balance query", "Payslip question", "Policy clarification", "Employee record update"],
    "Accounts": ["Vendor payment delayed", "Invoice mismatch", "Refund request", "Expense reimbursement"],
    "Compliance": ["Approval check", "Audit document request", "Data handling question", "Policy exception"],
}


def seed_demo(n: int = 40, seed: int = 7) -> int:
    init_db()
    rnd = random.Random(seed)
    now = datetime.now()
    made = 0
    for _ in range(n):
        dept = rnd.choice(list(SUBJECTS))
        prio = rnd.choices(PRIORITIES, weights=[3, 5, 3, 1])[0]
        t = create_ticket(rnd.choice(SUBJECTS[dept]), "Demo ticket", dept, prio,
                          customer_name=rnd.choice(["Ravi", "Priya", "Arjun", "Sana", "Meena", "Karthik"]))
        created = now - timedelta(hours=rnd.randint(1, 30 * 24))
        status = rnd.choices(["RESOLVED", "CLOSED", "IN PROGRESS", "OPEN", "ESCALATED", "WAITING FOR APPROVAL",
                              "PENDING INFORMATION"], weights=[10, 8, 5, 4, 3, 2, 2])[0]
        with get_session() as s:
            row = s.scalars(select(Ticket).where(Ticket.ticket_id == t["ticket_id"])).first()
            row.created_at = created
            row.due_at = created + timedelta(hours=SLA_HOURS[prio])
            row.status = status
            row.escalated = status == "ESCALATED"
            if status in ("RESOLVED", "CLOSED"):
                row.resolved_at = created + timedelta(hours=rnd.randint(1, SLA_HOURS[prio] * 2))
                row.resolution = "Resolved (demo data)"
            row.updated_at = row.resolved_at or created
            for e in s.scalars(select(TicketEvent).where(TicketEvent.ticket_id == t["ticket_id"])).all():
                e.created_at = created
            s.commit()
        made += 1
    return made


if __name__ == "__main__":
    print(seed_demo(), "demo tickets added")
