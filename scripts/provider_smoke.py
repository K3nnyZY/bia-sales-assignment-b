"""Explicit paid provider smoke through Runtime API; never run by make verify."""

import json
import os
from urllib.request import Request, urlopen

base = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000")
token = os.environ["DEMO_CREATOR_TOKEN"]


def request(path, body=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(base + path, data=payload, headers=headers), timeout=125) as response:
        return json.load(response)


versions = request("/api/v1/runtime/agents")
selected = next(
    (
        item
        for item in reversed(versions)
        if item["agent_id"] == "billing-assistant"
        and item["model_provider"] == "openai"
        and "provider" in item["available_modes"]
    ),
    None,
)
if selected is None:
    raise SystemExit("No approved OpenAI snapshot/grant with provider mode configured.")
model = request(f"/api/v1/models/{selected['model_id']}")
payload = {
    "agent_id": selected["agent_id"],
    "version": selected["version"],
    "mode": "provider",
    "task": "compare",
    "invoice_id": "INV-1002",
    "message": "Explica la diferencia con el mes anterior usando evidencia autorizada.",
}
run = request("/api/v1/runs", payload)
if run["status"] != "completed":
    print(
        json.dumps({"run_id": run["id"], "status": run["status"], "error_code": run["error_code"]})
    )
    raise SystemExit("Provider execution failed; inspect the persisted trace. No fallback used.")
assert run["mode"] == "provider" and run["model_id"] == model["id"]
assert run["calculations"]["difference_cop"] == "64400.00"
assert run["calculations"]["consumption_difference_kwh"] == "70.000"
assert "Modo determinista de prueba" not in run["answer"]
trace = request(f"/api/v1/runs/{run['id']}/trace")
assert len(trace["events"]) == 9 and len(trace["tool_calls"]) == 3
assert all(call["status"] == "completed" for call in trace["tool_calls"])
assert trace["run"] == run
denied = request("/api/v1/runs", payload | {"invoice_id": "INV-2002"})
assert denied["status"] == "denied" and denied["error_code"] == "INVOICE_NOT_ACCESSIBLE"
assert denied["input_tokens"] is None and denied["references"] == []
print(
    json.dumps(
        {
            "run_id": run["id"],
            "version": selected["version"],
            "model_id": model["id"],
            "model_identifier": model["model_identifier"],
            "status": run["status"],
            "mode": run["mode"],
            "input_tokens": run["input_tokens"],
            "output_tokens": run["output_tokens"],
            "estimated_cost_usd": run["estimated_cost_usd"],
            "calculations": run["calculations"],
            "references": run["references"],
            "nodes": [event["node"] for event in trace["events"]],
            "tool_calls": len(trace["tool_calls"]),
            "denied_run_id": denied["id"],
            "answer": run["answer"],
        },
        ensure_ascii=False,
    )
)
print("PASS: provider runtime, Python calculations, persisted trace and denied foreign invoice.")
