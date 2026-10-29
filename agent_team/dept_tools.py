"""
agent_team/dept_tools.py  -  the special tools of each department agent.

They read and update the MOCK company data created by core/seed.py.
Rules (like "no payment without approval") are enforced HERE in code, not in the AI prompt.
"""

from datetime import date

from sqlalchemy import select

from agent_team.tools import ADMIN_TOOLS, SHARED_TOOLS, _safe
from core.db import get_session
from core.models import MockApproval, MockEmployee, MockITAccount, MockPayment

L2_LIMIT = 200000        # invoices of Rs 2,00,000 or more need level 2 approval + compliance check


# ============================================================================
# Mock company policies (Phase 6 replaces the search with ChromaDB, same tool name)
# ============================================================================
POLICIES = [
    {"ref": "HR-POL-01", "department": "HR", "title": "Leave Policy (mock)",
     "text": "Yearly entitlement: casual leave 12 days, sick leave 8 days, earned leave 24 days. "
             "Casual leave needs 1 day notice. Sick leave of 3 or more days needs a medical certificate."},
    {"ref": "HR-POL-02", "department": "HR", "title": "Attendance and Shift Policy (mock)",
     "text": "Standard shift 09:00-18:00. Grace of 15 minutes. Three late marks in a month count as a half day leave."},
    {"ref": "HR-POL-03", "department": "HR", "title": "Benefits and Onboarding (mock)",
     "text": "Benefits: group health insurance, provident fund and gratuity. New joiners submit ID, address proof, "
             "bank details and education documents in the first week."},
    {"ref": "HR-POL-04", "department": "HR", "title": "Salary Query Policy (mock)",
     "text": "Salary queries go to HR payroll. Payslips are released by the 3rd of each month. Corrections are made in the next cycle."},
    {"ref": "IT-POL-01", "department": "IT", "title": "Password Policy (mock)",
     "text": "Minimum 12 characters, change every 90 days. Account locks after 5 failed attempts. "
             "Reset is done through the self-service link sent to the registered email."},
    {"ref": "IT-POL-02", "department": "IT", "title": "Software and Access Requests (mock)",
     "text": "Approved software list can be installed on request. Any other software needs manager and security approval. "
             "System access is granted on a least-privilege basis."},
    {"ref": "ACC-POL-01", "department": "Accounts", "title": "Vendor Payment Policy (mock)",
     "text": "Vendors are paid within 30 days of invoice. Invoices of Rs 2,00,000 or more need level 1 and level 2 (CFO) "
             "approval and a Compliance check before payment."},
    {"ref": "ACC-POL-02", "department": "Accounts", "title": "Refund Policy (mock)",
     "text": "Refunds apply only to PAID invoices, need Compliance approval, and are processed in 7 working days."},
    {"ref": "CMP-POL-01", "department": "Compliance", "title": "Data Privacy Policy (mock)",
     "text": "Any personal or customer data sent to a wrong person or leaked must be reported to Compliance immediately. "
             "Compliance assesses the incident within 24 hours and decides on notification."},
    {"ref": "CMP-POL-02", "department": "Compliance", "title": "Payment Compliance Policy (mock)",
     "text": "Before payment of Rs 2,00,000 or more, Compliance verifies the approvals and the vendor documents."},
]


@_safe
def search_policy(department: str, query: str) -> dict:
    """Search the company policies. department: HR, IT, Accounts, Compliance, or Any.
    query: a few words such as 'leave', 'password', 'refund', 'data privacy'. Returns up to 3 matches."""
    words = [w for w in query.lower().replace(",", " ").split() if len(w) > 2]
    results = []
    for p in POLICIES:
        if department.lower() not in ("any", "all", "") and p["department"].lower() != department.lower():
            continue
        blob = (p["title"] + " " + p["text"]).lower()
        score = sum(1 for w in words if w in blob)
        if score:
            results.append((score, p))
    results.sort(key=lambda x: -x[0])
    return {"matches": [p for _, p in results[:3]] or "No matching policy found"}


# ============================================================================
# IT agent
# ============================================================================
@_safe
def check_access(username: str) -> dict:
    """Look up an IT account: status (ACTIVE or LOCKED), last password reset, software access."""
    with get_session() as s:
        a = s.scalars(select(MockITAccount).where(MockITAccount.username == username.lower().strip())).first()
        if a is None:
            raise ValueError(f"No IT account named '{username}'")
        return {"username": a.username, "employee_id": a.employee_id, "status": a.status,
                "last_password_reset": a.last_password_reset, "software_access": a.software_access}


@_safe
def reset_password(username: str) -> dict:
    """Reset a user's password and unlock the account. A secure reset link is sent to the registered email
    (no password is shown here)."""
    with get_session() as s:
        a = s.scalars(select(MockITAccount).where(MockITAccount.username == username.lower().strip())).first()
        if a is None:
            raise ValueError(f"No IT account named '{username}'")
        was = a.status
        a.status = "ACTIVE"
        a.last_password_reset = date.today()
        s.commit()
        return {"username": a.username, "previous_status": was, "status": a.status,
                "result": "Password reset link sent to the registered email. Account is active."}


