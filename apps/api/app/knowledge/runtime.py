"""Registered billing adapter using the shared Knowledge service."""

from datetime import date
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.billing.contracts import KnowledgeInput
from app.catalogs.schemas import Contract
from app.identity.models import User
from app.knowledge.schemas import Evidence, SearchRequest
from app.knowledge.service import search
from app.runtime.errors import ExecutionError

if TYPE_CHECKING:
    from app.runtime.context import ExecutionContext


class RagResult(Contract):
    evidence: list[Evidence]


RAG_TOOL_ID = "billing-knowledge-v2"
RAG_ADAPTER = ("search_billing_knowledge", "2.0.0", KnowledgeInput, RagResult)


async def billing_retrieval(ctx: ExecutionContext, args: KnowledgeInput) -> RagResult:
    user = ctx.session.get(User, ctx.caller_id)
    pinned = ctx.snapshot.get("knowledge", [])
    if not pinned:
        raise ExecutionError("KNOWLEDGE_UNAVAILABLE", "La versión no fija documentos autorizados.")
    try:
        result = search(
            ctx.session,
            ctx.settings,
            user,
            SearchRequest(
                query="Tarifa consumo facturación COP kWh agosto septiembre "
                "preguntas frecuentes cargos",
                collection_ids=sorted({d["collection_id"] for d in pinned}),
                as_of=args.period,
                limit=4,
            ),
            pinned=pinned,
            run_id=ctx.run.id,
        )
    except HTTPException as exc:
        raise ExecutionError(
            exc.detail["code"],
            exc.detail["message"],
            status="denied" if exc.status_code == 403 else "escalated",
        ) from exc
    if not result.evidence:
        raise ExecutionError(
            "KNOWLEDGE_UNAVAILABLE",
            "No hay evidencia documental autorizada y vigente.",
            status="escalated",
        )
    return RagResult(evidence=result.evidence)


def evidence_period(state: dict) -> date:
    return date.fromisoformat(state.get("current", {}).get("period", state["period"]))
