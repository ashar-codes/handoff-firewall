"""Human-facing wording for repair actions, rendered deterministically from structured questions.

The business action (owner, kind, requirements, questions) is decided by deterministic code; this
module only words it, using business references, plain topic names, values and source names.
"""


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
