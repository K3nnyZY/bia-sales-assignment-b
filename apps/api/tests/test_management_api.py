from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import TOKENS, auth
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_management_unit import CONFIG

from app.agents.models import Agent, AgentTool, AgentVersion
from app.agents.service import configuration_hash
from app.catalogs.models import Model, Tool
from app.catalogs.schemas import ModelCreate
from app.identity.models import User
from app.seed import seed

pytestmark = pytest.mark.integration


def new_agent(client, agent_id="test-agent", role="creator"):
    result = client.post(
        "/api/v1/agents",
        headers=auth(role),
        json={"id": agent_id, "name": "Test Agent", "department": "Billing"},
    )
    assert result.status_code == 201, result.text
    return result.json()


def new_version(client, agent_id="test-agent", config=None):
    result = client.post(
        f"/api/v1/agents/{agent_id}/versions",
        headers=auth(),
        json={"configuration": config or CONFIG},
    )
    assert result.status_code == 201, result.text
    return result.json()


def freeze(client, number=1):
    result = client.post(
        f"/api/v1/agents/test-agent/versions/{number}/snapshot",
        headers=auth(),
        json={"expected_revision": 1},
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize("token", [None, "bogus", TOKENS["inactive"]])
def test_authentication_required(studio, token):
    headers = (
        {"Authorization": f"Bearer {token}"}
        if token
        else {"X-User-Id": "demo-administrator", "X-Role": "administrator"}
    )
    assert studio.get("/api/v1/agents", headers=headers).status_code == 401


def test_demo_disabled_is_fail_closed(studio):
    studio.app.state.settings.enable_demo_auth = False
    assert studio.get("/api/v1/agents", headers=auth()).status_code == 503
    assert studio.get("/health").status_code == 200


def test_agent_crud_and_persistence(studio, db_engine):
    agent = new_agent(studio)
    assert agent["owner_id"] == "demo-creator"
    response = studio.patch(
        "/api/v1/agents/test-agent",
        headers=auth(),
        json={
            "expected_revision": 1,
            "name": "Renamed",
            "description": "Synthetic",
            "department": "Finance",
            "owner_id": "demo-creator",
            "status": "disabled",
        },
    )
    assert response.status_code == 200
    with Session(db_engine) as session:
        saved = session.get(Agent, "test-agent")
        assert (saved.name, saved.status, saved.revision) == ("Renamed", "disabled", 2)
    assert (
        studio.get("/api/v1/agents?q=renamed&status=disabled", headers=auth("viewer")).json()[0][
            "id"
        ]
        == "test-agent"
    )
    assert (
        studio.delete("/api/v1/agents/test-agent?expected_revision=1", headers=auth()).status_code
        == 409
    )
    assert (
        studio.delete("/api/v1/agents/test-agent?expected_revision=2", headers=auth()).status_code
        == 204
    )
    assert studio.get("/api/v1/agents/test-agent", headers=auth()).status_code == 404


def test_cross_user_and_viewer_mutations_forbidden(studio):
    agent = new_agent(studio)
    payload = {
        key: agent[key] for key in ["name", "description", "department", "owner_id", "status"]
    } | {"expected_revision": 1}
    for role in ["outsider", "viewer"]:
        assert (
            studio.patch("/api/v1/agents/test-agent", headers=auth(role), json=payload).status_code
            == 403
        )
        assert (
            studio.delete(
                "/api/v1/agents/test-agent?expected_revision=1", headers=auth(role)
            ).status_code
            == 403
        )
        assert (
            studio.post(
                "/api/v1/agents/test-agent/versions",
                headers=auth(role),
                json={"configuration": CONFIG},
            ).status_code
            == 403
        )
    assert (
        studio.post(
            "/api/v1/agents",
            headers=auth("viewer"),
            json={"id": "viewer-agent", "name": "Viewer", "department": "Test"},
        ).status_code
        == 403
    )
    assert (
        studio.post(
            "/api/v1/agents",
            headers=auth(),
            json={
                "id": "stolen-agent",
                "name": "Stolen",
                "department": "Test",
                "owner_id": "demo-administrator",
            },
        ).status_code
        == 403
    )


@pytest.mark.parametrize("resource", ["models", "tools"])
def test_catalog_administration_requires_real_admin(studio, resource):
    item = "synthetic-balanced-v1" if resource == "models" else "invoice-read-v1"
    for role in ["creator", "viewer", "outsider"]:
        assert (
            studio.get(f"/api/v1/{resource}?approved_only=false", headers=auth(role)).status_code
            == 403
        )
        assert (
            studio.patch(
                f"/api/v1/{resource}/{item}",
                headers=auth(role) | {"X-Role": "administrator"},
                json={"status": "revoked"},
            ).status_code
            == 403
        )
        assert studio.delete(f"/api/v1/{resource}/{item}", headers=auth(role)).status_code == 403
    assert (
        studio.get(
            f"/api/v1/{resource}?approved_only=false", headers=auth("administrator")
        ).status_code
        == 200
    )


def test_catalog_creation_validation_uniqueness_and_deletion(studio):
    model = studio.get("/api/v1/models/synthetic-balanced-v1", headers=auth()).json()
    assert studio.post("/api/v1/models", headers=auth(), json=model).status_code == 403
    assert (
        studio.post("/api/v1/models", headers=auth("administrator"), json=model).status_code == 409
    )
    fresh = model | {"id": "new-model-v1", "model_identifier": "synthetic/new", "status": "pending"}
    assert (
        studio.post("/api/v1/models", headers=auth("administrator"), json=fresh).status_code == 201
    )
    assert (
        studio.patch(
            "/api/v1/models/new-model-v1",
            headers=auth("administrator"),
            json={"status": "approved"},
        ).status_code
        == 409
    )  # profile already approved
    assert (
        studio.delete("/api/v1/models/new-model-v1", headers=auth("administrator")).status_code
        == 204
    )
    tool = studio.get("/api/v1/tools/invoice-read-v1", headers=auth()).json() | {
        "id": "new-tool-v1",
        "name": "new_tool",
    }
    assert studio.post("/api/v1/tools", headers=auth("administrator"), json=tool).status_code == 201
    assert studio.post("/api/v1/tools", headers=auth(), json=tool).status_code == 403
    assert (
        studio.delete("/api/v1/tools/new-tool-v1", headers=auth("administrator")).status_code == 204
    )


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"model": {"model_id": "synthetic-advanced-v1"}}, 422),
        ({"model": {"model_id": "synthetic-restricted-v1"}}, 422),
        ({"model": {"model_id": "missing-model"}}, 422),
        ({"model": {"profile": "balanced", "max_output_tokens": 5000}}, 422),
        ({"required_capabilities": ["vision"]}, 422),
        ({"tool_ids": ["invoice-read-v2"]}, 422),
        ({"tool_ids": ["invoice-legacy-v1"]}, 422),
        ({"tool_ids": ["missing-tool"]}, 422),
        ({"tool_ids": ["invoice-export-v1"]}, 403),
        ({"tool_ids": ["invoice-write-v1"]}, 403),
        ({"permissions": ["invoices:export"]}, 422),
        ({"security": {"resource_scope": "all"}}, 422),
    ],
)
def test_unapproved_or_unauthorized_configuration_is_atomic(studio, db_engine, override, expected):
    new_agent(studio)
    result = studio.post(
        "/api/v1/agents/test-agent/versions",
        headers=auth(),
        json={"configuration": CONFIG | override},
    )
    assert result.status_code == expected, result.text
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(AgentVersion)) == 0
        assert session.get(Agent, "test-agent").next_version == 1


