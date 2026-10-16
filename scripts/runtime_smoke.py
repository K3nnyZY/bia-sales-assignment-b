"""HTTP smoke test against persisted local runtime, using server environment credentials."""

import hashlib
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000")
creator = os.environ["DEMO_CREATOR_TOKEN"]
customer_b = os.environ["DEMO_CUSTOMER_B_TOKEN"]


def request(path, token=creator, body=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(base + path, data=payload, headers=headers), timeout=125) as response:
        return json.load(response)


def trace_digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()


if os.environ.get("RUNTIME_TRACE_PROOF"):
    proof = json.loads(os.environ["RUNTIME_TRACE_PROOF"])
    for key, status, token in [
        ("run_id", "completed", creator),
        ("invoice_query_run_id", "completed", creator),
        ("denied_run_id", "denied", creator),
        ("failed_tool_run_id", "escalated", creator),
        ("customer_b_run_id", "completed", customer_b),
    ]:
        restored = request(f"/api/v1/runs/{proof[key]}/trace", token=token)
        assert restored["run"]["status"] == status
        assert trace_digest(restored) == proof["trace_digests"][proof[key]]
    print("PASS: all five persisted traces retain their exact SHA-256 after API restart.")
    raise SystemExit(0)


versions = request("/api/v1/runtime/agents")
selected = next(item for item in reversed(versions) if "deterministic" in item["available_modes"])
payload = {
    "agent_id": selected["agent_id"],
    "version": selected["version"],
    "message": "Compara mi factura INV-1002",
    "invoice_id": "INV-1002",
    "mode": "deterministic",
}
invoice = request("/api/v1/runs", body=payload | {"task": "invoice"})
assert invoice["status"] == "completed" and "344400.00 COP" in invoice["answer"]
assert invoice["calculations"] == {}
run = request("/api/v1/runs", body=payload)
assert run["status"] == "completed", run["error_code"]
assert run["calculations"]["difference_cop"] == "64400.00"
assert run["calculations"]["consumption_difference_kwh"] == "70.000"
assert run["calculations"]["percentage_change"] == "23.00"
assert run["calculations"]["consumption_effect_cop"] == "56000.00"
assert run["calculations"]["rate_effect_cop"] == "8400.00"
assert "sin llamada a un proveedor" in run["answer"]
assert run["input_tokens"] is None and run["estimated_cost_usd"] is None
trace = request(f"/api/v1/runs/{run['id']}/trace")
assert len(trace["events"]) == 9 and len(trace["tool_calls"]) == 3
assert trace["run"] == run
denied = request("/api/v1/runs", body=payload | {"invoice_id": "INV-2002"})
assert denied["status"] == "denied" and denied["error_code"] == "INVOICE_NOT_ACCESSIBLE"
assert denied["references"] == [] and denied["calculations"] == {}
failure = request("/api/v1/runs", body=payload | {"task": "compare", "invoice_id": "INV-1001"})
assert failure["status"] == "escalated"
assert failure["error_code"] == "PREVIOUS_INVOICE_UNAVAILABLE"
failed_trace = request(f"/api/v1/runs/{failure['id']}/trace")
assert failed_trace["tool_calls"][-1]["status"] == "failed"
assert failed_trace["events"][-1]["node"] == "failure"
own_b = request("/api/v1/runs", token=customer_b, body=payload | {"invoice_id": "INV-2002"})
assert own_b["status"] == "completed"
assert own_b["calculations"]["difference_cop"] == "27000.00"
try:
    request(f"/api/v1/runs/{run['id']}/trace", token=customer_b)
except HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError("Another customer could read a private trace")
print(
    json.dumps(
        {
            "run_id": run["id"],
            "version": selected["version"],
            "status": run["status"],
            "mode": run["mode"],
            "difference_cop": run["calculations"]["difference_cop"],
            "tool_calls": len(trace["tool_calls"]),
            "cross_customer": denied["status"],
            "invoice_query_run_id": invoice["id"],
            "denied_run_id": denied["id"],
            "failed_tool_run_id": failure["id"],
            "failed_tool_code": failure["error_code"],
            "customer_b_run_id": own_b["id"],
            "customer_b_difference_cop": own_b["calculations"]["difference_cop"],
            "consumption_difference_kwh": run["calculations"]["consumption_difference_kwh"],
            "nodes": [event["node"] for event in trace["events"]],
            "trace_sha256": trace_digest(trace),
            "trace_digests": {
                item["id"]: trace_digest(request(f"/api/v1/runs/{item['id']}/trace", token=token))
                for item, token in [
                    (run, creator),
                    (invoice, creator),
                    (denied, creator),
                    (failure, creator),
                    (own_b, customer_b),
                ]
            },
        }
    )
)
print("PASS: invoice, comparison, denied access, failed tool and persisted LangGraph traces.")
