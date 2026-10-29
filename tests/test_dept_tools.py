"""
tests/test_dept_tools.py  -  checks the department tools WITHOUT any AI.
Run from the project root:   python tests\test_dept_tools.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["DATABASE_URL"] = "sqlite:///test_support.db"

from autogen_core.tools import FunctionTool  # noqa: E402

from agent_team.dept_tools import (  # noqa: E402
    ALL_TOOL_LISTS, assess_risk, check_access, check_approval_status, check_payment_status,
    check_refund_eligibility, get_employee_info, grant_software_access, process_payment,
    record_compliance_decision, reset_password, search_policy, verify_invoice,
)
from core.db import engine, init_db  # noqa: E402
from core.models import Base  # noqa: E402
from core.seed import seed_mock_data  # noqa: E402


def reset():
    Base.metadata.drop_all(engine)
    init_db()
    seed_mock_data()


def j(text):
    assert not text.startswith("ERROR"), text
    return json.loads(text)


def test_every_department_tool_has_a_valid_ai_schema():
    for dept, tools in ALL_TOOL_LISTS.items():
        names = [f.__name__ for f in tools]
        assert len(names) == len(set(names)), f"duplicate tool names in {dept}"
        for f in tools:
            schema = FunctionTool(f, description=f.__doc__).schema
            assert schema["description"].strip(), f.__name__


def test_it_tools():
    reset()
    assert j(check_access("sana.khan"))["status"] == "LOCKED"
    r = j(reset_password("Sana.Khan"))
    assert r["previous_status"] == "LOCKED" and r["status"] == "ACTIVE"
    assert j(check_access("sana.khan"))["status"] == "ACTIVE"
    assert "Slack" in j(grant_software_access("ravi.kumar", "Slack"))["software_access"]
    assert "already" in j(grant_software_access("ravi.kumar", "slack"))["result"]
    assert reset_password("nobody").startswith("ERROR:")


def test_hr_tools():
    reset()
    e = j(get_employee_info("EMP001"))
    assert e["name"] == "Ravi Kumar" and e["leave_balance"]["casual"] == 6
    assert j(get_employee_info("priya"))["employee_id"] == "EMP002"
    assert get_employee_info("zzz").startswith("ERROR:")


def test_accounts_example_from_the_assignment():
    reset()
    st = j(check_payment_status("INV-1001"))
    assert st["status"] == "PENDING" and st["approval_status"] == "INCOMPLETE" and st["days_overdue"] == 20
    v = j(verify_invoice("INV-1001"))
    assert v["level_2_required"] and [a["status"] for a in v["approvals"]] == ["APPROVED", "APPROVED"]
    # Accounts cannot pay before Compliance verifies (rule is enforced in code)
    assert "Compliance" in process_payment("INV-1001", "Accounts_Agent")
    # Compliance verifies
    assert all(a["compliance_check"] == "NOT CHECKED" for a in j(check_approval_status("INV-1001"))["approvals"])
    assert j(record_compliance_decision("INV-1001", "COMPLIANT", "Approvals verified"))["decision"] == "COMPLIANT"
    # Now Accounts can pay
    paid = j(process_payment("INV-1001", "Accounts_Agent"))
    assert paid["status"] == "PAID"
    assert j(check_payment_status("INV-1001"))["approval_status"] == "COMPLETE"
    assert process_payment("INV-1001", "Accounts_Agent").startswith("ERROR:")       # cannot pay twice


def test_payment_guardrails():
    reset()
    assert "approvals" in process_payment("INV-1005", "Accounts_Agent")             # level 2 really pending
    assert record_compliance_decision("INV-1005", "COMPLIANT", "x").startswith("ERROR:")   # cannot approve unapproved
    assert j(process_payment("INV-1004", "Accounts_Agent"))["status"] == "PAID"     # small invoice, approvals complete
    assert record_compliance_decision("INV-1001", "MAYBE", "x").startswith("ERROR:")
    assert check_payment_status("INV-9999").startswith("ERROR:")


def test_refund_eligibility():
    reset()
    assert j(check_refund_eligibility("INV-1002"))["refund_eligible"] is True
    assert j(check_refund_eligibility("INV-1001"))["refund_eligible"] is False


def test_compliance_risk_rules():
    reset()
    r = j(assess_risk("Data sent to wrong person", "Customer data was emailed to the wrong person"))
    assert r["risk_level"] == "Critical" and r["regulation_references"]
    assert j(assess_risk("Vendor payment", "delayed", "INV-1005"))["risk_level"] == "High"
    assert j(assess_risk("Printer", "Printer is out of ink"))["risk_level"] == "Low"


def test_policy_search():
    reset()
    assert j(search_policy("HR", "leave"))["matches"][0]["ref"] == "HR-POL-01"
    assert j(search_policy("Any", "password reset"))["matches"][0]["ref"] == "IT-POL-01"
    assert j(search_policy("Accounts", "refund"))["matches"][0]["ref"] == "ACC-POL-02"
    assert j(search_policy("HR", "zzzz"))["matches"] == "No matching policy found"


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