def test_draft_edit_snapshot_clone_and_persistence(studio, db_engine):
    new_agent(studio)
    version = new_version(studio)
    assert version["configuration"]["model"]["model_id"] == "synthetic-balanced-v1"
    updated_config = CONFIG | {"instructions": "Updated instructions"}
    result = studio.put(
        "/api/v1/agents/test-agent/versions/1",
        headers=auth(),
        json={"expected_revision": 1, "configuration": updated_config},
    )
    assert result.status_code == 200
    assert result.json()["revision"] == 2
    assert (
        studio.put(
            "/api/v1/agents/test-agent/versions/1",
            headers=auth(),
            json={"expected_revision": 1, "configuration": CONFIG},
        ).status_code
        == 409
    )
    result = studio.post(
        "/api/v1/agents/test-agent/versions/1/snapshot",
        headers=auth(),
        json={"expected_revision": 2},
    )
    assert result.status_code == 200, result.text
    snapshot = result.json()
    assert snapshot["config_hash"] == configuration_hash(snapshot["snapshot"])
    assert snapshot["snapshot"]["policy"]["permissions"] == ["invoices:read"]
    assert snapshot["snapshot"]["model"]["model_identifier"] == "synthetic/balanced-v1"
    assert (
        studio.put(
            "/api/v1/agents/test-agent/versions/1",
            headers=auth(),
            json={"expected_revision": 3, "configuration": CONFIG},
        ).status_code
        == 409
    )
    assert (
        studio.delete("/api/v1/agents/test-agent?expected_revision=1", headers=auth()).status_code
        == 409
    )
    clone = studio.post(
        "/api/v1/agents/test-agent/versions",
        headers=auth(),
        json={"source_version": 1, "expected_source_revision": 3},
    )
    assert clone.status_code == 201, clone.text
    assert (clone.json()["number"], clone.json()["status"], clone.json()["source_version"]) == (
        2,
        "draft",
        1,
    )
    assert studio.get("/api/v1/agents/test-agent/versions/1", headers=auth()).json() == snapshot
    with Session(db_engine) as session:
        assert (
            session.get(AgentVersion, ("test-agent", 2)).configuration["instructions"]
            == "Updated instructions"
        )
        assert session.get(AgentTool, ("test-agent", 1, "invoice-read-v1")) is not None
        assert session.get(AgentVersion, ("test-agent", 1)).config_hash == snapshot["config_hash"]


