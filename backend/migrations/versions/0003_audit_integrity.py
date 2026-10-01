"""Explicit evidence decisions and explainable conflict lifecycle; additive upgrade."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("facts", sa.Column("review_decision", sa.String(20), nullable=True))
    op.add_column(
        "conflicts",
        sa.Column("kind", sa.String(40), nullable=False, server_default="source_disagreement"),
    )
    op.add_column(
        "conflicts", sa.Column("severity", sa.String(20), nullable=False, server_default="blocking")
    )
    op.add_column("conflicts", sa.Column("expected_value", sa.Text(), nullable=True))
    op.add_column(
        "conflicts",
        sa.Column("resolution_state", sa.String(30), nullable=False, server_default="OPEN"),
    )
    op.add_column(
        "conflicts", sa.Column("resolution", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column(
        "conflicts", sa.Column("created_at", sa.Double(), nullable=False, server_default="0")
    )
    op.execute("UPDATE conflicts SET resolution_state='LEGACY_CLOSED' WHERE resolved=true")


def downgrade():
    for column in [
        "created_at",
        "resolution",
        "resolution_state",
        "expected_value",
        "severity",
        "kind",
    ]:
        op.drop_column("conflicts", column)
    op.drop_column("facts", "review_decision")
