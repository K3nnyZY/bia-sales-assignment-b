"""Production identity and published execution use real authorization and PostgreSQL."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_session
from app.deployment.bootstrap import ROLES, bootstrap
from app.identity.credentials import issue, private_json
from app.identity.models import AccessToken, User
from app.main import create_app


def production_settings(**overrides):
    return Settings(
        _env_file=None,
        app_env="production",
        cors_origins=[],
        enable_access_token_auth=True,
        enable_published_runtime=True,
        **overrides,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"enable_demo_auth": True},
        {"enable_local_runtime": True},
    ],
)
def test_production_rejects_development_bypasses(changes):
    with pytest.raises(ValidationError):
        production_settings(**changes)


def test_published_runtime_requires_private_auth():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, enable_published_runtime=True)


def test_private_file_is_exclusive_and_restricted(tmp_path):
    target = tmp_path / "credential.json"
    private_json(target, {"token": "private"})
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        private_json(target, {})


@pytest.mark.integration
def test_secure_deployment_full_flow(db_engine):
    manifest, tokens = {}, {}
    for role in ROLES:
        token = "bia_" + secrets.token_urlsafe(32)
        tokens[role] = token
        manifest[role] = {
            "id": "pat-" + uuid4().hex,
            "user_id": "demo-" + role,
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
        }
    settings = production_settings()
    with Session(db_engine) as session:
        bootstrap(session, settings, manifest)
        bootstrap(session, settings, manifest)
        assert session.scalar(select(func.count()).select_from(AccessToken)) == len(ROLES)
        assert not any(
            user.token_hash == manifest["creator"]["token_hash"]
            for user in session.scalars(select(User))
        )

    def sessions():
        with Session(db_engine) as session:
            yield session

    app = create_app(settings)
    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:

        def request(method, path, role="creator", status=200, **kwargs):
            response = client.request(
                method,
                "/api/v1" + path,
                headers={"Authorization": "Bearer " + tokens[role]},
                **kwargs,
            )
            assert response.status_code == status, response.text
            return response.json()

        assert client.get("/api/v1/me").status_code == 401
        assert (
            client.get(
                "/api/v1/me", headers={"Authorization": "Bearer demo-creator-local-token-change-me"}
            ).status_code
            == 401
        )
        assert request("GET", "/me")["id"] == "demo-creator"
        assert request("GET", "/runtime/agents") == []
        base = "/agents/billing-assistant/versions/2"
        digest = request("GET", base)["config_hash"]
        run_input = {
            "agent_id": "billing-assistant",
            "version": 2,
            "message": "Compara mi factura",
            "invoice_id": "INV-1002",
            "task": "compare",
        }
        request("POST", "/runs", json=run_input, status=503)  # Preview remains closed.
        request("POST", "/runs", json={**run_input, "channel": "published"}, status=409)
        evaluated = request(
            "POST", base + "/evaluations", json={"expected_config_hash": digest}, status=201
        )
        assert evaluated["status"] == "passed" and evaluated["passed_count"] == 9

        def action():
            state = request("GET", base + "/governance")
            return {
                "expected_revision": state["revision"],
                "expected_config_hash": state["config_hash"],
            }

        request("POST", base + "/submit", json=action(), status=201)
        decision = {**action(), "decision": "approved", "reason": "Independent review"}
        request("POST", base + "/approve", json=decision, status=403)
        request("POST", base + "/approve", "approver", json=decision)
        state = request("GET", base + "/governance")
        request(
            "POST",
            base + "/publish",
            "approver",
            json={**action(), "expected_publication_revision": state["publication_revision"]},
        )
        options = request("GET", "/runtime/agents")
        assert len(options) == 1 and options[0]["published"] and not options[0]["local_preview"]
        run_input["channel"] = "published"
        run = request("POST", "/runs", json=run_input, status=201)
        assert run["status"] == "completed", run
        assert run["calculations"]["difference_cop"] == "64400.00"
        assert run["calculations"]["percentage_change"] == "23.00"
        assert any("#chunk-" in reference for reference in run["references"])
        assert run["input_tokens"] is None and run["estimated_cost_usd"] is None
        trace = request("GET", "/runs/" + run["id"] + "/trace")
        assert len(trace["events"]) == 9 and len(trace["knowledge_searches"]) == 1
        denied = request("POST", "/runs", "customer-b", json=run_input, status=201)
        assert denied["status"] == "denied" and not denied["references"]
        assert request("GET", "/runs/" + run["id"], "customer-b", status=404)
        request("PATCH", "/models/synthetic-balanced-v1", json={"status": "approved"}, status=403)
        with Session(db_engine) as session:
            item = session.get(AccessToken, manifest["creator"]["id"])
            item.revoked = True
            session.commit()
            bootstrap(session, settings, manifest)
            assert session.get(AccessToken, item.id).revoked
        request("GET", "/me", status=401)
        with Session(db_engine) as session:
            replacement = issue(session, "demo-creator", hours=1)
            session.commit()
            tokens["creator"] = replacement["token"]
            session.get(AccessToken, replacement["id"]).expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )
            # Keep the SQL expiry constraint valid while testing an already expired credential.
            session.get(AccessToken, replacement["id"]).created_at = datetime.now(UTC) - timedelta(
                hours=1
            )
            session.commit()
        request("GET", "/me", status=401)
