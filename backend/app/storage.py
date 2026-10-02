"""Evidence object storage. Domain code uses only evidence_storage() and valid_original().

Keys are relative, slash-separated and built by object_key(); objects are write-once, so a new
document version is always a new key and older evidence can never be overwritten.
"""

import hashlib
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import httpx

from .config import settings

log = logging.getLogger(__name__)
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$")


class StorageError(Exception):
    """Evidence could not be stored or read; never treated as valid evidence."""


def object_key(tenant_id, case_id, document_id, version, filename):
    """<workspace>/<case>/<document>/v<version>/<safe filename>; every segment validated."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name).lstrip(".")[:120] or "upload"
    segments = [tenant_id, case_id, document_id, f"v{int(version)}", safe_name]
    if not all(_SAFE_SEGMENT.match(s) and s not in {".", ".."} for s in segments):
        raise StorageError("Unsafe evidence object key")
    return "/".join(segments)


def _checked(key):
    parts = key.split("/")
    if not key or key.startswith("/") or any(p in {"", ".", ".."} for p in parts):
        raise StorageError("Unsafe evidence object key")
    return key


def file_path(key):
    root = Path(settings().storage_path).resolve()
    candidate = (root / _checked(key)).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("File key is outside the configured store")
    return candidate


class LocalEvidenceStorage:
    """Private files beneath STORAGE_PATH (development, tests, persistent-disk hosts)."""

    def put(self, key, content):
        target = file_path(key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with target.open("xb") as out:  # write-once
                out.write(content)
        except FileExistsError:
            raise StorageError("Evidence object already exists") from None
        except OSError:
            raise StorageError("Evidence storage unavailable") from None
        os.chmod(target, 0o600)

    def get(self, key):
        try:
            target = file_path(key)
            if not target.is_file() or target.stat().st_size > settings().upload_limit:
                raise StorageError("Evidence object missing")
            return target.read_bytes()
        except (OSError, ValueError):
            raise StorageError("Evidence object unavailable") from None


class SupabaseEvidenceStorage:
    """Private Supabase Storage bucket, reached only by the backend with a server-side key."""

    def __init__(self, transport=None):
        s = settings()
        self.transport = transport  # tests inject an httpx.MockTransport
        key = s.supabase_service_role_key.get_secret_value()
        # New secret keys belong only in apikey; legacy service_role JWTs also need Bearer.
        self.headers = {"apikey": key}
        if key.startswith("eyJ"):
            self.headers["Authorization"] = "Bearer " + key
        self.base = f"{s.supabase_url}/storage/v1/object/{s.supabase_storage_bucket}/"
        self.timeout = s.storage_timeout

    def _url(self, key):
        return self.base + quote(_checked(key), safe="/")

    def _request(self, method, key, extra_headers=None, **kwargs):
        headers = {**self.headers, **(extra_headers or {})}
        try:
            with httpx.Client(
                timeout=self.timeout, trust_env=False, transport=self.transport
            ) as client:
                return client.request(method, self._url(key), headers=headers, **kwargs)
        except httpx.HTTPError:
            log.warning("evidence_storage %s failed: provider unreachable", method)
            raise StorageError("Evidence storage unavailable") from None

    def put(self, key, content):
        response = self._request(
            "POST",
            key,
            content=content,
            extra_headers={"Content-Type": "application/octet-stream", "x-upsert": "false"},
        )
        if response.status_code in {200, 201}:
            return
        log.warning("evidence_storage put failed: HTTP %s", response.status_code)
        if response.status_code in {400, 409} and "exist" in response.text.lower():
            raise StorageError("Evidence object already exists")
        raise StorageError("Evidence storage rejected the upload")

    def get(self, key):
        response = self._request("GET", key)
        if response.status_code == 200 and len(response.content) <= settings().upload_limit:
            return response.content
        log.warning("evidence_storage get failed: HTTP %s", response.status_code)
        raise StorageError("Evidence object missing or unavailable")


@lru_cache
def evidence_storage():
    if settings().storage_provider == "supabase":
        return SupabaseEvidenceStorage()
    return LocalEvidenceStorage()


def valid_original(document):
    """True only if the stored original exists and still matches its recorded SHA-256."""
    try:
        content = evidence_storage().get(document.path)
    except StorageError:
        return False
    return hashlib.sha256(content).hexdigest() == document.sha256
