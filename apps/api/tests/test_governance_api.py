import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.governance.seed import seed_governance
from app.runtime.seed import seed_runtime
from tests.conftest import TOKENS, auth

pytestmark = pytest.mark.integration
ROLE_TOKENS = {
    role: f"test-{role}-governance-token-00000000" for role in ["reviewer", "approver", "auditor"]
}
TOKENS.update(ROLE_TOKENS)


@pytest.fixture
def governed(studio, db_engine):
    studio.app.state.settings.enable_local_runtime = True
    with Session(db_engine) as session:
        seed_runtime(session, "test-customer-b-token-00000000")
        seed_governance(session, ROLE_TOKENS)
    return studio


def get(client, path, role="creator"):
    r = client.get("/api/v1" + path, headers=auth(role))
    assert r.status_code == 200, r.text
    return r.json()


BASE = "/agents/billing-assistant/versions/1"


def action(client, base=BASE):
    state = get(client, base + "/governance")
    return {"expected_revision": state["revision"], "expected_config_hash": state["config_hash"]}


def post(client, path, data, role="creator", status=200):
    r = client.post("/api/v1" + path, headers=auth(role), json=data)
    assert r.status_code == status, r.text
    return r.json() if r.content else None


def evaluate(client, base=BASE):
    h = get(client, base)["config_hash"]
    result = post(client, base + "/evaluations", {"expected_config_hash": h}, status=201)
    details = get(client, "/evaluations/" + result["id"])
    assert result["status"] == "passed", details
    assert result["passed_count"] == result["total"] == 9, details
    return details


def publish(client, base=BASE):
    evaluate(client, base)
    post(client, base + "/submit", action(client, base), status=201)
    post(
        client,
        base + "/approve",
        {**action(client, base), "decision": "approved", "reason": "Reviewed synthetic checks"},
        "approver",
    )
    state = get(client, base + "/governance")
    return post(
        client,
        base + "/publish",
        {**action(client, base), "expected_publication_revision": state["publication_revision"]},
        "approver",
    )


def test_full_publication_runtime_audit(governed, db_engine):
    client = governed
    state = publish(client)
    assert state["stage"] == "published" and state["gate"]["eligible"]
    run = post(
        client,
        "/runs",
        {
            "agent_id": "billing-assistant",
            "channel": "published",
            "message": "Compara mi factura",
            "invoice_id": "INV-1002",
            "task": "compare",
        },
        status=201,
    )
    assert run["status"] == "completed", run
    assert run["calculations"]["difference_cop"] == "64400.00"
    assert run["channel"] == "published" and run["evaluation_id"] is None
    assert get(client, "/runs/" + run["id"] + "/trace", "auditor")["tool_calls"]
    # Logical Agent.status remains draft after publication: it is not sufficient
    # to decide deletion. All version/run/approval history must remain intact.
    agent_before = get(client, "/agents/billing-assistant")
    assert agent_before["status"] == "draft"
    denied_delete = client.delete(
        "/api/v1/agents/billing-assistant",
        headers=auth("administrator"),
        params={"expected_revision": agent_before["revision"]},
    )
    assert denied_delete.status_code == 409
    assert denied_delete.json()["detail"]["code"] == "HISTORY_EXISTS"
    assert get(client, "/agents/billing-assistant") == agent_before
    assert get(client, BASE + "/governance")["stage"] == "published"
    assert get(client, "/runs/" + run["id"] + "/trace", "auditor")["run"]["id"] == run["id"]
    assert client.get("/api/v1/runs/" + run["id"], headers=auth("administrator")).status_code == 404
    metrics = get(client, "/metrics")
    assert metrics["runs"] == 1 and metrics["models"][0]["input_tokens"] is None
    assert metrics["models"][0]["estimated_cost_usd"] is None
    events = get(client, "/audit-events")
    assert {e["action"] for e in events} >= {
        "evaluation.completed",
        "approval.approved",
        "version.published",
    }
    with Session(db_engine) as session:
        from app.runtime.models import AgentRun

        assert (
            session.scalar(select(AgentRun).where(AgentRun.id == run["id"])).channel == "published"
        )


