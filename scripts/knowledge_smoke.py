"""Real HTTP retrieval/runtime/trace checks; no external generation call."""

import hashlib
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = os.getenv("SMOKE_API_URL", "http://127.0.0.1:8000")
creator = os.environ["DEMO_CREATOR_TOKEN"]
viewer = os.environ["DEMO_VIEWER_TOKEN"]


def request(path, token=creator, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(
        Request(
            base + "/api/v1" + path,
            data=data,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        ),
        timeout=125,
    ) as response:
        return json.load(response)


if os.getenv("KNOWLEDGE_TRACE_PROOF"):
    proof = json.loads(os.environ["KNOWLEDGE_TRACE_PROOF"])
    trace = request("/runs/" + proof["run_id"] + "/trace")
    value = hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()
    assert value == proof["trace_hash"], "Trace changed across restart"
    print("PASS: run, StateGraph events, tool calls and retrieval log survive API restart.")
    raise SystemExit(0)

versions = request("/agents/billing-assistant/versions")
selected = next(
    v
    for v in reversed(versions)
    if v["status"] == "snapshot"
    and v["configuration"].get("knowledge")
    and v["model_id"] == "synthetic-balanced-v1"
)
search = request(
    "/knowledge/search",
    body={
        "query": "Electricity consumption and billing price",
        "collection_ids": ["billing-reference"],
        "as_of": "2026-09-01",
    },
)
assert search["mode"] == "hybrid-semantic" and search["evidence"]
for e in search["evidence"]:
    source = request(
        f"/knowledge/documents/{e['document_id']}/versions/{e['version']}/chunks/{e['chunk']}?as_of=2026-09-01"
    )
    assert source["content"] == e["content"] and source["content_hash"] == e["content_hash"]
try:
    request(
        "/knowledge/search",
        token=viewer,
        body={"query": "tarifa", "collection_ids": ["billing-reference"], "as_of": "2026-09-01"},
    )
except HTTPError as error:
    assert error.code == 403
else:
    raise AssertionError("Viewer without grant could retrieve knowledge")
payload = {
    "agent_id": "billing-assistant",
    "version": selected["number"],
    "message": "Compara INV-1002",
    "invoice_id": "INV-1002",
    "mode": "deterministic",
}
run = request("/runs", body=payload)
assert run["status"] == "completed", run
assert run["calculations"]["difference_cop"] == "64400.00"
assert run["calculations"]["percentage_change"] == "23.00"
assert any("#chunk-" in ref for ref in run["references"])
assert "sin llamada a un proveedor" in run["answer"]
trace = request("/runs/" + run["id"] + "/trace")
assert trace["knowledge_searches"] and len(trace["events"]) == 9
assert trace["knowledge_searches"][0]["references"]
denied = request("/runs", body=payload | {"invoice_id": "INV-2002"})
assert denied["status"] == "denied" and denied["references"] == []
print(
    json.dumps(
        {
            "version": selected["number"],
            "run_id": run["id"],
            "trace_hash": hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest(),
            "search_id": search["id"],
            "references": run["references"],
            "difference_cop": run["calculations"]["difference_cop"],
            "percentage_change": run["calculations"]["percentage_change"],
            "retrieval_mode": search["mode"],
            "embedding_version": search["embedding_version"],
            "generation_mode": run["mode"],
            "provider_called": False,
            "denied_run_id": denied["id"],
        },
        indent=2,
    )
)
