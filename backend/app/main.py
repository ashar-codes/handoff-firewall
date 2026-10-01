import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from .action_routes import router as action_router
from .admin_routes import router as admin_router
from .agents import execute_action
from .config import settings
from .db import SessionLocal, get_db
from .domain import (
    audit,
    canonical,
    case_rows,
    fingerprint,
    invalidate,
    retry,
    scoped,
    snapshot,
    transition,
)
from .evidence_text import affected_rules
from .models import (
    Action,
    Approval,
    AuthSession,
    Case,
    Conflict,
    Document,
    Event,
    Fact,
    Job,
    LoginGuard,
    Template,
    Tenant,
    User,
    now,
)
from .request_limits import BodyLimitMiddleware, BodyTooLarge
from .retrieval import ExactTextRetriever
from .schemas import (
    CaseIn,
    DecisionIn,
    LoginIn,
    ReplyIn,
    ReviewIn,
    TemplateIn,
    TransitionIn,
    UserIn,
)
from .security import (
    PERMISSIONS,
    check_origin,
    current_user,
    digest,
    hasher,
    require,
    verify_password,
)
from .storage import file_path

app = FastAPI(title="Handoff Firewall", version="0.1.0", dependencies=[Depends(check_origin)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Last-Event-ID"],
)


@app.middleware("http")
async def headers(request, call_next):
    request_id = str(uuid4())
    if request.method in {"POST", "PUT", "PATCH"}:
        length = request.headers.get("content-length")
        if length is not None and (
            not length.isdigit() or int(length) > settings().upload_limit + 1024 * 1024
        ):
            return Response(status_code=413)
    try:
        response = await call_next(request)
    except BodyTooLarge:
        response = JSONResponse(status_code=413, content={"detail": "Request body exceeds limit"})
    except Exception:
        # Catch before server-error middleware can log exception SQL parameters,
        # source content or credentials. Correlate only with the safe request ID.
        logging.getLogger(__name__).error("Request failed: %s", request_id)
        response = JSONResponse(
            status_code=500, content={"detail": "Request failed; no completion was assumed"}
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(IntegrityError)
async def conflict_error(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=409, content={"detail": "A duplicate or conflicting record exists"}
    )


@app.exception_handler(Exception)
async def safe_error(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500, content={"detail": "Request failed; no completion was assumed"}
    )


def public(row, omit=()):
    return {
        col.name: getattr(row, col.name)
        for col in row.__table__.columns
        if col.name not in {"password_hash", "path", "token_hash", "csrf_hash", *omit}
    }


def owner_valid(db, owner, tenant):
    user = scoped(db, User, owner, tenant)
    if not user.active:
        raise HTTPException(422, "Owner must be an active workspace user")


def queue(db, case, actor):
    active = db.scalar(
        select(Job).where(Job.active_key == case.id, Job.tenant_id == case.tenant_id)
    )
    if active:
        return active
    job = Job(tenant_id=case.tenant_id, case_id=case.id, actor_id=actor, active_key=case.id)
    db.add(job)
    db.flush()
    audit(db, case.tenant_id, case.id, "run_queued", "Case queued for bounded execution", actor)
    return job


@app.get("/api/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response, db=Depends(get_db)):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "unknown"
    guards = []
    for key in [digest("email:" + email), digest("ip:" + ip)]:
        guard = db.scalar(select(LoginGuard).where(LoginGuard.key == key).with_for_update())
        if not guard:
            guard = LoginGuard(key=key, attempts=0, window_start=now())
            db.add(guard)
            db.flush()
        if guard.window_start < now() - 900:
            guard.attempts = 0
            guard.window_start = now()
        if guard.attempts >= 10:
            db.commit()
            raise HTTPException(429, "Too many sign-in attempts; retry after 15 minutes")
        guards.append(guard)
    user = db.scalar(select(User).where(User.email == email))
    # Constant-cost verification for nonexistent identities.
    stored = user.password_hash if user else DUMMY_HASH
    valid = verify_password(stored, body.password)
    if not user or not user.active or not valid:
        for guard in guards:
            guard.attempts += 1
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=now() + settings().session_hours * 3600,
        )
    )
    guards[0].attempts = 0
    audit(db, user.tenant_id, None, "login", "User signed in", user.id)
    db.commit()
    response.set_cookie(
        "hf_session",
        token,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        "hf_csrf",
        csrf,
        httponly=False,
        secure=settings().cookie_secure,
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return public(user)


DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return public(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == digest(request.cookies.get("hf_session", ""))
        )
    )
    if session:
        db.delete(session)
    db.commit()
    response.delete_cookie("hf_session", path="/")
    response.delete_cookie("hf_csrf", path="/")
    return {"ok": True}


@app.get("/api/users")
def users(user=Depends(require("read")), db=Depends(get_db)):
    return [public(u) for u in db.scalars(select(User).where(User.tenant_id == user.tenant_id))]


@app.post("/api/users", status_code=201)
def create_user(body: UserIn, user=Depends(require("admin")), db=Depends(get_db)):
    if "@" not in body.email:
        raise HTTPException(422, "A valid email is required")
    u = User(
        tenant_id=user.tenant_id,
        email=body.email.strip().lower(),
        name=body.name,
        role=body.role,
        password_hash=hasher.hash(body.password),
    )
    db.add(u)
    db.flush()
    audit(
        db,
        user.tenant_id,
        None,
        "user_created",
        f"Created user with role {u.role}",
        user.id,
        data={"user_id": u.id},
    )
    db.commit()
    return public(u)


@app.get("/api/templates")
def templates(user=Depends(require("read")), db=Depends(get_db)):
    return [
        public(t)
        for t in db.scalars(
            select(Template)
            .where(Template.tenant_id == user.tenant_id)
            .order_by(Template.created_at.desc())
        )
    ]


def save_template(db, body, user, previous=None):
    rules = [r.model_dump() for r in body.rules]
    for r in rules:
        if r.get("owner_id"):
            owner_valid(db, r["owner_id"], user.tenant_id)
    family = previous.family if previous else str(uuid4())
    version = (
        db.scalar(
            select(func.max(Template.version)).where(
                Template.tenant_id == user.tenant_id, Template.family == family
            )
        )
        or 0
    ) + 1
    row = Template(
        tenant_id=user.tenant_id,
        family=family,
        version=version,
        name=body.name,
        source=body.source,
        destination=body.destination,
        rules=rules,
        rule_hash=digest(canonical(rules)),
    )
    db.add(row)
    db.flush()
    audit(
        db,
        user.tenant_id,
        None,
        "policy_version",
        f"Created approved workflow version {version}",
        user.id,
        data={"template_id": row.id, "hash": row.rule_hash},
    )
    db.commit()
    return public(row)


@app.post("/api/templates", status_code=201)
def create_template(body: TemplateIn, user=Depends(require("policy")), db=Depends(get_db)):
    return save_template(db, body, user)


@app.post("/api/templates/{template_id}/versions", status_code=201)
def version_template(
    template_id: str, body: TemplateIn, user=Depends(require("policy")), db=Depends(get_db)
):
    old = scoped(db, Template, template_id, user.tenant_id, lock=True)
    return save_template(db, body, user, old)


def case_summary(db, case):
    t = scoped(db, Template, case.template_id, case.tenant_id)
    mandatory = [r["id"] for r in t.rules if r.get("mandatory", True)]
    satisfied = sum(
        case.statuses.get(k, {}).get("state") in {"SATISFIED", "NOT_APPLICABLE"} for k in mandatory
    )
    return {
        **public(case),
        "source": t.source,
        "destination": t.destination,
        "workflow_name": t.name,
        "rule_version": t.version,
        "readiness": round(satisfied / len(mandatory) * 100) if mandatory else 100,
    }


@app.get("/api/cases")
def cases(user=Depends(require("read")), db=Depends(get_db)):
    return [
        case_summary(db, c)
        for c in db.scalars(
            select(Case)
            .where(Case.tenant_id == user.tenant_id)
            .order_by(Case.updated_at.desc())
            .limit(1000)
        )
    ]


@app.post("/api/cases", status_code=201)
def create_case(body: CaseIn, user=Depends(require("operate")), db=Depends(get_db)):
    if body.context and "review" not in PERMISSIONS.get(user.role, set()):
        raise HTTPException(403, "Reviewer permission is required to establish case conditions")
    if len(canonical(body.context)) > 10000:
        raise HTTPException(422, "Context is too large")
    scoped(db, Template, body.template_id, user.tenant_id)
    owner = body.owner_id or user.id
    owner_valid(db, owner, user.tenant_id)
    c = Case(
        tenant_id=user.tenant_id,
        title=body.title,
        business_key=body.business_key,
        template_id=body.template_id,
        owner_id=owner,
        goal=body.goal,
        context=body.context,
    )
    db.add(c)
    db.flush()
    audit(
        db,
        user.tenant_id,
        c.id,
        "case_created",
        "Handoff case created",
        user.id,
        data={"template_id": c.template_id, "context": c.context},
    )
    db.commit()
    return case_summary(db, c)


@app.get("/api/cases/{case_id}")
def detail(case_id: str, user=Depends(require("read")), db=Depends(get_db)):
    c = scoped(db, Case, case_id, user.tenant_id)
    template = scoped(db, Template, c.template_id, user.tenant_id)
    return {
        **case_summary(db, c),
        "template": public(template),
        "documents": [public(d) for d in case_rows(db, Document, c)],
        "facts": [public(f) for f in case_rows(db, Fact, c)],
        "conflicts": [public(f) for f in case_rows(db, Conflict, c) if not f.resolved],
        "conflict_history": [public(f) for f in case_rows(db, Conflict, c)],
        "approvals": [
            public(a)
            for a in db.scalars(
                select(Approval)
                .join(Action, Approval.action_id == Action.id)
                .where(
                    Action.case_id == c.id,
                    Action.tenant_id == c.tenant_id,
                    Approval.tenant_id == c.tenant_id,
                )
            )
        ],
        "actions": [public(a) for a in case_rows(db, Action, c)],
        "events": [public(e) for e in sorted(case_rows(db, Event, c), key=lambda x: x.seq)],
        "jobs": [public(j) for j in case_rows(db, Job, c)],
    }


@app.post("/api/cases/{case_id}/run", status_code=202)
def run(case_id: str, user=Depends(require("operate")), db=Depends(get_db)):
    c = scoped(db, Case, case_id, user.tenant_id, lock=True)
    if c.state == "READY":
        transition(db, c, "VERIFYING", "Authorized readiness integrity recheck", user.id)
    if c.state == "ESCALATED":
        invalidate(db, c, actor=user.id, reason="Authorized retry after escalation")
    # A deliberate retry repeats failed investigation/drafting; unchanged evidence keeps its
    # revision so approvals and sent requests are not invalidated or duplicated.
    if c.error:
        retry(db, c, user.id)
    j = queue(db, c, user.id)
    db.commit()
    return public(j)


@app.post("/api/cases/{case_id}/transition")
def manual_transition(
    case_id: str, body: TransitionIn, user=Depends(require("review")), db=Depends(get_db)
):
    c = scoped(db, Case, case_id, user.tenant_id, lock=True)
    transition(db, c, body.state, body.reason, user.id)
    db.commit()
    return case_summary(db, c)


@app.put("/api/cases/{case_id}/context")
def context(
    case_id: str, body: dict[str, str], user=Depends(require("review")), db=Depends(get_db)
):
    if len(canonical(body)) > 10000:
        raise HTTPException(422, "Context is too large")
    c = scoped(db, Case, case_id, user.tenant_id, lock=True)
    previous_context = c.context
    c.context = body
    invalidate(db, c, actor=user.id, reason="Reviewer updated case conditions")
    audit(
        db,
        c.tenant_id,
        c.id,
        "conditions_changed",
        "Reviewer changed applicability inputs",
        user.id,
        data={"before": previous_context, "after": body},
    )
    db.commit()
    return case_summary(db, c)


@app.post("/api/cases/{case_id}/rules/{template_id}")
def rebind(case_id: str, template_id: str, user=Depends(require("policy")), db=Depends(get_db)):
    c = scoped(db, Case, case_id, user.tenant_id, lock=True)
    scoped(db, Template, template_id, user.tenant_id)
    c.template_id = template_id
    for action in case_rows(db, Action, c):
        if action.status in {"PROPOSED", "APPROVED", "WAITING"}:
            action.status = "INVALIDATED"
    invalidate(db, c, actor=user.id, reason="Authorized policy version migration")
    db.commit()
    return case_summary(db, c)


@app.post("/api/cases/{case_id}/documents", status_code=201)
def upload(
    case_id: str,
    file: UploadFile = File(...),
    replaces_id: str | None = Form(None),
    user=Depends(require("operate")),
    db=Depends(get_db),
):
    c = scoped(db, Case, case_id, user.tenant_id, lock=True)
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(file.filename or "upload").name)[:180]
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".txt", ".csv", ".json"}:
        raise HTTPException(422, "Only PDF, TXT, CSV and JSON are supported")
    content = file.file.read(settings().upload_limit + 1)
    if not content or len(content) > settings().upload_limit:
        raise HTTPException(413, "File is empty or too large")
    filehash = hashlib.sha256(content).hexdigest()
    if any(d.active and d.sha256 == filehash for d in case_rows(db, Document, c)):
        raise HTTPException(409, "Identical active document already exists")
    previous = scoped(db, Document, replaces_id, user.tenant_id) if replaces_id else None
    if previous and (previous.case_id != c.id or not previous.active):
        raise HTTPException(422, "Replacement must target an active document in this case")
    root = Path(settings().storage_path).resolve()
    target = root / user.tenant_id / c.id / (str(uuid4()) + suffix)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with target.open("xb") as out:
        out.write(content)
    os.chmod(target, 0o600)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.parse_file", str(target)],
            capture_output=True,
            timeout=12,
            check=False,
        )
        parsed = (
            json.loads(result.stdout)
            if result.returncode == 0
            else {"text": "", "error": "Parser failed"}
        )
    except (subprocess.TimeoutExpired, ValueError):
        parsed = {"text": "", "error": "Parser timed out or returned invalid data"}
    d = Document(
        tenant_id=user.tenant_id,
        case_id=c.id,
        name=name,
        sha256=filehash,
        path=str(target.relative_to(root)),
        text=parsed["text"],
        parse_error=parsed["error"],
        version=previous.version + 1 if previous else 1,
        replaces_id=replaces_id,
    )
    if previous:
        previous.active = False
    db.add(d)
    db.flush()
    t = scoped(db, Template, c.template_id, user.tenant_id)
    affected = set()
    if previous:
        affected |= {
            f.requirement_id for f in case_rows(db, Fact, c) if f.document_id == previous.id
        }
    affected |= affected_rules(parsed["text"], t.rules)
    invalidate(db, c, affected or None, user.id, "Document added or version replaced")
    audit(
        db,
        user.tenant_id,
        c.id,
        "document_uploaded",
        f"Uploaded {name}",
        user.id,
        data={
            "document_id": d.id,
            "hash": d.sha256,
            "version": d.version,
            "parse_error": d.parse_error,
        },
    )
    db.commit()
    return public(d)