def clone(client, config=None):
    source = get(client, BASE)
    data = {"source_version": 1, "expected_source_revision": source["revision"]}
    if config:
        data["configuration"] = config
    version = post(client, "/agents/billing-assistant/versions", data, status=201)
    base = f"/agents/billing-assistant/versions/{version['number']}"
    frozen = post(client, base + "/snapshot", {"expected_revision": version["revision"]})
    return base, frozen


@pytest.mark.parametrize("role", ["creator", "viewer", "reviewer", "auditor"])
def test_unauthorized_governance_writes(governed, role):
    for operation, extra in [
        ("approve", {"decision": "approved", "reason": "attack"}),
        ("publish", {"expected_publication_revision": 0}),
        ("disable", {}),
    ]:
        post(governed, BASE + "/" + operation, {**action(governed), **extra}, role, 403)
    post(
        governed,
        BASE + "/invocations",
        {"user_id": "demo-viewer", "enabled": True, "reason": "attack"},
        role,
        403,
    )
    assert not get(governed, BASE + "/governance")["publication_enabled"]


def test_exact_hash_stale_revision_and_transitions(governed):
    post(governed, BASE + "/evaluations", {"expected_config_hash": "0" * 64}, status=409)
    post(
        governed,
        BASE + "/publish",
        {**action(governed), "expected_publication_revision": 0},
        "approver",
        409,
    )
    post(governed, BASE + "/submit", action(governed), status=409)
    evaluate(governed)
    post(governed, BASE + "/submit", {**action(governed), "expected_revision": 999}, status=409)
    post(governed, BASE + "/submit", action(governed), status=201)
    stale = action(governed)
    post(governed, BASE + "/approve", {**stale, "decision": "approved", "reason": "ok"}, "approver")
    post(
        governed,
        BASE + "/approve",
        {**stale, "decision": "approved", "reason": "again"},
        "approver",
        409,
    )
    post(
        governed,
        BASE + "/publish",
        {**action(governed), "expected_publication_revision": 9},
        "approver",
        409,
    )


def test_self_approval_blocked_even_for_administrator(governed, db_engine):
    from app.identity.models import User

    # Evaluate and request as owner, then elevate that same trusted principal in DB.
    evaluate(governed)
    post(governed, BASE + "/submit", action(governed), status=201)
    with Session(db_engine) as session:
        session.get(User, "demo-creator").role = "administrator"
        session.commit()
    result = post(
        governed,
        BASE + "/approve",
        {**action(governed), "decision": "approved", "reason": "self"},
        status=403,
    )
    assert result["detail"]["code"] == "SELF_APPROVAL_FORBIDDEN"


def test_critical_failure_blocks_submission_and_publication(governed):
    config = get(governed, BASE)["configuration"]
    config["limits"]["max_tool_calls"] = 1
    base, frozen = clone(governed, config)
    result = post(
        governed, base + "/evaluations", {"expected_config_hash": frozen["config_hash"]}, status=201
    )
    assert result["status"] == "failed" and result["critical_failures"] > 0
    detail = get(governed, "/evaluations/" + result["id"])
    assert any(not r["passed"] and r["critical"] for r in detail["results"])
    post(governed, base + "/submit", action(governed, base), status=409)
    post(
        governed,
        base + "/publish",
        {**action(governed, base), "expected_publication_revision": 0},
        "approver",
        409,
    )


def test_suite_omitting_security_cannot_bypass_gate(governed):
    suite = {"id": "weak-suite", "version": 1, "name": "Weak suite", "checks": ["configuration"]}
    post(governed, "/evaluation-suites", suite, status=403)
    post(governed, "/evaluation-suites", suite, "reviewer", 201)
    result = post(
        governed,
        BASE + "/evaluations",
        {
            "expected_config_hash": action(governed)["expected_config_hash"],
            "suite_id": "weak-suite",
        },
        status=201,
    )
    assert result["status"] == "passed"
    state = get(governed, BASE + "/governance")
    assert "MANDATORY_CHECKS_MISSING" in state["gate"]["reasons"]
    post(governed, BASE + "/submit", action(governed), status=409)


