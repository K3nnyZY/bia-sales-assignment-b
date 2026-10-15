import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_session
from app.identity.auth import hash_token
from app.identity.models import User
from app.main import create_app
from app.seed import seed

TOKENS = {
    "administrator": "test-administrator-token-000000",
    "creator": "test-creator-token-0000000000",
    "viewer": "test-viewer-token-00000000000",
    "outsider": "test-outsider-token-000000000",
    "no-grants": "test-no-grants-token-00000000",
    "inactive": "test-inactive-token-000000000",
}


def auth(role="creator"):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None, app_env="test"))) as test_client:
        yield test_client


@pytest.fixture
def db_engine():
    if os.getenv("RUN_DB_TESTS") != "1":
        pytest.skip("Set RUN_DB_TESTS=1 for real PostgreSQL tests")
    schema = f"test_{uuid4().hex}"
    admin = create_engine(Settings().sqlalchemy_url)
    engine = create_engine(
        Settings().sqlalchemy_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        with engine.begin() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def studio(db_engine):
    with Session(db_engine) as session:
        seed(session, {key: TOKENS[key] for key in ["administrator", "creator", "viewer"]})
        for key in ["outsider", "no-grants", "inactive"]:
            session.add(
                User(
                    id=f"demo-{key}",
                    name=key,
                    role="creator",
                    permissions=["invoices:read"] if key == "outsider" else [],
                    token_hash=hash_token(TOKENS[key]),
                    active=key != "inactive",
                )
            )
        session.commit()

    def sessions():
        with Session(db_engine) as session:
            yield session

    app = create_app(Settings(_env_file=None, app_env="test", enable_demo_auth=True))
    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as test_client:
        yield test_client
