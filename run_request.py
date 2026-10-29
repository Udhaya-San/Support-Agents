"""Terminal test:  python run_request.py "My laptop login is locked, username sana.khan" """
import sys
from agent_team.workflow import run

req = " ".join(sys.argv[1:]) or "I cannot log in to my account. My username is sana.khan"
out = run(req, customer_name="Test User", customer_email="test@example.com")
for m in out["conversation"]:
    print(f"[{m['source']}] {m['type']}: {m['text'][:300]}")
print("\nSTOP:", out["stop_reason"])
for t in out["tickets"]:
    print("TICKET:", t["ticket_id"], t["department"], t["priority"], t["status"], "| due", t["due_at"])

print("FINISHED:", out["finished"], "" if out["finished"] else "<- agents stopped before the ticket was resolved")
