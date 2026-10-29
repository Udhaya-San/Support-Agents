"""Streamlit front end:  streamlit run app.py"""
import asyncio
import os
import re

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent_team.workflow import process_customer_request  # noqa: E402
from core import ticket_service as ts  # noqa: E402
from core.db import init_db  # noqa: E402

st.set_page_config(page_title="Customer Support Agents", page_icon="🎧", layout="wide")
init_db()
from ui_common import render_sidebar  # noqa: E402
render_sidebar()

EXAMPLES = {
    "IT: locked account": "I cannot log in to my account. My username is sana.khan",
    "Accounts + Compliance: overdue invoice": "Please process the payment for invoice INV-1001, it is overdue",
    "Accounts: refund": "I paid invoice INV-1002 twice by mistake. Please refund it.",
    "HR: leave balance": "How many leave days does employee EMP001 have left?",
    "Compliance: data leak": "A customer file with personal data was emailed to the wrong person. Please investigate.",
}
STATUS_ICON = {"RESOLVED": "✅", "CLOSED": "✅", "ESCALATED": "🔺", "WAITING FOR APPROVAL": "⏳",
               "PENDING INFORMATION": "❓", "IN PROGRESS": "🔧", "OPEN": "🆕", "ASSIGNED": "📌"}

st.title("🎧 Multi-Agent Customer Support")
st.caption("A team of AI agents works on your request. Ticket IDs, status rules and approval rules "
           "are plain Python, not AI.")

if not os.getenv("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY is missing. Add it to the .env file and restart the app.")
    st.stop()

# ---------------------------------------------------------------- request form
st.subheader("Raise a request")
example = st.selectbox("Try an example (or write your own below)", ["(write my own)"] + list(EXAMPLES))
default_text = EXAMPLES.get(example, "")
with st.form("request_form"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Your name", "Test User")
    email = c2.text_input("Your email", "test@example.com")
    request = st.text_area("What do you need help with?", value=default_text, height=100,
                           key=f"req_{example}")
    submitted = st.form_submit_button("Send to the support team", type="primary")

if submitted:
    if not request.strip():
        st.warning("Please write your request.")
    else:
        try:
            with st.status("Agents are working...", expanded=True) as status:
                st.write("📝 Admin creates a ticket and routes it...")
                out = asyncio.run(process_customer_request(request.strip(), name, email))
                status.update(label="Done", state="complete", expanded=False)
            st.session_state["out"] = out
        except Exception as e:  # noqa: BLE001
            st.error(f"Something went wrong: {e}")


# ---------------------------------------------------------------- results
def tool_names(text: str) -> list[str]:
    return re.findall(r"name='(\w+)'", text)


def show_conversation(conv: list[dict]):
    for m in conv:
        who, kind, text = m["source"], m["type"], m["text"]
        if kind == "TextMessage" and who == "user":
            with st.chat_message("user"):
                st.write(text)
        elif kind == "TextMessage":
            with st.chat_message("assistant"):
                st.markdown(f"**{who}**: {text}")
        elif kind == "ToolCallRequestEvent":
            st.markdown(f"🔧 **{who}** uses `{', '.join(tool_names(text))}`")
        elif kind == "HandoffMessage":
            target = re.search(r"Transferred to (\w+)", text)
            st.markdown(f"➡️ **{who}** hands off to **{target.group(1) if target else '?'}**")
        elif kind == "ToolCallSummaryMessage":
            st.caption(f"{who}: {text[:200]}")


out = st.session_state.get("out")
if out:
    st.divider()
    if out["finished"]:
        st.success("Your request is resolved.")
    else:
        st.warning("The agents stopped before the ticket was resolved. See the ticket status below.")

    for t in out["tickets"]:
        with st.container(border=True):
            st.subheader(f"🎫 {t['ticket_id']}  {STATUS_ICON.get(t['status'], '')} {t['status']}")
            a, b, c, d = st.columns(4)
            a.metric("Department", t["department"])
            b.metric("Priority", t["priority"])
            c.metric("Assigned to", t["assigned_to"])
            d.metric("SLA deadline", str(t["due_at"])[:16])
            st.write(f"**Subject:** {t['subject']}")
            if t.get("resolution"):
                st.info(f"**Resolution:** {t['resolution']}")

    tab1, tab2, tab3 = st.tabs(["💬 Conversation", "📨 Agent messages (JSON)", "🕑 Ticket history"])
    with tab1:
        show_conversation(out["conversation"])
    with tab2:
        shown = False
        for t in out["tickets"]:
            for msg in ts.get_agent_messages(t["ticket_id"]):
                st.json(msg)
                shown = True
        if not shown:
            st.caption("No agent-to-agent messages in this request.")
    with tab3:
        for t in out["tickets"]:
            full = ts.get_ticket(t["ticket_id"])
            st.json(full)
