"""Upgrade-only migrations for deployment start-up; never downgrades, resets or seeds.

On PostgreSQL an advisory lock serialises concurrent starters, so the upgrade runs once.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from .config import settings

LOCK_ID = 774_301_2025  # arbitrary, stable advisory-lock key for Handoff Firewall migrations


def main():
    url = settings().migration_database_url or settings().database_url
    config = Config("alembic.ini")
    if not url.startswith("postgresql"):
        command.upgrade(config, "head")
        return
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_ID})
        try:
            command.upgrade(config, "head")
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID})
            connection.commit()
    engine.dispose()
    print("Database migrations are at head")


if __name__ == "__main__":
    main()
