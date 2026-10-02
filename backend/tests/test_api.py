import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from app.models import PrintJob, utcnow
from app.schemas import ProductInput, TemplateInput
from app.services import printing
from app.services.jobs import recover_stale_jobs
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session


def request(catalog, **overrides):
    return {
        "product_id": catalog["product"]["id"],
        "printer_id": catalog["printer"]["id"],
        "quantity": 40,
        "reason": "Relabeling",
        "note": "Quality inspection",
        "reference": "REF-001",
        "idempotency_key": str(uuid.uuid4()),
    } | overrides


def input_fields(schema, data):
    return {k: data[k] for k in schema.model_fields}


def test_sent_audited_idempotent_and_reprint(client, catalog, monkeypatch):
    sends = []
    monkeypatch.setattr(printing, "send_zpl", lambda *args: sends.append(args))
    data = request(catalog)
    created = client.post("/api/print-jobs", json=data)
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] == "sent" and job["quantity"] == 40 and "^PQ40,0,1,Y" in job["zpl"]
    assert (
        job["user_snapshot"]["username"] == "admin"
        and job["product_snapshot"]["product_code"] == "ABC"
    )
    assert job["zpl_hash"] and job["finished_at"] and len(sends) == 1
    assert "physical label output is not confirmed" in job["delivery_message"]
    assert client.post("/api/print-jobs", json=data).json()["id"] == job["id"]
    assert len(sends) == 1
    assert client.post("/api/print-jobs", json=data | {"quantity": 41}).status_code == 409
    changed = input_fields(ProductInput, catalog["product"]) | {
        "product_code": "CHANGED",
        "qr_content": "different",
    }
    assert client.put(f"/api/products/{catalog['product']['id']}", json=changed).status_code == 200
    replay_data = {"quantity": 2, "reason": "Quality action", "idempotency_key": str(uuid.uuid4())}
    reprint = client.post(f"/api/print-jobs/{job['id']}/reprint", json=replay_data).json()
    assert reprint["id"] != job["id"] and reprint["original_job_id"] == job["id"]
    assert reprint["product_snapshot"]["product_code"] == "ABC" and reprint["quantity"] == 2
    assert (
        client.post(f"/api/print-jobs/{job['id']}/reprint", json=replay_data).json()["id"]
        == reprint["id"]
    )
    assert len(sends) == 2
    history = client.get("/api/print-jobs", params={"q": "ABC", "status": "sent"}).json()
    assert len(history) == 2 and all("zpl" not in j for j in history)
    assert (
        client.get(f"/api/print-jobs/{job['id']}").json()["product_snapshot"]["product_code"]
        == "ABC"
    )


def test_failure_is_audited_without_automatic_retry(client, catalog, monkeypatch):
    attempts = []

    def fail(*args):
        attempts.append(args)
        raise TimeoutError("printer offline")

    monkeypatch.setattr(printing, "send_zpl", fail)
    data = request(catalog)
    job = client.post("/api/print-jobs", json=data).json()
    assert job["status"] == "failed" and "offline" in job["error"] and job["finished_at"]
    assert job["zpl_hash"]
    assert client.post("/api/print-jobs", json=data).json()["id"] == job["id"]
    assert len(attempts) == 1
    assert len(client.get("/api/print-jobs?status=failed").json()) == 1


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, "40", 100000])
def test_invalid_quantities(client, catalog, quantity):
    assert (
        client.post("/api/print-jobs", json=request(catalog, quantity=quantity)).status_code == 422
    )


@pytest.mark.parametrize(
    "change,error",
    [
        ({"quantity": 501}, "maximum"),
        ({"reason": ""}, "required"),
        ({"reason": "unconfigured"}, "configured"),
        ({"product_id": 9999}, "Product"),
        ({"printer_id": 9999}, "Printer"),
    ],
)
def test_semantic_rejections_are_audited(client, catalog, monkeypatch, change, error):
    monkeypatch.setattr(printing, "send_zpl", lambda *args: pytest.fail("must not send"))
    job = client.post("/api/print-jobs", json=request(catalog, **change)).json()
    assert job["status"] == "failed" and error in job["error"]
    assert len(client.get("/api/print-jobs").json()) == 1