def test_revocation_blocks_edits_snapshots_and_clones(studio):
    new_agent(studio)
    new_version(studio)
    frozen = freeze(studio)
    studio.post(
        "/api/v1/agents/test-agent/versions",
        headers=auth(),
        json={"source_version": 1, "expected_source_revision": frozen["revision"]},
    )
    assert (
        studio.patch(
            "/api/v1/tools/invoice-read-v1",
            headers=auth("administrator"),
            json={"status": "revoked"},
        ).status_code
        == 200
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions/2/snapshot",
            headers=auth(),
            json={"expected_revision": 1},
        ).status_code
        == 422
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions",
            headers=auth(),
            json={"source_version": 1, "expected_source_revision": frozen["revision"]},
        ).status_code
        == 422
    )
    assert (
        studio.put(
            "/api/v1/agents/test-agent/versions/2",
            headers=auth(),
            json={"expected_revision": 1, "configuration": CONFIG},
        ).status_code
        == 422
    )
    assert studio.get("/api/v1/agents/test-agent/versions/1", headers=auth()).json() == frozen
    assert (
        studio.delete(
            "/api/v1/models/synthetic-balanced-v1", headers=auth("administrator")
        ).status_code
        == 409
    )
    assert (
        studio.delete("/api/v1/tools/invoice-read-v1", headers=auth("administrator")).status_code
        == 409
    )


def test_admin_cannot_bypass_owner_grants(studio):
    result = studio.post(
        "/api/v1/agents",
        headers=auth("administrator"),
        json={
            "id": "limited-agent",
            "name": "Limited",
            "department": "Test",
            "owner_id": "demo-no-grants",
        },
    )
    assert result.status_code == 201
    assert (
        studio.post(
            "/api/v1/agents/limited-agent/versions",
            headers=auth("administrator"),
            json={"configuration": CONFIG},
        ).status_code
        == 403
    )


@pytest.mark.parametrize("role", ["viewer", "reviewer", "approver", "auditor"])
def test_read_only_roles_are_enforced_with_persisted_identity(studio, db_engine, role):
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET role=:role WHERE id='demo-viewer'"), {"role": role}
        )
    response = studio.post(
        "/api/v1/agents",
        headers=auth("viewer"),
        json={"id": "reader-agent", "name": "Reader", "department": "Test"},
    )
    assert response.status_code == 403
    assert (
        studio.patch(
            "/api/v1/tools/invoice-read-v1", headers=auth("viewer"), json={"status": "revoked"}
        ).status_code
        == 403
    )


def test_cross_owner_draft_edit_snapshot_and_clone_are_forbidden(studio):
    new_agent(studio)
    new_version(studio)
    assert (
        studio.put(
            "/api/v1/agents/test-agent/versions/1",
            headers=auth("outsider"),
            json={"expected_revision": 1, "configuration": CONFIG},
        ).status_code
        == 403
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions/1/snapshot",
            headers=auth("outsider"),
            json={"expected_revision": 1},
        ).status_code
        == 403
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions",
            headers=auth("outsider"),
            json={"source_version": 1, "expected_source_revision": 1},
        ).status_code
        == 403
    )


