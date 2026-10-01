from conftest import make_case, process, upload


def test_admin_can_revoke_access_and_cannot_disable_self(client):
    users = client.get("/api/users").json()
    viewer = next(u for u in users if u["role"] == "Viewer")
    assert (
        client.patch(
            "/api/users/" + viewer["id"], json={"role": "Viewer", "active": False}
        ).status_code
        == 200
    )
    me = client.get("/api/auth/me").json()
    assert (
        client.patch("/api/users/" + me["id"], json={"role": "Viewer", "active": False}).status_code
        == 409
    )
    from conftest import PASSWORD

    assert (
        client.post(
            "/api/auth/login", json={"email": viewer["email"], "password": PASSWORD}
        ).status_code
        == 401
    )


def test_external_draft_bound_and_never_sent(client):
    c = make_case(client)
    body = {
        "recipient": "customer@example.test",
        "message": "Please confirm the terms",
        "requirements": ["terms"],
    }
    assert client.post("/api/cases/" + c["id"] + "/external-drafts", json=body).status_code == 409
    process(client, c)
    r = client.post("/api/cases/" + c["id"] + "/external-drafts", json=body)
    assert r.status_code == 201, r.text
    draft = next(
        a
        for a in client.get("/api/cases/" + c["id"]).json()["actions"]
        if a["kind"] == "external_draft"
    )
    assert draft["approval_required"]
    assert (
        client.post("/api/actions/" + draft["id"] + "/execute", json={}).json()["action"]["status"]
        == "PROPOSED"
    )
    assert (
        client.post(
            "/api/actions/" + draft["id"] + "/decision",
            json={
                "fingerprint": draft["fingerprint"],
                "decision": "APPROVED",
                "comment": "Approved exact draft; no delivery requested",
            },
        ).status_code
        == 200
    )
    from app.worker import tick

    assert tick()
    after = client.get("/api/cases/" + c["id"]).json()
    executed = next(a for a in after["actions"] if a["id"] == draft["id"])
    assert executed["status"] == "COMPLETED"
    assert "no external delivery" in executed["result"]["effect"]
    assert after["state"] != "READY"


def test_policy_change_cannot_reuse_fact_from_removed_alias(client):
    c = make_case(client)
    upload(client, c, "payment_terms: 30 days")
    assert process(client, c)["state"] == "READY"
    t = c["template_id"]
    new = client.post(
        "/api/templates/" + t + "/versions",
        json={
            "name": "Stricter",
            "source": "Sales",
            "destination": "Finance",
            "rules": [
                {"id": "terms", "label": "New source", "fields": ["approved_contract_terms"]}
            ],
        },
    ).json()
    assert client.post("/api/cases/" + c["id"] + "/rules/" + new["id"], json={}).status_code == 200
    after = process(client, c)
    assert after["state"] != "READY"
    assert after["statuses"]["terms"]["state"] == "MISSING"


def test_dependency_repair_does_not_ask_for_evidence_already_present(client):
    c = make_case(
        client,
        [
            {"id": "po", "label": "PO", "fields": ["po"]},
            {"id": "account", "label": "Account", "fields": ["account"], "depends_on": ["po"]},
        ],
    )
    upload(client, c, "account: AC-1")
    after = process(client, c)
    assert after["actions"][0]["payload"]["requirements"] == ["po"]


def test_unrelated_outstanding_request_not_duplicated(client):
    users = client.get("/api/users").json()
    other = next(u for u in users if u["role"] == "Operator")
    c = make_case(
        client,
        [
            {"id": "po", "label": "PO", "fields": ["po"]},
            {"id": "tax", "label": "Tax", "fields": ["tax"], "owner_id": other["id"]},
        ],
    )
    out = process(client, c)
    tax_action = next(a for a in out["actions"] if "tax" in a["payload"]["requirements"])
    upload(client, c, "po: PO-1")
    after = process(client, c)
    assert next(a for a in after["actions"] if a["id"] == tax_action["id"])["status"] == "WAITING"
    assert (
        len(
            [
                a
                for a in after["actions"]
                if a["status"] == "WAITING" and "tax" in a["payload"]["requirements"]
            ]
        )
        == 1
    )


def test_not_applicable_condition_does_not_require_unrelated_dependency(client):
    c = make_case(
        client,
        [
            {"id": "po", "label": "Optional", "fields": ["po"], "mandatory": False},
            {
                "id": "discount",
                "label": "Discount",
                "fields": ["approval"],
                "depends_on": ["po"],
                "condition": {"field": "discount", "equals": "yes"},
            },
        ],
        {"discount": "no"},
    )
    assert process(client, c)["state"] == "READY"
