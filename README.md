# Multi-Agent Customer Support Management System

A team of AI agents (built with **AutoGen**) that handles customer requests the way a real support desk does:
an **Admin** agent creates a ticket and routes it to **IT**, **HR**, **Accounts** or **Compliance**, agents
hand work to each other, and a **Supervisor** agent handles escalations. A Streamlit app shows tickets,
SLA deadlines, dashboards and reports.

> Week 5 assignment (AutoGen). This is a working MVP that uses **mock data** (fake invoices, employees and
> IT accounts). See "What is real and what is not" below.

## Key idea: prompts are probability, code is deterministic

AI can slip, so anything that must always be right is plain Python, not an AI decision:

| Plain Python (always correct) | AI agents (judgement) |
|---|---|
| Ticket IDs (`ACC-2026-001`) | Understanding the request |
| Status rules (OPEN -> IN PROGRESS -> RESOLVED...) | Choosing department and priority |
| SLA deadlines and auto-escalation | Deciding who to hand off to |
| Payment rules (large invoices need L1+L2 approval **and** a compliance check) | Writing notes and resolutions |
| Data or security incidents are always Critical | |
| Wrong ticket ID from an agent is replaced by the real one | |

Tools return `ERROR: ...` text instead of crashing, so an agent can read the problem and try again.

## Features

- 6 agents: Admin, IT, HR, Accounts, Compliance, Supervisor (AutoGen `Swarm` with handoffs)
- Tickets with IDs and these statuses: NEW, OPEN, ASSIGNED, IN PROGRESS, PENDING INFORMATION,
  WAITING FOR APPROVAL, ESCALATED, RESOLVED, CLOSED, REOPENED (state machine enforced in code)
- SLA: Low 48h, Medium 24h, High 8h, Critical 2h. Overdue tickets escalate automatically
  (status ESCALATED, priority up one level, new deadline, Admin + Supervisor notified)
- Structured agent-to-agent messages (JSON: ticket_id, from_agent, to_agent, message, timestamp)
- Streamlit pages: **Raise a request**, **Track a ticket**, **SLA Monitor**, **Dashboard**
  (Admin / Department / Supervisor views, daily / weekly / monthly CSV reports)
- Tests that run without AI (fast and free)

## Example: the assignment scenario

> "Please process the payment for invoice INV-1001, it is overdue"

1. Admin creates an Accounts ticket and hands off to Accounts.
2. Accounts checks the invoice (Rs 4,85,000) and tries to pay. The code refuses: a compliance check is missing.
3. Accounts hands off to Compliance. Compliance checks the approvals and risk and records COMPLIANT.
4. Control returns to Accounts, which pays, adds a note and marks the ticket RESOLVED.

## Project structure

```
agent_team/   agents.py (6 agents) | tools.py, dept_tools.py (what agents can do) | workflow.py (Swarm run)
core/         models.py, db.py | ticket_service.py (IDs, status rules) | sla.py | notifications.py
              queries.py | seed.py (mock data) | demo.py (40 demo tickets)
pages/        Track_Ticket | SLA_Monitor | Dashboard
tests/        test_tickets.py, test_tools.py, test_dept_tools.py, test_sla.py
app.py        Streamlit main page      run_request.py   same thing in the terminal
```

## Setup (Windows PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then put your OpenAI key in .env
python -m core.db             # create the database (support.db)
python -m core.seed           # mock invoices, employees, IT accounts
python -m core.demo           # optional: 40 demo tickets for the dashboard
streamlit run app.py
```

Run the tests (no AI, no cost):

```powershell
python tests\test_tickets.py
python tests\test_tools.py
python tests\test_dept_tools.py
python tests\test_sla.py
```

Try it in the terminal: `python run_request.py "I cannot log in to my account. My username is sana.khan"`

## Try these in the app

| Request | What happens |
|---|---|
| I cannot log in to my account. My username is sana.khan | IT unlocks the account, ticket RESOLVED |
| Please process the payment for invoice INV-1001, it is overdue | Accounts -> Compliance -> Accounts, paid |
| Please process the payment for invoice INV-1005, it is urgent | Blocked: L2 approval is still pending |
| A customer file with personal data was emailed to the wrong person | Priority forced to Critical, Compliance, Supervisor |

## What is real and what is not

Real: the agents, handoffs, tool calling, ticket engine, status rules, SLA engine, dashboards, reports, tests.

Not real (honest limits of this MVP):
- Invoices, employees and IT accounts are **mock data** in the database
- The database is **SQLite** (a file). Set `DATABASE_URL` to use PostgreSQL
- No login: this is a demo, not a secured system
- Notifications are saved in the database and shown in the app; no email or Slack is sent
- An AI model can still make mistakes. The code rules above limit the damage, and the app shows
  "stopped before the ticket was resolved" when agents do not finish

## Production roadmap (not built)

FastAPI backend, JWT login with roles, PostgreSQL, Redis queue, ChromaDB for policy search (RAG),
email / Slack / SMS notifications, Docker Compose + Nginx on a VPS, ELK logging.

## Tech

Python, AutoGen 0.7.5 (`autogen-agentchat`, `autogen-ext[openai]`), OpenAI `gpt-4o-mini`, Streamlit,
SQLAlchemy 2.0, SQLite, pandas.
