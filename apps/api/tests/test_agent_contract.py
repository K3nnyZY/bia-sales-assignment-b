import pytest
from conftest import auth
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentVersion

pytestmark = pytest.mark.integration

CREATE = {
    "name": "Billing Assistant",
    "description": "Explica facturas a clientes",
    "department": "customer_service",
    "owner": "demo-creator",
    "model_profile": "balanced",
    "tools": ["get_customer_invoice"],
}


def test_generated_id_and_initial_configuration_contract(studio, db_engine):
    response = studio.post("/api/v1/agents", headers=auth(), json=CREATE)
    assert response.status_code == 201, response.text
    agent = response.json()
    assert agent["id"].startswith("agent-")
    assert agent["state"] == "DRAFT"
    assert agent["status"] == "draft"
    assert agent["owner_id"] == "demo-creator"
    assert response.headers["location"] == f"/api/v1/agents/{agent['id']}"
    reference = agent["initial_configuration"]
    assert reference == f"/api/v1/agents/{agent['id']}/versions/1"
    version = studio.get(reference, headers=auth()).json()
    assert version["status"] == "draft"
    assert version["configuration"]["model"]["model_id"] == "synthetic-balanced-v1"
    assert version["configuration"]["tool_ids"] == ["invoice-read-v1"]
    assert version["configuration"]["objective"] == CREATE["description"]
    assert studio.get(f"/api/v1/agents/{agent['id']}", headers=auth()).json() == agent
    assert any(
        row["id"] == agent["id"] for row in studio.get("/api/v1/agents", headers=auth()).json()
    )
    versions_url = f"/api/v1/agents/{agent['id']}/versions"
    assert len(studio.get(versions_url, headers=auth()).json()) == 1
    candidate = studio.post(
        versions_url, headers=auth(), json={"source_version": 1, "expected_source_revision": 1}
    )
    assert candidate.status_code == 201
    assert candidate.json()["number"] == 2
    for catalog in ["models", "tools"]:
        assert studio.get(f"/api/v1/{catalog}", headers=auth()).status_code == 200
    with Session(db_engine) as session:
        assert session.get(AgentVersion, (agent["id"], 1)) is not None
        assert session.get(Agent, agent["id"]).next_version == 3


def test_generated_ids_are_unique_and_registration_remains_compatible(studio):
    agents = [
        studio.post(
            "/api/v1/agents", headers=auth(), json={"name": "Same name", "department": "Test"}
        ).json()
        for _ in range(2)
    ]
    assert agents[0]["id"] != agents[1]["id"]
    assert all(
        agent["state"] == "DRAFT" and agent["initial_configuration"] is None for agent in agents
    )
    response = studio.post(
        "/api/v1/agents",
        headers=auth(),
        json={"id": "custom-slug", "name": "Custom", "department": "Test"},
    )
    assert response.status_code == 201
    assert response.json()["id"] == "custom-slug"


@pytest.mark.parametrize(
    ("override", "status"),
    [
        ({"model_profile": "advanced"}, 422),
        ({"model_profile": "restricted"}, 422),
        ({"tools": ["search_billing_knowledge"]}, 422),
        ({"tools": ["invoice-read-v2"]}, 422),
        ({"tools": ["invoice-legacy-v1"]}, 422),
        ({"tools": ["export_invoice"]}, 403),
        ({"tools": ["write_invoice"]}, 403),
        ({"owner": "demo-administrator"}, 403),
        ({"tools": ["invoice-read-v1", "get_customer_invoice"]}, 422),
    ],
)
def test_initial_configuration_failure_rolls_back_agent(studio, db_engine, override, status):
    response = studio.post("/api/v1/agents", headers=auth(), json=CREATE | override)
    assert response.status_code == status, response.text
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Agent)) == 0
        assert session.scalar(select(func.count()).select_from(AgentVersion)) == 0


def test_ambiguous_tool_name_requires_exact_catalog_id(studio):
    headers = auth("administrator")
    response = studio.patch(
        "/api/v1/tools/invoice-read-v2", headers=headers, json={"status": "approved"}
    )
    assert response.status_code == 200
    response = studio.post("/api/v1/agents", headers=auth(), json=CREATE)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "AMBIGUOUS_TOOL"
    response = studio.post(
        "/api/v1/agents", headers=auth(), json=CREATE | {"tools": ["invoice-read-v2"]}
    )
    assert response.status_code == 201


def test_owner_alias_is_validated_and_admin_uses_owner_grants(studio):
    response = studio.post(
        "/api/v1/agents", headers=auth("administrator"), json=CREATE | {"owner": "billing-team"}
    )
    assert response.status_code == 422
    response = studio.post(
        "/api/v1/agents", headers=auth("administrator"), json=CREATE | {"owner": "demo-no-grants"}
    )
    assert response.status_code == 403
    response = studio.post("/api/v1/agents", headers=auth("administrator"), json=CREATE)
    assert response.status_code == 201
    assert response.json()["owner_id"] == "demo-creator"


def test_partial_patch_preserves_omitted_metadata_and_revision_guard(studio):
    response = studio.post("/api/v1/agents", headers=auth(), json=CREATE)
    agent = response.json()
    path = f"/api/v1/agents/{agent['id']}"
    response = studio.patch(
        path, headers=auth(), json={"expected_revision": 1, "description": "Updated description"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == agent | {"revision": 2, "description": "Updated description"}
    assert (
        studio.patch(
            path, headers=auth(), json={"expected_revision": 1, "name": "Stale"}
        ).status_code
        == 409
    )
    assert (
        studio.patch(
            path, headers=auth(), json={"expected_revision": 2, "permissions": ["admin:all"]}
        ).status_code
        == 422
    )
    assert (
        studio.patch(path, headers=auth(), json={"expected_revision": 2, "name": None}).status_code
        == 422
    )
    assert studio.patch(path, headers=auth(), json={"expected_revision": 2}).status_code == 422