def test_reevaluation_revokes_approval_and_latest_failed_result_wins(governed, db_engine):
    from app.billing.models import Invoice

    evaluate(governed)
    post(governed, BASE + "/submit", action(governed), status=201)
    post(
        governed,
        BASE + "/approve",
        {**action(governed), "decision": "approved", "reason": "ok"},
        "approver",
    )
    with Session(db_engine) as session:
        session.get(Invoice, "INV-9002").unit_rate_cop = 821
        session.get(Invoice, "INV-9002").charge_cop = 344820
        session.commit()
    result = post(
        governed,
        BASE + "/evaluations",
        {"expected_config_hash": action(governed)["expected_config_hash"]},
        status=201,
    )
    assert result["status"] == "failed" and result["critical_failures"] > 0
    state = get(governed, BASE + "/governance")
    assert state["approval_id"] is None and state["stage"] == "testing"
    assert "EVALUATION_NOT_PASSED" in state["gate"]["reasons"]


def test_dependency_revocation_blocks_publish_and_runtime(governed):
    publish(governed)
    r = governed.patch(
        "/api/v1/tools/invoice-lookup-v3",
        headers=auth("administrator"),
        json={"status": "revoked"},
    )
    assert r.status_code == 200, r.text
    state = get(governed, BASE + "/governance")
    assert not state["gate"]["eligible"]
    post(
        governed,
        "/runs",
        {"channel": "published", "invoice_id": "INV-1002", "message": "Factura"},
        status=409,
    )


def test_rollback_disable_and_no_unevaluated_or_never_published_target(governed):
    first = publish(governed)
    base, frozen = clone(governed)
    second = publish(governed, base)
    assert second["publication_version"] == frozen["number"]
    assert get(governed, BASE + "/governance")["stage"] == "deprecated"
    post(
        governed,
        "/runs",
        {"version": 1, "channel": "published", "invoice_id": "INV-1002", "message": "Factura"},
        status=409,
    )
    restored = post(
        governed,
        "/agents/billing-assistant/rollback",
        {
            "target_version": 1,
            "expected_publication_revision": second["publication_revision"],
            "reason": "Restore approved release",
        },
        "approver",
    )
    assert (
        restored["stage"] == "published"
        and restored["publication_revision"] > first["publication_revision"]
    )
    post(governed, BASE + "/disable", action(governed), "approver")
    post(governed, "/runs", {"channel": "published", "message": "Factura"}, status=409)
    third_base, third = clone(governed)
    evaluate(governed, third_base)
    state = get(governed, third_base + "/governance")
    post(
        governed,
        "/agents/billing-assistant/rollback",
        {
            "target_version": third["number"],
            "expected_publication_revision": state["publication_revision"],
            "reason": "bypass",
        },
        "approver",
        409,
    )
    assert any(e["action"] == "publication.rollback" for e in get(governed, "/audit-events"))


@pytest.mark.parametrize(
    "target",
    ["snapshot", "suite", "evaluation", "result", "approval", "audit", "publication", "governance"],
)
def test_database_history_and_gate_constraints(governed, db_engine, target):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    publish(governed)
    statements = {
        "snapshot": (
            "UPDATE agent_versions SET configuration='{}' "
            "WHERE agent_id='billing-assistant' AND number=1"
        ),
        "suite": "DELETE FROM evaluation_suites",
        "evaluation": "UPDATE evaluation_runs SET config_hash=repeat('0',64)",
        "result": "UPDATE evaluation_results SET passed=false",
        "approval": "UPDATE approvals SET status='rejected'",
        "audit": "DELETE FROM audit_events",
        "publication": "DELETE FROM agent_publications",
        "governance": "UPDATE version_governance SET stage='approved',revision=revision+1",
    }
    with db_engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(text(statements[target]))


def test_fake_evaluation_channel_and_cross_user_visibility(governed):
    detail = evaluate(governed)
    rid = next(r["run_id"] for r in detail["results"] if r["run_id"])
    for role in ["viewer", "outsider"]:
        assert (
            governed.get(
                "/api/v1/evaluations/" + detail["evaluation"]["id"], headers=auth(role)
            ).status_code
            == 404
        )
        assert governed.get("/api/v1/runs/" + rid + "/trace", headers=auth(role)).status_code == 404
        assert get(governed, "/evaluations", role) == []
    assert get(governed, "/runs/" + rid + "/trace", "reviewer")["run"]["channel"] == "evaluation"
    post(
        governed,
        "/runs",
        {"channel": "evaluation", "evaluation_id": detail["evaluation"]["id"], "message": "bypass"},
        status=422,
    )
    post(
        governed,
        BASE + "/invocations",
        {"user_id": "evaluation-customer-a", "enabled": True, "reason": "bypass"},
        "administrator",
        422,
    )
    assert get(governed, "/metrics")["runs"] == 0


