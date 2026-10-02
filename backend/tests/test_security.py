from app.config import Config
from fastapi.testclient import TestClient


def test_password_whitespace_preserved_and_sessions_revoked(client):
    from app.main import app

    password = " leading-and-trailing-password "
    user = client.post(
        "/api/users", json={"username": "secure-user", "role": "engineer", "password": password}
    ).json()
    with TestClient(app) as other:
        result = other.post(
            "/api/auth/login", json={"username": "secure-user", "password": password}
        )
        assert result.status_code == 200
        cookie = result.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
        assert "password" not in result.json() and "password_hash" not in result.json()["user"]
        assert other.get("/api/auth/me").status_code == 200
        values = {k: user[k] for k in ("username", "display_name", "role", "active")}
        assert (
            client.put(
                f"/api/users/{user['id']}", json=values | {"password": "new-password-for-test-123"}
            ).status_code
            == 200
        )
        assert other.get("/api/auth/me").status_code == 401
        assert (
            other.post(
                "/api/auth/login", json={"username": "secure-user", "password": password}
            ).status_code
            == 401
        )
        assert (
            other.post(
                "/api/auth/login",
                json={"username": "secure-user", "password": "new-password-for-test-123"},
            ).status_code
            == 200
        )
        assert (
            client.put(f"/api/users/{user['id']}", json=values | {"active": False}).status_code
            == 200
        )
        assert other.get("/api/auth/me").status_code == 401


def test_configuration_escapes_database_password():
    from sqlalchemy.engine import make_url

    config = Config(
        _env_file=None,
        database_url="",
        secret_key="x" * 32,
        admin_password="y" * 12,
        postgres_password="symbols:@/#%$",
    )
    assert make_url(config.database_url).password == "symbols:@/#%$"


def test_placeholder_secrets_rejected():
    import pytest

    with pytest.raises(ValueError):
        Config(
            _env_file=None,
            database_url="sqlite://",
            secret_key="change-me-" + "x" * 32,
            admin_password="y" * 12,
        )


def test_login_rate_limit_and_validation_redacts_password(client):
    from app.main import app

    with TestClient(app) as other:
        for _ in range(10):
            assert (
                other.post(
                    "/api/auth/login", json={"username": "wrong-user", "password": "wrong"}
                ).status_code
                == 401
            )
        assert (
            other.post(
                "/api/auth/login", json={"username": "wrong-user", "password": "wrong"}
            ).status_code
            == 429
        )
    secret = "x" * 260
    response = client.post("/api/users", json={"username": "too-long", "password": secret})
    assert response.status_code == 422 and secret not in response.text
