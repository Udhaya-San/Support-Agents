"""
core/seed.py  -  fills the MOCK company tables with fake data for the agents to look up.

Run from the project root:
    python -m core.seed

Safe to run many times: it clears only the mock tables and fills them again.
It never touches your tickets.
"""

from datetime import date, timedelta

from core.db import get_session, init_db
from core.models import MockApproval, MockEmployee, MockITAccount, MockPayment


def seed_mock_data():
    init_db()
    today = date.today()

    payments = [
        # The assignment example: vendor payment not processed for 20 days.
        # Both approvals really happened, but the workflow flag was never updated.
        MockPayment(invoice_no="INV-1001", vendor="Apex Supplies Pvt Ltd", amount=485000,
                    invoice_date=today - timedelta(days=35), due_date=today - timedelta(days=20),
                    status="PENDING", approval_status="INCOMPLETE",
                    note="Payment on hold: approval workflow shows INCOMPLETE."),
        # Already paid, can be used to test a refund request
        MockPayment(invoice_no="INV-1002", vendor="BrightLabs Services", amount=120000,
                    invoice_date=today - timedelta(days=40), due_date=today - timedelta(days=25),
                    status="PAID", approval_status="COMPLETE", paid_on=today - timedelta(days=24),
                    note="Paid in full. Refund possible only with Compliance approval."),
        MockPayment(invoice_no="INV-1003", vendor="Nova Logistics", amount=67500,
                    invoice_date=today - timedelta(days=30), due_date=today - timedelta(days=15),
                    status="PAID", approval_status="COMPLETE", paid_on=today - timedelta(days=14)),
        # Normal pending invoice, not due yet
        MockPayment(invoice_no="INV-1004", vendor="Greenfield Stationers", amount=18400,
                    invoice_date=today - timedelta(days=5), due_date=today + timedelta(days=10),
                    status="PENDING", approval_status="COMPLETE",
                    note="Scheduled in the next payment run."),
        # Overdue because level 2 approval is genuinely still pending
        MockPayment(invoice_no="INV-1005", vendor="Orbit IT Hardware", amount=295000,
                    invoice_date=today - timedelta(days=25), due_date=today - timedelta(days=3),
                    status="PENDING", approval_status="PENDING",
                    note="Waiting for level 2 (CFO) approval."),
    ]

    approvals = [
        MockApproval(ref="APR-1001-L1", invoice_no="INV-1001", level="L1", approver="Finance Manager",
                     status="APPROVED", compliance_check="NOT CHECKED"),
        MockApproval(ref="APR-1001-L2", invoice_no="INV-1001", level="L2", approver="CFO",
                     status="APPROVED", compliance_check="NOT CHECKED",
                     note="Approved by email, but the workflow system was not updated."),
        MockApproval(ref="APR-1002-L1", invoice_no="INV-1002", level="L1", approver="Finance Manager",
                     status="APPROVED", compliance_check="COMPLIANT"),
        MockApproval(ref="APR-1005-L1", invoice_no="INV-1005", level="L1", approver="Finance Manager",
                     status="APPROVED", compliance_check="NOT CHECKED"),
        MockApproval(ref="APR-1005-L2", invoice_no="INV-1005", level="L2", approver="CFO",
                     status="PENDING", compliance_check="NOT CHECKED"),
    ]

    employees = [
        MockEmployee(employee_id="EMP001", name="Ravi Kumar", department="Engineering",
                     casual_leave=6, sick_leave=4, earned_leave=12, shift="09:00-18:00"),
        MockEmployee(employee_id="EMP002", name="Priya Nair", department="HR",
                     casual_leave=3, sick_leave=7, earned_leave=15, shift="09:30-18:30"),
        MockEmployee(employee_id="EMP003", name="Arjun Mehta", department="Finance",
                     casual_leave=8, sick_leave=5, earned_leave=9, shift="09:00-18:00"),
        MockEmployee(employee_id="EMP004", name="Sana Khan", department="Sales",
                     casual_leave=2, sick_leave=6, earned_leave=20, shift="10:00-19:00"),
    ]

    it_accounts = [
        MockITAccount(username="ravi.kumar", employee_id="EMP001", status="ACTIVE",
                      last_password_reset=today - timedelta(days=60), software_access="Email, VPN, Jira, GitHub"),
        MockITAccount(username="priya.nair", employee_id="EMP002", status="ACTIVE",
                      last_password_reset=today - timedelta(days=20), software_access="Email, HRMS"),
        MockITAccount(username="arjun.mehta", employee_id="EMP003", status="ACTIVE",
                      last_password_reset=today - timedelta(days=90), software_access="Email, ERP, Finance Portal"),
        MockITAccount(username="sana.khan", employee_id="EMP004", status="LOCKED",
                      last_password_reset=today - timedelta(days=120), software_access="Email, CRM"),
    ]

    with get_session() as s:
        for model in (MockPayment, MockApproval, MockEmployee, MockITAccount):
            s.query(model).delete()
        s.add_all(payments + approvals + employees + it_accounts)
        s.commit()
    return {"payments": len(payments), "approvals": len(approvals),
            "employees": len(employees), "it_accounts": len(it_accounts)}


if __name__ == "__main__":
    counts = seed_mock_data()
    print("Mock data ready:", counts)
    with get_session() as s:
        p = s.query(MockPayment).filter_by(invoice_no="INV-1001").first()
        print(f"Sample: {p.invoice_no} | {p.vendor} | Rs {p.amount:,} | due {p.due_date} | "
              f"{p.status} | approval {p.approval_status}")