@app.get("/api/documents/{document_id}/download")
def download(document_id: str, user=Depends(require("read")), db=Depends(get_db)):
    d = scoped(db, Document, document_id, user.tenant_id)
    scoped(db, Case, d.case_id, user.tenant_id)
    return FileResponse(file_path(d.path), filename=d.name, media_type="application/octet-stream")


@app.get("/api/cases/{case_id}/search")
def search(case_id: str, q: str, user=Depends(require("read")), db=Depends(get_db)):
    if not 1 <= len(q) <= 150:
        raise HTTPException(422, "Search must contain 1–150 characters")
    c = scoped(db, Case, case_id, user.tenant_id)
    return [public(d, ("text",)) for d in ExactTextRetriever().search(db, c, q)]


@app.post("/api/facts/{fact_id}/review")
def review_fact(fact_id: str, body: ReviewIn, user=Depends(require("review")), db=Depends(get_db)):
    f = scoped(db, Fact, fact_id, user.tenant_id)
    c = scoped(db, Case, f.case_id, user.tenant_id, lock=True)
    db.refresh(f)
    if f.document_id:
        doc = scoped(db, Document, f.document_id, user.tenant_id)
        if (
            not doc.active
            or doc.parse_error
            or doc.sha256 != f.source_hash
            or doc.version != f.source_version
        ):
            raise HTTPException(409, "Cannot review stale evidence")
    for sid in body.supersedes:
        old = scoped(db, Fact, sid, user.tenant_id)
        if old.id == f.id or old.case_id != c.id or old.requirement_id != f.requirement_id:
            raise HTTPException(422, "Superseded evidence must belong to the same requirement")
        remaining, seen = [old], set()
        while remaining:
            ancestor = remaining.pop()
            if ancestor.id == f.id:
                raise HTTPException(422, "Evidence precedence cannot be cyclic")
            if ancestor.id in seen:
                continue
            seen.add(ancestor.id)
            remaining.extend(scoped(db, Fact, key, user.tenant_id) for key in ancestor.supersedes)
        if f.id in old.supersedes:
            raise HTTPException(422, "Evidence precedence cannot be cyclic")
    before = {
        "accepted": f.accepted,
        "supersedes": f.supersedes,
        "review_decision": f.review_decision,
    }
    f.accepted = body.accepted
    f.review_decision = "ACCEPTED" if body.accepted else "REJECTED"
    f.accepted_by = user.id if body.accepted else None
    f.supersedes = body.supersedes if body.accepted else []
    invalidate(db, c, [f.requirement_id], user.id, "Human evidence decision: " + body.comment)
    audit(
        db,
        c.tenant_id,
        c.id,
        "fact_reviewed",
        body.comment,
        user.id,
        data={
            "fact_id": f.id,
            "document_id": f.document_id,
            "source_hash": f.source_hash,
            "before": before,
            "after": {
                "accepted": f.accepted,
                "supersedes": f.supersedes,
                "review_decision": f.review_decision,
            },
        },
    )
    db.commit()
    return public(f)


