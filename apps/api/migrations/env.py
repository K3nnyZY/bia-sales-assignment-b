from alembic import context
from sqlalchemy import create_engine, pool, text

from app.core.config import Settings
from app.db import models  # noqa: F401 — register domain metadata
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=Settings().sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table_schema=connection.scalar(text("SELECT current_schema()")),
        include_object=lambda obj, name, kind, reflected, compare_to: (
            not (kind == "table" and name == "alembic_version")
        ),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        migrate(supplied_connection)
        return
    engine = create_engine(Settings().sqlalchemy_url, poolclass=pool.NullPool)
    try:
        # current_schema() starts a transaction before Alembic configures its own.
        # Own that transaction explicitly so CLI migrations commit on success.
        with engine.begin() as connection:
            migrate(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