def test_published_snapshot_cannot_edit_or_reevaluate(governed):
    publish(governed)
    v = get(governed, BASE)
    response = governed.put(
        "/api/v1" + BASE,
        headers=auth(),
        json={"expected_revision": v["revision"], "configuration": v["configuration"]},
    )
    assert response.status_code == 409
    post(governed, BASE + "/evaluations", {"expected_config_hash": v["config_hash"]}, status=409)
    assert get(governed, BASE)["config_hash"] == v["config_hash"]


def test_tool_failure_is_persisted_and_blocks_gate(governed, monkeypatch):
    from app.billing import tools
    from app.runtime.errors import ExecutionError

    async def unavailable(ctx, args):
        raise ExecutionError("UPSTREAM_UNAVAILABLE", "Synthetic controlled failure")

    monkeypatch.setitem(tools.IMPLEMENTATIONS, "invoice-lookup-v3", unavailable)
    result = post(
        governed,
        BASE + "/evaluations",
        {"expected_config_hash": action(governed)["expected_config_hash"]},
        status=201,
    )
    assert result["status"] == "failed" and result["critical_failures"] > 0
    details = get(governed, "/evaluations/" + result["id"])
    failed = next(r for r in details["results"] if r["check"] == "comparison")
    trace = get(governed, "/runs/" + failed["run_id"] + "/trace")
    assert trace["run"]["status"] == "failed" and trace["tool_calls"]
    assert all(c["error_code"] == "UPSTREAM_UNAVAILABLE" for c in trace["tool_calls"])
    post(governed, BASE + "/submit", action(governed), status=409)


def test_evaluation_deadline_fails_closed_with_complete_results(governed):
    governed.app.state.settings.evaluation_timeout_seconds = 0.001
    result = post(
        governed,
        BASE + "/evaluations",
        {"expected_config_hash": action(governed)["expected_config_hash"]},
        status=201,
    )
    assert result["status"] == "failed" and result["critical_failures"] > 0
    assert len(get(governed, "/evaluations/" + result["id"])["results"]) == 9
    assert not get(governed, BASE + "/governance")["gate"]["eligible"]


def test_database_rejects_direct_publication_without_approval(governed, db_engine):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    evaluate(governed)
    with db_engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "UPDATE version_governance SET stage='published',ever_published=true,"
                "revision=revision+1"
            )
        )


def test_dependency_changes_require_fresh_evaluation_before_approval(governed, db_engine):
    from app.billing.models import BillingKnowledge

    evaluate(governed)
    with Session(db_engine) as session:
        doc = session.scalars(select(BillingKnowledge)).first()
        doc.content += " Additional synthetic approved context."
        session.commit()
    assert (
        "EVALUATED_DEPENDENCIES_CHANGED" in get(governed, BASE + "/governance")["gate"]["reasons"]
    )
    post(governed, BASE + "/submit", action(governed), status=409)


def test_invocation_grants_do_not_give_invoice_permissions(governed):
    publish(governed)
    post(
        governed,
        BASE + "/invocations",
        {"user_id": "demo-no-grants", "enabled": True, "reason": "Invocation only"},
        "administrator",
        204,
    )
    run = post(
        governed,
        "/runs",
        {"channel": "published", "invoice_id": "INV-1002", "message": "Factura"},
        "no-grants",
        201,
    )
    assert run["status"] == "denied" and run["error_code"] == "TOOL_PERMISSION"
    assert run["references"] == []
    post(
        governed,
        BASE + "/invocations",
        {"user_id": "demo-creator", "enabled": False, "reason": "Revoke caller"},
        "administrator",
        204,
    )
    post(governed, "/runs", {"channel": "published", "message": "Factura"}, status=403)


def test_concurrent_publication_has_one_winner(governed):
    from concurrent.futures import ThreadPoolExecutor

    evaluate(governed)
    post(governed, BASE + "/submit", action(governed), status=201)
    post(
        governed,
        BASE + "/approve",
        {**action(governed), "decision": "approved", "reason": "Concurrency test"},
        "approver",
    )
    payload = {**action(governed), "expected_publication_revision": 0}

    def publish_once(_):
        return governed.post(
            "/api/v1" + BASE + "/publish", headers=auth("approver"), json=payload
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(publish_once, range(2))) == [200, 409]
    assert get(governed, BASE + "/governance")["publication_revision"] == 1
    assert sum(e["action"] == "version.published" for e in get(governed, "/audit-events")) == 1


