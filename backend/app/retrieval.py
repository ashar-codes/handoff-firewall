"""Tenant/case-bound retrieval seam. Semantic retrieval can implement this contract later."""

from typing import Protocol

from sqlalchemy import func, select

from .models import Document


class CaseRetriever(Protocol):
    def search(self, db, case, query: str) -> list[Document]: ...


class ExactTextRetriever:
    def search(self, db, case, query):
        statement = select(Document).where(
            Document.tenant_id == case.tenant_id,
            Document.case_id == case.id,
            Document.active.is_(True),
        )
        if db.bind.dialect.name == "postgresql":
            statement = statement.where(
                func.to_tsvector("simple", Document.text).op("@@")(
                    func.plainto_tsquery("simple", query)
                )
            )
        else:
            statement = statement.where(Document.text.contains(query, autoescape=True))
        return list(db.scalars(statement.limit(20)))
