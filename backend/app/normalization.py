"""Deterministic business-value normalization used before any equality or conflict decision.

Each parser returns a canonical string for an unambiguous value, or None when the value is vague,
malformed or could mean more than one thing. Callers then fall back to the conservative raw
comparison, so an unparsed value can only cause review, never a false match.
"""

import re
from decimal import Decimal, InvalidOperation

VERSION = "biz-v1"

_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}  # fmt: skip
_NUMBER = (
    r"\d{1,3}|(?:"
    + "|".join(_TENS)
    + r")(?:[\s-](?:"
    + "|".join(list(_UNITS)[:9])
    + r"))?|"
    + "|".join(sorted(_UNITS, key=len, reverse=True))
)
_DAYS = re.compile(rf"\b({_NUMBER})\s*(?:calendar\s+)?days?\b", re.I)
_NET = re.compile(r"\bnet(?:\s+|-)?(\d{1,3})\b", re.I)
_ANY_NUMBER = re.compile(rf"\b(?:{_NUMBER}|\d+)\b", re.I)
# Different payment mechanics; never folded into "net N days".
_NOT_NET = re.compile(
    r"business|working|end of (the )?month|\beom\b|advance|prepay|on delivery|\bcod\b|"
    r"instal|milestone|%|percent|discount|\b\d+\s*/\s*\d+\b",
    re.I,
)
PAYMENT_CONTEXT = re.compile(r"\bpay|payment|remit|\bdue\b|\bterms?\b|\bnet\s*-?\s*\d", re.I)
AMOUNT_CONTEXT = re.compile(r"\btotal|amount|\bvalue\b|price|\bsum\b|payable|invoice", re.I)

_CURRENCY = {
    "pkr": "PKR", "rs": "PKR", "rs.": "PKR", "₨": "PKR", "rupees": "PKR",
    "usd": "USD", "us$": "USD", "$": "USD", "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP",
}  # fmt: skip
_CUR = r"(PKR|Rs\.?|₨|rupees|USD|US\$|\$|EUR|€|GBP|£)"
_NUM = r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_AMOUNT = re.compile(rf"{_CUR}\s*{_NUM}\b|\b{_NUM}\s*{_CUR}", re.I)
_SEPARATORS = re.compile(r"[\s_-]+")


def _number(token):
    token = token.lower().replace("-", " ").strip()
    if token.isdigit():
        return int(token)
    parts = token.split()
    total = 0
    for part in parts:
        if part in _TENS:
            total += _TENS[part]
        elif part in _UNITS:
            total += _UNITS[part]
        else:
            return None
    return total or None


def payment_terms(text):
    """'Net 30', '30 days', 'within thirty days of invoice' -> 'net_days:30'; vague -> None."""
    if not text or _NOT_NET.search(text):
        return None
    days = {int(m) for m in _NET.findall(text)}
    days |= {n for m in _DAYS.findall(text) if (n := _number(m))}
    # "30 or 45 days", invoice numbers and the like: any other number makes it ambiguous.
    if len(days) != 1 or {_number(m) for m in _ANY_NUMBER.findall(text)} - days:
        return None
    (value,) = days
    return f"net_days:{value}" if 0 < value <= 365 else None


def amounts(text, default_currency=None):
    """Every explicit currency amount in text as 'PKR 500000'; bare numbers only with a default."""
    found = []
    for m in _AMOUNT.finditer(text or ""):
        currency, number = (m[1], m[2]) if m[1] else (m[4], m[3])
        try:
            value = Decimal(number.replace(",", ""))
        except InvalidOperation:
            continue
        found.append(f"{_CURRENCY[currency.lower()]} {_plain(value)}")
    if not found and default_currency and re.fullmatch(rf"\s*{_NUM}\s*", text or ""):
        found.append(f"{default_currency} {_plain(Decimal(text.strip().replace(',', '')))}")
    return found


def amount(text, default_currency=None):
    values = set(amounts(text, default_currency))
    return values.pop() if len(values) == 1 else None


