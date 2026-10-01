"""One lexical contract for source mapping and exact extraction."""

import re


def exact_fields(text):
    for line_no, line in enumerate(text.splitlines(), 1):
        match = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9_ ]{0,79})\s*[:=]\s*(.{1,2000})\s*", line)
        if match and match[2].strip():
            yield (line_no, match[1].strip().lower().replace(" ", "_"), match[2].strip(), line)


def affected_rules(text, rules):
    fields = {field for _, field, _, _ in exact_fields(text)}
    return {r["id"] for r in rules if fields.intersection(r["fields"])}
