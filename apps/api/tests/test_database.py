"""Opt-in real PostgreSQL checks, isolated in a unique schema per test run."""

import os
import subprocess
import sys
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


def test_alembic_cli_commits_migrations_on_its_own_connection():
    """Exercise the CLI path, without supplying the transaction used by fixtures."""
    settings = Settings()
    schema = f"test_cli_{uuid4().hex}"
    admin = create_engine(settings.sqlalchemy_url)
    scoped_url = settings.sqlalchemy_url.update_query_dict(
        {"options": f"-csearch_path={schema},public"}
    )
    engine = create_engine(scoped_url)
    config_path = str(Path(__file__).resolve().parents[1] / "alembic.ini")
    environment = {**os.environ, "DATABASE_URL": scoped_url.render_as_string(hide_password=False)}

    def cli(*arguments: str) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", config_path, *arguments],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

    def committed_tables() -> set[str]:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names(schema=schema))

    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        assert committed_tables() == set()
        cli("upgrade", "head")
        assert {"agents", "agent_runs", "knowledge_chunks"} <= committed_tables()
        with engine.connect() as connection:
            revision = connection.execute(
                text(f'SELECT version_num FROM "{schema}".alembic_version')
            ).scalar_one()
            assert revision == SCHEMA_REVISION
        cli("upgrade", "head")
        cli("check")
        cli("downgrade", "base")
        assert committed_tables() == {"alembic_version"}
        cli("upgrade", "head")
        cli("check")
        assert "knowledge_chunks" in committed_tables()
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


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
            settings.sqlalchemy_url, connect_args={"options": f"-csearch_path={schema},public"}
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
                    "access_tokens",
                    "alembic_version",
                    "knowledge_collections",
                    "knowledge_grants",
                    "knowledge_objects",
                    "knowledge_documents",
                    "knowledge_versions",
                    "knowledge_chunks",
                    "knowledge_searches",
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
                    "evaluation_suites",
                    "evaluation_runs",
                    "evaluation_results",
                    "approvals",
                    "version_governance",
                    "agent_publications",
                    "audit_events",
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
