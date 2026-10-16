"""Reproducible S5 audit: fresh PDF/TXT/MD -> HTTP ingestion -> SQL -> real runtime.

Run inside API after make verify. Creates synthetic audit records, never deletes history.
Credentials stay in the server environment. No provider generation call is requested.
"""

import hashlib
import json
import os
from uuid import uuid4

import httpx
import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import build_engine
from app.knowledge.embeddings import EMBEDDING_VERSION, embed
from app.knowledge.extract import extract
from app.knowledge.models import KnowledgeChunk, KnowledgeObject, KnowledgeVersion


def pdf_bytes(content: str) -> bytes:
    """Generate a synthetic text PDF with explicit objects and xref byte offsets."""
    escaped = content.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 10 Tf 10 250 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(output)
    output += b"xref\n0 6\n0000000000 65535 f \n"
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return output + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


def main() -> None:
    settings = Settings()
    if settings.app_env not in {"development", "test"} or not settings.enable_demo_auth:
        raise SystemExit("This mutating synthetic audit requires explicit local demo auth")
    prefix = "s5-audit-" + uuid4().hex[:12]
    tokens = {role: os.environ[f"DEMO_{role}_TOKEN"] for role in ["CREATOR", "ADMIN", "VIEWER"]}
    client = httpx.Client(base_url=os.getenv("SMOKE_API_URL", "http://127.0.0.1:8000"), timeout=125)
    engine = build_engine(settings)

    def call(path, method="GET", *, role="CREATOR", expected=200, **kwargs):
        response = client.request(
            method, "/api/v1" + path, headers={"Authorization": "Bearer " + tokens[role]}, **kwargs
        )
        assert response.status_code == expected, (method, path, response.status_code, response.text)
        return response.json() if response.content else None

    def query(as_of="2026-09-01", *, role="CREATOR", expected=200):
        return call(
            "/knowledge/search",
            "POST",
            role=role,
            expected=expected,
            json={
                "query": "Tarifa consumo electricidad facturacion energia kWh",
                "collection_ids": [prefix],
                "as_of": as_of,
                "limit": 6,
            },
        )

    def fingerprint(docid):
        with Session(engine) as session:
            versions = session.scalars(
                select(KnowledgeVersion).where(KnowledgeVersion.document_id == docid)
            ).all()
            rows = session.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == docid)
                .order_by(KnowledgeChunk.ordinal)
            ).all()
            value = hashlib.sha256(
                b"".join(
                    r.content_hash.encode() + np.asarray(r.embedding, dtype=np.float32).tobytes()
                    for r in rows
                )
            ).hexdigest()
            return {"versions": len(versions), "chunks": len(rows), "vectors_hash": value}

    try:
        caller = call("/me")["id"]
        call(
            "/knowledge/collections",
            "POST",
            expected=201,
            json={"id": prefix, "name": "Sprint 5 audit corpus"},
        )
        evidence_report, refs = [], []
        for extension in ["txt", "md", "pdf"]:
            docid = prefix + "-" + extension
            content = (
                f"Documento sintetico {docid}. "
                + (
                    "Tarifa de energia electrica: 800 COP/kWh en agosto y 820 COP/kWh "
                    "en septiembre de 2026. La facturacion usa consumo y tarifa; "
                    "los calculos se verifican con Python. "
                )
                * 7
            )
            raw = pdf_bytes(content) if extension == "pdf" else content.encode()
            call(
                f"/knowledge/collections/{prefix}/documents",
                "POST",
                expected=201,
                json={"id": docid, "title": f"Tarifas y FAQ de auditoria {extension}"},
            )

            def upload(docid=docid, extension=extension, raw=raw):
                return call(
                    f"/knowledge/documents/{docid}/versions",
                    "POST",
                    expected=201,
                    files={"file": (f"audit.{extension}", raw)},
                    data={
                        "source": f"synthetic://audit/{docid}",
                        "valid_from": "2026-08-01",
                        "valid_to": "2026-09-30",
                    },
                )

            uploaded = upload()
            assert uploaded["number"] == 1 and uploaded["status"] == "pending"
            ready = call(f"/knowledge/documents/{docid}/versions/1/ingest", "POST")
            assert ready["status"] == "ready" and ready["chunk_count"] >= 2, ready
            before = fingerprint(docid)
            assert upload()["number"] == 1
            repeated = call(f"/knowledge/documents/{docid}/versions/1/ingest", "POST")
            assert repeated["chunk_count"] == ready["chunk_count"]
            assert fingerprint(docid) == before, "Reingestion or duplicate upload changed evidence"
            with Session(engine) as session:
                version = session.get(KnowledgeVersion, (docid, 1))
                original = session.get(KnowledgeObject, version.object_key).content
                assert bytes(original) == raw
                assert hashlib.sha256(raw).hexdigest() == version.content_hash
                extracted = extract(raw, "." + extension)
                assert content in extracted
                rows = session.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.document_id == docid)
                    .order_by(KnowledgeChunk.ordinal)
                ).all()
                for row in rows:
                    assert row.content == extracted[row.char_start : row.char_end]
                    assert row.content_hash == hashlib.sha256(row.content.encode()).hexdigest()
                    assert "INV-1002" not in row.content and "INV-2002" not in row.content
                vectors = np.asarray(
                    embed([r.content for r in rows], settings.knowledge_model_path)
                )
                stored = np.asarray([r.embedding for r in rows])
                assert np.allclose(vectors, stored, atol=1e-7), (
                    "Persisted vectors differ from model"
                )
                assert np.allclose(np.linalg.norm(stored, axis=1), 1, atol=1e-6)
                physical = (
                    session.execute(
                        text("""
                    SELECT pg_typeof(embedding)::text AS type, vector_dims(embedding) AS dims
                    FROM knowledge_chunks WHERE document_id=:id LIMIT 1
                """),
                        {"id": docid},
                    )
                    .mappings()
                    .one()
                )
                assert physical["type"] == "vector" and physical["dims"] == 256
                assert version.embedding_version == EMBEDDING_VERSION
            call(
                f"/knowledge/documents/{docid}/versions/1",
                "PATCH",
                role="ADMIN",
                json={"approval": "approved"},
            )
            refs.append({"document_id": docid, "version": 1})
            evidence_report.append(
                {
                    "document_id": docid,
                    "format": extension,
                    "extracted_characters": len(extracted),
                    **before,
                    "physical_vector_type": "vector(256)",
                    "real_embeddings_match_database": True,
                }
            )

        denied = query(role="VIEWER", expected=403)
        assert denied["detail"]["code"] == "KNOWLEDGE_FORBIDDEN"
        assert query(role="ADMIN", expected=403)["detail"]["code"] == "KNOWLEDGE_FORBIDDEN"
        dates = {}
        for as_of, available in [
            ("2026-07-31", False),
            ("2026-08-01", True),
            ("2026-09-30", True),
            ("2026-10-01", False),
        ]:
            result = query(as_of)
            assert bool(result["evidence"]) == available, (as_of, result)
            dates[as_of] = len(result["evidence"])
        result = query()
        assert result["evidence"]
        for item in result["evidence"]:
            actual = call(
                f"/knowledge/documents/{item['document_id']}/versions/1/chunks/{item['chunk']}?as_of=2026-09-01"
            )
            assert actual["content"] == item["content"]
            assert actual["content_hash"] == item["content_hash"]

        source = call("/agents/billing-assistant/versions/1")["configuration"]
        source["tool_ids"] = ["invoice-lookup-v3", "invoice-previous-v1", "billing-knowledge-v2"]
        source["knowledge"] = {"documents": refs}
        call(
            "/agents",
            "POST",
            expected=201,
            json={
                "id": prefix,
                "name": "S5 audit billing",
                "department": "quality",
                "description": "Synthetic audit of fresh document ingestion and billing runtime",
            },
        )
        draft = call(
            f"/agents/{prefix}/versions", "POST", expected=201, json={"configuration": source}
        )
        frozen = call(
            f"/agents/{prefix}/versions/1/snapshot",
            "POST",
            json={"expected_revision": draft["revision"]},
        )
        assert {d["document_id"] for d in frozen["snapshot"]["knowledge"]} == {
            ref["document_id"] for ref in refs
        }
        call(
            f"/agents/{prefix}/versions/1/invocations",
            "POST",
            role="ADMIN",
            expected=204,
            json={
                "user_id": caller,
                "enabled": True,
                "reason": "Synthetic Sprint 5 audit invocation",
            },
        )
        payload = {
            "agent_id": prefix,
            "version": 1,
            "mode": "deterministic",
            "message": "Compara INV-1002 con el periodo anterior",
            "invoice_id": "INV-1002",
            "task": "compare",
        }
        run = call("/runs", "POST", expected=201, json=payload)
        assert run["status"] == "completed", run
        assert run["calculations"]["difference_cop"] == "64400.00"
        assert run["calculations"]["percentage_change"] == "23.00"
        assert run["input_tokens"] is None and run["estimated_cost_usd"] is None
        assert "sin llamada a un proveedor" in run["answer"]
        trace = call("/runs/" + run["id"] + "/trace")
        assert [e["node"] for e in trace["events"]] == [
            "authorize",
            "route",
            "invoice",
            "previous",
            "knowledge",
            "calculate",
            "generate",
            "validate_output",
            "finalize",
        ]
        assert [c["tool_id"] for c in trace["tool_calls"]] == [
            "invoice-lookup-v3",
            "invoice-previous-v1",
            "billing-knowledge-v2",
        ]
        assert trace["tool_calls"][0]["result_references"] == ["INV-1002"]
        assert trace["tool_calls"][1]["result_references"] == ["INV-1001"]
        assert trace["knowledge_searches"][0]["as_of"] == "2026-09-01"
        with engine.connect() as connection:
            invoices = (
                connection.execute(
                    text(
                        "SELECT id, charge_cop FROM invoices "
                        "WHERE id IN ('INV-1001','INV-1002') "
                        "AND owner_id=:caller ORDER BY id"
                    ),
                    {"caller": caller},
                )
                .mappings()
                .all()
            )
        assert [i["id"] for i in invoices] == ["INV-1001", "INV-1002"]
        assert invoices[1]["charge_cop"] - invoices[0]["charge_cop"] == 64400
        assert (invoices[1]["charge_cop"] - invoices[0]["charge_cop"]) / invoices[0][
            "charge_cop"
        ] * 100 == 23
        persisted_refs = []
        with Session(engine) as session:
            for item in trace["knowledge_searches"][0]["references"]:
                row = session.get(
                    KnowledgeChunk, (item["document_id"], item["version"], item["chunk"])
                )
                assert row and row.content_hash == item["content_hash"]
                assert item["reference"] in run["references"] and item["reference"] in run["answer"]
                persisted_refs.append(item["reference"])
        assert persisted_refs
        denied_run = call("/runs", "POST", expected=201, json=payload | {"invoice_id": "INV-2002"})
        assert denied_run["status"] == "denied" and not denied_run["references"]
        denied_trace = call("/runs/" + denied_run["id"] + "/trace")
        assert not denied_trace["knowledge_searches"], "Invoice denial must not fall back to RAG"
        assert len(denied_trace["tool_calls"]) == 1
        assert denied_trace["tool_calls"][0]["tool_id"] == "invoice-lookup-v3"
        missing = call(
            "/runs",
            "POST",
            expected=201,
            json=payload | {"invoice_id": None, "task": "knowledge", "period": "2026-10-01"},
        )
        assert missing["status"] == "escalated" and missing["error_code"] == "KNOWLEDGE_UNAVAILABLE"
        print(
            json.dumps(
                {
                    "agent_id": prefix,
                    "version": 1,
                    "config_hash": frozen["config_hash"],
                    "documents": evidence_report,
                    "embedding_version": EMBEDDING_VERSION,
                    "date_filter_counts": dates,
                    "unauthorized_http_status": 403,
                    "search_id": result["id"],
                    "run_id": run["id"],
                    "persisted_citations": persisted_refs,
                    "nodes": len(trace["events"]),
                    "tools": [c["tool_id"] for c in trace["tool_calls"]],
                    "difference_cop": run["calculations"]["difference_cop"],
                    "percentage_change": run["calculations"]["percentage_change"],
                    "transactional_invoice_table": "invoices",
                    "transactional_invoice_ids": [i["id"] for i in invoices],
                    "generation_mode": run["mode"],
                    "denied_run_id": denied_run["id"],
                    "expired_knowledge_run_id": missing["id"],
                },
                indent=2,
            )
        )
    finally:
        client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
