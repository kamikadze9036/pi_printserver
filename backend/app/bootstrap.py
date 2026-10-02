"""Idempotent first-start setup. Only Alembic manages the schema."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_config
from .database import get_engine
from .models import Setting, User

DEFAULT_REASONS = ["Index change", "Relabeling", "Customer request", "Quality action", "Other"]


def bootstrap():
    config = get_config()
    with Session(get_engine()) as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(7129036)"))
        if not db.scalar(select(User.id).limit(1)):
            db.add(
                User(
                    username=config.admin_username,
                    display_name="Administrator",
                    password_hash=hash_password(config.admin_password),
                    role="admin",
                )
            )
        defaults = {
            "default_quantity": config.default_print_quantity,
            "max_quantity": config.max_print_quantity,
            "reason_required": config.reason_required,
            "reasons": DEFAULT_REASONS,
        }
        for key, value in defaults.items():
            if not db.get(Setting, key):
                db.add(Setting(key=key, value=value))
        db.commit()


if __name__ == "__main__":
    bootstrap()
