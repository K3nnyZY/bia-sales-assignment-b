"""AUD-01: persisted metadata history, deletion compatibility and backend isolation."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import Agent
from app.governance.audit import record
from app.governance.models import AuditEvent
from app.governance.seed import seed_governance
from tests.conftest import TOKENS

pytestmark = pytest.mark.integration
GOVERNANCE_TOKENS = {
    role: f"history-{role}-test-token-0000000000" for role in ("reviewer", "approver", "auditor")
}


def headers(role="creator"):
    return {"Authorization": "Bearer " + (TOKENS | GOVERNANCE_TOKENS)[role]}


@pytest.fixture
def history(studio, db_engine):
    with Session(db_engine) as session:
        seed_governance(session, GOVERNANCE_TOKENS)
    return studio


def create(client, aid="metadata-history-test", role="creator", owner="demo-creator"):
    response = client.post(
        "/api/v1/agents",
        headers=headers(role),
        json={
            "id": aid,
            "name": "Metadata history test",
            "department": "quality",
            "owner_id": owner,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def events(client, aid=None, role="creator"):
    response = client.get(
        "/api/v1/audit-events", headers=headers(role), params={"agent_id": aid} if aid else {}
    )
    assert response.status_code == 200, response.text
    return response.json()


def edit(client, agent, **changes):
    response = client.patch(
        "/api/v1/agents/" + agent["id"],
        headers=headers("administrator"),
        json={"expected_revision": agent["revision"], **changes},
    )
    assert response.status_code == 200, response.text
    return response.json()


def delete(client, agent):
    response = client.delete(
        "/api/v1/agents/" + agent["id"],
        headers=headers("administrator"),
        params={"expected_revision": agent["revision"]},
    )
    assert response.status_code == 204, response.text


@pytest.mark.parametrize("role", ["creator", "administrator", "reviewer", "approver", "auditor"])
def test_metadata_creation_and_edit_are_visible_to_owner_and_staff(history, role):
    # Actor and owner differ: administrator activity must still be visible to the owner.
    agent = create(history, role="administrator")
    edit(history, agent, description="Updated metadata")
    filtered = events(history, agent["id"], role)
    assert {e["action"] for e in filtered} == {"agent.created", "agent.updated"}
    assert all(e["agent_id"] == agent["id"] for e in filtered)
    assert all(e["details"]["owner_id"] == "demo-creator" for e in filtered)
    assert {e["id"] for e in filtered} <= {e["id"] for e in events(history, role=role)}


def test_metadata_does_not_expose_other_owners_or_catalog_collisions(history, db_engine):
    own = create(history)
    other = create(history, "other-history-test", "outsider", "demo-outsider")
    with Session(db_engine) as session:
        record(session, "demo-administrator", "catalog.status_changed", resource_id=own["id"])
        session.commit()
    assert {e["agent_id"] for e in events(history)} == {own["id"]}
    assert events(history, other["id"]) == []
    assert events(history, own["id"], "outsider") == []
    assert {e["agent_id"] for e in events(history, role="outsider")} == {other["id"]}
    assert events(history, role="viewer") == []
    assert {e["action"] for e in events(history, own["id"], "auditor")} == {"agent.created"}


def test_deleted_history_survives_and_reused_id_does_not_leak_to_new_owner(history, db_engine):
    agent = create(history, role="administrator")
    agent = edit(history, agent, description="Before deleting an empty agent")
    delete(history, agent)
    before = events(history, agent["id"])
    assert {e["action"] for e in before} == {"agent.created", "agent.updated", "agent.deleted"}
    with Session(db_engine) as session:
        assert session.get(Agent, agent["id"]) is None
        assert all(session.get(AuditEvent, e["id"]).agent_id is None for e in before)
    create(history, agent["id"], "outsider", "demo-outsider")
    new_owner = events(history, agent["id"], "outsider")
    assert len(new_owner) == 1 and new_owner[0]["action"] == "agent.created"
    assert not {e["id"] for e in before} & {e["id"] for e in new_owner}
    assert {e["id"] for e in events(history, agent["id"])} == {e["id"] for e in before}
    assert len(events(history, agent["id"], "auditor")) == 4


def test_legacy_records_are_resolved_without_rewriting_or_guessing_deleted_ownership(
    history, db_engine
):
    agent = create(history, role="administrator")
    with Session(db_engine) as session:
        record(session, "demo-administrator", "agent.updated", resource_id=agent["id"], revision=1)
        session.commit()
        legacy = session.scalar(select(AuditEvent).where(AuditEvent.action == "agent.updated"))
        legacy_id, original = legacy.id, (dict(legacy.details), legacy.agent_id, legacy.created_at)
    active = events(history, agent["id"])
    assert legacy_id in {e["id"] for e in active}
    assert events(history, agent["id"], "outsider") == []
    with Session(db_engine) as session:
        persisted = session.get(AuditEvent, legacy_id)
        assert (persisted.details, persisted.agent_id, persisted.created_at) == original
    delete(history, agent)
    assert legacy_id not in {e["id"] for e in events(history, agent["id"])}
    assert legacy_id in {e["id"] for e in events(history, agent["id"], "auditor")}
    create(history, agent["id"], "outsider", "demo-outsider")
    assert legacy_id not in {e["id"] for e in events(history, agent["id"], "outsider")}


def test_metadata_ownership_is_recorded_at_event_time(history):
    agent = create(history)
    edit(history, agent, owner_id="demo-outsider")
    original_owner = events(history, agent["id"])
    new_owner = events(history, agent["id"], "outsider")
    assert [e["action"] for e in original_owner] == ["agent.created"]
    assert [e["action"] for e in new_owner] == ["agent.updated"]
    assert new_owner[0]["details"]["owner_id"] == "demo-outsider"
