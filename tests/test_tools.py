"""
tests/test_tools.py  -  checks the agent tools WITHOUT any AI (free and fast).
Run from the project root:   python tests\test_tools.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["DATABASE_URL"] = "sqlite:///test_support.db"

from autogen_core.tools import FunctionTool  # noqa: E402

from agent_team.tools import (  # noqa: E402
    ADMIN_TOOLS, SHARED_TOOLS, add_ticket_note, assign_ticket_tool, close_ticket,
    create_ticket_tool, get_ticket_details, notify_customer, send_agent_message,
    update_ticket_status,
)
from core.db import engine, init_db  # noqa: E402
from core.models import Base  # noqa: E402
from core.notifications import get_notifications  # noqa: E402


def reset():
    Base.metadata.drop_all(engine)
    init_db()


def test_every_tool_has_a_valid_ai_schema():
    for f in ADMIN_TOOLS:
        schema = FunctionTool(f, description=f.__doc__).schema
        assert schema["name"] == f.__name__
        assert schema["description"].strip(), f.__name__
        assert schema["parameters"]["properties"], f.__name__


def test_full_happy_path_like_the_assignment_example():
    reset()
    t = json.loads(create_ticket_tool("Vendor payment delayed", "Not processed for 20 days",
                                      "Accounts", "Medium", "Ravi"))
    tid = t["ticket_id"]
    assert tid.startswith("ACC-") and t["status"] == "OPEN"
    json.loads(send_agent_message(tid, "Accounts_Agent", "Compliance_Agent", "Please verify approval status."))
    json.loads(send_agent_message(tid, "Compliance_Agent", "Accounts_Agent", "Approval verified. Payment is compliant."))
    assert json.loads(update_ticket_status(tid, "IN PROGRESS", "Accounts_Agent"))["status"] == "IN PROGRESS"
    json.loads(add_ticket_note(tid, "Approval workflow was incomplete.", "Accounts_Agent"))
    done = json.loads(update_ticket_status(tid, "RESOLVED", "Accounts_Agent",
                                           resolution="Workflow corrected and payment processed."))
    assert done["status"] == "RESOLVED"
    json.loads(notify_customer(tid, "Your payment has been processed."))
    assert json.loads(close_ticket(tid))["status"] == "CLOSED"
    details = json.loads(get_ticket_details(tid))
    assert details["messages_so_far"] == 2 and details["resolution"].startswith("Workflow corrected")
    assert len(get_notifications(tid)) == 1


def test_wrong_ticket_id_is_replaced_by_the_real_one():
    reset()
    tid = json.loads(create_ticket_tool("x", "d", "IT"))["ticket_id"]
    out = json.loads(update_ticket_status("1", "IN PROGRESS", "IT_Agent"))
    assert out["ticket_id"] == tid and out["status"] == "IN PROGRESS"


def test_mistakes_come_back_as_error_text_not_crashes():
    reset()
    assert create_ticket_tool("x", "d", "Cooking").startswith("ERROR:")
    tid = json.loads(create_ticket_tool("x", "d", "IT"))["ticket_id"]
    assert update_ticket_status(tid, "CLOSED", "IT_Agent").startswith("ERROR:")
    assert "Allowed next statuses" in update_ticket_status(tid, "CLOSED", "IT_Agent")
    assert send_agent_message(tid, "IT_Agent", "Chef_Agent", "hi").startswith("ERROR:")
    import agent_team.tools as _t
    _t.reset_request_context()                       # no ticket created in this request -> bad ID is an error
    assert get_ticket_details("NOPE-1").startswith("ERROR:")
    assert notify_customer("NOPE-1", "hi").startswith("ERROR:")
    _t.CREATED_TICKETS.append(tid)
    assert close_ticket(tid).startswith("ERROR:")                       # OPEN cannot be closed


def test_reassign_moves_ticket_to_new_department():
    reset()
    tid = json.loads(create_ticket_tool("x", "d", "IT"))["ticket_id"]
    t = json.loads(assign_ticket_tool(tid, "Compliance"))
    assert t["department"] == "Compliance" and t["assigned_to"] == "Compliance_Agent"
    assert t["status"] == "ASSIGNED"
    assert assign_ticket_tool(tid, "Cooking").startswith("ERROR:")


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    tests.sort(key=lambda x: x[1].__code__.co_firstlineno)
    failed = 0
    for name, func in tests:
        try:
            func(); print("PASS ", name)
        except Exception as e:  # noqa: BLE001
            failed += 1; print("FAIL ", name, "->", repr(e))
    engine.dispose()
    if os.path.exists("test_support.db"):
        os.remove("test_support.db")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
