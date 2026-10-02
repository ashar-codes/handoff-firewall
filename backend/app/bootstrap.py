"""Create the first workspace administrator; refuses once any user exists.

Interactive:   uv run python -m app.bootstrap --email you@example.com
Deployment:    uv run python -m app.bootstrap --from-env
               (BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD; skipped when unset or when a
               user already exists, so it is safe on every start. Remove the password afterwards.)
"""

import argparse
import getpass
import os
import re

from sqlalchemy import select

from .db import SessionLocal
from .models import Tenant, User
from .security import hasher


def create_admin(email, password, name, workspace):
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or email.endswith("@example.test"):
        raise SystemExit("Bootstrap needs a real administrator email (not a sample account)")
    if len(password) < 12:
        raise SystemExit("Bootstrap password must contain at least 12 characters")
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            return False
        t = Tenant(name=workspace)
        db.add(t)
        db.flush()
        db.add(
            User(
                tenant_id=t.id,
                email=email,
                name=name,
                role="Administrator",
                password_hash=hasher.hash(password),
            )
        )
        db.commit()
    return True


def main():
    parser = argparse.ArgumentParser(description="Bootstrap one workspace administrator")
    parser.add_argument("--email")
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--workspace", default="My workspace")
    parser.add_argument("--from-env", action="store_true")
    args = parser.parse_args()
    if args.from_env:
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "")
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        if not email or not password:
            print("Bootstrap skipped: BOOTSTRAP_ADMIN_EMAIL/BOOTSTRAP_ADMIN_PASSWORD not set")
            return
        created = create_admin(
            email,
            password,
            os.getenv("BOOTSTRAP_ADMIN_NAME", args.name),
            os.getenv("BOOTSTRAP_WORKSPACE", args.workspace),
        )
        print(
            "Administrator created; remove BOOTSTRAP_ADMIN_PASSWORD from the environment."
            if created
            else "Bootstrap skipped: a user already exists"
        )
        return
    if not args.email:
        parser.error("--email is required unless --from-env is used")
    password = getpass.getpass("Administrator password (12+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords must match")
    if not create_admin(args.email, password, args.name, args.workspace):
        raise SystemExit("Bootstrap disabled: a user already exists. Use Admin UI.")
    print("Administrator created. No password was written to source files.")


if __name__ == "__main__":
    main()
