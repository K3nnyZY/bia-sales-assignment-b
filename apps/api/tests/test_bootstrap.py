"""Real database tests for explicit synthetic data loading and managed identity access."""

import hashlib
import json
import secrets
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from test_deployment import production_settings

from app.agents.models import Agent
from app.billing.models import Invoice
from app.catalogs.models import Model
from app.db.session import get_session
from app.deployment import bootstrap as module
from app.deployment.bootstrap import bootstrap, provision_identities, revoke_access, status
from app.identity.auth import hash_token
from app.identity.credentials import issue
from app.identity.models import AccessToken, User
from app.knowledge.models import KnowledgeCollection, KnowledgeGrant, KnowledgeVersion
from app.main import create_app
from app.runtime.models import InvocationGrant

pytestmark = pytest.mark.integration


def manifest():
    result = {}
    for role in module.ROLES:
        token = "bia_" + secrets.token_urlsafe(32)
        result[role] = {
            "id": "pat-" + uuid4().hex,
            "user_id": "demo-" + role,
            "role": "viewer" if role == "customer-b" else role,
            "permissions": ["invoices:read"] if role in {"creator", "customer-b"} else [],
            "token_hash": hash_token(token),
            "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
        }
    return result


def snapshot(engine):
    """Compare all rows without printing sensitive fields or large object contents."""
    with engine.connect() as connection:
        result = {}
        for table in inspect(connection).get_table_names():
            rows = connection.scalars(
                text(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY row_to_json(t)::text')
            ).all()
            result[table] = hashlib.sha256("\n".join(rows).encode()).hexdigest()
        return result


@pytest.fixture
def provisioned(db_engine):
    data = manifest()
    with Session(db_engine) as session:
        provision_identities(session, production_settings(), data)
        session.commit()
    return data


def load(engine):
    with Session(engine) as session:
        result = bootstrap(session, production_settings())
        session.commit()
        return result


def test_data_loading_does_not_change_identities_or_create_access(db_engine, provisioned):
    before = snapshot(db_engine)
    assert load(db_engine)["already_initialized"] is False
    after = snapshot(db_engine)
    assert after["users"] == before["users"]
    assert after["access_tokens"] == before["access_tokens"]
    assert after["knowledge_grants"] == before["knowledge_grants"]
    assert after["agent_invocations"] == before["agent_invocations"]
    assert after["evaluation_runs"] == before["evaluation_runs"]
    with Session(db_engine) as session:
        report = status(session)
        assert report["synthetic_invoices"] == 8
        assert report["billing_versions"] == report["evaluation_suites"] == 1
        assert report["evaluation_runs"] == 0  # Never invent successful evaluations.
        assert report["embedding_dimensions"] == 256 and report["knowledge_vectors"] == 2
        assert len(report["documents"]) == 2
        assert all(
            doc["status"] == "ready" and doc["approval"] == "approved"
            for doc in report["documents"]
        )
        assert list(session.scalars(select(KnowledgeGrant))) == []
        assert list(session.scalars(select(InvocationGrant))) == []
        assert (
            session.scalar(select(AccessToken).where(AccessToken.user_id.like("evaluation-%")))
            is None
        )
        for uid in module.EVAL_PRINCIPALS:
            with pytest.raises(ValueError):
                issue(session, uid)
    assert load(db_engine)["already_initialized"] is True
    assert snapshot(db_engine) == after


def test_replay_preserves_changed_data_disabled_accounts_and_revocations(db_engine, provisioned):
    load(db_engine)
    with Session(db_engine) as session:
        user = session.get(User, "demo-creator")
        user.permissions, user.active = [], False
        session.get(AccessToken, provisioned["creator"]["id"]).revoked = True
        session.get(Agent, "billing-assistant").description = "Operator edited this record"
        session.get(Agent, "billing-assistant").status = "disabled"
        session.get(KnowledgeCollection, "billing-reference").enabled = False
        session.get(KnowledgeVersion, ("billing-faq-rag", 1)).approval = "revoked"
        session.add(
            KnowledgeGrant(collection_id="billing-reference", user_id=user.id, enabled=False)
        )
        session.add(
            InvocationGrant(
                agent_id="billing-assistant", version_number=1, user_id=user.id, enabled=False
            )
        )
        session.commit()
    before = snapshot(db_engine)
    load(db_engine)
    with Session(db_engine) as session:
        provision_identities(session, production_settings(), provisioned)
        session.commit()
    assert snapshot(db_engine) == before


def test_bootstrap_does_not_regrant_missing_business_permission(db_engine, provisioned):
    with Session(db_engine) as session:
        session.get(User, "demo-creator").permissions = []
        session.commit()
    before = snapshot(db_engine)
    with Session(db_engine) as session, pytest.raises(ValueError, match="invoices:read"):
        bootstrap(session, production_settings())
    assert snapshot(db_engine) == before


def test_ingestion_failure_rolls_back_dataset_including_inner_commits(
    db_engine, provisioned, monkeypatch
):
    from app.knowledge import service

    real_embed = service.embed
    calls = 0

    def fail_second_embedding(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic failure")
        return real_embed(*args, **kwargs)

    monkeypatch.setattr(service, "embed", fail_second_embedding)
    before = snapshot(db_engine)
    with Session(db_engine) as session, pytest.raises(ValueError, match="unavailable"):
        bootstrap(session, production_settings())
    assert calls == 2
    assert snapshot(db_engine) == before
    monkeypatch.setattr(service, "embed", real_embed)
    assert load(db_engine)["already_initialized"] is False


@pytest.mark.parametrize("resource", ["agent", "invoice", "collection"])
def test_reserved_collision_never_overwrites_existing_resources(db_engine, provisioned, resource):
    with Session(db_engine) as session:
        if resource == "agent":
            session.add(
                Agent(
                    id="billing-assistant",
                    name="Existing",
                    description="Keep",
                    department="billing",
                    owner_id="demo-creator",
                )
            )
        elif resource == "collection":
            session.add(
                KnowledgeCollection(
                    id="billing-reference", name="Existing", owner_id="demo-creator"
                )
            )
        else:
            session.add(
                Invoice(
                    id="INV-1002",
                    owner_id="demo-customer-b",
                    period=datetime(2026, 9, 1).date(),
                    consumption_kwh=1,
                    unit_rate_cop=820,
                    charge_cop=820,
                )
            )
        session.commit()
    before = snapshot(db_engine)
    with Session(db_engine) as session, pytest.raises(ValueError, match="already exist"):
        bootstrap(session, production_settings())
    assert snapshot(db_engine) == before


def test_unrelated_existing_catalog_and_principal_are_preserved(db_engine, provisioned):
    from app.seed import seed_catalogs

    with Session(db_engine) as session:
        seed_catalogs(session)
        session.get(Model, "synthetic-advanced-v1").status = "approved"
        session.add(
            User(
                id="existing-staff",
                name="Keep existing",
                role="viewer",
                permissions=[],
                token_hash=hash_token(secrets.token_urlsafe(32)),
                active=True,
            )
        )
        session.commit()
    before = snapshot(db_engine)
    load(db_engine)
    after = snapshot(db_engine)
    assert before["models"] == after["models"]
    assert before["users"] == after["users"]


@pytest.mark.parametrize("violation", ["permission", "role", "existing-user", "duplicate-token"])
def test_identity_provisioning_never_elevates_existing_principals(db_engine, violation):
    data = manifest()
    if violation == "permission":
        data["creator"]["permissions"].append("invoices:write")
    elif violation == "role":
        data["customer-b"]["role"] = "administrator"
    elif violation == "duplicate-token":
        data["viewer"]["token_hash"] = data["creator"]["token_hash"]
    else:
        with Session(db_engine) as session:
            session.add(
                User(
                    id="demo-creator",
                    name="Existing staff",
                    role="viewer",
                    permissions=[],
                    token_hash=hash_token(secrets.token_urlsafe(32)),
                    active=True,
                )
            )
            session.commit()
    before = snapshot(db_engine)
    with Session(db_engine) as session, pytest.raises(ValueError):
        provision_identities(session, production_settings(), data)
    assert snapshot(db_engine) == before


def test_revoke_all_managed_access_preserves_history_and_other_users(db_engine, provisioned):
    load(db_engine)
    with Session(db_engine) as session:
        rotated = issue(session, "demo-creator")
        session.add(
            User(
                id="outside",
                name="Outside",
                role="viewer",
                permissions=[],
                token_hash=hash_token(secrets.token_urlsafe(32)),
                active=True,
            )
        )
        session.commit()
        revoke_access(session, production_settings())
        session.commit()
    before = snapshot(db_engine)
    load(db_engine)
    with Session(db_engine) as session:
        provision_identities(session, production_settings(), provisioned)
        revoke_access(session, production_settings())
        session.commit()
        assert session.get(AccessToken, rotated["id"]).revoked
        assert session.get(User, "outside").active
        assert status(session)["valid_demo_tokens"] == 0
    assert snapshot(db_engine) == before


def test_concurrent_loading_initializes_once(db_engine, provisioned):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: load(db_engine), range(2)))
    assert sorted(row["already_initialized"] for row in results) == [False, True]
    after = snapshot(db_engine)
    load(db_engine)
    assert snapshot(db_engine) == after