def _plain(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def identifier(text):
    """Case and separator style only: 'so 1042' == 'SO-1042'; never letter/digit look-alikes."""
    text = (text or "").strip()
    if not text or len(text) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*", text):
        return None
    return _SEPARATORS.sub("-", text.upper())


def value_type(rule):
    """Explicit rule value_type, else a conservative inference from the field names."""
    if rule.get("value_type"):
        return rule["value_type"]
    fields = set(rule["fields"])
    if fields & {"payment_terms", "terms"}:
        return "payment_terms"
    if any(f.endswith(("_total", "_amount")) or f in {"total", "amount"} for f in fields):
        return "amount"
    if all(f.endswith(("_id", "_number")) for f in fields):
        return "identifier"
    return "text"


def canonical(rule, value):
    """Comparable form plus method; unparsed values compare by conservative raw text."""
    kind = value_type(rule)
    parsed = None
    if kind == "payment_terms":
        parsed = payment_terms(value)
    elif kind == "amount":
        parsed = amount(value, rule.get("currency"))
    elif kind == "identifier":
        parsed = identifier(value)
    if parsed is not None:
        return f"{kind}:{parsed}", kind
    return "raw:" + " ".join(str(value).strip().casefold().split()), "raw"


# Identifier-shaped token (must contain a digit) and the few words allowed between a requirement's
# own label and its value: "tax registration number for this order is PKR-TAX-77128".
_ID = r"[A-Za-z0-9](?:[A-Za-z0-9]|[-_/](?=[A-Za-z0-9])){2,39}"
_LINK = (
    r"(?:\s+(?:number|no\.?|id|is|was|reads|now|correct|new|updated|registration|reference|"
    r"ref|of|the|our|their|on file|for this (?:order|case|customer))\b|\s*[:#=])*"
)
_GENERIC = r"\b(customer|approved|consistent|current|the|a|an)\b"


def keywords(rule):
    """Phrases that name this requirement in prose: its label and field names, generic words removed."""
    found = set()
    for text in [rule["label"], *(f.replace("_", " ") for f in rule["fields"])]:
        phrase = " ".join(re.sub(_GENERIC, " ", text.lower()).split())
        if phrase:
            found.add(phrase)
            found.add(re.sub(r" (id|number|no)$", "", phrase))
    return sorted(found, key=len, reverse=True)


def mentions(text, value):
    """Does text mention this identifier, allowing harmless separator/case differences?"""
    canonical_id = identifier(value)
    if not canonical_id:
        return False
    parts = [re.escape(p) for p in canonical_id.split("-")]
    return (
        re.search(r"(?<![A-Za-z0-9])" + r"[\s_-]?".join(parts) + r"(?![A-Za-z0-9])", text, re.I)
        is not None
    )


def _foreign(line, reference):
    """The line names another reference in the business key's own format (e.g. SO-882I vs SO-8821)."""
    prefix = re.match(r"([A-Za-z]{2,6})[\s_-]", reference or "")
    if not prefix:
        return False
    # Whole multi-part references ("SO-HACK-1046"), not just their first segment.
    pattern = rf"\b{re.escape(prefix[1])}[\s_-]?[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*\b"
    for token in re.findall(pattern, line, re.I):
        if identifier(token) != identifier(reference):
            return True
    return False


def detect(rule, line, reference=None):
    """Typed values a prose line states for this rule: payment terms, amounts, labelled identifiers."""
    kind = value_type(rule)
    if kind == "identifier":
        if _foreign(line, reference):
            return []
        found = []
        for phrase in keywords(rule):
            pattern = rf"\b{re.escape(phrase)}\b{_LINK}\s*({_ID})"
            for m in re.finditer(pattern, line, re.I):
                token = m.group(1)
                if re.search(r"\d", token) and identifier(token) and token not in found:
                    found.append(token)
        return found
    if kind == "payment_terms" and PAYMENT_CONTEXT.search(line):
        spans = [m.group(0) for m in _NET.finditer(line)] + [
            m.group(0) for m in _DAYS.finditer(line)
        ]
        values = {payment_terms(s) for s in spans} - {None}
        # One clear day count per line; two counts ("30 or 45 days") are left to the model/human.
        if len(values) == 1 and not _NOT_NET.search(line):
            return [spans[0]]
    if kind == "amount" and AMOUNT_CONTEXT.search(line):
        return [m.group(0).strip() for m in _AMOUNT.finditer(line)]
    return []
