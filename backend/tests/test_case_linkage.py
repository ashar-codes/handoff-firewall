"""Hidden approvals are found through case linkage; unlinked approvals never cross cases."""

from conftest import make_case, process, upload

from app.agents import run_case
from app.schemas import Extracted

RULES = [
    {"id": "po", "label": "Customer purchase order", "fields": ["po_number"]},
    {
        "id": "discount",
        "label": "Discount approval",
        "fields": ["discount_approval"],
        "review": True,
    },
]
APPROVAL = "I approve the 12% loyalty discount"


class Linking:
    """Proposes the approval only when told the document is linked to the case (observed C06)."""

    def __init__(self):
        self.seen = []

    def structured(self, task, data, schema):
        self.seen.append(data["case"])
        line = next((x for x in data["document"].splitlines() if APPROVAL in x), None)
        if not line:
            return Extracted()
        return Extracted(candidates=[{
            "requirement_id": "discount", "field": "discount_approval", "value": APPROVAL, "quote": line,
        }])  # fmt: skip


def run(client, docs, key="SO-6"):
    case = make_case(client, RULES, business_key=key)
    for name, text in docs:
        upload(client, case, text, name)
    model = Linking()
    me = client.get("/api/auth/me").json()
    run_case(case["id"], me["tenant_id"], me["id"], model)
    return case, model, client.get("/api/cases/" + case["id"]).json()


def test_hidden_approval_is_linked_through_a_known_identifier(client):
    case, model, out = run(client, [
        ("scan_00417.txt", f"Forwarded message:\n{APPROVAL} for purchase order PO-6606 from Kestrel."),
        ("ERP export.txt", "po_number: PO-6606"),
    ])  # fmt: skip
    # The model is told the case's references and which of them the document mentions,
    # even though the approval scan is searched before the ERP export.
    assert model.seen[0]["known_identifiers"] == {
        "Business reference": ["SO-6"], "Customer purchase order": ["PO-6606"]
    }  # fmt: skip
    assert model.seen[0]["document_mentions"] == ["PO-6606"]
    assert [(a["kind"], a["payload"]["requirements"]) for a in out["actions"]] == [
        ("review_evidence", ["discount"])
    ]
    action = out["actions"][0]
    client.post(
        "/api/actions/" + action["id"] + "/decision",
        json={"fingerprint": action["fingerprint"], "decision": "APPROVED", "comment": "Checked"},
    )
    assert process(client, case)["state"] == "READY"


def test_business_reference_alone_links_an_approval(client):
    _, _, out = run(client, [
        ("note.txt", f"Re SO 6: {APPROVAL}."), ("ERP export.txt", "po_number: PO-1"),
    ])  # fmt: skip
    assert [a["kind"] for a in out["actions"]] == ["review_evidence"]


def test_unlinked_or_other_case_approval_is_ignored(client):
    for key, text in [
        ("SO-7", f"{APPROVAL}."),  # no reference at all
        ("SO-8", f"{APPROVAL} for purchase order PO-9999."),  # another order's PO
    ]:
        _, _, out = run(
            client, [("approval.txt", text), ("ERP export.txt", "po_number: PO-1")], key
        )
        assert out["state"] != "READY"
        assert not [f for f in out["facts"] if f["requirement_id"] == "discount"]
        requests = [(a["kind"], a["payload"]["requirements"]) for a in out["actions"]]
        assert ("internal_clarification", ["discount"]) in requests
        assert not any(k == "review_evidence" and r == ["discount"] for k, r in requests)
        assert any(e["kind"] == "unlinked_candidate" for e in out["events"])
    # The other order's PO stated in prose is itself flagged for review, never accepted.
    assert ("review_evidence", ["po"]) in requests


def test_label_wording_does_not_make_a_rule_an_approval(client):
    """'Approved quotation' is a quotation requirement; its candidates need no case linkage."""

    class Quotes:
        def structured(self, task, data, schema):
            line = data["document"]
            return Extracted(candidates=[{
                "requirement_id": "quote", "field": "quotation_id", "value": "QT-77", "quote": line,
            }])  # fmt: skip

    case = make_case(
        client, [{"id": "quote", "label": "Approved quotation", "fields": ["quotation_id"]}]
    )
    upload(client, case, "Our quotation reference is QT-77 for this purchase.", "email.txt")
    me = client.get("/api/auth/me").json()
    run_case(case["id"], me["tenant_id"], me["id"], Quotes())
    out = client.get("/api/cases/" + case["id"]).json()
    assert [f["value"] for f in out["facts"] if f["method"] == "model_candidate"] == ["QT-77"]
    assert not any(e["kind"] == "unlinked_candidate" for e in out["events"])
