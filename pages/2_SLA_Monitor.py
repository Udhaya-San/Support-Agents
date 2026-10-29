"""SLA monitor: see deadlines and escalate overdue tickets (demo: simulate time passing)."""
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core.db import init_db  # noqa: E402
from core.queries import list_tickets  # noqa: E402
from core.sla import run_sla_check, time_left  # noqa: E402

st.set_page_config(page_title="SLA Monitor", page_icon="⏱️", layout="wide")
init_db()
from ui_common import render_sidebar  # noqa: E402
render_sidebar()
st.title("⏱️ SLA Monitor")
st.caption("Deadlines: Critical 2h, High 8h, Medium 24h, Low 48h. Overdue tickets are escalated: status ESCALATED, "
           "priority one level up, a new deadline, and Admin + Supervisor are notified. This is plain Python, not AI.")

hours = st.select_slider("Simulate time passing (demo)", options=[0, 2, 8, 24, 48, 72], value=0,
                         format_func=lambda h: "now" if h == 0 else f"+{h} hours")
now = datetime.now() + timedelta(hours=hours)

if st.button("Run SLA check", type="primary"):
    done = run_sla_check(now)
    if done:
        st.warning(f"{len(done)} ticket(s) escalated")
        st.dataframe(done, width="stretch", hide_index=True)
    else:
        st.success("No overdue tickets. Everything is within SLA.")

active = [t for t in list_tickets(500) if t["status"] not in ("RESOLVED", "CLOSED")]
rows = [{"Ticket": t["ticket_id"], "Dept": t["department"], "Priority": t["priority"], "Status": t["status"],
         "Deadline": t["due_at"], "Time": time_left(t, now)} for t in active]
st.subheader(f"Active tickets ({len(rows)})")
if rows:
    rows.sort(key=lambda r: r["Deadline"] or "")
    st.dataframe(rows, width="stretch", hide_index=True)
else:
    st.info("No active tickets.")
