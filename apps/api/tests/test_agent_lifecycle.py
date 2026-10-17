from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_management_api import freeze, new_agent, new_version

from app.agents.models import Agent, AgentTool, AgentVersion
from app.governance.models import AuditEvent
from tests.conftest import auth

pytestmark = pytest.mark.integration
BASE = "/api/v1/agents/test-agent"


def clone(client, source=1, revision=2):
    return client.post(
        BASE + "/versions",
        headers=auth(),
        json={
            "source_version": source,
            "expected_source_revision": revision,
        },
    )


def test_registration_creates_one_editable_draft(studio):
    response = studio.post(
        "/api/v1/agents", headers=auth(), json={"name": "Initial", "department": "Test"}
    )
    assert response.status_code == 201, response.text
    agent = response.json()
    assert agent["initial_configuration"].endswith("/versions/1")
    versions = studio.get(f"/api/v1/agents/{agent['id']}/versions", headers=auth()).json()
    assert len(versions) == 1
    assert (versions[0]["status"], versions[0]["source_version"], versions[0]["revision"]) == (
        "draft",
        None,
        1,
    )


@pytest.mark.parametrize("role", ["creator", "viewer", "reviewer", "approver", "auditor"])
def test_only_admin_may_delete_even_when_other_roles_own_agent(studio, db_engine, role):
    new_agent(studio)
    with db_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET role=:role WHERE id='demo-creator'"), {"role": role}
        )
    response = studio.delete(
        BASE + "?expected_revision=1", headers=auth() | {"X-Role": "administrator"}
    )
    assert response.status_code == 403
    assert studio.get(BASE, headers=auth()).status_code == 200


def test_admin_deletes_foreign_agent_without_snapshots_and_preserves_history(studio, db_engine):
    new_agent(studio)
    original = new_version(studio)
    response = studio.delete(BASE + "?expected_revision=1", headers=auth("administrator"))
    assert response.status_code == 204, response.text
    assert studio.get(BASE, headers=auth()).status_code == 404
    assert studio.get("/api/v1/agents", headers=auth()).json() == []
    with Session(db_engine) as session:
        agent = session.get(Agent, "test-agent")
        version = session.get(AgentVersion, (agent.id, 1))
        assert agent.deleted_at is not None and agent.status == "deprecated"
        assert version.status == "discarded" and version.discard_reason == "agent_deleted"
        assert version.configuration["objective"] == original["configuration"]["objective"]
        assert session.get(AgentTool, (agent.id, 1, "invoice-read-v1")) is not None
        events = session.scalars(select(AuditEvent)).all()
        assert {e.action for e in events} >= {
            "agent.created",
            "version.created",
            "agent.deleted",
            "version.discarded",
        }
        assert (
            next(e for e in events if e.action == "agent.deleted").actor_id == "demo-administrator"
        )
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE agents SET deleted_at=NULL,status='draft' WHERE id='test-agent'")
            )
        session.rollback()


def test_single_draft_snapshot_lineage_discard_and_monotonic_numbers(studio, db_engine):
    new_agent(studio)
    assert clone(studio, revision=1).json()["detail"]["code"] == "ACTIVE_DRAFT_EXISTS"
    assert (
        studio.delete(BASE + "/versions/1?expected_revision=1", headers=auth()).status_code == 409
    )
    snapshot = freeze(studio)
    assert (
        studio.delete(BASE + "?expected_revision=1", headers=auth("administrator")).status_code
        == 409
    )
    with Session(db_engine) as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE agents SET deleted_at=now(),status='deprecated' WHERE id='test-agent'")
            )
        session.rollback()
    assert (
        studio.post(
            BASE + "/versions", headers=auth(), json={"configuration": snapshot["configuration"]}
        ).json()["detail"]["code"]
        == "SOURCE_SNAPSHOT_REQUIRED"
    )
    draft = clone(studio).json()
    assert (draft["number"], draft["source_version"]) == (2, 1)
    assert clone(studio).status_code == 409
    assert (
        studio.delete(BASE + "/versions/2?expected_revision=2", headers=auth()).status_code == 409
    )
    assert (
        studio.delete(BASE + "/versions/2?expected_revision=1", headers=auth("viewer")).status_code
        == 403
    )
    assert (
        studio.delete(BASE + "/versions/2?expected_revision=1", headers=auth()).status_code == 204
    )
    discarded = studio.get(BASE + "/versions/2", headers=auth()).json()
    assert discarded["status"] == "discarded" and discarded["discarded_at"]
    assert (
        studio.post(
            BASE + "/versions/2/snapshot", headers=auth(), json={"expected_revision": 2}
        ).status_code
        == 409
    )
    assert studio.get(BASE + "/versions/1", headers=auth()).json() == snapshot
    assert clone(studio).json()["number"] == 3