def test_metrics_use_only_reported_usage_with_known_coverage(governed, db_engine, monkeypatch):
    from decimal import Decimal

    from app.runtime import gateway
    from tests.test_runtime_api import model_response, provision_provider

    number = provision_provider(governed, db_engine)

    async def sdk_double(**kwargs):
        return model_response(kwargs)

    monkeypatch.setattr(gateway, "provider_completion", sdk_double)
    response = post(
        governed,
        "/runs",
        {
            "version": number,
            "mode": "provider",
            "message": "Compara",
            "task": "compare",
            "invoice_id": "INV-1002",
        },
        status=201,
    )
    assert response["status"] == "completed"
    post(
        governed,
        "/runs",
        {"version": 1, "message": "Compara", "invoice_id": "INV-1002"},
        status=201,
    )
    metrics = get(governed, "/metrics")
    provider = next(m for m in metrics["models"] if m["mode"] == "provider")
    assert provider["input_tokens"] == 11 and provider["output_tokens"] == 7
    assert provider["cost_known_runs"] == provider["runs"] == 1
    assert Decimal(provider["estimated_cost_usd"]) == Decimal("0.000025")
    synthetic = next(m for m in metrics["models"] if m["mode"] == "deterministic")
    assert synthetic["input_tokens"] is None and synthetic["estimated_cost_usd"] is None
    assert metrics["runs"] == 2 and metrics["latency_p95_ms"] >= 0


def test_audit_cannot_publish_another_configuration_with_existing_evaluation(governed):
    evaluated = evaluate(governed)
    approval = post(governed, BASE + "/submit", action(governed), status=201)
    post(
        governed,
        BASE + "/approve",
        {**action(governed), "decision": "approved", "reason": "Exact-hash audit"},
        "approver",
    )
    original = get(governed, BASE)
    configuration = original["configuration"]
    configuration["instructions"] += " Changed after evaluating the original snapshot."
    other_base, other = clone(governed, configuration)
    assert original["config_hash"] != other["config_hash"]
    swapped = action(governed, other_base) | {"expected_config_hash": original["config_hash"]}
    denied = post(governed, other_base + "/submit", swapped, status=409)
    assert denied["detail"]["code"] == "CONFIG_HASH_MISMATCH"
    post(
        governed,
        other_base + "/publish",
        action(governed, other_base) | {"expected_publication_revision": 0},
        "approver",
        409,
    )
    post(
        governed,
        other_base + "/publish",
        action(governed, other_base)
        | {
            "expected_publication_revision": 0,
            "evaluation_id": evaluated["evaluation"]["id"],
            "approval_id": approval["id"],
        },
        "approver",
        422,
    )
    denied = post(
        governed,
        BASE + "/publish",
        action(governed)
        | {"expected_config_hash": other["config_hash"], "expected_publication_revision": 0},
        "approver",
        409,
    )
    assert denied["detail"]["code"] == "CONFIG_HASH_MISMATCH"
    mutation = governed.put(
        "/api/v1" + BASE,
        headers=auth(),
        json={"expected_revision": original["revision"], "configuration": configuration},
    )
    assert mutation.status_code == 409
    published = post(
        governed,
        BASE + "/publish",
        action(governed) | {"expected_publication_revision": 0},
        "approver",
    )
    assert published["publication_version"] == 1
    assert published["config_hash"] == evaluated["evaluation"]["config_hash"]
    assert get(governed, BASE)["snapshot"] == original["snapshot"]
    assert get(governed, other_base + "/governance")["latest_evaluation_id"] is None


