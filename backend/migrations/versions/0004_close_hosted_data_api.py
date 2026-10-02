"""Close hosted-PostgreSQL browser roles (e.g. Supabase anon/authenticated) to app tables.

Handoff Firewall is reached only through its own API and RBAC. Where these roles exist, they
lose every privilege on this schema's tables, sequences and functions, now and for objects the
migration role creates later. Elsewhere this is a no-op. Additive: no data is changed.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ROLES = ("anon", "authenticated")


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for role in ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role};
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role};
                REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {role};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM {role};
              END IF;
            END $$;
            """
        )


def downgrade():
    # Deliberately does not restore browser-role access.
    pass
