from alembic import context
from app import models  # noqa: F401
from app.config import get_config
from app.database import Base
from sqlalchemy import create_engine, pool

url = get_config().database_url


def run_migrations():
    if context.is_offline_mode():
        context.configure(
            url=url,
            target_metadata=Base.metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        with create_engine(url, poolclass=pool.NullPool).connect() as connection:
            context.configure(
                connection=connection, target_metadata=Base.metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()


run_migrations()
