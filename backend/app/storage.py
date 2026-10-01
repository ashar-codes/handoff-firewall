import hashlib
from pathlib import Path

from .config import settings


def file_path(key):
    root = Path(settings().storage_path).resolve()
    candidate = (root / key).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("File key is outside the configured store")
    return candidate


def valid_original(document):
    try:
        p = file_path(document.path)
        if not p.is_file() or p.stat().st_size > settings().upload_limit:
            return False
        sha = hashlib.sha256()
        with p.open("rb") as source:
            for chunk in iter(lambda: source.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest() == document.sha256
    except (OSError, ValueError):
        return False
