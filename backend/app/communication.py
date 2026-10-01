"""Human-facing wording for repair actions, rendered from structured questions.

The business action (owner, kind, requirements, questions) is decided by deterministic code.
This module only words it. Deterministic templates are always available; an optional model
rewrite is accepted only if it keeps every topic and leaks no internal detail.
"""

import re

# Internal implementation details that must never reach a business recipient.
_LEAK = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\b[0-9a-f]{16,}\b|"
    r"\b(AWAITING_REVIEW|MISSING|CONFLICTING|INVALIDATED|SATISFIED|NOT_APPLICABLE|UNREADABLE|"
    r"AMBIGUOUS|PROPOSED|WAITING)\b|\b[a-z]+(?:_[a-z0-9]+)+\b",
)
_JARGON = re.compile(
    r"fact[\s_-]*id|requirement[\s_-]*id|fingerprint|\bhash\b|\bagent\b|orchestrator|"
    r"candidate evidence|accepted evidence|\bstate\b|\bschema\b|https?://|[\w.+-]+@[\w-]+\.\w+|"
    r"already (been )?approved|has been (approved|sent)|\bignore\b",
    re.I,
)


# Courtesy and request words a rewrite may add; every other content word must already appear in
# the deterministic wording, so a rewrite cannot introduce a topic, identifier or claim.
_COURTESY = set(
    "could would you your please kindly review confirm provide share check verify accept correct "
    "valid whether which value values these those them this that the and for with from any are "
    "following details information items item thank thanks advance when possible help appreciate "
    "let know regarding about can will its it's they their our we hello dear team colleague "
    "evidence document documents source sources differ different shown listed below above "
    "reference determine discrepancy noting compare versus between supply".split()
)


def topic(rule):
    label = rule["label"].strip()
    return "the " + label[:1].lower() + label[1:]


def _quote(value):
    value = " ".join(str(value).split())
    return f"“{value[:120]}”"


def _source(fact, documents):
    if fact.document_id and fact.document_id in documents:
        return documents[fact.document_id].name
    return "a clarification reply"


def questions(rules, statuses):
    """Structured, wording-free questions: what is asked about which requirement."""
    asks = {
        "AMBIGUOUS": "confirm_applicability",
        "CONFLICTING": "confirm_correct_value",
        "AWAITING_REVIEW": "review",
    }
    return [
        {
            "requirement": r["id"],
            "topic": topic(r),
            "ask": asks.get(statuses[r["id"]]["state"], "provide"),
        }
        for r in rules
    ]


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def render(kind, reference, items, facts_by_requirement, documents):
    """Deterministic professional wording; never contains internal identifiers."""
    if kind == "review_evidence":
        parts = []
        for q in items:
            facts = facts_by_requirement.get(q["requirement"], [])
            seen = {}
            for f in facts:
                seen.setdefault(" ".join(f.value.split()).casefold(), f)
            found = [f"{_quote(f.value)} in {_source(f, documents)}" for f in seen.values()]
            if len(found) > 1:
                parts.append(f"{q['topic']}, where {_join(found)} differ")
            elif found:
                parts.append(f"{q['topic']} ({found[0]})")
            else:
                parts.append(q["topic"])
        verb = (
            "decide which value is correct"
            if any(" differ" in p for p in parts)
            else (
                "accept it if it is valid" if len(parts) == 1 else "accept the items that are valid"
            )
        )
        return f"Please review {_join(parts)} for {reference} and {verb}."
    sentences = []
    provide = [q["topic"] for q in items if q["ask"] == "provide"]
    if provide:
        if len(provide) == 1:
            sentences.append(f"Could you please provide {provide[0]} for {reference}?")
        else:
            sentences.append(
                f"Could you please provide the following for {reference}: {_join(provide)}?"
            )
    for q in items:
        if q["ask"] == "confirm_applicability":
            sentences.append(
                f"Could you please confirm whether {q['topic']} applies to {reference}?"
            )
        elif q["ask"] == "confirm_correct_value":
            facts = facts_by_requirement.get(q["requirement"], [])
            found = [f"{_quote(f.value)} in {_source(f, documents)}" for f in facts][:3]
            detail = f" The sources disagree: {_join(found)}." if len(found) > 1 else ""
            sentences.append(f"Could you please confirm {q['topic']} for {reference}?{detail}")
    return " ".join(sentences)


def acceptable(message, reference, items, other_topics, fallback):
    """A model rewrite may only change wording, never content, recipients or authority."""
    if not message or len(message) > 700 or "\n\n\n" in message:
        return False
    # Document names and quoted values come from the deterministic fallback and may legitimately
    # contain underscores or words such as "approved"; anything else of that shape is a leak.
    flagged = [m.group(0) for m in _LEAK.finditer(message)]
    flagged += [m.group(0) for m in _JARGON.finditer(message)]
    if any(token not in fallback for token in flagged):
        return False
    lowered = message.casefold()
    if reference.casefold() not in lowered:
        return False
    for q in items:
        words = [w for w in re.findall(r"[a-z0-9]+", q["topic"].casefold()) if w != "the"]
        if not all(w in lowered for w in words):
            return False
    # No new questions: other requirements of the same policy must not be mentioned.
    if any(t.removeprefix("the ").casefold() in lowered for t in other_topics):
        return False
    allowed = set(re.findall(r"[a-z0-9]+", fallback.casefold())) | _COURTESY
    if any(w not in allowed for w in re.findall(r"[a-z]{3,}", lowered)):
        return False
    # Quoted values may be rephrased away but never invented.
    quoted = set(re.findall(r"“([^”]+)”", message))
    return quoted <= set(re.findall(r"“([^”]+)”", fallback))