@_safe
def grant_software_access(username: str, software: str) -> dict:
    """Add a software or system to a user's access list (for approved software requests)."""
    with get_session() as s:
        a = s.scalars(select(MockITAccount).where(MockITAccount.username == username.lower().strip())).first()
        if a is None:
            raise ValueError(f"No IT account named '{username}'")
        current = [x.strip() for x in a.software_access.split(",") if x.strip()]
        if software.strip().lower() in [c.lower() for c in current]:
            return {"username": a.username, "result": f"{software} is already available"}
        current.append(software.strip())
        a.software_access = ", ".join(current)
        s.commit()
        return {"username": a.username, "software_access": a.software_access, "result": f"{software} added"}


# ============================================================================
# HR agent
# ============================================================================
@_safe
def get_employee_info(employee: str) -> dict:
    """Find an employee by employee ID (like EMP001) or by name. Returns department, leave balance and shift."""
    q = employee.strip()
    with get_session() as s:
        e = s.scalars(select(MockEmployee).where(MockEmployee.employee_id == q.upper())).first()
        if e is None:
            e = s.scalars(select(MockEmployee).where(MockEmployee.name.ilike(f"%{q}%"))).first()
        if e is None:
            raise ValueError(f"No employee found for '{employee}'")
        return {"employee_id": e.employee_id, "name": e.name, "department": e.department,
                "leave_balance": {"casual": e.casual_leave, "sick": e.sick_leave, "earned": e.earned_leave},
                "shift": e.shift}


# ============================================================================
# Accounts agent
# ============================================================================
def _payment(s, invoice_no: str) -> MockPayment:
    p = s.scalars(select(MockPayment).where(MockPayment.invoice_no == invoice_no.upper().strip())).first()
    if p is None:
        raise ValueError(f"Invoice {invoice_no} not found")
    return p


@_safe
def check_payment_status(invoice_no: str) -> dict:
    """Check a vendor invoice: vendor, amount, due date, payment status, approval status, days overdue."""
    with get_session() as s:
        p = _payment(s, invoice_no)
        overdue = (date.today() - p.due_date).days if p.status == "PENDING" and date.today() > p.due_date else 0
        return {"invoice_no": p.invoice_no, "vendor": p.vendor, "amount": p.amount, "due_date": p.due_date,
                "status": p.status, "approval_status": p.approval_status, "days_overdue": overdue,
                "paid_on": p.paid_on, "note": p.note}


@_safe
def verify_invoice(invoice_no: str) -> dict:
    """Check the approval records of an invoice (level 1, level 2, who approved, compliance check result).
    Use it to find why a payment is stuck."""
    with get_session() as s:
        p = _payment(s, invoice_no)
        rows = s.scalars(select(MockApproval).where(MockApproval.invoice_no == p.invoice_no)
                         .order_by(MockApproval.level)).all()
        return {"invoice_no": p.invoice_no, "amount": p.amount, "payment_approval_status": p.approval_status,
                "level_2_required": p.amount >= L2_LIMIT,
                "approvals": [{"level": r.level, "approver": r.approver, "status": r.status,
                               "compliance_check": r.compliance_check, "note": r.note} for r in rows]}


@_safe
def process_payment(invoice_no: str, verified_by: str) -> dict:
    """Release a pending vendor payment. Allowed ONLY when the approvals are complete and (for invoices of
    Rs 2,00,000 or more) Compliance has marked them COMPLIANT. Otherwise an error explains what is missing."""
    with get_session() as s:
        p = _payment(s, invoice_no)
        if p.status != "PENDING":
            raise ValueError(f"{p.invoice_no} is {p.status}, nothing to process")
        if p.amount >= L2_LIMIT:
            rows = s.scalars(select(MockApproval).where(MockApproval.invoice_no == p.invoice_no)).all()
            levels = {r.level for r in rows if r.status == "APPROVED"}
            if not {"L1", "L2"} <= levels:
                raise ValueError("Level 1 and level 2 approvals are both required and not complete yet.")
            if any(r.compliance_check != "COMPLIANT" for r in rows):
                raise ValueError("Compliance has not marked the approvals COMPLIANT yet. Ask the Compliance_Agent to verify.")
        elif p.approval_status != "COMPLETE":
            raise ValueError("Approval is not complete yet.")
        p.status = "PAID"
        p.approval_status = "COMPLETE"
        p.paid_on = date.today()
        p.note = f"Payment released. Verified by {verified_by}."
        s.commit()
        return {"invoice_no": p.invoice_no, "status": p.status, "paid_on": p.paid_on,
                "result": "Payment released. Approval workflow updated to COMPLETE."}


@_safe
def check_refund_eligibility(invoice_no: str) -> dict:
    """Check whether an invoice can be refunded. Only PAID invoices qualify, and Compliance approval is needed."""
    with get_session() as s:
        p = _payment(s, invoice_no)
        eligible = p.status == "PAID"
        return {"invoice_no": p.invoice_no, "vendor": p.vendor, "amount": p.amount, "status": p.status,
                "refund_eligible": eligible,
                "next_step": ("Ask the Compliance_Agent for refund approval, then process within 7 working days (ACC-POL-02)."
                              if eligible else "Not eligible: only PAID invoices can be refunded.")}


