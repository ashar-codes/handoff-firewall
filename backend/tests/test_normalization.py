"""Deterministic business-value normalization matrix."""

import pytest

from app.normalization import amount, canonical, detect, identifier, payment_terms

TERMS = {"id": "terms", "label": "Payment terms", "fields": ["payment_terms"]}
TOTAL = {"id": "total", "label": "Order total", "fields": ["order_total"]}
TOTAL_PKR = {**TOTAL, "currency": "PKR"}
ORDER = {"id": "order", "label": "Sales order", "fields": ["order_number"]}


def same(rule, a, b):
    return canonical(rule, a)[0] == canonical(rule, b)[0]


@pytest.mark.parametrize(
    "a,b",
    [
        ("Net 30", "30 days"),
        ("NET30", "within thirty days"),
        ("Net 30", "payment due in 30 days"),
        ("30 days", "payment due thirty days after invoice"),
        ("within thirty calendar days", "Net-30"),
        ("forty-five days from invoice date", "Net 45"),
    ],
)
def test_equivalent_payment_terms(a, b):
    assert same(TERMS, a, b)


@pytest.mark.parametrize(
    "a,b", [("Net 30", "Net 45"), ("30 days", "45 days"), ("Net 30", "30 business days")]
)
def test_different_payment_terms_stay_different(a, b):
    assert not same(TERMS, a, b)


@pytest.mark.parametrize(
    "vague",
    [
        "standard terms",
        "Standard payment terms apply",
        "normal terms",
        "usual payment period",
        "as agreed",
        "end of month",
        "2/10 net 30",
        "30 or 45 days",
        "50% advance, balance in 30 days",
        "",
    ],
)
def test_vague_or_complex_terms_are_ambiguous(vague):
    assert payment_terms(vague) is None
    assert canonical(TERMS, vague)[1] == "raw"


@pytest.mark.parametrize(
    "a,b",
    [
        ("PKR 500,000", "Rs. 500000"),
        ("Rs 500,000.00", "PKR 500000"),
        ("500000 PKR", "₨500,000"),
        ("PKR 5,00,000", "PKR 500000"),
        ("USD 1,250.50", "$1250.5"),
    ],
)
def test_equivalent_amounts(a, b):
    assert same(TOTAL, a, b)


def test_currency_is_never_guessed():
    assert not same(TOTAL, "PKR 500000", "USD 500000")
    assert amount("500000") is None and canonical(TOTAL, "500000")[1] == "raw"
    assert not same(TOTAL, "500000", "PKR 500000")
    # Only an approved rule may supply the currency for a bare number.
    assert same(TOTAL_PKR, "500,000", "PKR 500000")
    assert amount("PKR 100 and USD 100") is None


def test_identifier_formatting_but_not_lookalikes():
    assert identifier("so 1042") == identifier("SO-1042") == identifier("so_1042") == "SO-1042"
    assert same(ORDER, "so 1042", "SO-1042")
    assert not same(ORDER, "SO-8821", "SO-882I")
    assert not same(ORDER, "SO-1042", "SO-1O42")
    assert identifier("SO/1042") is None and canonical(ORDER, "SO/1042")[1] == "raw"


def test_explicit_value_type_overrides_inference():
    rule = {"id": "ref", "label": "Reference", "fields": ["reference"], "value_type": "identifier"}
    assert same(rule, "ab 12", "AB-12")
    assert canonical({"id": "n", "label": "Note", "fields": ["note"]}, "Net 30")[1] == "raw"


@pytest.mark.parametrize("junk", [None, "∞", "Rs. abc", "net -5", "Net 999", "x" * 5000])
def test_malformed_values_fail_safely(junk):
    for rule in (TERMS, TOTAL, ORDER):
        key, method = canonical(rule, junk or "")
        assert key.startswith(("raw:", "payment_terms:", "amount:", "identifier:"))
    assert payment_terms(junk) is None


def test_prose_detection_needs_business_context():
    assert detect(TERMS, "Payment is due forty-five days from invoice date.") == ["forty-five days"]
    assert detect(TERMS, "Delivery will take 14 days.") == []
    assert detect(TERMS, "Standard payment terms apply.") == []
    assert detect(TOTAL, "The order total is PKR 1,180,000 inclusive of tax.") == ["PKR 1,180,000"]
    assert detect(TOTAL, "Warehouse 500000 is in Lahore.") == []
