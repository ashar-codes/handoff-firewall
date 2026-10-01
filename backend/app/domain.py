import json

from fastapi import HTTPException
from sqlalchemy import func, select

from .models import Action, Conflict, Document, Event, Fact, Template, now
from .security import digest
from .storage import valid_original

TRANSITIONS = {
    "NEW": {"CHECKING", "ESCALATED"},
    "CHECKING": {"BLOCKED", "VERIFYING", "ESCALATED"},
    "BLOCKED": {"CHECKING", "WAITING", "VERIFYING", "ESCALATED"},
    "WAITING": {"VERIFYING", "ESCALATED"},
    "VERIFYING": {"READY", "BLOCKED", "ESCALATED"},
    "READY": {"VERIFYING"},
    "ESCALATED": {"VERIFYING"},
}


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scoped(db, cls, object_id, tenant_id, lock=False):
    stmt = select(cls).where(cls.id == object_id, cls.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update()
    obj = db.scalar(stmt)
    if not obj:
        raise HTTPException(404, "Record not found")
    return obj


def case_rows(db, cls, case):
    return list(
        db.scalars(select(cls).where(cls.case_id == case.id, cls.tenant_id == case.tenant_id))
    )


def audit(db, tenant_id, case_id, kind, summary, actor=None, agent=None, data=None):
    seq = (
        db.scalar(
            select(func.max(Event.seq)).where(
                Event.tenant_id == tenant_id, Event.case_id == case_id
            )
        )
        or 0
    ) + 1
    e = Event(
        tenant_id=tenant_id,
        case_id=case_id,
        seq=seq,
        kind=kind,
        summary=summary,
        actor_id=actor,
        agent=agent,
        data=data or {},
    )
    db.add(e)
    db.flush()
    return e


def transition(db, case, target, reason, actor=None):
    if case.state == target:
        return
    if target not in TRANSITIONS.get(case.state, set()):
        raise HTTPException(409, f"Invalid transition: {case.state} to {target}")
    old = case.state
    case.state = target
    case.updated_at = now()
    audit(db, case.tenant_id, case.id, "state", reason, actor, data={"from": old, "to": target})


def snapshot(db, case):
    t = scoped(db, Template, case.template_id, case.tenant_id)
    docs = case_rows(db, Document, case)
    return {
        "case_id": case.id,
        "tenant_id": case.tenant_id,
        "revision": case.revision,
        "rule_id": t.id,
        "rule_hash": t.rule_hash,
        "documents": sorted(
            [{"id": d.id, "hash": d.sha256, "version": d.version} for d in docs if d.active],
            key=lambda d: d["id"],
        ),
    }


def fingerprint(kind, payload, snap, owner):
    return digest(canonical({"kind": kind, "payload": payload, "snapshot": snap, "owner": owner}))


def mark_dirty(case, rules, requirement_ids):
    affected = set(requirement_ids) | set(case.graph.get("dirty", []))
    for _ in rules:
        affected |= {r["id"] for r in rules if set(r.get("depends_on", [])) & affected}
    case.graph = {**case.graph, "dirty": sorted(affected)}


def invalidate(db, case, requirement_ids=None, actor=None, reason="Evidence changed"):
    t = scoped(db, Template, case.template_id, case.tenant_id)
    affected = set(requirement_ids or [r["id"] for r in t.rules])
    affected |= set(case.graph.get("dirty", []))
    while True:
        extra = {r["id"] for r in t.rules if set(r.get("depends_on", [])) & affected}
        if extra <= affected:
            break
        affected |= extra
    case.revision += 1
    statuses = dict(case.statuses)
    for key in affected:
        statuses[key] = {"state": "INVALIDATED", "facts": [], "reason": reason}
    case.statuses = statuses
    case.graph = {
        "dirty": sorted(affected),
        "change": {"actor_id": actor, "reason": reason},
        "extracted": case.graph.get("extracted", {}),
    }
    case.error = None
    case.updated_at = now()
    for a in case_rows(db, Action, case):
        if (
            a.kind == "internal_clarification"
            and a.status == "WAITING"
            and not (
                (
                    set(a.payload["requirements"])
                    - set((a.result or {}).get("answered_requirements", []))
                )
                & affected
            )
        ):
            continue  # preserve unrelated outstanding requests; no duplicate outreach
        if a.status in {"PROPOSED", "APPROVED", "WAITING"}:
            a.status = "INVALIDATED"
    for conflict in case_rows(db, Conflict, case):
        if conflict.requirement_id in affected and not conflict.resolved:
            conflict.resolution_state = "REVALIDATING"
    if case.state in {"READY", "WAITING", "ESCALATED", "BLOCKED", "CHECKING"}:
        transition(db, case, "VERIFYING", reason, actor)
    audit(
        db,
        case.tenant_id,
        case.id,
        "invalidate",
        reason,
        actor,
        data={"requirements": sorted(affected), "revision": case.revision},
    )


def retry(db, case, actor):
    """Repeat a failed investigation/drafting step without treating unchanged evidence as new.

    The revision is unchanged, so proposals, approvals and already-sent requests stay bound and
    valid; the planner may refresh unsent wording in place. Source changes still use invalidate().
    """
    t = scoped(db, Template, case.template_id, case.tenant_id)
    retained = [
        a.id for a in case_rows(db, Action, case) if a.status in {"PROPOSED", "APPROVED", "WAITING"}
    ]
    reason = "Authorized retry of failed investigation"
    case.graph = {
        "dirty": [r["id"] for r in t.rules],
        "change": {"actor_id": actor, "reason": reason},
        "extracted": case.graph.get("extracted", {}),
    }
    case.error = None
    case.updated_at = now()
    if case.state in {"WAITING", "BLOCKED", "CHECKING"}:
        transition(db, case, "VERIFYING", reason, actor)
    audit(
        db,
        case.tenant_id,
        case.id,
        "retry",
        reason + "; existing proposals, approvals and sent requests retained",
        actor,
        data={"retained_actions": retained},
    )


def normalize(value):
    return " ".join(str(value).strip().casefold().split())


def evaluate(db, case, force=False):
    template = scoped(db, Template, case.template_id, case.tenant_id)
    documents = {d.id: d for d in case_rows(db, Document, case) if d.active}
    allfacts = case_rows(db, Fact, case)
    current = [
        f
        for f in allfacts
        if not f.document_id
        or (
            f.document_id in documents
            and not documents[f.document_id].parse_error
            and documents[f.document_id].sha256 == f.source_hash
            and documents[f.document_id].version == f.source_version
        )
    ]
    superseded = {x for f in current if f.accepted for x in f.supersedes}
    statuses = dict(case.statuses)
    dirty = (
        {r["id"] for r in template.rules}
        if force
        else set(case.graph.get("dirty", [r["id"] for r in template.rules]))
    )
    for r in template.rules:
        if r["id"] not in dirty and r["id"] in statuses:
            continue
        facts = [
            f
            for f in current
            if f.requirement_id == r["id"]
            and f.field in r["fields"]
            and f.id not in superseded
            and f.review_decision != "REJECTED"
        ]
        accepted = [f for f in facts if f.accepted]
        condition = r.get("condition")
        if condition and condition["field"] not in case.context:
            state, reason = "AMBIGUOUS", "Condition field is unknown; no assumption was made"
        elif condition and normalize(case.context[condition["field"]]) != normalize(
            condition["equals"]
        ):
            state, reason = "NOT_APPLICABLE", "Approved condition excludes this requirement"
        elif not accepted:
            state = (
                "AWAITING_REVIEW"
                if facts
                else ("UNREADABLE" if any(d.parse_error for d in documents.values()) else "MISSING")
            )
            reason = (
                "Candidate evidence requires a reviewer"
                if facts
                else "No accepted current evidence"
            )
        else:
            if r.get("precedence") == "latest_document":
                # Version counters are meaningful only inside one replacement lineage.
                all_docs = {d.id: d for d in case_rows(db, Document, case)}

                def root_id(f, records=all_docs):
                    if not f.document_id:
                        return f.id
                    d = records[f.document_id]
                    while d.replaces_id:
                        d = records[d.replaces_id]
                    return d.id

                if len({root_id(f) for f in accepted}) == 1:
                    latest = max(f.source_version for f in accepted)
                    accepted = [f for f in accepted if f.source_version == latest]
            values = {normalize(f.value) for f in accepted}
            if len(values) > 1:
                state, reason = "CONFLICTING", "Current accepted sources disagree"
            elif any(not f.accepted and normalize(f.value) not in values for f in facts):
                state, reason = (
                    "AWAITING_REVIEW",
                    "Candidate evidence contradicts accepted evidence",
                )
            elif r.get("expected") is not None and values != {normalize(r["expected"])}:
                state, reason = "CONFLICTING", "Evidence differs from the approved expected value"
            elif r.get("review") and not any(f.accepted_by for f in accepted):
                state, reason = "AWAITING_REVIEW", "Policy requires human acceptance"
            else:
                state, reason = "SATISFIED", "Current source evidence satisfies the rule"
        statuses[r["id"]] = {
            "state": state,
            "reason": reason,
            "facts": [f.id for f in facts],
            "rule_version": template.version,
        }
    # Dependencies can only reduce readiness, never prove a missing requirement.
    for _ in template.rules:
        for r in template.rules:
            if statuses[r["id"]]["state"] == "SATISFIED" and any(
                statuses[k]["state"] not in {"SATISFIED", "NOT_APPLICABLE"}
                for k in r.get("depends_on", [])
            ):
                statuses[r["id"]] = {
                    **statuses[r["id"]],
                    "state": "MISSING",
                    "reason": "A prerequisite remains unresolved",
                }
    case.statuses = statuses
    case.graph = {**case.graph, "dirty": []}
    for conflict in case_rows(db, Conflict, case):
        status = statuses.get(conflict.requirement_id, {})
        if not conflict.resolved and status.get("state") != "INVALIDATED":
            same_conflict = status.get("state") == "CONFLICTING" and set(conflict.facts) == set(
                status.get("facts", [])
            )
            if same_conflict:
                conflict.resolution_state = "OPEN"
            else:
                conflict.resolved = True
                conflict.resolution_state = (
                    "RESOLVED"
                    if status.get("state") in {"SATISFIED", "NOT_APPLICABLE"}
                    else "SUPERSEDED"
                )
                conflict.resolution = {
                    **case.graph.get("change", {}),
                    "at": now(),
                    "requirement_state": status.get("state"),
                    "facts": status.get("facts", []),
                }
                audit(
                    db,
                    case.tenant_id,
                    case.id,
                    "conflict_closed",
                    "Conflict revalidated: " + conflict.resolution_state,
                    conflict.resolution.get("actor_id"),
                    data={"conflict_id": conflict.id, **conflict.resolution},
                )
    return statuses


def ready(db, case):
    t = scoped(db, Template, case.template_id, case.tenant_id)
    for doc in case_rows(db, Document, case):
        if doc.active and doc.parse_error:
            case.error = "Active source is unreadable; replace it or obtain a reviewer exclusion"
            return False
        if doc.active and not valid_original(doc):
            if doc.parse_error != "Original file integrity check failed":
                doc.parse_error = "Original file integrity check failed"
                invalidate(
                    db, case, actor=None, reason="Original source file changed or is missing"
                )
            return False
    # Clearance never trusts the incremental cache. This bounded rules-only pass
    # has no model calls and independently checks every authoritative condition.
    evaluate(db, case, force=True)
    return all(
        case.statuses.get(r["id"], {}).get("state") in {"SATISFIED", "NOT_APPLICABLE"}
        for r in t.rules
        if r.get("mandatory", True)
    )
