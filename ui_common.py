"""Shared sidebar: shows the support team on every page."""
import streamlit as st

TEAM = [
    ("🧭", "Admin", "Creates tickets, routes work, notifies customers"),
    ("💻", "IT", "Passwords, access, software"),
    ("👥", "HR", "Leave, employee info, policies"),
    ("💰", "Accounts", "Invoices, payments, refunds"),
    ("🛡️", "Compliance", "Approvals, risk, audits"),
    ("🧑‍💼", "Supervisor", "Escalations and quality review"),
]
SLA = [("Critical", "2 hours"), ("High", "8 hours"), ("Medium", "24 hours"), ("Low", "48 hours")]


def render_sidebar():
    with st.sidebar:
        st.markdown("### 🎧 Support team")
        for icon, name, role in TEAM:
            st.markdown(f"**{icon} {name}**  \n<span style='opacity:.7;font-size:.85em'>{role}</span>",
                        unsafe_allow_html=True)
        st.divider()
        st.markdown("### ⏱️ SLA targets")
        for pr, hrs in SLA:
            st.markdown(f"**{pr}**: {hrs}")
        st.divider()
        st.caption("AutoGen agents + Python rules. Mock data.")
