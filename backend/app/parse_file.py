"""Trusted parser subprocess. No network or tool authority is given to document content."""

import csv
import io
import json
import sys
from pathlib import Path


def cell(value):
    # A cell is data, never another field. Escaping every line separator prevents
    # values/headers from manufacturing exact evidence during text conversion.
    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys require source correction")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("Non-finite JSON numbers are unsupported")


def extract(path):
    p = Path(path)
    suffix = p.suffix.lower()
    raw = p.read_bytes()
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF signature")
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages) > 200:
            raise ValueError("Encrypted PDF or page limit exceeded")
        for page in reader.pages:
            if "/AA" in page:
                raise ValueError("Active PDF content is unsupported")
        if any(x in reader.trailer["/Root"] for x in ["/OpenAction", "/AA"]):
            raise ValueError("Active PDF content is unsupported")
        text = "\n".join(
            f"[page {i + 1}]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages)
        )
        if not text.strip() or not any(page.extract_text() for page in reader.pages):
            raise ValueError("No text layer; OCR is not configured")
        return text
    text = raw.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError("Binary content is not accepted")
    if suffix == ".json":
        data = json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if not isinstance(data, (dict, list)):
            raise ValueError("JSON must contain an object or object list")
        rows = [data] if isinstance(data, dict) else data
        if len(rows) > 5000 or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Unsupported JSON structure")
        return "\n".join(
            f"{cell(k)}: {cell(v)}"
            for row in rows
            for k, v in row.items()
            if isinstance(v, (str, int, float, bool))
        )
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV headers must be present and unique")
        rows = list(reader)
        if len(rows) > 5000:
            raise ValueError("CSV row limit exceeded")
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("CSV row width does not match headers")
        return "\n".join(f"{cell(k)}: {cell(v)}" for row in rows for k, v in row.items() if k and v)
    if suffix == ".txt":
        return text
    raise ValueError("Unsupported file format")


if __name__ == "__main__":
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        except ValueError:
            # macOS rejects address-space limits below the interpreter's mapped size. CPU,
            # file-size, caller timeout and upload-size bounds still apply; Linux stays capped.
            if sys.platform != "darwin":
                raise
        resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
        text = extract(sys.argv[1])
        if len(text) > 500000:
            raise ValueError("Extracted text exceeds limit")
        print(json.dumps({"text": text, "error": None}))
    except Exception as e:
        print(json.dumps({"text": "", "error": str(e)[:180]}))