@app.get("/api/actions")
def actions(user=Depends(require("read")), db=Depends(get_db)):
    return [
        public(a)
        for a in db.scalars(
            select(Action)
            .where(Action.tenant_id == user.tenant_id)
            .order_by(Action.created_at.desc())
            .limit(1000)
        )
    ]


@app.post("/api/actions/{action_id}/decision")
def decision(action_id: str, body: DecisionIn, user=Depends(require("review")), db=Depends(get_db)):
    a = scoped(db, Action, action_id, user.tenant_id)
    c = scoped(db, Case, a.case_id, user.tenant_id, lock=True)
    db.refresh(a)
    if a.status not in {"PROPOSED", "APPROVED"} or not a.approval_required:
        raise HTTPException(409, "Action is not awaiting approval")
    if body.fingerprint != a.fingerprint or a.snapshot != snapshot(db, c):
        raise HTTPException(409, "Approval view is stale; review the current action")
    if fingerprint(a.kind, a.payload, a.snapshot, a.owner_id) != a.fingerprint:
        raise HTTPException(409, "Payload changed")
    db.add(
        Approval(
            tenant_id=user.tenant_id,
            action_id=a.id,
            actor_id=user.id,
            fingerprint=a.fingerprint,
            decision=body.decision,
            comment=body.comment,
            expires_at=now() + 86400,
        )
    )
    a.status = "APPROVED" if body.decision == "APPROVED" else "REJECTED"
    audit(
        db,
        user.tenant_id,
        c.id,
        "human_decision",
        body.comment,
        user.id,
        data={"action_id": a.id, "decision": body.decision, "fingerprint": a.fingerprint},
    )
    if a.status == "APPROVED":
        if c.state == "WAITING":
            transition(db, c, "VERIFYING", "Human approval arrived", user.id)
        queue(db, c, user.id)
    elif c.state not in {"READY", "ESCALATED"}:
        transition(
            db, c, "ESCALATED", "Reviewer rejected the proposed action: " + body.comment, user.id
        )
    db.commit()
    return public(a)


