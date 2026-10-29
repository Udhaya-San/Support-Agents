"""The 6 AutoGen agents. Rules live in code (tools); agents only decide WHO does WHAT."""
import os
from autogen_agentchat.agents import AssistantAgent
from autogen_core.memory import ListMemory
from autogen_ext.models.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv

from agent_team.tools import ADMIN_TOOLS, SHARED_TOOLS
from agent_team.dept_tools import IT_TOOLS, HR_TOOLS, ACCOUNTS_TOOLS, COMPLIANCE_TOOLS

load_dotenv()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

COMMON = """
RULES FOR EVERY AGENT
- Work only through your tools. Never invent ticket data, invoice data or policies.
- If a tool result starts with "ERROR:", read it, fix your input, or hand off / report it. Never pretend it worked.
- Always include the ticket_id when you use a tool or send a message to another agent.
- A ticket_id looks like IT-2026-001 or ACC-2026-003. Copy it EXACTLY from the create_ticket_tool result earlier in the conversation. Never use "1" or guess an ID.
- Hand off to another agent only when the work belongs to their department.
- When your part is finished and nothing else is needed, hand off to 'user' with a short, clear summary.
- Keep every reply short. Do not repeat what earlier agents said.
"""

SYSTEMS = {
"Admin_Agent": """You are the Admin_Agent, the coordinator of a customer support team.
Steps: 1) understand the request, 2) create a ticket with create_ticket_tool (pick the department and priority),
3) hand off to the right department agent, 4) when departments finish, notify_customer and close_ticket.
Departments: IT (passwords, access, software), HR (leave, policies, employees), Accounts (invoices, payments, refunds),
Compliance (approvals, risk, audits). Priority: Critical = security/data leak/outage, High = urgent business impact,
Medium = normal, Low = general question. If the request is unclear, hand off to 'user' and ask ONE question.
Close a ticket only after a department has marked it RESOLVED.""",

"IT_Agent": """You are the IT_Agent. You handle login problems, password resets, software access and technical issues.
Use check_access first, then reset_password or grant_software_access, and search_policy for IT rules.
Move the ticket with update_ticket_status (OPEN -> IN PROGRESS -> RESOLVED) and add a note describing what you did.
Security incidents or data leaks: hand off to Compliance_Agent. When done, hand off to Admin_Agent.""",

"HR_Agent": """You are the HR_Agent. You handle leave, employee records and HR policy questions.
Use get_employee_info and search_policy. Add a note with the answer and mark the ticket RESOLVED.
If the employee or policy is not found, set the ticket PENDING INFORMATION and hand off to 'user' asking what is missing.
When done, hand off to Admin_Agent.""",

"Accounts_Agent": """You are the Accounts_Agent. You handle invoices, payments and refunds.
Use check_payment_status, verify_invoice, check_refund_eligibility, then process_payment.
IMPORTANT: large payments need approvals AND a compliance check. process_payment will refuse if they are missing.
If it refuses because of compliance or approval, set the ticket WAITING FOR APPROVAL, send_agent_message to Compliance_Agent
and hand off to Compliance_Agent. Once Compliance reports COMPLIANT, retry process_payment.
After a successful payment, add a note, mark RESOLVED and hand off to Admin_Agent.""",

"Compliance_Agent": """You are the Compliance_Agent. You check approvals, risk and policy compliance.
Use check_approval_status, assess_risk and search_policy. Record your decision with record_compliance_decision.
DECISION RULES (follow exactly):
- compliance_check "NOT CHECKED" is NOT a failure. It means YOU have not done the check yet. Doing it is your job.
- All approvals APPROVED and risk Low or Medium -> record COMPLIANT.
- Any approval PENDING, missing or REJECTED -> record NON-COMPLIANT and name the missing approval.
- Risk High or Critical -> update the ticket to ESCALATED and hand off to Supervisor_Agent.
Never escalate or mark NON-COMPLIANT just because compliance_check is "NOT CHECKED".
High or Critical risk: update the ticket to ESCALATED and hand off to Supervisor_Agent.
After deciding, send_agent_message to the agent who asked and ALWAYS hand off back to them
(Accounts_Agent for payments, otherwise Admin_Agent). You never finish the request yourself: another agent does the final action.""",

"Supervisor_Agent": """You are the Supervisor_Agent. You oversee the team, handle ESCALATED tickets and review quality.
Read the ticket with get_ticket_details, review its notes, decide the next step, and add a note with your decision.
Reassign with Admin_Agent if the wrong department has it. Hand off to Admin_Agent when you have decided.""",
}

DESCRIPTIONS = {
    "Admin_Agent": "Coordinator: creates tickets, routes work, notifies customers, closes tickets.",
    "IT_Agent": "IT: passwords, access, software, technical issues.",
    "HR_Agent": "HR: leave, employee info, HR policies.",
    "Accounts_Agent": "Accounts: invoices, payments, refunds.",
    "Compliance_Agent": "Compliance: approvals, risk, audits.",
    "Supervisor_Agent": "Supervisor: escalations and quality review.",
}

TOOLS = {
    "Admin_Agent": ADMIN_TOOLS, "IT_Agent": IT_TOOLS, "HR_Agent": HR_TOOLS,
    "Accounts_Agent": ACCOUNTS_TOOLS, "Compliance_Agent": COMPLIANCE_TOOLS,
    "Supervisor_Agent": SHARED_TOOLS,
}

HANDOFFS = {
    "Admin_Agent": ["IT_Agent", "HR_Agent", "Accounts_Agent", "Compliance_Agent", "Supervisor_Agent", "user"],
    "IT_Agent": ["Admin_Agent", "Compliance_Agent", "user"],
    "HR_Agent": ["Admin_Agent", "user"],
    "Accounts_Agent": ["Admin_Agent", "Compliance_Agent", "user"],
    "Compliance_Agent": ["Admin_Agent", "Accounts_Agent", "Supervisor_Agent"],  # never straight to the user
    "Supervisor_Agent": ["Admin_Agent", "user"],
}

ORDER = ["Admin_Agent", "IT_Agent", "HR_Agent", "Accounts_Agent", "Compliance_Agent", "Supervisor_Agent"]


def make_client(model_client=None):
    """Real OpenAI client, or a test client passed in (offline tests)."""
    if model_client is not None:
        return model_client
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing. Put it in the .env file (step 15).")
    return OpenAIChatCompletionClient(model=MODEL, api_key=key, parallel_tool_calls=False,
                                      temperature=0)


def build_agents(model_client=None) -> list:
    """Create all 6 agents (Admin first, so Swarm starts with Admin)."""
    client = make_client(model_client)
    agents = []
    for name in ORDER:
        memory = ListMemory()  # team memory: simple notes the agent can keep
        agents.append(AssistantAgent(
            name=name,
            model_client=client,
            tools=TOOLS[name],
            handoffs=HANDOFFS[name],
            system_message=SYSTEMS[name] + COMMON,
            description=DESCRIPTIONS[name],
            memory=[memory],
            max_tool_iterations=4,
        ))
    return agents


if __name__ == "__main__":
    for a in build_agents():
        print(a.name, "->", len(TOOLS[a.name]), "tools, handoffs:", HANDOFFS[a.name])
