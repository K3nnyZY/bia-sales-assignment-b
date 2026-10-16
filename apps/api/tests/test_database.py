"""Opt-in real PostgreSQL checks, isolated in a unique schema per test run."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.api.health import SCHEMA_REVISION
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 for PostgreSQL"
    ),
]


def test_postgres_migration_roundtrip_and_readiness():
    settings = Settings()
    schema = f"test_{uuid4().hex}"
    admin = create_engine(settings.sqlalchemy_url)
    engine = None
    try:
        with admin.begin() as connection:
            assert connection.dialect.name == "postgresql"
            assert connection.execute(text("SHOW server_version_num")).scalar_one().startswith("16")
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            settings.sqlalchemy_url, connect_args={"options": f"-csearch_path={schema}"}
        )
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

        def migrate(target, revision):
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                target(config, revision)

        def session_override():
            with Session(engine) as session:
                yield session

        app = create_app(settings)
        app.dependency_overrides[get_session] = session_override
        with TestClient(app) as client:
            assert client.get("/health/ready").json()["migrations"] == "pending"
            migrate(command.upgrade, "head")
            migrate(command.upgrade, "head")  # Idempotent replay.
            with engine.connect() as connection:
                assert MigrationContext.configure(connection).get_current_heads() == (
                    SCHEMA_REVISION,
                )
                assert set(inspect(connection).get_table_names()) == {
                    "alembic_version",
                    "users",
                    "models",
                    "tools",
                    "agents",
                    "agent_versions",
                    "agent_tools",
                    "invoices",
                    "billing_knowledge",
                    "agent_invocations",
                    "agent_runs",
                    "tool_calls",
                    "run_events",
                }
            assert client.get("/health/ready").status_code == 200
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.check(config)
            migrate(command.downgrade, "base")
            assert client.get("/health/ready").status_code == 503
            migrate(command.upgrade, "head")
            assert client.get("/health/ready").status_code == 200
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
