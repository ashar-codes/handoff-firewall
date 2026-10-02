"""Evidence storage: local and Supabase providers, path safety, hash integrity, failures."""

import logging

import httpx
import pytest
from conftest import make_case, process, upload
from pydantic import SecretStr

from app import main, storage
from app.config import settings
from app.storage import (
    LocalEvidenceStorage,
    StorageError,
    SupabaseEvidenceStorage,
    object_key,
    valid_original,
)

SECRET = "sb_secret_fixture_value_123"
LEGACY = "eyJhbGciOiJIUzI1NiJ9.fixture.signature"


class FakeSupabase:
    """In-memory Supabase Storage endpoints for one private bucket."""

    def __init__(self):
        self.objects, self.requests, self.fail = {}, [], None

    def __call__(self, request):
        self.requests.append(request)
        if self.fail == "timeout":
            raise httpx.ReadTimeout("slow")
        if self.fail:
            return httpx.Response(self.fail, json={"error": "failure"})
        if request.headers.get("apikey") not in {SECRET, LEGACY}:
            return httpx.Response(403, json={"error": "Unauthorized"})
        prefix = "/storage/v1/object/handoff-evidence/"
        if not request.url.path.startswith(prefix):
            return httpx.Response(400, json={"error": "Bucket not found"})
        key = request.url.path[len(prefix) :]
        if request.method == "POST":
            if key in self.objects:
                return httpx.Response(400, json={"error": "The resource already exists"})
            self.objects[key] = request.content
            return httpx.Response(200, json={"Key": key})
        if key not in self.objects:
            return httpx.Response(400, json={"error": "Object not found"})
        return httpx.Response(200, content=self.objects[key])


@pytest.fixture
def supabase(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, "storage_provider", "supabase")
    monkeypatch.setattr(s, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(s, "supabase_service_role_key", SecretStr(SECRET))
    fake = FakeSupabase()
    provider = SupabaseEvidenceStorage(transport=httpx.MockTransport(fake))
    monkeypatch.setattr(storage, "evidence_storage", lambda: provider)
    monkeypatch.setattr(main, "evidence_storage", lambda: provider)
    return fake


def test_object_keys_are_scoped_versioned_and_safe():
    key = object_key("tenant-1", "case-2", "doc-3", 2, "../../Customer PO (final).txt")
    assert key == "tenant-1/case-2/doc-3/v2/Customer_PO__final_.txt"
    for bad in [
        ("..", "c", "d", 1, "x.txt"),
        ("t", "c/x", "d", 1, "x.txt"),
        ("t", "", "d", 1, "a"),
    ]:
        with pytest.raises(StorageError):
            object_key(*bad)
    with pytest.raises(StorageError):
        storage._checked("tenant/../other-tenant/file.txt")


def test_local_storage_is_write_once_and_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings(), "storage_path", str(tmp_path))
    local = LocalEvidenceStorage()
    local.put("t/c/d/v1/a.txt", b"payment_terms: 30 days")
    assert local.get("t/c/d/v1/a.txt") == b"payment_terms: 30 days"
    with pytest.raises(StorageError):
        local.put("t/c/d/v1/a.txt", b"overwrite attempt")
    with pytest.raises(StorageError):
        local.get("t/c/d/v1/missing.txt")
    with pytest.raises(StorageError):
        local.get("../outside.txt")


def test_supabase_requests_are_private_backend_calls(supabase):
    provider = storage.evidence_storage()
    provider.put("t/c/d/v1/a.txt", b"hello")
    put = supabase.requests[-1]
    assert (
        str(put.url)
        == "https://project.supabase.co/storage/v1/object/handoff-evidence/t/c/d/v1/a.txt"
    )
    assert put.headers["apikey"] == SECRET and "authorization" not in put.headers
    assert put.headers["x-upsert"] == "false"
    assert provider.get("t/c/d/v1/a.txt") == b"hello"
    with pytest.raises(StorageError):
        provider.put("t/c/d/v1/a.txt", b"overwrite attempt")  # never silently replaced


def test_legacy_service_role_jwt_is_also_sent_as_bearer(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(s, "supabase_service_role_key", SecretStr(LEGACY))
    fake = FakeSupabase()
    SupabaseEvidenceStorage(transport=httpx.MockTransport(fake)).put("t/c/d/v1/a", b"x")
    assert fake.requests[-1].headers["authorization"] == "Bearer " + LEGACY


@pytest.mark.parametrize("failure", [401, 403, 404, 500, 503, "timeout"])
def test_storage_failures_never_leak_or_pass(supabase, caplog, failure):
    provider = storage.evidence_storage()
    supabase.fail = failure
    with caplog.at_level(logging.WARNING), pytest.raises(StorageError) as error:
        provider.get("t/c/d/v1/a.txt")
    with pytest.raises(StorageError):
        provider.put("t/c/d/v1/b.txt", b"x")
    assert SECRET not in str(error.value) and SECRET not in caplog.text


def test_supabase_backed_case_verifies_hashes_end_to_end(client, supabase):
    case = make_case(client)
    doc = upload(client, case, "payment_terms: 30 days")
    [key] = supabase.objects
    assert key.startswith(f"{doc['tenant_id']}/{case['id']}/{doc['id']}/v1/")
    assert "path" not in doc  # storage keys are never returned to the browser
    assert process(client, case)["state"] == "READY"
    r = client.get("/api/documents/" + doc["id"] + "/download")
    assert r.status_code == 200 and r.content == b"payment_terms: 30 days"

    supabase.objects[key] = b"payment_terms: 45 days"  # changed behind the application's back
    assert process(client, case)["state"] != "READY"
    assert client.get("/api/documents/" + doc["id"] + "/download").status_code == 409


def test_missing_or_unreachable_object_blocks_ready(client, supabase):
    case = make_case(client)
    upload(client, case, "payment_terms: 30 days")
    supabase.objects.clear()
    assert process(client, case)["state"] != "READY"
    case2 = make_case(client, business_key="ORDER-2")
    upload(client, case2, "payment_terms: 30 days", "other.txt")
    supabase.fail = 503
    assert process(client, case2)["state"] != "READY"


def test_upload_failure_creates_no_document(client, supabase):
    case = make_case(client)
    supabase.fail = 503
    r = client.post(
        "/api/cases/" + case["id"] + "/documents",
        files={"file": ("e.txt", b"payment_terms: 30 days", "text/plain")},
    )
    assert r.status_code == 503 and r.json()["detail"] == "Evidence storage rejected the upload"
    assert client.get("/api/cases/" + case["id"]).json()["documents"] == []


def test_object_from_another_workspace_path_is_not_this_documents_evidence(client, supabase):
    from app.db import SessionLocal
    from app.models import Document

    case = make_case(client)
    doc = upload(client, case, "payment_terms: 30 days")
    supabase.objects["other-tenant/x/y/v1/evidence.txt"] = b"payment_terms: 30 days"
    with SessionLocal() as db:
        stored = db.get(Document, doc["id"])
        assert stored.path.startswith(stored.tenant_id + "/" + stored.case_id + "/")
        foreign = Document(**{**{c: getattr(stored, c) for c in ("tenant_id", "case_id", "name", "sha256", "text")},
                              "path": "other-tenant/x/y/v1/missing-here.txt"})  # fmt: skip
        assert not valid_original(foreign)
