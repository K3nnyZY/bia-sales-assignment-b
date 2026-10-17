"""Local HTTP acceptance flow. Uses deterministic mode, never contacts an LLM provider."""

import hashlib
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000") + "/api/v1"
TOKENS = {
    role: os.environ[f"DEMO_{role.upper()}_TOKEN"] for role in ("creator", "approver", "auditor")
}


def call(path, body=None, role="creator", expected=200, method=None):
    request = Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {TOKENS[role]}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=125) as response:
            assert response.status == expected, response.status
            return json.load(response)
    except HTTPError as exc:
        detail = json.load(exc)
        assert exc.code == expected, (exc.code, detail)
        return detail


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


if os.environ.get("GOVERNANCE_TRACE_PROOF"):
    proof = json.loads(os.environ["GOVERNANCE_TRACE_PROOF"])
    for rid, checksum in proof["traces"].items():
        assert digest(call(f"/runs/{rid}/trace", role="auditor")) == checksum
    assert call("/evaluations/" + proof["evaluation_id"])["evaluation"]["status"] == "passed"
    assert any(
        e["action"] == "publication.rollback"
        for e in call("/audit-events?agent_id=" + proof["agent_id"])
    )
    print("PASS: evaluation, rollback audit and exact trace hashes survived backend restart.")
    raise SystemExit(0)

agent_id = "quality-smoke-" + uuid4().hex[:12]
source = call("/agents/billing-assistant/versions/1")
assert source["snapshot"]["model"]["provider"] == "synthetic"
call(
    "/agents",
    {
        "id": agent_id,
        "name": "Quality smoke billing",
        "department": "quality",
        "description": "Synthetic governance acceptance flow",
    },
    expected=201,
)


def candidate(configuration):
    versions = call(f"/agents/{agent_id}/versions")
    draft = next((v for v in versions if v["status"] == "draft"), None)
    if draft is not None:
        # This fresh smoke-test agent owns only its automatically created initial draft.
        assert draft["number"] == 1 and draft["source_version"] is None
        version = call(
            f"/agents/{agent_id}/versions/1",
            {"expected_revision": draft["revision"], "configuration": configuration},
            method="PUT",
        )
    else:
        source = next(v for v in versions if v["status"] == "snapshot")
        version = call(
            f"/agents/{agent_id}/versions",
            {
                "source_version": source["number"],
                "expected_source_revision": source["revision"],
                "configuration": configuration,
            },
            expected=201,
        )
    base = f"/agents/{agent_id}/versions/{version['number']}"
    frozen = call(base + "/snapshot", {"expected_revision": version["revision"]})
    return base, frozen


def action(base):
    state = call(base + "/governance")
    return {"expected_revision": state["revision"], "expected_config_hash": state["config_hash"]}


def publish(base):
    evaluated = call(
        base + "/evaluations",
        {"expected_config_hash": action(base)["expected_config_hash"]},
        expected=201,
    )
    assert evaluated["status"] == "passed" and evaluated["passed_count"] == 9, evaluated
    call(base + "/submit", action(base), expected=201)
    call(
        base + "/approve",
        {
            **action(base),
            "decision": "approved",
            "reason": "Reviewed persisted synthetic test results",
        },
        "approver",
    )
    state = call(base + "/governance")
    result = call(
        base + "/publish",
        {**action(base), "expected_publication_revision": state["publication_revision"]},
        "approver",
    )
    assert result["stage"] == "published" and result["gate"]["eligible"]
    return evaluated, result


first_base, first = candidate(source["configuration"])
evaluation, _ = publish(first_base)
payload = {
    "agent_id": agent_id,
    "channel": "published",
    "message": "Compara mi factura",
    "invoice_id": "INV-1002",
    "task": "compare",
    "mode": "deterministic",
}
run = call("/runs", payload, expected=201)
assert run["status"] == "completed" and run["calculations"]["difference_cop"] == "64400.00"
assert run["calculations"]["percentage_change"] == "23.00"
assert run["input_tokens"] is None and run["estimated_cost_usd"] is None
denied = call("/runs", payload | {"invoice_id": "INV-2002"}, expected=201)
assert denied["status"] == "denied" and not denied["references"]
missing = call("/runs", payload | {"invoice_id": "INV-1001"}, expected=201)
assert missing["error_code"] == "PREVIOUS_INVOICE_UNAVAILABLE"
second_base, _ = candidate(source["configuration"])
_, second = publish(second_base)
restored = call(
    f"/agents/{agent_id}/rollback",
    {
        "target_version": first["number"],
        "expected_publication_revision": second["publication_revision"],
        "reason": "Acceptance rollback to approved v1",
    },
    "approver",
)
assert restored["publication_version"] == first["number"]
unsafe = json.loads(json.dumps(source["configuration"]))
unsafe["limits"]["max_tool_calls"] = 1
unsafe_base, frozen = candidate(unsafe)
failed = call(
    unsafe_base + "/evaluations", {"expected_config_hash": frozen["config_hash"]}, expected=201
)
assert failed["status"] == "failed" and failed["critical_failures"] > 0
blocked = call(unsafe_base + "/submit", action(unsafe_base), expected=409)
assert blocked["detail"]["code"] == "PUBLICATION_GATE_BLOCKED"
events = call("/audit-events?agent_id=" + agent_id, role="auditor")
assert {e["action"] for e in events} >= {
    "version.published",
    "approval.approved",
    "publication.rollback",
    "run.finalized",
}
traces = {
    r["id"]: digest(call(f"/runs/{r['id']}/trace", role="auditor")) for r in (run, denied, missing)
}
print(
    json.dumps(
        {
            "agent_id": agent_id,
            "evaluation_id": evaluation["id"],
            "checks_passed": evaluation["passed_count"],
            "unsafe_critical_failures": failed["critical_failures"],
            "run_id": run["id"],
            "denied_run_id": denied["id"],
            "missing_previous_run_id": missing["id"],
            "traces": traces,
            "provider_calls": 0,
        }
    )
)
