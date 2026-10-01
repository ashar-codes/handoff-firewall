import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .config import settings
from .db import get_db
from .models import AuthSession, User, now

hasher = PasswordHasher()
PERMISSIONS = {
    "Administrator": {"read", "operate", "review", "policy", "admin"},
    "Policy Manager": {"read", "policy"},
    "Operator": {"read", "operate"},
    "Reviewer": {"read", "review", "operate"},
    "Viewer": {"read"},
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(stored, password):
    try:
        return hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get("hf_session", "")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(token)))
    if not session or session.expires_at <= now():
        raise HTTPException(401, "Sign in required")
    user = db.get(User, session.user_id)
    if not user or not user.active or session.tenant_id != user.tenant_id:
        raise HTTPException(401, "Session invalid")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(digest(csrf), session.csrf_hash):
            raise HTTPException(403, "CSRF validation failed")
    return user


def require(permission):
    def dependency(user=Depends(current_user)):
        if permission not in PERMISSIONS.get(user.role, set()):
            raise HTTPException(403, "Permission denied")
        return user

    return dependency


def check_origin(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != settings().frontend_origin:
            raise HTTPException(403, "Origin not allowed")
