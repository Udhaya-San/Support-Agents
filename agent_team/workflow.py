"""Runs one customer request through the 6-agent Swarm team."""
import asyncio
from datetime import datetime

from autogen_agentchat.conditions import (HandoffTermination, MaxMessageTermination,
                                          TextMentionTermination)
from autogen_agentchat.teams import Swarm
from sqlalchemy import select

from agent_team.agents import build_agents
from agent_team.tools import reset_request_context
from core.db import get_session, init_db
from core.models import Ticket
from core.ticket_service import ticket_to_dict


def _find_tickets_since(start: datetime) -> list[dict]:
    with get_session() as s:
        rows = s.scalars(select(Ticket).where(Ticket.created_at >= start)
                         .order_by(Ticket.id)).all()
        return [ticket_to_dict(t) for t in rows]


def _msg_text(m) -> str:
    c = getattr(m, "content", "")
    return c if isinstance(c, str) else str(c)


async def process_customer_request(request: str, customer_name: str = "Customer",
                                   customer_email: str = "", model_client=None,
                                   max_messages: int = 25) -> dict:
    """Returns {tickets, conversation, stop_reason}. Code (not AI) reports the final ticket state."""
    init_db()
    reset_request_context()
    start = datetime.now()
    agents = build_agents(model_client)
    stop = (HandoffTermination(target="user")
            | TextMentionTermination("TERMINATE")
            | MaxMessageTermination(max_messages))
    team = Swarm(agents, termination_condition=stop)
    task = (f"Customer: {customer_name} <{customer_email or 'no email'}>\n"
            f"Request: {request}")
    result = await team.run(task=task)

    conversation = []
    for m in result.messages:
        kind = type(m).__name__
        if kind in ("ToolCallRequestEvent", "ToolCallExecutionEvent", "ToolCallSummaryMessage",
                    "HandoffMessage", "TextMessage"):
            conversation.append({"source": m.source, "type": kind, "text": _msg_text(m)[:600]})
    tickets = _find_tickets_since(start)
    # Code checks the truth: did the work actually finish?
    finished = bool(tickets) and all(t["status"] in ("RESOLVED", "CLOSED") for t in tickets)
    return {"tickets": tickets, "conversation": conversation,
            "stop_reason": result.stop_reason, "finished": finished}


def run(request: str, **kw) -> dict:
    return asyncio.run(process_customer_request(request, **kw))