@app.post("/api/actions/{action_id}/execute")
def manual_execute(action_id: str, user=Depends(require("operate")), db=Depends(get_db)):
    a = scoped(db, Action, action_id, user.tenant_id)
    c = scoped(db, Case, a.case_id, user.tenant_id, lock=True)
    db.refresh(a)
    try:
        result = execute_action(db, c, a)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    db.commit()
    return {"action": public(a), "result": result}


@app.post("/api/actions/{action_id}/reply")
def reply(action_id: str, body: ReplyIn, user=Depends(require("operate")), db=Depends(get_db)):
    a = scoped(db, Action, action_id, user.tenant_id)
    c = scoped(db, Case, a.case_id, user.tenant_id, lock=True)
    db.refresh(a)
    if a.kind != "internal_clarification" or a.status != "WAITING":
        raise HTTPException(409, "Clarification request is not waiting")
    if user.id != a.owner_id and "review" not in PERMISSIONS[user.role]:
        raise HTTPException(403, "Only the assigned owner or reviewer may record the reply")
    answered = set((a.result or {}).get("answered_requirements", []))
    allowed = {k: v for k, v in a.payload["fields"].items() if k not in answered}
    if not set(body.values) <= set(allowed):
        raise HTTPException(422, "Reply contains unrelated requirements")
    for key, value in body.values.items():
        if not value.strip() or len(value) > 2000:
            raise HTTPException(422, "Reply values must contain 1–2000 characters")
        db.add(
            Fact(
                tenant_id=user.tenant_id,
                case_id=c.id,
                requirement_id=key,
                field=allowed[key][0],
                value=value,
                source_hash=digest(canonical(body.model_dump())),
                source_version=c.revision,
                location="Clarification " + a.id,
                quote=body.comment,
                method="human_reply",
                accepted=False,
            )
        )
    answered |= set(body.values)
    a.status = "COMPLETED" if answered >= set(a.payload["requirements"]) else "WAITING"
    a.result = {
        "reply_by": user.id,
        "comment": body.comment,
        "answered_requirements": sorted(answered),
    }
    db.flush()
    audit(
        db,
        c.tenant_id,
        c.id,
        "clarification_received",
        body.comment,
        user.id,
        data={
            "action_id": a.id,
            "requirements": sorted(body.values),
            "source_hash": digest(canonical(body.model_dump())),
        },
    )
    invalidate(
        db,
        c,
        list(body.values),
        user.id,
        "Clarification reply received; reviewer acceptance required",
    )
    queue(db, c, user.id)
    db.commit()
    return {"ok": True}