def test_inactive_and_missing_templates(client, catalog, monkeypatch):
    monkeypatch.setattr(printing, "send_zpl", lambda *args: pytest.fail("must not send"))
    values = input_fields(TemplateInput, catalog["template"]) | {"active": False}
    assert client.put(f"/api/templates/{catalog['template']['id']}", json=values).status_code == 200
    job = client.post("/api/print-jobs", json=request(catalog)).json()
    assert job["status"] == "failed" and "template" in job["error"]
    assert client.delete(f"/api/templates/{catalog['template']['id']}").status_code == 409
    values = input_fields(ProductInput, catalog["product"]) | {"template_id": None}
    assert client.put(f"/api/products/{catalog['product']['id']}", json=values).status_code == 200
    assert (
        client.post(
            "/api/preview", json={k: request(catalog)[k] for k in ("product_id", "printer_id")}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "role,can_edit,can_print",
    [("engineer", True, True), ("team_leader", False, True), ("viewer", False, False)],
)
def test_roles_and_csrf(client, catalog, role, can_edit, can_print, monkeypatch):
    from app.main import app

    user = client.post(
        "/api/users", json={"username": role, "password": "password-for-test-123", "role": role}
    ).json()
    assert "password_hash" not in user
    monkeypatch.setattr(printing, "send_zpl", lambda *args: None)
    with TestClient(app) as other:
        assert other.get("/api/products").status_code == 401
        login = other.post(
            "/api/auth/login", json={"username": role, "password": "password-for-test-123"}
        )
        assert login.status_code == 200
        assert other.post("/api/print-jobs", json=request(catalog)).status_code == 403
        other.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        assert other.get("/api/products").status_code == 200
        assert other.get("/api/users").status_code == 403
        assert (
            other.post("/api/printers", json={"name": "Forbidden", "host": "localhost"}).status_code
            == 403
        )
        response = other.post("/api/products", json={"product_code": role})
        assert response.status_code == (201 if can_edit else 403)
        response = other.post("/api/print-jobs", json=request(catalog))
        assert response.status_code == (201 if can_print else 403)
        assert other.post("/api/auth/logout").status_code == 204
        assert other.get("/api/auth/me").status_code == 401


def test_login_and_last_admin(client):
    from app.main import app

    with TestClient(app) as guest:
        assert (
            guest.post(
                "/api/auth/login", json={"username": "admin", "password": "wrong"}
            ).status_code
            == 401
        )
        assert (
            guest.post(
                "/api/auth/login",
                json={"username": "admin", "password": "test-admin-password-123"},
                headers={"Origin": "https://evil.local"},
            ).status_code
            == 403
        )
    admin = client.get("/api/auth/me").json()["user"]
    assert client.delete(f"/api/users/{admin['id']}").status_code == 409
    assert (
        client.put(
            f"/api/users/{admin['id']}",
            json={k: admin[k] for k in ("username", "display_name", "role", "active")}
            | {"active": False},
        ).status_code
        == 409
    )


def test_crud_duplicates_and_preview(client, catalog):
    assert client.post("/api/products", json={"product_code": "ABC"}).status_code == 409
    assert (
        client.post(
            "/api/products", json={"product_code": "missing", "template_id": 999}
        ).status_code
        == 404
    )
    copied = client.post(
        f"/api/products/{catalog['product']['id']}/duplicate", json={"name": "COPY"}
    ).json()
    assert copied["product_code"] == "COPY" and copied["template_id"] == catalog["template"]["id"]
    copied_t = client.post(
        f"/api/templates/{catalog['template']['id']}/duplicate", json={"name": "Template copy"}
    ).json()
    assert copied_t["elements"] == catalog["template"]["elements"]
    preview = client.post(
        "/api/preview",
        json={"product_id": copied["id"], "printer_id": catalog["printer"]["id"], "quantity": 40},
    )
    assert (
        preview.status_code == 200
        and "<svg" in preview.json()["svg"]
        and "^PQ40" in preview.json()["zpl"]
    )
    assert client.delete(f"/api/products/{copied['id']}").status_code == 204
    assert client.delete(f"/api/templates/{copied_t['id']}").status_code == 204


def test_bad_template_printer_and_arbitrary_destination(client, catalog):
    assert (
        client.post(
            "/api/printers", json={"name": "URL", "host": "http://localhost:9100"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/templates",
            json={
                "name": "bad",
                "width_mm": 60,
                "height_mm": 40,
                "elements": [{"type": "text", "x": 59, "w": 10}],
            },
        ).status_code
        == 422
    )
    assert (
        client.post("/api/print-jobs", json=request(catalog, host="evil.local")).status_code == 422
    )


def test_audit_immutable_and_restart_recovery(client, catalog, database, monkeypatch):
    monkeypatch.setattr(printing, "send_zpl", lambda *args: None)
    job = client.post("/api/print-jobs", json=request(catalog)).json()
    with Session(database) as db:
        with pytest.raises(DatabaseError):
            db.execute(text("UPDATE print_jobs SET quantity=2 WHERE id=:id"), {"id": job["id"]})
            db.commit()
        db.rollback()
        with pytest.raises(DatabaseError):
            db.execute(text("DELETE FROM print_jobs WHERE id=:id"), {"id": job["id"]})
            db.commit()
        db.rollback()
        interrupted = PrintJob(
            user_id=1,
            idempotency_key=str(uuid.uuid4()),
            request_hash="x" * 64,
            created_at=utcnow() - timedelta(minutes=10),
            user_snapshot={},
            product_snapshot={},
            template_snapshot={},
            printer_snapshot={},
            quantity=1,
            reason="Other",
            note="",
            reference="",
            status="queued",
        )
        db.add(interrupted)
        db.commit()
        ident = interrupted.id
        recover_stale_jobs(db)
        db.expire_all()
        assert db.get(PrintJob, ident).status == "failed"
        assert "uncertain" in db.get(PrintJob, ident).error


def test_concurrent_idempotency_sends_once(client, catalog, monkeypatch):
    gate, release = threading.Event(), threading.Event()
    sends = []

    def send(*args):
        sends.append(args)
        gate.set()
        assert release.wait(10)

    monkeypatch.setattr(printing, "send_zpl", send)
    data = request(catalog)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, "/api/print-jobs", json=data)
        assert gate.wait(10)
        second = client.post("/api/print-jobs", json=data)
        assert second.status_code == 201 and second.json()["status"] == "queued"
        release.set()
        result = first.result(timeout=10)
    assert result.json()["id"] == second.json()["id"] and result.json()["status"] == "sent"
    assert len(sends) == 1


def test_multiple_printers_and_test_print(client, catalog, monkeypatch):
    sends = []
    monkeypatch.setattr(printing, "send_zpl", lambda *args: sends.append(args))
    second = client.post(
        "/api/printers", json={"name": "Zebra B", "host": "zebra-b.local", "dpi": 300, "port": 9200}
    ).json()
    job = client.post("/api/print-jobs", json=request(catalog, printer_id=second["id"])).json()
    assert job["status"] == "sent" and sends[0][0] == "zebra-b.local" and sends[0][2] == 9200
    assert "^PW709" in sends[0][1]
    test = client.post(
        f"/api/printers/{second['id']}/test-print",
        json={"reason": "Printer test", "idempotency_key": str(uuid.uuid4())},
    ).json()
    assert test["status"] == "sent" and test["quantity"] == 1

    def offline(*args):
        raise ConnectionRefusedError("offline")

    monkeypatch.setattr(printing, "test_connection", offline)
    assert client.post(f"/api/printers/{second['id']}/test-connection").json()["status"] == "failed"
