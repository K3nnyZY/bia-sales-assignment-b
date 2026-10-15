from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.api.health import SCHEMA_REVISION
from app.db.session import get_session


def test_liveness_without_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "bia-api"}


@pytest.mark.parametrize(
    ("heads", "status_code", "migration_status"),
    [((SCHEMA_REVISION,), 200, "ok"), ((), 503, "pending"), (("outdated",), 503, "pending")],
)
def test_readiness_checks_revision(client, monkeypatch, heads, status_code, migration_status):
    session = MagicMock()
    client.app.dependency_overrides[get_session] = lambda: session
    migration_context = MagicMock()
    migration_context.get_current_heads.return_value = heads
    monkeypatch.setattr("app.api.health.MigrationContext.configure", lambda _: migration_context)
    response = client.get("/health/ready")
    assert response.status_code == status_code
    assert response.json()["database"] == "ok"
    assert response.json()["migrations"] == migration_status


def test_readiness_database_failure_is_safe(client):
    session = MagicMock()
    session.execute.side_effect = OperationalError("private-connection-secret", {}, Exception())
    client.app.dependency_overrides[get_session] = lambda: session
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "service": "bia-api",
        "database": "error",
        "migrations": "unknown",
    }
    assert "private-connection-secret" not in response.text


def test_cors_allowed_origin(client):
    response = client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin(client):
    response = client.options(
        "/health",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
