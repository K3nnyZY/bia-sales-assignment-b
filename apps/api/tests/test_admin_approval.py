"""Administrator exceptions preserve gates, hash binding and independent Approvers."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_governance_api import BASE, action, clone, evaluate, get, post
from test_governance_api import governed as governed

from app.governance.models import Approval, AuditEvent
from app.identity.models import User
from tests.conftest import auth

pytestmark = pytest.mark.integration


def set_role(engine, user_id, role):
    with Session(engine) as session:
        session.get(User, user_id).role = role
        session.commit()


@pytest.mark.parametrize("relation", ["all", "author", "owner", "requester", "independent"])
def test_admin_may_approve_and_publish_any_valid_candidate(governed, db_engine, relation):
    base = BASE
    actor = "creator" if relation in {"all", "owner"} else "administrator"
    if relation in {"all", "owner"}:
        # Before evaluation: changing owner roles later would invalidate its dependency hash.
        set_role(db_engine, "demo-creator", "administrator")
    if relation in {"author", "owner"}:
        source = get(governed, BASE)
        draft = post(
            governed,
            "/agents/billing-assistant/versions",
            {"source_version": 1, "expected_source_revision": source["revision"]},
            "administrator",
            201,
        )
        base = f"/agents/billing-assistant/versions/{draft['number']}"
        post(
            governed, base + "/snapshot", {"expected_revision": draft["revision"]}, "administrator"
        )
    evaluate(governed, base)
    requester = "administrator" if relation in {"owner", "requester"} else "creator"
    pending = post(governed, base + "/submit", action(governed, base), requester, 201)
    result = post(
        governed,
        base + "/approve",
        {
            **action(governed, base),
            "decision": "approved",
            "reason": "Admin reviewed exact evidence",
        },
        actor,
    )
    assert result["status"] == "approved" and result["decided_by"] == "demo-" + actor
    assert result["config_hash"] == pending["config_hash"]
    with Session(db_engine) as session:
        event = session.scalar(select(AuditEvent).where(AuditEvent.action == "approval.approved"))
        assert event.actor_id == result["decided_by"]
        assert event.details["administrator_override"] is (relation != "independent")
        assert event.details["decision_role"] == "administrator"
        assert event.details["reason"] == result["reason"]
        assert event.details["config_hash"] == pending["config_hash"]
    state = get(governed, base + "/governance")
    published = post(
        governed,
        base + "/publish",
        {**action(governed, base), "expected_publication_revision": state["publication_revision"]},
        actor,
    )
    assert published["stage"] == "published" and published["gate"]["eligible"]
    assert (
        post(
            governed,
            base + "/approve",
            {
                **action(governed, base),
                "decision": "rejected",
                "reason": "Cannot rewrite a decision",
            },
            actor,
            409,
        )["detail"]["code"]
        == "INVALID_TRANSITION"
    )


@pytest.mark.parametrize("reason", ["", "   "])
def test_admin_cannot_decide_without_reason(governed, reason):
    evaluate(governed)
    post(governed, BASE + "/submit", action(governed), "administrator", 201)
    post(
        governed,
        BASE + "/approve",
        {**action(governed), "decision": "approved", "reason": reason},
        "administrator",
        422,
    )
    assert get(governed, BASE + "/governance")["stage"] == "pending_approval"


def test_admin_cannot_bypass_exact_hash_or_dependency_checks(governed):
    evaluate(governed)
    post(governed, BASE + "/submit", action(governed), "administrator", 201)
    result = post(
        governed,
        BASE + "/approve",
        {
            **action(governed),
            "expected_config_hash": "f" * 64,
            "decision": "approved",
            "reason": "Wrong hash",
        },
        "administrator",
        409,
    )
    assert result["detail"]["code"] == "CONFIG_HASH_MISMATCH"
    response = governed.patch(
        "/api/v1/tools/invoice-lookup-v3", headers=auth("administrator"), json={"status": "revoked"}
    )
    assert response.status_code == 200
    result = post(
        governed,
        BASE + "/approve",
        {**action(governed), "decision": "approved", "reason": "Revoked dependency"},
        "administrator",
        409,
    )
    assert result["detail"]["code"] == "PUBLICATION_GATE_BLOCKED"
    assert get(governed, BASE + "/governance")["stage"] == "pending_approval"


def test_admin_cannot_approve_or_publish_critical_failures(governed):
    config = get(governed, BASE)["configuration"]
    config["limits"]["max_tool_calls"] = 1
    base, frozen = clone(governed, config)
    outcome = post(
        governed,
        base + "/evaluations",
        {"expected_config_hash": frozen["config_hash"]},
        "administrator",
        201,
    )
    assert outcome["critical_failures"] > 0
    assert (
        post(governed, base + "/submit", action(governed, base), "administrator", 409)["detail"][
            "code"
        ]
        == "PUBLICATION_GATE_BLOCKED"
    )
    post(
        governed,
        base + "/approve",
        {**action(governed, base), "decision": "approved", "reason": "Cannot bypass failures"},
        "administrator",
        409,
    )
    post(
        governed,
        base + "/publish",
        {**action(governed, base), "expected_publication_revision": 0},
        "administrator",
        409,
    )


@pytest.mark.parametrize("role", ["creator", "reviewer", "auditor", "viewer"])
def test_forged_admin_header_cannot_approve(governed, role):
    evaluate(governed)
    post(governed, BASE + "/submit", action(governed), status=201)
    response = governed.post(
        "/api/v1" + BASE + "/approve",
        headers=auth(role) | {"X-Role": "administrator"},
        json={**action(governed), "decision": "approved", "reason": "Forged role"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["administrator", "approver", "creator"])
def test_database_allows_only_admin_self_decisions(governed, db_engine, role):
    evaluate(governed)
    pending = post(governed, BASE + "/submit", action(governed), "administrator", 201)
    set_role(db_engine, "demo-administrator", role)

    def decide():
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE approvals SET status='approved', "
                    "decided_by=requested_by,decided_at=now(),reason='SQL policy check' "
                    "WHERE id=:id"
                ),
                {"id": pending["id"]},
            )

    if role == "administrator":
        decide()
        with Session(db_engine) as session:
            assert session.get(Approval, pending["id"]).status == "approved"
    else:
        with pytest.raises(IntegrityError):
            decide()


def test_admin_decision_history_survives_migration_roundtrip(governed, db_engine):
    evaluate(governed)
    pending = post(governed, BASE + "/submit", action(governed), "administrator", 201)
    decided = post(
        governed,
        BASE + "/approve",
        {**action(governed), "decision": "approved", "reason": "Audited self-decision"},
        "administrator",
    )
    later_base, _ = clone(governed)
    evaluate(governed, later_base)
    later_pending = post(
        governed, later_base + "/submit", action(governed, later_base), "administrator", 201
    )
    events = get(governed, "/audit-events?agent_id=billing-assistant", "auditor")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007_agent_lifecycle")
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE approvals SET status='approved', "
                "decided_by=requested_by,decided_at=now(),reason='Old rule must block' WHERE id=:id"
            ),
            {"id": later_pending["id"]},
        )
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
    approvals = get(governed, "/approvals", "auditor")
    assert next(a for a in approvals if a["id"] == pending["id"]) == decided
    assert get(governed, "/audit-events?agent_id=billing-assistant", "auditor") == events


@pytest.mark.parametrize("override", ["reason='   '", "config_hash=repeat('f',64)"])
def test_database_admin_requires_reason_and_immutable_hash(governed, db_engine, override):
    evaluate(governed)
    pending = post(governed, BASE + "/submit", action(governed), "administrator", 201)
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE approvals SET status='approved',decided_by=requested_by,decided_at=now(), "
                + override
                + " WHERE id=:id"
            ),
            {"id": pending["id"]},
        )
    with Session(db_engine) as session:
        assert session.get(Approval, pending["id"]).status == "pending"