@app.get("/api/cases/{case_id}/export")
def export(case_id: str, user=Depends(require("read")), db=Depends(get_db)):
    package = detail(case_id, user, db)
    return Response(
        json.dumps(package, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="handoff-{case_id}.json"'},
    )


@app.get("/api/audit")
def audit_list(user=Depends(require("read")), db=Depends(get_db)):
    return [
        public(e)
        for e in db.scalars(
            select(Event)
            .where(Event.tenant_id == user.tenant_id)
            .order_by(Event.created_at.desc())
            .limit(500)
        )
    ]


@app.get("/api/system")
def system(user=Depends(require("admin")), db=Depends(get_db)):
    tenant = db.get(Tenant, user.tenant_id)
    return {
        "workspace": tenant.name,
        "environment": settings().app_env,
        "provider": settings().model_provider,
        "model": settings().model_name,
        "external_delivery": "Not configured — drafts only",
        "max_steps": settings().max_steps,
    }


@app.get("/api/cases/{case_id}/events")
async def stream(
    case_id: str,
    request: Request,
    after: int = 0,
    user=Depends(require("read")),
    db=Depends(get_db),
):
    scoped(db, Case, case_id, user.tenant_id)
    last = request.headers.get("last-event-id", "")
    cursor = max(after, int(last) if last.isdigit() else 0)
    tenant_id, user_id = user.tenant_id, user.id
    db.close()  # release the dependency's checked-out connection before streaming

    # Do not hold a database session or transaction for the connection lifetime.
    async def generate():
        nonlocal cursor
        started = now()
        while now() - started < 60:
            if await request.is_disconnected():
                return
            with SessionLocal() as session:
                token = request.cookies.get("hf_session", "")
                auth = session.scalar(
                    select(AuthSession).where(AuthSession.token_hash == digest(token))
                )
                active = session.get(User, user_id)
                if (
                    not auth
                    or auth.expires_at <= now()
                    or not active
                    or not active.active
                    or auth.user_id != user_id
                    or auth.tenant_id != tenant_id
                    or active.tenant_id != tenant_id
                    or "read" not in PERMISSIONS.get(active.role, set())
                ):
                    return
                rows = list(
                    session.scalars(
                        select(Event)
                        .where(
                            Event.tenant_id == tenant_id,
                            Event.case_id == case_id,
                            Event.seq > cursor,
                        )
                        .order_by(Event.seq)
                        .limit(100)
                    )
                )
                events = [public(e) for e in rows]
            for e in events:
                cursor = e["seq"]
                yield f"id: {cursor}\ndata: {json.dumps(e)}\n\n"
            if not events:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


app.include_router(admin_router)
app.include_router(action_router)
app.add_middleware(BodyLimitMiddleware)