def test_discard_does_not_require_reapproving_revoked_dependencies(studio):
    new_agent(studio)
    freeze(studio)
    assert clone(studio).status_code == 201
    assert (
        studio.patch(
            "/api/v1/models/synthetic-balanced-v1",
            headers=auth("administrator"),
            json={"status": "revoked"},
        ).status_code
        == 200
    )
    assert (
        studio.delete(BASE + "/versions/2?expected_revision=1", headers=auth()).status_code == 204
    )
    assert clone(studio).status_code == 422


def test_concurrent_clone_and_freeze_have_only_one_winner(studio):
    new_agent(studio)
    freeze(studio)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: clone(studio), range(4)))
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: studio.post(
                    BASE + "/versions/2/snapshot", headers=auth(), json={"expected_revision": 1}
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 409]


def test_legacy_multiple_drafts_are_retained_and_only_latest_stays_active(studio, db_engine):
    new_agent(studio)
    frozen = freeze(studio)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006_private_access_tokens")
        connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        for number in (2, 3):
            connection.execute(
                text("""INSERT INTO agent_versions
              (agent_id,number,source_version,status,revision,model_id,configuration,created_by)
              SELECT agent_id,:number,:source,'draft',1,model_id,configuration,created_by
              FROM agent_versions WHERE agent_id='test-agent' AND number=1"""),
                {"number": number, "source": number - 1},
            )
            connection.execute(
                text(
                    "INSERT INTO agent_tools SELECT agent_id,:number,tool_id FROM agent_tools "
                    "WHERE agent_id='test-agent' AND version_number=1"
                ),
                {"number": number},
            )
        connection.execute(text("UPDATE agents SET next_version=4 WHERE id='test-agent'"))
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
    # Populated downgrade/upgrade preserves content and frozen hashes too.
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006_private_access_tokens")
        assert (
            connection.execute(
                text("SELECT status FROM agent_versions WHERE agent_id='test-agent' AND number=2")
            ).scalar_one()
            == "draft"
        )
        command.upgrade(config, "head")
        command.check(config)
    versions = studio.get(BASE + "/versions", headers=auth()).json()
    assert [(v["number"], v["status"]) for v in versions] == [
        (3, "draft"),
        (2, "discarded"),
        (1, "snapshot"),
    ]
    assert versions[1]["discard_reason"] == "legacy_superseded_draft"
    assert versions[0]["source_version"] == 2  # Existing lineage is not rewritten.
    assert studio.get(BASE + "/versions/1", headers=auth()).json() == frozen


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO agent_versions "
        "(agent_id,number,status,revision,model_id,configuration,created_by) "
        "SELECT agent_id,2,'draft',1,model_id,configuration,created_by "
        "FROM agent_versions WHERE agent_id='test-agent' AND number=1",
        "UPDATE agent_versions SET status='discarded',revision=revision+1,discarded_at=now(),"
        "discard_reason='editor_discard' WHERE agent_id='test-agent' AND number=1",
    ],
)
def test_database_rejects_second_draft_and_discarding_initial(studio, db_engine, statement):
    new_agent(studio)
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(text(statement))
    assert studio.get(BASE + "/versions/1", headers=auth()).json()["status"] == "draft"


def test_discarded_versions_cannot_be_edited_or_used_as_new_sources(studio, db_engine):
    new_agent(studio)
    freeze(studio)
    assert clone(studio).status_code == 201
    assert (
        studio.delete(BASE + "/versions/2?expected_revision=1", headers=auth()).status_code == 204
    )
    assert clone(studio, source=2).json()["detail"]["code"] == "SOURCE_SNAPSHOT_REQUIRED"
    discarded = studio.get(BASE + "/versions/2", headers=auth()).json()
    assert (
        studio.put(
            BASE + "/versions/2",
            headers=auth(),
            json={"expected_revision": 2, "configuration": discarded["configuration"]},
        ).status_code
        == 409
    )
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE agent_versions SET revision=revision+1 "
                "WHERE agent_id='test-agent' AND number=2"
            )
        )
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM agent_versions WHERE agent_id='test-agent' AND number=2")
        )


def test_concurrent_delete_and_freeze_never_delete_frozen_snapshot(studio):
    new_agent(studio)

    def delete():
        return studio.delete(BASE + "?expected_revision=1", headers=auth("administrator"))

    def freeze_initial():
        return studio.post(
            BASE + "/versions/1/snapshot", headers=auth(), json={"expected_revision": 1}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted, frozen = pool.submit(delete), pool.submit(freeze_initial)
        outcomes = deleted.result().status_code, frozen.result().status_code
    assert outcomes in {(204, 404), (409, 200)}
    if outcomes[1] == 200:
        assert studio.get(BASE + "/versions/1", headers=auth()).json()["status"] == "snapshot"