def test_ownership_transfer_revalidates_grants_and_locks_after_snapshot(studio):
    agent = new_agent(studio)
    new_version(studio)
    payload = {
        key: agent[key] for key in ["name", "description", "department", "owner_id", "status"]
    } | {"expected_revision": 1}
    assert (
        studio.patch(
            "/api/v1/agents/test-agent",
            headers=auth("administrator"),
            json=payload | {"owner_id": "demo-no-grants"},
        ).status_code
        == 403
    )
    freeze(studio)
    assert (
        studio.patch(
            "/api/v1/agents/test-agent",
            headers=auth("administrator"),
            json=payload | {"owner_id": "demo-outsider"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("agent_status", ["disabled", "deprecated"])
def test_agent_states_block_configuration_changes(studio, agent_status):
    agent = new_agent(studio)
    new_version(studio)
    payload = {
        key: agent[key] for key in ["name", "description", "department", "owner_id", "status"]
    } | {"expected_revision": 1, "status": agent_status}
    assert (
        studio.patch("/api/v1/agents/test-agent", headers=auth(), json=payload).status_code == 200
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions", headers=auth(), json={"configuration": CONFIG}
        ).status_code
        == 409
    )
    assert (
        studio.put(
            "/api/v1/agents/test-agent/versions/1",
            headers=auth(),
            json={"expected_revision": 1, "configuration": CONFIG},
        ).status_code
        == 409
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions/1/snapshot",
            headers=auth(),
            json={"expected_revision": 1},
        ).status_code
        == 409
    )
    if agent_status == "deprecated":
        assert (
            studio.patch(
                "/api/v1/agents/test-agent",
                headers=auth(),
                json=payload | {"expected_revision": 2, "status": "draft"},
            ).status_code
            == 409
        )


def test_model_revocation_and_missing_tool_calling_are_rejected(studio):
    new_agent(studio)
    new_version(studio)
    assert (
        studio.patch(
            "/api/v1/models/synthetic-balanced-v1",
            headers=auth("administrator"),
            json={"status": "revoked"},
        ).status_code
        == 200
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions/1/snapshot",
            headers=auth(),
            json={"expected_revision": 1},
        ).status_code
        == 422
    )
    model = studio.get("/api/v1/models/synthetic-economy-v1", headers=auth()).json() | {
        "id": "chat-only-v1",
        "model_identifier": "synthetic/chat-only",
        "profile": "restricted",
        "capabilities": ["chat"],
    }
    assert (
        studio.post("/api/v1/models", headers=auth("administrator"), json=model).status_code == 201
    )
    assert (
        studio.post(
            "/api/v1/agents/test-agent/versions",
            headers=auth(),
            json={"configuration": CONFIG | {"model": {"model_id": "chat-only-v1"}}},
        ).status_code
        == 422
    )


def test_no_auth_secrets_in_responses(studio):
    response = studio.get("/api/v1/users", headers=auth("administrator"))
    assert response.status_code == 200
    assert "token_hash" not in response.text
    assert all(token not in response.text for token in TOKENS.values())


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE agent_versions SET config_hash = repeat('f',64) WHERE agent_id='test-agent'",
        "UPDATE agent_versions SET status='draft',snapshot=NULL,config_hash=NULL "
        "WHERE agent_id='test-agent'",
        "DELETE FROM agent_versions WHERE agent_id='test-agent'",
        "DELETE FROM agent_tools WHERE agent_id='test-agent'",
        "UPDATE agent_tools SET tool_id='invoice-export-v1' WHERE agent_id='test-agent'",
        "UPDATE agents SET owner_id='demo-outsider' WHERE id='test-agent'",
        "INSERT INTO agent_tools VALUES ('test-agent',1,'invoice-export-v1')",
    ],
)
def test_database_protects_immutable_snapshots(studio, db_engine, statement):
    new_agent(studio)
    new_version(studio)
    frozen = freeze(studio)
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(text(statement))
    assert studio.get("/api/v1/agents/test-agent/versions/1", headers=auth()).json() == frozen


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE agents SET status='published' WHERE id='test-agent'",
        "UPDATE agents SET owner_id='missing-owner' WHERE id='test-agent'",
        "UPDATE models SET max_output_tokens=-1 WHERE id='synthetic-balanced-v1'",
        "UPDATE tools SET input_schema='[]'::jsonb WHERE id='invoice-read-v1'",
        "UPDATE users SET role='god' WHERE id='demo-creator'",
        "UPDATE agent_versions SET model_id='synthetic-advanced-v1' WHERE agent_id='test-agent'",
        "DELETE FROM agent_tools WHERE agent_id='test-agent'",
    ],
)
def test_database_constraints_and_relation_consistency(studio, db_engine, statement):
    new_agent(studio)
    new_version(studio)
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(text(statement))


def test_concurrent_versions_have_unique_monotonic_numbers(studio):
    new_agent(studio)

    def add(_):
        return new_version(studio)["number"]

    with ThreadPoolExecutor(max_workers=4) as workers:
        numbers = list(workers.map(add, range(4)))
    assert sorted(numbers) == [1, 2, 3, 4]


def test_seed_is_idempotent_and_preserves_catalog_changes(studio, db_engine):
    studio.patch(
        "/api/v1/models/synthetic-balanced-v1",
        headers=auth("administrator"),
        json={"status": "revoked"},
    )
    with Session(db_engine) as session:
        seed(session, {key: TOKENS[key] for key in ["administrator", "creator", "viewer"]})
        assert session.get(Model, "synthetic-balanced-v1").status == "revoked"
        assert session.scalar(select(func.count()).select_from(Tool)) == 5
        assert session.scalar(select(func.count()).select_from(User)) == 6
        data = ModelCreate.model_validate(session.get(Model, "synthetic-economy-v1")).model_dump()
        session.add(
            Model(**(data | {"id": "duplicate-profile", "model_identifier": "synthetic/duplicate"}))
        )
        with pytest.raises(IntegrityError):
            session.commit()
