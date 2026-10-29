"""Track a ticket by ID (second page of the app)."""
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core import ticket_service as ts  # noqa: E402
from core.db import init_db  # noqa: E402
from core.notifications import get_notifications  # noqa: E402
from core.queries import get_events, list_tickets  # noqa: E402

st.set_page_config(page_title="Track a ticket", page_icon="🔎", layout="wide")
init_db()
from ui_common import render_sidebar  # noqa: E402
render_sidebar()
st.title("🔎 Track a ticket")

tickets = list_tickets()
if not tickets:
    st.info("No tickets yet. Raise a request on the main page first.")
    st.stop()

ids = [t["ticket_id"] for t in tickets]
c1, c2 = st.columns([1, 2])
typed = c1.text_input("Ticket ID", placeholder="e.g. ACC-2026-001").strip().upper()
picked = c2.selectbox("...or pick a recent ticket", ids)
ticket_id = typed or picked

t = ts.get_ticket(ticket_id)
if t is None:
    st.error(f"Ticket {ticket_id} not found.")
    st.stop()

with st.container(border=True):
    st.subheader(f"🎫 {t['ticket_id']}  |  {t['status']}")
    a, b, c, d = st.columns(4)
    a.metric("Department", t["department"])
    b.metric("Priority", t["priority"])
    c.metric("Assigned to", t["assigned_to"])
    d.metric("SLA deadline", t["due_at"] or "-")
    st.write(f"**Subject:** {t['subject']}")
    st.write(f"**Description:** {t['description']}")
    st.write(f"**Customer:** {t['customer_name']}  ({t['customer_email'] or 'no email'})   |   "
             f"**Created:** {t['created_at']}   |   **Escalated:** {'yes' if t['escalated'] else 'no'}")
    if t["resolution"]:
        st.success(f"**Resolution:** {t['resolution']}")
    st.caption("Next allowed statuses: " + (", ".join(ts.allowed_next_statuses(t["status"])) or "none"))

tab1, tab2, tab3 = st.tabs(["🕑 History", "📨 Agent messages", "🔔 Notifications"])
with tab1:
    events = get_events(ticket_id)
    if events:
        st.dataframe(events, width="stretch", hide_index=True)
    else:
        st.caption("No events.")
with tab2:
    msgs = ts.get_agent_messages(ticket_id)
    for m in msgs:
        st.json(m)
    if not msgs:
        st.caption("No agent-to-agent messages for this ticket.")
with tab3:
    notes = get_notifications(ticket_id)
    if notes:
        st.dataframe(notes, width="stretch", hide_index=True)
    else:
        st.caption("No notifications.")