# ============================================================================
# Compliance agent
# ============================================================================
@_safe
def check_approval_status(invoice_no: str) -> dict:
    """Show every approval record of an invoice with approver, status and compliance check result."""
    with get_session() as s:
        rows = s.scalars(select(MockApproval).where(MockApproval.invoice_no == invoice_no.upper().strip())
                         .order_by(MockApproval.level)).all()
        if not rows:
            raise ValueError(f"No approval records for {invoice_no}")
        return {"invoice_no": invoice_no.upper().strip(),
                "approvals": [{"ref": r.ref, "level": r.level, "approver": r.approver, "status": r.status,
                               "compliance_check": r.compliance_check, "note": r.note} for r in rows]}


@_safe
def record_compliance_decision(invoice_no: str, decision: str, remarks: str) -> dict:
    """Record the Compliance decision for an invoice: COMPLIANT (approve) or NON-COMPLIANT (reject).
    Only use COMPLIANT after you verified that the approvals are APPROVED."""
    decision = decision.strip().upper()
    if decision not in ("COMPLIANT", "NON-COMPLIANT"):
        raise ValueError("decision must be COMPLIANT or NON-COMPLIANT")
    with get_session() as s:
        rows = s.scalars(select(MockApproval).where(MockApproval.invoice_no == invoice_no.upper().strip())).all()
        if not rows:
            raise ValueError(f"No approval records for {invoice_no}")
        if decision == "COMPLIANT" and any(r.status != "APPROVED" for r in rows):
            raise ValueError("Cannot mark COMPLIANT: at least one approval is not APPROVED yet.")
        for r in rows:
            r.compliance_check = decision
        s.commit()
        return {"invoice_no": invoice_no.upper().strip(), "decision": decision, "remarks": remarks}


_HIGH_WORDS = ["data leak", "leak", "breach", "wrong person", "wrong recipient", "personal data", "customer data",
               "shared password", "unauthorized", "unauthorised", "hacked", "phishing"]


@_safe
def assess_risk(subject: str, details: str, invoice_no: str = "") -> dict:
    """Rule-based risk assessment. For a data or security incident, describe it in subject and details.
    For a payment, also give the invoice_no. Returns risk level (Low, Medium, High, Critical),
    reasons, indicative regulation references and a recommended action."""
    text = f"{subject} {details}".lower()
    reasons, level = [], 0                                  # 0 Low, 1 Medium, 2 High, 3 Critical
    hits = [w for w in _HIGH_WORDS if w in text]
    if hits:
        level = 2
        reasons.append("Possible data or security incident: " + ", ".join(hits))
        if any(w in text for w in ("customer data", "personal data", "wrong person", "wrong recipient")):
            level = 3
            reasons.append("Personal or customer data may have been exposed")
    if invoice_no:
        with get_session() as s:
            p = _payment(s, invoice_no)
            rows = s.scalars(select(MockApproval).where(MockApproval.invoice_no == p.invoice_no)).all()
            if p.amount >= 500000:
                level = max(level, 1)
                reasons.append(f"High value payment (Rs {p.amount:,})")
            if p.amount >= L2_LIMIT and not {"L1", "L2"} <= {r.level for r in rows if r.status == "APPROVED"}:
                level = max(level, 2)
                reasons.append("Required approvals are not complete")
    names = ["Low", "Medium", "High", "Critical"]
    refs = []
    if hits:
        refs += ["Company Data Privacy Policy CMP-POL-01 (mock)", "India DPDP Act, 2023 - personal data breach duties (indicative)"]
    if invoice_no:
        refs.append("Payment Compliance Policy CMP-POL-02 (mock)")
    action = {0: "No special action.", 1: "Verify documents before payment.",
              2: "Investigate now and keep the Admin_Agent informed.",
              3: "Escalate immediately, contain the exposure and inform Admin_Agent and Supervisor_Agent."}[level]
    return {"risk_level": names[level], "reasons": reasons or ["No risk indicators found"],
            "regulation_references": refs, "recommended_action": action}


# ============================================================================
# Tool lists used when we create the agents (step 15)
# ============================================================================
IT_TOOLS = [check_access, reset_password, grant_software_access, search_policy] + SHARED_TOOLS
HR_TOOLS = [get_employee_info, search_policy] + SHARED_TOOLS
ACCOUNTS_TOOLS = [check_payment_status, verify_invoice, process_payment, check_refund_eligibility,
                  search_policy] + SHARED_TOOLS
COMPLIANCE_TOOLS = [check_approval_status, record_compliance_decision, assess_risk, search_policy] + SHARED_TOOLS
ALL_TOOL_LISTS = {"Admin": ADMIN_TOOLS, "IT": IT_TOOLS, "HR": HR_TOOLS,
                  "Accounts": ACCOUNTS_TOOLS, "Compliance": COMPLIANCE_TOOLS}
