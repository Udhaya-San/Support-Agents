"""Dashboards (Admin / Department / Supervisor) and reports."""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core.db import init_db  # noqa: E402
from core.queries import list_tickets  # noqa: E402

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
init_db()
from ui_common import render_sidebar  # noqa: E402
render_sidebar()
st.title("📊 Dashboard")

df = pd.DataFrame(list_tickets(2000))
if df.empty:
    st.info("No tickets yet. Raise requests on the main page, or run `python -m core.demo` for demo data.")
    st.stop()
df["created_at"] = pd.to_datetime(df["created_at"])
df["due_at"] = pd.to_datetime(df["due_at"])
now = datetime.now()
df["overdue"] = (~df["status"].isin(["RESOLVED", "CLOSED"])) & (df["due_at"] < now)

role = st.sidebar.radio("View as", ["Admin", "Department", "Supervisor"])

if role == "Admin":
    a, b, c, d = st.columns(4)
    a.metric("Total tickets", len(df))
    b.metric("Open / active", int((~df["status"].isin(["RESOLVED", "CLOSED"])).sum()))
    c.metric("Resolved / closed", int(df["status"].isin(["RESOLVED", "CLOSED"]).sum()))
    d.metric("Overdue", int(df["overdue"].sum()))
    l, r = st.columns(2)
    l.subheader("By status")
    l.bar_chart(df["status"].value_counts())
    r.subheader("By department")
    r.bar_chart(df["department"].value_counts())
    st.subheader("By priority")
    st.bar_chart(df["priority"].value_counts())

elif role == "Department":
    dept = st.selectbox("Department", sorted(df["department"].unique()))
    d = df[df["department"] == dept]
    a, b, c = st.columns(3)
    a.metric("Tickets", len(d))
    b.metric("Active", int((~d["status"].isin(["RESOLVED", "CLOSED"])).sum()))
    c.metric("Overdue", int(d["overdue"].sum()))
    st.bar_chart(d["status"].value_counts())
    st.dataframe(d[["ticket_id", "subject", "priority", "status", "assigned_to", "due_at"]],
                 width="stretch", hide_index=True)

else:
    a, b, c = st.columns(3)
    a.metric("Escalated", int((df["status"] == "ESCALATED").sum()))
    b.metric("Overdue", int(df["overdue"].sum()))
    done = df[df["status"].isin(["RESOLVED", "CLOSED"])]
    c.metric("Resolved rate", f"{round(100 * len(done) / len(df))}%")
    st.subheader("Escalated tickets")
    esc = df[df["status"] == "ESCALATED"]
    if len(esc):
        st.dataframe(esc[["ticket_id", "department", "priority", "subject", "assigned_to", "due_at"]],
                     width="stretch", hide_index=True)
    else:
        st.caption("None")
    st.subheader("Overdue tickets")
    od = df[df["overdue"]]
    if len(od):
        st.dataframe(od[["ticket_id", "department", "priority", "status", "due_at"]],
                     width="stretch", hide_index=True)
    else:
        st.caption("None")

st.divider()
st.subheader("Reports (CSV)")
period = st.radio("Period", ["Daily (last 24h)", "Weekly (last 7 days)", "Monthly (last 30 days)"], horizontal=True)
days = {"Daily": 1, "Weekly": 7, "Monthly": 30}[period.split()[0]]
rep = df[df["created_at"] >= now - timedelta(days=days)]
c1, c2, c3 = st.columns(3)
c1.metric("Tickets created", len(rep))
c2.metric("Resolved", int(rep["status"].isin(["RESOLVED", "CLOSED"]).sum()))
c3.metric("Escalated", int((rep["status"] == "ESCALATED").sum()))
st.dataframe(rep[["ticket_id", "department", "priority", "status", "created_at", "due_at"]],
             width="stretch", hide_index=True)
st.download_button("Download report as CSV", rep.to_csv(index=False).encode(),
                   file_name=f"support_report_{period.split()[0].lower()}.csv", mime="text/csv")
