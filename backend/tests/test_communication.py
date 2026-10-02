"""Human-facing wording is professional, bundled by owner and free of internal details."""

import re

from conftest import login_as, make_case, process, upload

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-")
JARGON = re.compile(r"AWAITING_REVIEW|MISSING|CONFLICTING|_id\b|payment_terms|fact|hash", re.I)


def clean(message):
    return not UUID.search(message) and not JARGON.search(message)


def test_one_owner_gets_one_bundled_professional_request(client):
    rules = [
        {"id": "quote", "label": "Approved quotation", "fields": ["quotation_id"]},
        {"id": "terms", "label": "Payment terms", "fields": ["payment_terms"]},
        {"id": "tax", "label": "Tax registration", "fields": ["tax_id"]},
    ]
    out = process(client, make_case(client, rules, business_key="SO-1042"))
    [action] = out["actions"]
    assert action["payload"]["message"] == (
        "Could you please provide the following for SO-1042: the approved quotation, "
        "the payment terms and the tax registration?"
    )
    assert [q["ask"] for q in action["payload"]["questions"]] == ["provide"] * 3
    assert clean(action["payload"]["message"])


def test_different_owners_receive_separate_requests(client):
    users = {u["role"]: u["id"] for u in client.get("/api/users").json()}
    rules = [
        {"id": "terms", "label": "Payment terms", "fields": ["payment_terms"],
         "owner_id": users["Reviewer"]},
        {"id": "tax", "label": "Tax registration", "fields": ["tax_id"],
         "owner_id": users["Operator"]},
    ]  # fmt: skip
    out = process(client, make_case(client, rules, business_key="SO-7"))
    messages = {a["owner_id"]: a["payload"]["message"] for a in out["actions"]}
    assert messages == {
        users["Reviewer"]: "Could you please provide the payment terms for SO-7?",
        users["Operator"]: "Could you please provide the tax registration for SO-7?",
    }


def test_conflict_and_review_wording_names_values_and_sources_not_ids(client):
    rules = [{"id": "terms", "label": "Payment terms", "fields": ["payment_terms"]}]
    case = make_case(client, rules, business_key="SO-3303")
    upload(client, case, "payment_terms: 30 days", "ERP export.txt")
    upload(client, case, "payment_terms: 45 days", "Customer PO.txt")
    out = process(client, case)
    [action] = out["actions"]
    assert action["payload"]["message"] == (
        "Could you please confirm the payment terms for SO-3303? The sources disagree: "
        "“30 days” in ERP export.txt and “45 days” in Customer PO.txt."
    )
    assert clean(action["payload"]["message"])
    review = make_case(client, [{**rules[0], "review": True}], business_key="SO-5")
    upload(client, review, "payment_terms: 30 days", "ERP export.txt")
    message = process(client, review)["actions"][0]["payload"]["message"]
    assert message == (
        "Please review the payment terms (“30 days” in ERP export.txt) for SO-5 "
        "and accept it if it is valid."
    )


def test_unknown_condition_asks_whether_it_applies(client):
    rules = [
        {"id": "discount", "label": "Discount approval", "fields": ["discount_approval"],
         "condition": {"field": "discount_requires_approval", "equals": "yes"}},
    ]  # fmt: skip
    login_as(client, "Administrator")
    out = process(client, make_case(client, rules, business_key="SO-9"))
    assert out["actions"][0]["payload"]["message"] == (
        "Could you please confirm whether the discount approval applies to SO-9?"
    )
