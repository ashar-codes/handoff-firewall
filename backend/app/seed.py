"""Development samples. Explicit environment gate and user-supplied password."""

import argparse
import getpass
import os
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .domain import audit, canonical
from .models import Action, Case, Document, Fact, Template, Tenant, User, now
from .schemas import TemplateIn
from .security import digest, hasher


def seed(password):
    if settings().app_env not in {"development", "test"}:
        raise RuntimeError("Sample seed is forbidden outside development/test")
    if len(password) < 12:
        raise ValueError("Provide a sample password with at least 12 characters")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "admin@example.test")):
            return
        tenant = Tenant(name="Sample workspace")
        db.add(tenant)
        db.flush()
        admin = User(
            tenant_id=tenant.id,
            name="Sample Administrator",
            email="admin@example.test",
            role="Administrator",
            password_hash=hasher.hash(password),
        )
        db.add(admin)
        db.flush()
        for name, role in [
            ("Operator", "Operator"),
            ("Reviewer", "Reviewer"),
            ("Viewer", "Viewer"),
        ]:
            db.add(
                User(
                    tenant_id=tenant.id,
                    name="Sample " + name,
                    role=role,
                    email=name.lower() + "@example.test",
                    password_hash=hasher.hash(password),
                )
            )
        body = TemplateIn(
            name="Order ready for Finance",
            source="Sales",
            destination="Finance",
            rules=[
                {
                    "id": "purchase_order",
                    "label": "Customer purchase order",
                    "fields": ["po_number", "purchase_order"],
                },
                {"id": "quotation", "label": "Approved quotation", "fields": ["quotation_id"]},
                {"id": "account", "label": "Customer account", "fields": ["account_id"]},
                {"id": "terms", "label": "Consistent payment terms", "fields": ["payment_terms"]},
                {"id": "tax", "label": "Tax registration", "fields": ["tax_id"]},
                {
                    "id": "discount",
                    "label": "Discount approval",
                    "fields": ["discount_approval"],
                    "condition": {"field": "discount_requires_approval", "equals": "yes"},
                    "review": True,
                },
            ],
        )
        rules = [r.model_dump() for r in body.rules]
        t = Template(
            tenant_id=tenant.id,
            family=tenant.id,
            version=1,
            name=body.name,
            source=body.source,
            destination=body.destination,
            rules=rules,
            rule_hash=digest(canonical(rules)),
        )
        db.add(t)
        db.flush()
        samples = [
            (
                "SO-1042",
                "Commercial order with conflicting terms",
                "yes",
                [
                    (
                        "Customer PO.txt",
                        "po_number: PO-1042\naccount_id: AC-302\npayment_terms: 30 days",
                    ),
                    ("Approved quotation.txt", "quotation_id: QT-771\npayment_terms: 45 days"),
                    ("Archive-note-17.txt", "discount_approval: Approved by commercial director"),
                ],
            ),
            (
                "SO-1043",
                "Complete order awaiting verification",
                "no",
                [
                    (
                        "Order package.txt",
                        "po_number: PO-1043\nquotation_id: QT-772\naccount_id: AC-304\npayment_terms: 30 days\ntax_id: TAX-91",
                    )
                ],
            ),
            ("SO-1044", "Missing customer evidence", "no", [("Intake.txt", "account_id: AC-305")]),
            (
                "SO-1045",
                "Conflicting identifiers",
                "no",
                [
                    ("Sales note.txt", "po_number: PO-1045"),
                    ("Customer note.txt", "po_number: PO-2045"),
                ],
            ),
            (
                "SO-1046",
                "Stale document replaced",
                "no",
                [("Old order.txt", "account_id: AC-old"), ("New order.txt", "account_id: AC-new")],
            ),
            (
                "SO-1047",
                "Approval evidence needs reviewer",
                "yes",
                [
                    (
                        "Finance file.txt",
                        "po_number: PO-1047\nquotation_id: QT-775\naccount_id: AC-307\npayment_terms: 30 days\ntax_id: TAX-93\ndiscount_approval: Sales manager approved",
                    )
                ],
            ),
            (
                "SO-1048",
                "Clarification received; ready to resume verification",
                "no",
                [
                    (
                        "Order package.txt",
                        "po_number: PO-1048\nquotation_id: QT-776\naccount_id: AC-308\npayment_terms: 30 days",
                    )
                ],
            ),
        ]
        for business_key, title, discount, docs in samples:
            case = Case(
                tenant_id=tenant.id,
                title=title,
                business_key=business_key,
                template_id=t.id,
                owner_id=admin.id,
                goal="Ready for receiving-team review",
                context={"discount_requires_approval": discount},
                sample=True,
            )
            db.add(case)
            db.flush()
            previous = None
            for name, contents in docs:
                path = Path(settings().storage_path).resolve() / tenant.id / case.id / name
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                path.write_text(contents)
                os.chmod(path, 0o600)
                document = Document(
                    tenant_id=tenant.id,
                    case_id=case.id,
                    name=name,
                    sha256=digest(contents),
                    path=str(path.relative_to(Path(settings().storage_path).resolve())),
                    text=contents,
                )
                if business_key == "SO-1046" and previous:
                    previous.active = False
                    document.version = 2
                    document.replaces_id = previous.id
                db.add(document)
                db.flush()
                previous = document
            audit(
                db,
                tenant.id,
                case.id,
                "sample_case",
                "Development sample case created",
                admin.id,
                data={"created_at": now()},
            )
            if business_key in {"SO-1047", "SO-1048"}:
                # Clearly labeled imported sample states, not fake live model executions.
                from .agents import evidence_agent, requirement_agent
                from .domain import evaluate, fingerprint, snapshot, transition
                from .providers import TestProvider

                transition(db, case, "CHECKING", "Development fixture initialization", admin.id)
                requirement_agent(db, case)
                evidence_agent(db, case, TestProvider())
                if business_key == "SO-1047":
                    snap = snapshot(db, case)
                    payload = {
                        "requirements": ["discount"],
                        "message": "Review imported sample discount approval",
                        "recipient": admin.id,
                        "connector": "internal",
                        "fields": {"discount": ["discount_approval"]},
                        "candidate_facts": case.statuses["discount"]["facts"],
                        "permissions_needed": ["operate", "review"],
                    }
                    fp = fingerprint("review_evidence", payload, snap, admin.id)
                    db.add(
                        Action(
                            tenant_id=tenant.id,
                            case_id=case.id,
                            kind="review_evidence",
                            owner_id=admin.id,
                            payload=payload,
                            snapshot=snap,
                            fingerprint=fp,
                            dedupe_key=fp,
                            approval_required=True,
                            effort=3,
                            reason="Imported development fixture; human review remains pending",
                        )
                    )
                    case.graph = {**case.graph, "planned": True}
                    transition(
                        db, case, "BLOCKED", "Sample evidence requires human review", admin.id
                    )
                    transition(db, case, "WAITING", "Sample waiting-for-review scenario", admin.id)
                else:
                    reviewer = db.scalar(
                        select(User).where(User.tenant_id == tenant.id, User.role == "Reviewer")
                    )
                    quote = "Development fixture: previously received tax clarification accepted by sample reviewer"
                    db.add(
                        Fact(
                            tenant_id=tenant.id,
                            case_id=case.id,
                            requirement_id="tax",
                            field="tax_id",
                            value="TAX-94",
                            source_hash=digest(quote),
                            source_version=1,
                            location="Sample clarification archive",
                            quote=quote,
                            method="human_reply",
                            accepted=True,
                            accepted_by=reviewer.id,
                        )
                    )
                    db.flush()
                    evaluate(db, case, force=True)
                    transition(
                        db,
                        case,
                        "VERIFYING",
                        "Imported sample clarification ready for resumed verification",
                        admin.id,
                    )
                audit(
                    db,
                    tenant.id,
                    case.id,
                    "sample_fixture",
                    "Imported synthetic development state; not a live model execution",
                    admin.id,
                )
        db.commit()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--password-env", default="SEED_PASSWORD")
    args = p.parse_args()
    password = os.getenv(args.password_env) or getpass.getpass(
        "Development sample password (12+ chars): "
    )
    seed(password)
    print("Sample workspace created. Sign in as admin@example.test with your chosen password.")


if __name__ == "__main__":
    main()
