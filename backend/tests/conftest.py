import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

os.environ.setdefault("SECRET_KEY", "test-only-secret-" + "a" * 40)
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password-123")


@pytest.fixture
def database(tmp_path, monkeypatch):
    from app.config import get_config
    from app.database import get_engine

    url = os.environ.get("TEST_DATABASE_URL") or "sqlite:///" + (tmp_path / "app.sqlite").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    get_config.cache_clear()
    get_engine.cache_clear()
    config = AlembicConfig(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    from app.bootstrap import bootstrap

    bootstrap()
    yield get_engine()
    if os.environ.get("TEST_DATABASE_URL"):
        command.downgrade(config, "base")
    get_engine().dispose()
    get_engine.cache_clear()
    get_config.cache_clear()


@pytest.fixture
def client(database):
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "test-admin-password-123"}
        )
        assert login.status_code == 200, login.text
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        yield client


@pytest.fixture
def catalog(client):
    template = client.post(
        "/api/templates",
        json={
            "name": "60x40",
            "width_mm": 60,
            "height_mm": 40,
            "elements": [
                {"type": "qr", "x": 2, "y": 2, "w": 20, "h": 20, "content": "{qr_content}"},
                {"type": "text", "x": 24, "y": 2, "w": 34, "h": 8, "content": "{product_code}"},
                {
                    "type": "text",
                    "x": 2,
                    "y": 28,
                    "w": 56,
                    "h": 8,
                    "content": "{text_content} {operator}",
                },
            ],
        },
    ).json()
    printer = client.post(
        "/api/printers", json={"name": "Zebra A", "host": "127.0.0.1", "dpi": 203}
    ).json()
    product = client.post(
        "/api/products",
        json={
            "product_code": "abc",
            "description": "Example",
            "qr_content": "https://example.local/ABC",
            "text_content": "Test",
            "template_id": template["id"],
            "preferred_printer_id": printer["id"],
        },
    ).json()
    return {"template": template, "printer": printer, "product": product}
