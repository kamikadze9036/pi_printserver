import uuid

from app.services import printing


def test_settings_server_enforced_and_optional_reason(client, catalog, monkeypatch):
    monkeypatch.setattr(printing, "send_zpl", lambda *args: None)
    settings = client.get("/api/settings").json()
    changed = settings | {
        "default_quantity": 2,
        "max_quantity": 10,
        "reason_required": False,
        "reasons": ["New reason"],
    }
    assert client.put("/api/settings", json=changed).status_code == 200
    data = {
        "product_id": catalog["product"]["id"],
        "printer_id": catalog["printer"]["id"],
        "quantity": 10,
        "reason": "",
        "idempotency_key": str(uuid.uuid4()),
    }
    assert client.post("/api/print-jobs", json=data).json()["status"] == "sent"
    failed = client.post(
        "/api/print-jobs", json=data | {"quantity": 11, "idempotency_key": str(uuid.uuid4())}
    ).json()
    assert failed["status"] == "failed" and "maximum 10" in failed["error"]
    assert client.put("/api/settings", json=changed | {"default_quantity": 11}).status_code == 422
    assert (
        client.put("/api/settings", json=changed | {"reasons": ["same", "same"]}).status_code == 422
    )
