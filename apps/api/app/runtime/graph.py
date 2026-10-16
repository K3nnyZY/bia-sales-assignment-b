import asyncio
import re
from datetime import UTC, datetime
from time import monotonic
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from sqlalchemy import select

from app.billing.calculations import compare_invoices
from app.billing.contracts import InvoiceData, KnowledgeItem
from app.billing.models import BillingKnowledge
from app.billing.tools import execute_tool, owned_invoice
from app.knowledge.runtime import RAG_TOOL_ID, evidence_period
from app.runtime.context import ExecutionContext
from app.runtime.errors import ExecutionError
from app.runtime.gateway import explain
from app.runtime.models import RunEvent
from app.runtime.policy import authorize_context


class BillingState(TypedDict, total=False):
    message: str
    task: str
    invoice_id: str | None
    period: str
    current: dict
    previous: dict
    knowledge: dict
    calculations: dict
    observations: list[str]
    references: list[str]
    answer: str
    error: dict[str, str]


async def authorize(state: BillingState, ctx: ExecutionContext) -> dict:
    authorize_context(ctx)
    return {}


async def route(state: BillingState, ctx: ExecutionContext) -> dict:
    task = state["task"]
    message = state["message"].casefold()
    if task == "auto":
        task = (
            "knowledge"
            if any(word in message for word in ["faq", "tarifa", "tariff"])
            and not state.get("invoice_id")
            and not re.search(r"INV-\d+", state["message"], re.I)
            else "compare"
        )
    invoice_id = state.get("invoice_id")
    if task != "knowledge" and invoice_id is None:
        matches = set(re.findall(r"\bINV-[0-9]{4,12}\b", state["message"], re.I))
        if len(matches) != 1:
            raise ExecutionError(
                "INVOICE_REQUIRED",
                "Indica una única factura para consultar o comparar.",
                status="escalated",
            )
        invoice_id = matches.pop().upper()
    return {"task": task, "invoice_id": invoice_id}


async def invoice(state: BillingState, ctx: ExecutionContext) -> dict:
    return {
        "current": await execute_tool(ctx, "invoice-lookup-v3", {"invoice_id": state["invoice_id"]})
    }


async def previous(state: BillingState, ctx: ExecutionContext) -> dict:
    return {
        "previous": await execute_tool(
            ctx, "invoice-previous-v1", {"invoice_id": state["invoice_id"]}
        )
    }


async def knowledge(state: BillingState, ctx: ExecutionContext) -> dict:
    period = state.get("current", {}).get("period", state["period"])
    return {
        "knowledge": await execute_tool(
            ctx, RAG_TOOL_ID if ctx.config.knowledge else "billing-knowledge-v1", {"period": period}
        )
    }


async def calculate(state: BillingState, ctx: ExecutionContext) -> dict:
    calculations, observations, references = {}, [], []
    if state.get("current"):
        current = InvoiceData.model_validate(state["current"])
        references.append(current.invoice_id)
        observations.append(
            f"La factura {current.invoice_id} de {current.period:%Y-%m} registra "
            f"{current.consumption_kwh} kWh a {current.unit_rate_cop} COP/kWh: "
            f"{current.charge_cop} COP de cargo por consumo."
        )
        if state.get("previous"):
            old = InvoiceData.model_validate(state["previous"])
            calculations = compare_invoices(current, old)
            references.append(old.invoice_id)
            percent = calculations["percentage_change"]
            observations.append(
                f"Frente a {old.invoice_id} ({old.consumption_kwh} kWh y "
                f"{old.charge_cop} COP), el consumo varió "
                f"{calculations['consumption_difference_kwh']} kWh y "
                f"el cargo varió {calculations['difference_cop']} COP"
                + (
                    f" ({percent}%)."
                    if percent is not None
                    else "; porcentaje no definido porque el cargo anterior es cero."
                )
            )
            observations.append(
                f"Efecto del consumo: {calculations['consumption_effect_cop']} COP; "
                f"efecto de la tarifa: {calculations['rate_effect_cop']} COP; "
                f"ajuste de redondeo: {calculations['rounding_adjustment_cop']} COP. "
                "Cálculos realizados en Python con Decimal."
            )
    for item in state["knowledge"].get("evidence", []):
        reference = item["reference"]
        references.append(reference)
        observations.append(f"Fuente aprobada [{reference}] — {item['title']}: «{item['content']}»")
    for item in state["knowledge"].get("items", []):
        reference = f"{item['id']}@{item['version']}"
        references.append(reference)
        # Quote source text as data. It cannot change routing, identity or tool arguments.
        observations.append(f"Fuente aprobada [{reference}] — {item['title']}: «{item['content']}»")
    return {"calculations": calculations, "observations": observations, "references": references}


async def generate(state: BillingState, ctx: ExecutionContext) -> dict:
    authorize_context(ctx)
    ctx.session.commit()  # Do not hold catalog/identity locks across external provider calls.
    evidence = {
        key: state[key]
        for key in ["current", "previous", "knowledge", "calculations"]
        if key in state
    }
    return {"answer": await explain(ctx, state["observations"], state["references"], evidence)}