def test_cli_requires_explicit_confirmation_and_status_is_read_only(
    db_engine, provisioned, monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(module, "Settings", production_settings)
    monkeypatch.setattr(module, "build_engine", lambda _: db_engine)
    monkeypatch.setattr(sys, "argv", ["bootstrap", "load"])
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert caught.value.code == 2
    monkeypatch.setattr(sys, "argv", ["bootstrap", "load", "--confirm-synthetic-demo"])
    module.main()
    capsys.readouterr()
    before = snapshot(db_engine)
    monkeypatch.setattr(sys, "argv", ["bootstrap", "status"])
    module.main()
    output = capsys.readouterr().out
    assert json.loads(output)["initialized"]
    assert "token_hash" not in output and "bia_" not in output
    assert snapshot(db_engine) == before


def test_no_grant_allows_no_retrieval_even_for_owner(db_engine, provisioned):
    load(db_engine)
    with Session(db_engine) as session:
        token = issue(session, "demo-creator")["token"]
        session.commit()
    app = create_app(production_settings())

    def sessions():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/knowledge/search",
            headers={"Authorization": "Bearer " + token},
            json={
                "collection_ids": ["billing-reference"],
                "query": "tarifa",
                "as_of": "2026-09-01",
            },
        )
        assert response.status_code == 403
        assert "820 COP" not in response.text
