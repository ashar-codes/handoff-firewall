import argparse
import getpass

from sqlalchemy import select

from .db import SessionLocal
from .models import Tenant, User
from .security import hasher


def main():
    parser = argparse.ArgumentParser(description="Bootstrap one workspace administrator")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--workspace", default="My workspace")
    args = parser.parse_args()
    password = getpass.getpass("Administrator password (12+ characters): ")
    if len(password) < 12 or password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords must match and contain at least 12 characters")
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            raise SystemExit("Bootstrap disabled: a user already exists. Use Admin UI.")
        t = Tenant(name=args.workspace)
        db.add(t)
        db.flush()
        db.add(
            User(
                tenant_id=t.id,
                email=args.email.strip().lower(),
                name=args.name,
                role="Administrator",
                password_hash=hasher.hash(password),
            )
        )
        db.commit()
    print("Administrator created. No password was written to source files.")


if __name__ == "__main__":
    main()
