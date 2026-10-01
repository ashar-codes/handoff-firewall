from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .db import get_db
from .domain import audit, canonical, case_rows, fingerprint, scoped, snapshot
from .models import Action, Case, Document
from .schemas import Strict
from .security import digest, require

router = APIRouter(prefix="/api")


class ExternalDraft(Strict):
    recipient: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=254)
    message: str = Field(min_length=1, max_length=4000)
    requirements: list[str] = Field(min_length=1, max_length=50)


class ExcludeSource(Strict):
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/documents/{document_id}/exclude")
def exclude_source(
    document_id: str, body: ExcludeSource, user=Depends(require("review")), db=Depends(get_db)
):
    from .domain import invalidate

    doc = scoped(db, Document, document_id, user.tenant_id)
    c = scoped(db, Case, doc.case_id, user.tenant_id, lock=True)
    doc.active = False
    invalidate(db, c, actor=user.id, reason="Reviewer excluded source: " + body.reason)
    audit(
        db,
        user.tenant_id,
        c.id,
        "source_excluded",
        body.reason,
        user.id,
        data={"document_id": doc.id, "source_hash": doc.sha256},
    )
    db.commit()
    return {"id": doc.id, "active": False}


@router.post("/cases/{case_id}/external-drafts", status_code=201)
def external_draft(
    case_id: str, body: ExternalDraft, user=Depends(require("operate")), db=Depends(get_db)
):
    c = scoped(db, Case, case_id, user.tenant_id, lock=True)
    if not c.graph.get("searched"):
        raise HTTPException(
            409, "Search existing authorized evidence before preparing external outreach"
        )
    if not set(body.requirements) <= set(c.statuses):
        raise HTTPException(422, "Unknown requirement")
    payload = {
        "recipient": body.recipient,
        "message": body.message,
        "requirements": body.requirements,
        "connector": "external-draft-only",
        "permissions_needed": ["operate", "review"],
        "fields": {},
        "candidate_facts": [],
    }
    snap = snapshot(db, c)
    fp = fingerprint("external_draft", payload, snap, c.owner_id)
    existing = next((a for a in case_rows(db, Action, c) if a.dedupe_key == fp), None)
    if existing:
        return {"id": existing.id, "status": existing.status}
    a = Action(
        tenant_id=user.tenant_id,
        case_id=c.id,
        kind="external_draft",
        owner_id=c.owner_id,
        payload=payload,
        snapshot=snap,
        fingerprint=fp,
        dedupe_key=fp,
        approval_required=True,
        effort=8,
        reason="Human-requested external draft; approval required; no delivery configured",
    )
    db.add(a)
    db.flush()
    audit(
        db,
        user.tenant_id,
        c.id,
        "external_draft",
        "Prepared an external clarification draft; nothing sent",
        user.id,
        data={"action_id": a.id, "fingerprint": fp, "payload_hash": digest(canonical(payload))},
    )
    db.commit()
    return {"id": a.id, "status": a.status}
