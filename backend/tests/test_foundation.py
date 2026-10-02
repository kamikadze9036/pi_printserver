import pytest
from app.auth import hasher
from app.models import User
from app.schemas import TemplateInput
from app.services.zpl import render_zpl
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session


def test_migration_and_idempotent_bootstrap(database):
    from app.bootstrap import bootstrap

    bootstrap()
    assert {"users", "templates", "products", "printers", "print_jobs", "import_runs"} <= set(
        inspect(database).get_table_names()
    )
    with Session(database) as db:
        users = list(db.scalars(select(User)))
        assert len(users) == 1
        assert hasher.verify(users[0].password_hash, "test-admin-password-123")
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    command.check(Config(str(Path(__file__).parents[1] / "alembic.ini")))


def test_template_validation_and_renderer():
    template = {
        "name": "60x40",
        "width_mm": 60,
        "height_mm": 40,
        "elements": [
            {"type": "qr", "x": 2, "y": 2, "w": 20, "h": 20, "content": "{qr_content}"},
            {"type": "text", "x": 24, "y": 2, "w": 34, "h": 8, "content": "{product_code}"},
        ],
    }
    now = __import__("datetime").datetime(2026, 10, 2, 6, 30)
    zpl = render_zpl(
        template, {"product_code": "ABC^XZ~JA", "qr_content": "Hello"}, "user", quantity=40, now=now
    )
    assert zpl == render_zpl(
        template, {"product_code": "ABC^XZ~JA", "qr_content": "Hello"}, "user", quantity=40, now=now
    )
    assert "^PW480" in zpl and "^LL320" in zpl and "^PQ40,0,1,Y" in zpl
    assert zpl.count("^XZ") == 1 and "~JA" not in zpl and "^BQN,2," in zpl
    with pytest.raises(ValueError):
        TemplateInput.model_validate(
            template | {"elements": [{"type": "text", "content": "{evil}"}]}
        )
