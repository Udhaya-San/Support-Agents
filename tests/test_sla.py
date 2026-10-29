"""
tests/test_sla.py  -  SLA engine checks, no AI.   Run from the project root:  python tests\test_sla.py
"""
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["DATABASE_URL"] = "sqlite:///test_support.db"

from core import ticket_service as ts  # noqa: E402
from core.db import engine, init_db  # noqa: E402
from core.models import Base  # noqa: E402
from core.notifications import get_notifications  # noqa: E402
from core.queries import get_events  # noqa: E402
from core.sla import find_overdue, run_sla_check, time_left  # noqa: E402


def reset():
    Base.metadata.drop_all(engine)
    init_db()


def test_nothing_overdue_means_nothing_happens():
    reset()
    ts.create_ticket("a", "d", "IT", "Low")
    assert find_overdue() == []
    assert run_sla_check() == []


def test_overdue_ticket_is_escalated_and_priority_goes_up():
    reset()
    t = ts.create_ticket("Slow", "d", "Accounts", "Medium")          # SLA 24h
    out = run_sla_check(datetime.now() + timedelta(hours=25))
    assert len(out) == 1 and out[0]["new_status"] == "ESCALATED" and out[0]["new_priority"] == "High"
    got = ts.get_ticket(t["ticket_id"])
    assert got["status"] == "ESCALATED" and got["priority"] == "High" and got["escalated"]


def test_admin_and_supervisor_are_notified_and_history_is_written():
    reset()
    t = ts.create_ticket("Slow", "d", "HR", "High")
    run_sla_check(datetime.now() + timedelta(hours=9))
    who = {n["recipient"] for n in get_notifications(t["ticket_id"])}
    assert {"Admin_Agent", "Supervisor_Agent"} <= who
    kinds = {e["event"] for e in get_events(t["ticket_id"])}
    assert "priority_change" in kinds and "status_change" in kinds


def test_resolved_and_closed_tickets_are_ignored():
    reset()
    t = ts.create_ticket("Done", "d", "IT", "Critical")
    ts.update_status(t["ticket_id"], "RESOLVED", "IT_Agent", resolution="ok")
    assert run_sla_check(datetime.now() + timedelta(hours=100)) == []


def test_critical_stays_critical_and_new_deadline_is_set():
    reset()
    t = ts.create_ticket("Leak", "d", "Compliance", "Critical")      # SLA 2h
    out = run_sla_check(datetime.now() + timedelta(hours=3))
    assert out[0]["new_priority"] == "Critical"
    assert run_sla_check(datetime.now() + timedelta(hours=3)) == []   # new deadline is in the future


def test_a_ticket_already_escalated_is_bumped_again_not_crashed():
    reset()
    t = ts.create_ticket("Slow", "d", "IT", "Low")                   # 48h
    run_sla_check(datetime.now() + timedelta(hours=49))              # Low -> Medium, ESCALATED
    out = run_sla_check(datetime.now() + timedelta(hours=49 + 25))   # Medium deadline missed too
    assert out and out[0]["new_priority"] == "High" and out[0]["new_status"] == "ESCALATED"


def test_time_left_text():
    reset()
    t = ts.create_ticket("x", "d", "IT", "Low")
    assert "left" in time_left(ts.get_ticket(t["ticket_id"]))
    assert "OVERDUE" in time_left(ts.get_ticket(t["ticket_id"]), datetime.now() + timedelta(hours=60))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("PASS ", fn.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL ", fn.__name__, "->", repr(e))
    print(f"\n{len(tests) - failed} passed, {failed} failed")
