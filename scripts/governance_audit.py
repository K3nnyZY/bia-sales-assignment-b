"""Read-only audit of the latest local quality-smoke publication against PostgreSQL.

Run inside the API container after make governance-smoke. Exit 2 reports an
incomplete audit view; assertions indicate a failed critical invariant. No LLM calls.
"""

import hashlib
import json
import math
import os
from urllib.request import Request, urlopen

from sqlalchemy import text

from app.core.config import Settings
from app.db.session import build_engine


def request(path, role="AUDITOR"):
    token = os.environ[f"DEMO_{role}_TOKEN"]
    req = Request(
        "http://127.0.0.1:8000/api/v1" + path, headers={"Authorization": f"Bearer {token}"}
    )
    with urlopen(req, timeout=10) as response:
        return json.load(response)


engine = build_engine(Settings())
try:
    with engine.connect() as conn:
        counts = (
            conn.execute(
                text("""
            SELECT count(*) AS runs,
              count(*) FILTER (WHERE status='completed') AS completed,
              count(*) FILTER (WHERE status='failed') AS failed,
              count(*) FILTER (WHERE status='denied') AS denied,
              count(*) FILTER (WHERE status='escalated') AS escalated,
              count(*) FILTER (WHERE status='running') AS running,
              avg(extract(epoch FROM completed_at-started_at)*1000) AS latency_avg_ms,
              percentile_cont(0.5) WITHIN GROUP
                (ORDER BY extract(epoch FROM completed_at-started_at)*1000) AS latency_p50_ms,
              percentile_cont(0.95) WITHIN GROUP
                (ORDER BY extract(epoch FROM completed_at-started_at)*1000) AS latency_p95_ms
            FROM agent_runs WHERE channel<>'evaluation'
        """)
            )
            .mappings()
            .one()
        )
        metrics = request("/metrics")
        for key, value in counts.items():
            if key.startswith("latency_") and value is not None:
                assert math.isclose(float(value), metrics[key], abs_tol=1e-6), key
            else:
                assert metrics[key] == value, key
        tools = conn.execute(
            text("""
            SELECT count(*), count(*) FILTER (WHERE t.status<>'completed')
            FROM tool_calls t JOIN agent_runs r ON r.id=t.run_id WHERE r.channel<>'evaluation'
        """)
        ).one()
        assert (metrics["tool_calls"], metrics["tool_errors"]) == tuple(tools)
        row = (
            conn.execute(
                text("""
            SELECT p.agent_id, p.version_number, v.snapshot, v.config_hash,
              e.id AS evaluation_id, e.config_hash AS evaluation_hash,
              a.id AS approval_id, a.config_hash AS approval_hash,
              a.evaluation_id AS approved_evaluation_id,
              e.status AS evaluation_status, a.status AS approval_status
            FROM agent_publications p
            JOIN agents ag ON ag.id=p.agent_id
            JOIN agent_versions v ON v.agent_id=p.agent_id AND v.number=p.version_number
            JOIN version_governance g ON g.agent_id=p.agent_id AND g.version_number=p.version_number
            JOIN evaluation_runs e ON e.id=g.latest_evaluation_id
            JOIN approvals a ON a.id=g.approval_id
            WHERE p.enabled AND p.agent_id LIKE 'quality-smoke-%'
            ORDER BY ag.created_at DESC LIMIT 1
        """)
            )
            .mappings()
            .one()
        )
        canonical = json.dumps(
            row["snapshot"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        assert hashlib.sha256(canonical).hexdigest() == row["config_hash"]
        assert row["config_hash"] == row["evaluation_hash"] == row["approval_hash"]
        assert row["evaluation_id"] == row["approved_evaluation_id"]
        assert (row["evaluation_status"], row["approval_status"]) == ("passed", "approved")
        aid = row["agent_id"]
        metadata_ids = set(
            conn.scalars(
                text("""
            SELECT id FROM audit_events WHERE action IN ('agent.created','agent.updated')
              AND details->>'resource_id'=:agent_id
        """),
                {"agent_id": aid},
            )
        )
        filtered = request("/audit-events?agent_id=" + aid)
        owner_filtered = request("/audit-events?agent_id=" + aid, "CREATOR")
        omitted = sorted(metadata_ids - {e["id"] for e in filtered})
        owner_omitted = sorted(metadata_ids - {e["id"] for e in owner_filtered})
        findings = []
        if omitted or owner_omitted:
            findings.append(
                {
                    "code": "AGENT_METADATA_AUDIT_FILTER",
                    "severity": "medium",
                    "persisted_but_omitted_from_agent_filter": omitted,
                    "omitted_from_owner_view": owner_omitted,
                }
            )
        print(
            json.dumps(
                {
                    "metrics_match_sql": True,
                    "measured_runs": metrics["runs"],
                    "tool_calls": metrics["tool_calls"],
                    "tool_errors": metrics["tool_errors"],
                    "latency_p50_ms": metrics["latency_p50_ms"],
                    "latency_p95_ms": metrics["latency_p95_ms"],
                    "publication_hash_chain_matches": True,
                    "agent_id": aid,
                    "version": row["version_number"],
                    "config_hash": row["config_hash"],
                    "evaluation_id": row["evaluation_id"],
                    "approval_id": row["approval_id"],
                    "findings": findings,
                }
            )
        )
finally:
    engine.dispose()
raise SystemExit(2 if findings else 0)