def test_audit_database_rejects_cross_version_evaluation_and_approval(governed, db_engine):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    publish(governed)
    state = get(governed, BASE + "/governance")
    other_base, other = clone(governed)
    # Even an identical declarative config belongs to a different frozen version/hash.
    assert get(governed, BASE)["configuration"] == other["configuration"]
    assert state["config_hash"] != other["config_hash"]
    post(
        governed,
        other_base + "/evaluations",
        {"expected_config_hash": other["config_hash"]},
        status=201,
    )
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE version_governance SET stage='pending_approval',revision=revision+1,"
                "latest_evaluation_id=:evaluation,approval_id=:approval "
                "WHERE agent_id='billing-assistant' AND version_number=:number"
            ),
            {
                "evaluation": state["latest_evaluation_id"],
                "approval": state["approval_id"],
                "number": other["number"],
            },
        )
    assert get(governed, other_base + "/governance")["stage"] == "testing"
    assert get(governed, BASE + "/governance")["publication_version"] == 1


@pytest.mark.parametrize("role", ["creator", "viewer", "reviewer", "auditor"])
def test_audit_rollback_requires_governance_role(governed, role):
    post(
        governed,
        "/agents/billing-assistant/rollback",
        {
            "target_version": 1,
            "expected_publication_revision": 1,
            "reason": "Attempt without authorized role",
        },
        role,
        403,
    )


def test_audit_rollback_rechecks_revoked_dependencies(governed):
    publish(governed)
    other_base, _ = clone(governed)
    current = publish(governed, other_base)
    revoked = governed.patch(
        "/api/v1/tools/invoice-lookup-v3",
        headers=auth("administrator"),
        json={"status": "revoked"},
    )
    assert revoked.status_code == 200
    denied = post(
        governed,
        "/agents/billing-assistant/rollback",
        {
            "target_version": 1,
            "expected_publication_revision": current["publication_revision"],
            "reason": "Previously approved cannot bypass revocation",
        },
        "approver",
        409,
    )
    assert denied["detail"]["code"] == "PUBLICATION_GATE_BLOCKED"
    unchanged = get(governed, other_base + "/governance")
    assert unchanged["publication_version"] == current["publication_version"]
    assert unchanged["publication_revision"] == current["publication_revision"]


def test_checklist_create_and_execute_versioned_billing_suite(governed):
    from app.governance.schemas import REQUIRED_CHECKS

    suite = post(
        governed,
        "/evaluation-suites",
        {
            "id": "billing-checklist",
            "version": 2,
            "name": "Billing checklist v2",
            "checks": sorted(REQUIRED_CHECKS | {"missing_previous"}),
        },
        "reviewer",
        201,
    )
    outcome = post(
        governed,
        BASE + "/evaluations",
        {
            "expected_config_hash": action(governed)["expected_config_hash"],
            "suite_id": suite["id"],
            "suite_version": suite["version"],
        },
        status=201,
    )
    assert outcome["status"] == "passed"
    assert outcome["suite_hash"] == suite["suite_hash"]
    assert outcome["suite_version"] == 2 and outcome["completed_at"]
    persisted = get(governed, "/evaluations/" + outcome["id"])
    assert len(persisted["results"]) == outcome["passed_count"] == 9
    for result in persisted["results"]:
        assert result["passed"] and result["duration_ms"] >= 0
        assert result["critical"] == (result["check"] in REQUIRED_CHECKS)


def test_checklist_numeric_regression_is_detected_and_blocks_publication(governed, monkeypatch):
    from app.runtime import graph

    correct = graph.compare_invoices

    def incorrect_calculation(current, previous):
        result = correct(current, previous)
        result["difference_cop"] = "60000.00"
        result["percentage_change"] = "20.00"
        return result

    # Controlled numeric fault only; real graph, tools, identity and authorization remain active.
    monkeypatch.setattr(graph, "compare_invoices", incorrect_calculation)
    candidate, frozen = clone(governed)
    outcome = post(
        governed,
        candidate + "/evaluations",
        {"expected_config_hash": frozen["config_hash"]},
        status=201,
    )
    assert outcome["status"] == "failed" and outcome["critical_failures"] > 0
    persisted = get(governed, "/evaluations/" + outcome["id"])
    comparison = next(r for r in persisted["results"] if r["check"] == "comparison")
    assert not comparison["passed"] and comparison["critical"]
    trace = get(governed, "/runs/" + comparison["run_id"] + "/trace")
    assert trace["events"] and trace["tool_calls"]
    post(governed, candidate + "/submit", action(governed, candidate), status=409)
    post(
        governed,
        candidate + "/publish",
        action(governed, candidate) | {"expected_publication_revision": 0},
        "approver",
        409,
    )
