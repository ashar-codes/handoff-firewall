"""Search indexes and immutable approved policy versions."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_facts_case_requirement", "facts", ["case_id", "requirement_id"])
    op.create_index("ix_documents_case_active", "documents", ["case_id", "active"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_documents_fts ON documents USING gin(to_tsvector('simple', text))"
        )
        op.execute(
            "CREATE TRIGGER policy_immutable BEFORE UPDATE OR DELETE ON templates "
            "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER policy_immutable ON templates")
        op.drop_index("ix_documents_fts", table_name="documents")
    op.drop_index("ix_documents_case_active", table_name="documents")
    op.drop_index("ix_facts_case_requirement", table_name="facts")