async def validate_output(state: BillingState, ctx: ExecutionContext) -> dict:
    authorize_context(ctx)
    # Recheck authorization before releasing a response, including revocations during generation.
    from app.runtime.policy import authorize_tool

    for tool_id in ctx.config.tool_ids:
        authorize_tool(ctx, tool_id)
    for key in ["current", "previous"]:
        if state.get(key):
            owned_invoice(ctx, state[key]["invoice_id"])
    if ctx.config.knowledge:
        from app.knowledge.service import verify_evidence

        try:
            verify_evidence(
                ctx.session,
                authorize_context(ctx),
                state["knowledge"]["evidence"],
                evidence_period(state),
            )
        except Exception as exc:
            raise ExecutionError(
                "KNOWLEDGE_CHANGED", "La evidencia dejó de estar autorizada.", status="denied"
            ) from exc
    for source in state["knowledge"].get("items", []):
        row = ctx.session.scalar(
            select(BillingKnowledge).where(
                BillingKnowledge.id == source["id"],
                BillingKnowledge.version == source["version"],
                BillingKnowledge.status == "approved",
            )
        )
        if row is None or KnowledgeItem.model_validate(row).model_dump(mode="json") != source:
            raise ExecutionError(
                "KNOWLEDGE_CHANGED",
                "La evidencia dejó de estar aprobada o cambió durante la ejecución.",
                status="escalated",
            )
    if not state.get("answer") or len(state["answer"]) > 24000:
        raise ExecutionError("INVALID_OUTPUT", "No se obtuvo una explicación válida.")
    return {}


async def finalize(state: BillingState, ctx: ExecutionContext) -> dict:
    return {}


async def failure(state: BillingState, ctx: ExecutionContext) -> dict:
    return {"answer": state["error"]["message"]}


def tracked(name, operation, *, terminal=False):
    async def node(state: BillingState, runtime: Runtime[ExecutionContext]) -> dict:
        ctx = runtime.context
        start, started_at = monotonic(), datetime.now(UTC)
        error = None
        try:
            if not terminal:
                if ctx.steps >= ctx.config.limits.max_steps:
                    raise ExecutionError("STEP_LIMIT", "Se agotó el límite de pasos de ejecución.")
                ctx.steps += 1
            ctx.node_names.append(name)
            result = await operation(state, ctx)
        except ExecutionError as exc:
            error, result = exc, {"error": exc.as_dict()}
        except asyncio.CancelledError:
            error = ExecutionError("RUN_TIMEOUT", "La ejecución alcanzó su tiempo máximo.")
            raise
        except Exception:
            ctx.session.rollback()
            error = ExecutionError(
                "INTERNAL_ERROR", "No se pudo completar esta etapa de la ejecución."
            )
            result = {"error": error.as_dict()}
        finally:
            ctx.session.add(
                RunEvent(
                    id=f"evt-{uuid4().hex}",
                    run_id=ctx.run.id,
                    step=ctx.steps,
                    node=name,
                    status="failed" if error else "completed",
                    error_code=error.code if error else None,
                    started_at=started_at,
                    duration_ms=max(0, int((monotonic() - start) * 1000)),
                )
            )
            ctx.session.commit()
        return result

    return node


def build_graph():
    builder = StateGraph(BillingState, context_schema=ExecutionContext)
    operations = {
        "authorize": authorize,
        "route": route,
        "invoice": invoice,
        "previous": previous,
        "knowledge": knowledge,
        "calculate": calculate,
        "generate": generate,
        "validate_output": validate_output,
        "finalize": finalize,
    }
    for name, operation in operations.items():
        builder.add_node(name, tracked(name, operation))
    builder.add_node("failure", tracked("failure", failure, terminal=True))
    builder.add_edge(START, "authorize")
    builder.add_conditional_edges(
        "authorize",
        lambda state: "failure" if state.get("error") else "route",
        ["failure", "route"],
    )
    builder.add_conditional_edges(
        "route",
        lambda state: (
            "failure"
            if state.get("error")
            else "knowledge"
            if state["task"] == "knowledge"
            else "invoice"
        ),
        ["failure", "knowledge", "invoice"],
    )
    builder.add_conditional_edges(
        "invoice",
        lambda state: (
            "failure"
            if state.get("error")
            else "previous"
            if state["task"] == "compare"
            else "knowledge"
        ),
        ["failure", "previous", "knowledge"],
    )
    for source, target in [
        ("previous", "knowledge"),
        ("knowledge", "calculate"),
        ("calculate", "generate"),
        ("generate", "validate_output"),
        ("validate_output", "finalize"),
    ]:
        builder.add_conditional_edges(
            source,
            lambda state, target=target: "failure" if state.get("error") else target,
            ["failure", target],
        )
    builder.add_conditional_edges(
        "finalize", lambda state: "failure" if state.get("error") else END, ["failure", END]
    )
    builder.add_edge("failure", END)
    return builder.compile()


BILLING_GRAPH = build_graph()
