"""Future external capability contract. No live connector is registered in this release."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class AuthorizedWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    case_id: str
    action_id: str
    fingerprint: str
    idempotency_key: str
    payload: dict


class Connector(Protocol):
    def reconcile(self, tenant_id: str, idempotency_key: str) -> dict | None: ...
    def execute(self, authorized: AuthorizedWrite) -> dict: ...


# Add adapters only with tenant credentials, capability checks, exact approval binding,
# reconciliation and sandbox integration tests. Do not pass this interface to a model.
