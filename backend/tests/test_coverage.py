"""READY needs affirmative, current support; a missed extraction must not clear a case."""

from conftest import make_case, process, upload

from app.agents import run_case
from app.schemas import Extracted

TERMS = [{"id": "terms", "label": "Payment terms", "fields": ["payment_terms"]}]


class Extracts:
    """A model that returns only the listed candidates (simulating partial extraction)."""

    def __init__(self, *candidates):
        self.candidates = candidates

    def structured(self, task, data, schema):
        if schema is not Extracted:
            return schema(message=data["request"])
        return Extracted(
            candidates=[
                {"requirement_id": "terms", "field": "payment_terms", "value": v, "quote": q}
                for v, q in self.candidates
                if q in data["document"]
            ]
        )


def run(client, case, model):
    me = client.get("/api/auth/me").json()
    run_case(case["id"], me["tenant_id"], me["id"], model)
    return client.get("/api/cases/" + case["id"]).json()


def test_missed_prose_contradiction_still_blocks_ready(client):
    case = make_case(client, TERMS)
    upload(client, case, "payment_terms: 30 days", "erp.txt")
    upload(client, case, "Payment is due forty-five days from invoice date.", "email.txt")
    out = run(client, case, Extracts())  # the model misses the contradicting sentence
    assert out["state"] != "READY"
    assert out["statuses"]["terms"]["state"] == "AWAITING_REVIEW"
    assert [(f["value"], f["method"]) for f in out["facts"] if not f["accepted"]] == [
        ("forty-five days", "pattern")
    ]


def test_one_sided_extraction_of_two_prose_sources_is_not_ready(client):
    case = make_case(client, TERMS)
    first = (
        "The customer shall remit payment within thirty calendar days following invoice receipt."
    )
    upload(client, case, first, "contract.txt")
    upload(client, case, "Payment is due forty-five days from invoice date.", "po.txt")
    out = run(client, case, Extracts(("within thirty calendar days", first)))
    assert out["state"] != "READY"
    values = sorted(f["value"] for f in out["facts"])
    assert values == ["forty-five days", "within thirty calendar days"]


def test_equivalent_prose_does_not_over_block_a_complete_case(client):
    case = make_case(client, TERMS)
    upload(client, case, "payment_terms: Net 30", "erp.txt")
    upload(client, case, "As agreed, payment is due within thirty days of invoice.", "email.txt")
    out = run(client, case, Extracts())
    assert out["state"] == "READY" and not out["actions"]
    [support] = out["statuses"]["terms"]["support"]
    assert support["value"] == "Net 30" and support["normalized"] == "payment_terms:net_days:30"
    assert support["method"] == "exact" and support["document_version"] == 1
    assert support["normalizer"] == "biz-v1" and support["source_hash"]


def test_complete_structured_case_is_ready_with_a_support_trace(client):
    rules = [
        {"id": "po", "label": "Purchase order", "fields": ["po_number", "purchase_order"]},
        {"id": "total", "label": "Order total", "fields": ["order_total"]},
        *TERMS,
    ]
    case = make_case(client, rules)
    upload(client, case, "purchase_order: PO-77\norder_total: PKR 500,000\npayment_terms: Net 30")
    upload(client, case, "order_total: Rs. 500000", "quotation.txt")
    out = process(client, case)  # alternative field and equivalent amounts, no human needed
    assert out["state"] == "READY" and not out["actions"] and not out["conflicts"]
    assert len(out["statuses"]["total"]["support"]) == 2
    assert out["statuses"]["po"]["support"][0]["value"] == "PO-77"


def test_reviewer_required_support_waits_for_a_human(client):
    case = make_case(client, [{**TERMS[0], "review": True}])
    upload(client, case, "payment_terms: 30 days")
    out = process(client, case)
    assert out["state"] != "READY" and out["statuses"]["terms"]["support"] == []
    [fact] = out["facts"]
    r = client.post(
        "/api/facts/" + fact["id"] + "/review", json={"accepted": True, "comment": "OK"}
    )
    assert r.status_code == 200
    out = process(client, case)
    assert out["state"] == "READY"
    assert out["statuses"]["terms"]["support"][0]["accepted_by"]


def test_replaced_support_is_no_longer_counted(client):
    case = make_case(client, TERMS)
    doc = upload(client, case, "payment_terms: 30 days")
    assert process(client, case)["state"] == "READY"
    upload(client, case, "note: terms to follow", "evidence.txt", doc["id"])
    out = process(client, case)
    assert out["state"] != "READY" and out["statuses"]["terms"]["support"] == []


def test_no_affirmative_evidence_is_never_ready(client):
    case = make_case(client, TERMS)
    upload(client, case, "Standard payment terms apply to this order.", "note.txt")
    out = run(client, case, Extracts())
    assert out["state"] != "READY" and out["statuses"]["terms"]["state"] == "MISSING"
