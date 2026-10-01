"""Account lifecycle operations kept outside agent capabilities."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import delete, select

from .db import get_db
from .domain import audit, scoped
from .models import AuthSession, Tenant, User
from .schemas import Strict
from .security import hasher, require

router = APIRouter(prefix="/api")


class UserUpdate(Strict):
    role: str = Field(pattern=r"^(Administrator|Policy Manager|Operator|Reviewer|Viewer)$")
    active: bool
    password: str | None = Field(default=None, min_length=12, max_length=256)


@router.patch("/users/{user_id}")
def update_user(
    user_id: str, body: UserUpdate, actor=Depends(require("admin")), db=Depends(get_db)
):
    db.scalar(select(Tenant).where(Tenant.id == actor.tenant_id).with_for_update())
    user = scoped(db, User, user_id, actor.tenant_id, lock=True)
    if user.id == actor.id and (not body.active or body.role != "Administrator"):
        raise HTTPException(409, "An administrator cannot disable or demote their own account")
    user.role = body.role
    user.active = body.active
    if body.password:
        user.password_hash = hasher.hash(body.password)
    db.execute(
        delete(AuthSession).where(
            AuthSession.user_id == user.id, AuthSession.tenant_id == actor.tenant_id
        )
    )
    audit(
        db,
        actor.tenant_id,
        None,
        "user_access_changed",
        "User access changed and sessions revoked",
        actor.id,
        data={
            "user_id": user.id,
            "role": user.role,
            "active": user.active,
            "password_reset": bool(body.password),
        },
    )
    db.commit()
    return {"id": user.id, "active": user.active, "role": user.role}
