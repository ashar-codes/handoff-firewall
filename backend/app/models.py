from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(UTC).timestamp()


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)


class Scoped(Identity):
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)


class Tenant(Identity, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(120))


class User(Scoped, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)
    email: Mapped[str] = mapped_column(String(254))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginGuard(Identity, Base):
    __tablename__ = "login_guards"
    key: Mapped[str] = mapped_column(String(64), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[float] = mapped_column(default=now)


class AuthSession(Scoped, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column()


class Template(Scoped, Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("tenant_id", "family", "version"),)
    family: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(180))
    source: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(80))
    rules: Mapped[list] = mapped_column(JSON)
    rule_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(default=now)


class Case(Scoped, Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("tenant_id", "business_key"),)
    title: Mapped[str] = mapped_column(String(180))
    business_key: Mapped[str] = mapped_column(String(120))
    template_id: Mapped[str] = mapped_column(ForeignKey("templates.id"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    goal: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default="NEW")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    statuses: Mapped[dict] = mapped_column(JSON, default=dict)
    graph: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(default=now)
    updated_at: Mapped[float] = mapped_column(default=now)


class Document(Scoped, Base):
    __tablename__ = "documents"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    replaces_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    text: Mapped[str] = mapped_column(Text, default="")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(default=now)


class Fact(Scoped, Base):
    __tablename__ = "facts"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    requirement_id: Mapped[str] = mapped_column(String(80))
    field: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    source_version: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(180))
    quote: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(30))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    review_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    supersedes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[float] = mapped_column(default=now)


class Conflict(Scoped, Base):
    __tablename__ = "conflicts"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    requirement_id: Mapped[str] = mapped_column(String(80))
    facts: Mapped[list] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(40), default="source_disagreement")
    severity: Mapped[str] = mapped_column(String(20), default="blocking")
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_state: Mapped[str] = mapped_column(String(30), default="OPEN")
    resolution: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(default=now)


class Action(Scoped, Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("case_id", "dedupe_key"),)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    prerequisites: Mapped[list] = mapped_column(JSON, default=list)
    snapshot: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(64))
    approval_required: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED")
    effort: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(default=now)


class Approval(Scoped, Base):
    __tablename__ = "approvals"
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[float] = mapped_column()
    created_at: Mapped[float] = mapped_column(default=now)


class Event(Scoped, Base):
    __tablename__ = "events"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kind: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint("tenant_id", "case_id", "seq"),)


class Job(Scoped, Base):
    __tablename__ = "jobs"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    active_key: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    lease_until: Mapped[float] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(default=now)


@event.listens_for(Event, "before_update")
@event.listens_for(Event, "before_delete")
@event.listens_for(Template, "before_update")
@event.listens_for(Template, "before_delete")
def immutable_event(*args):
    raise ValueError("Audit events and approved policy versions are append-only")
