import hashlib
import json
import sqlite3


def legacy_copy(tmp_path):
    path = tmp_path / "explicit-copy.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE templates (id INTEGER PRIMARY KEY, name TEXT, width_mm REAL, height_mm REAL, elements TEXT);
        CREATE TABLE products (id INTEGER PRIMARY KEY, product_code TEXT, qr_content TEXT, text_content TEXT,
        text2 TEXT, text3 TEXT, text4 TEXT, side TEXT, highlight_right INTEGER, template_id INTEGER);""")
        elements = [
            {"type": "qr", "x": 2, "y": 2, "w": 20, "h": 20, "content": "{qr_content}"},
            {
                "type": "text",
                "x": 24,
                "y": 2,
                "w": 34,
                "h": 8,
                "font_size": 10,
                "content": "{text_content}",
            },
        ]
        db.execute(
            "INSERT INTO templates VALUES (42,?,?,?,?)",
            ("Legacy standard", 60, 40, json.dumps(elements)),
        )
        db.execute(
            "INSERT INTO products VALUES (1,?,?,?,?,?,?,?,?,?)",
            ("fg 123", "QR payload", "Description", "second", "third", "fourth", "R", 1, 42),
        )
    return path


def test_import_dry_run_mapping_repeat_and_source_unchanged(client, tmp_path):
    path = legacy_copy(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    response = client.post(
        "/api/import/dry-run",
        files={"file": ("copy.db", path.read_bytes())},
        data={"confirm_copy": "true"},
    )
    assert response.status_code == 200, response.text
    dry = response.json()
    assert dry["source_hash"] == before and dry["report"]["products_create"] == ["FG 123"]
    assert client.get("/api/products").json() == []  # Dry-run never changes catalog.
    result = client.post(f"/api/import/{dry['id']}/execute")
    assert result.status_code == 200, result.text
    assert (
        client.post(f"/api/import/{dry['id']}/execute").json()["executed_at"]
        == result.json()["executed_at"]
    )
    product = client.get("/api/products").json()[0]
    template = client.get("/api/templates").json()[0]
    assert product["template_id"] == template["id"] and template["id"] != 42
    assert product["text_content"] == "Description" and product["text4"] == "fourth"
    assert product["side"] == "R" and product["highlight_right"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    again = client.post(
        "/api/import/dry-run",
        files={"file": ("copy.db", path.read_bytes())},
        data={"confirm_copy": "true"},
    ).json()
    assert again["report"]["products_skip"] == ["FG 123"] and not again["report"]["errors"]
    assert client.post(f"/api/import/{again['id']}/execute").status_code == 200


def test_import_requires_copy_and_rejects_invalid_files(client):
    assert (
        client.post(
            "/api/import/dry-run", files={"file": ("live.db", b"SQLite format 3\x00")}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/import/dry-run",
            files={"file": ("bad", b"not a database")},
            data={"confirm_copy": "true"},
        ).status_code
        == 422
    )
    assert client.post("/api/import/missing/execute").status_code == 404


def test_import_detects_catalog_changes(client, tmp_path):
    path = legacy_copy(tmp_path)
    dry = client.post(
        "/api/import/dry-run",
        files={"file": ("copy.db", path.read_bytes())},
        data={"confirm_copy": "true"},
    ).json()
    assert client.post("/api/products", json={"product_code": "FG 123"}).status_code == 201
    assert client.post(f"/api/import/{dry['id']}/execute").status_code == 409


def test_invalid_legacy_template_and_missing_mapping(client, tmp_path):
    path = legacy_copy(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE products SET template_id=99")
    response = client.post(
        "/api/import/dry-run",
        files={"file": ("copy.db", path.read_bytes())},
        data={"confirm_copy": "true"},
    )
    assert response.status_code == 422 and "missing source template" in response.text
