"""
agent_team/tools.py  -  the functions the AI agents can CALL (their "hands").

Rules for every tool:
  * clear name, type hints and a docstring (the AI reads these to know when and how to use it)
  * returns a short JSON text
  * never crashes: if something is wrong it returns "ERROR: ..." so the agent can fix it and retry

The real work is done by the plain Python code in core/ (IDs, rules, SLA), so the AI cannot
break the rules even if it makes a mistake.
"""

import functools
import json

from core import notifications as notif
from core import ticket_service as ts


def _safe(func):
    """Turn any exception into an 'ERROR: ...' text and return results as JSON text."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return json.dumps(func(*args, **kwargs), default=str)
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"
    return wrapper


# Tickets created through create_ticket_tool in the current request.
# If an agent writes a wrong/guessed ticket ID, code swaps in the real one (AI can slip, code cannot).
CREATED_TICKETS: list[str] = []


def reset_request_context():
    CREATED_TICKETS.clear()


def _fix_id(ticket_id: str) -> str:
    if CREATED_TICKETS and ticket_id not in CREATED_TICKETS:
        return CREATED_TICKETS[-1]
    return ticket_id


# ============================================================================
# SHARED tools (every agent gets these)
# ============================================================================
@_safe
def get_ticket_details(ticket_id: str) -> dict:
    """Read a ticket: subject, description, department, priority, status, deadline and resolution."""
    ticket_id = _fix_id(ticket_id)
    t = ts.get_ticket(ticket_id)
    if t is None:
        raise ValueError(f"Ticket {ticket_id} not found")
    t["messages_so_far"] = len(ts.get_agent_messages(ticket_id))
    return t


@_safe
def update_ticket_status(ticket_id: str, new_status: str, by_agent: str,
                         note: str = "", resolution: str = "") -> dict:
    """Change the ticket status. Allowed statuses: IN PROGRESS, PENDING INFORMATION,
    WAITING FOR APPROVAL, ESCALATED, RESOLVED. Rules are enforced; an illegal move returns an error
    that lists the allowed next statuses. When setting RESOLVED, give the final explanation in 'resolution'."""
    ticket_id = _fix_id(ticket_id)
    return ts.update_status(ticket_id, new_status, by_agent=by_agent,
                            note=note or None, resolution=resolution or None)


@_safe
def add_ticket_note(ticket_id: str, note: str, by_agent: str) -> dict:
    """Write a note into the ticket history (diagnosis, resolution steps, escalation notes)."""
    return ts.add_note(_fix_id(ticket_id), note, by_agent)


@_safe
def send_agent_message(ticket_id: str, from_agent: str, to_agent: str, message: str) -> dict:
    """Send a structured message to another agent about a ticket.
    Agent names: Admin_Agent, IT_Agent, HR_Agent, Accounts_Agent, Compliance_Agent, Supervisor_Agent."""
    return ts.log_agent_message(_fix_id(ticket_id), from_agent, to_agent, message)


# ============================================================================
# ADMIN agent tools
# ============================================================================
_CRITICAL_WORDS = ("data leak", "personal data", "customer data", "wrong person", "wrong recipient",
                   "breach", "hacked", "ransomware", "security incident")


def _priority_floor(subject: str, description: str, priority: str) -> str:
    """Code rule: data or security incidents are always Critical, whatever the AI chose."""
    text = f"{subject} {description}".lower()
    return "Critical" if any(w in text for w in _CRITICAL_WORDS) else priority


@_safe
def create_ticket_tool(subject: str, description: str, department: str, priority: str = "Medium",
                       customer_name: str = "Customer", customer_email: str = "") -> dict:
    """Create a support ticket and assign it to a department agent. Returns the ticket ID.
    department must be one of: IT, HR, Accounts, Compliance, Admin.
    priority must be one of: Low, Medium, High, Critical (decides the SLA deadline)."""
    priority = _priority_floor(subject, description, priority)
    t = ts.create_ticket(subject, description, department, priority,
                         customer_name=customer_name, customer_email=customer_email or None)
    CREATED_TICKETS.append(t["ticket_id"])
    return t


@_safe
def assign_ticket_tool(ticket_id: str, department: str) -> dict:
    """Move an existing ticket to another department (IT, HR, Accounts, Compliance, Admin).
    Not needed right after create_ticket_tool, which already assigns the ticket."""
    return ts.assign_ticket(_fix_id(ticket_id), department, by_agent="Admin_Agent")


@_safe
def notify_customer(ticket_id: str, message: str) -> dict:
    """Send the customer an update about their ticket (new ticket, progress, final resolution)."""
    return notif.notify(_fix_id(ticket_id), message, channel="ui")


@_safe
def close_ticket(ticket_id: str) -> dict:
    """Close a RESOLVED ticket after the customer has been told the resolution."""
    return ts.update_status(_fix_id(ticket_id), "CLOSED", by_agent="Admin_Agent")


# Lists used when we create the agents in step 15
SHARED_TOOLS = [get_ticket_details, update_ticket_status, add_ticket_note, send_agent_message]
ADMIN_TOOLS = [create_ticket_tool, assign_ticket_tool, notify_customer, close_ticket] + SHARED_TOOLS
