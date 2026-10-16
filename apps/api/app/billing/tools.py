import asyncio
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaValidationError
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.billing.calculations import previous_period
from app.billing.contracts import (
    ADAPTERS,
    InvoiceData,
    InvoiceInput,
    KnowledgeInput,
    KnowledgeItem,
    KnowledgeResult,
)
from app.billing.models import BillingKnowledge, Invoice
from app.knowledge.runtime import RAG_ADAPTER, RAG_TOOL_ID, billing_retrieval
from app.runtime.context import ExecutionContext
from app.runtime.errors import ExecutionError
from app.runtime.models import ToolCall
from app.runtime.policy import authorize_tool


def invoice_data(row: Invoice) -> InvoiceData:
    return InvoiceData(
        invoice_id=row.id,
        period=row.period,
        consumption_kwh=row.consumption_kwh,
        unit_rate_cop=row.unit_rate_cop,
        charge_cop=row.charge_cop,
    )


def owned_invoice(ctx: ExecutionContext, invoice_id: str) -> Invoice:
    # The identity is supplied only by authenticated server context, never by tool arguments.
    row = ctx.session.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.owner_id == ctx.caller_id)
    )
    if row is None:
        # Do not disclose whether a different customer's invoice exists.
        raise ExecutionError(
            "INVOICE_NOT_ACCESSIBLE", "Factura no disponible para este cliente.", status="denied"
        )
    return row


async def current_invoice(ctx: ExecutionContext, args: InvoiceInput) -> InvoiceData:
    return invoice_data(owned_invoice(ctx, args.invoice_id))


async def previous_invoice(ctx: ExecutionContext, args: InvoiceInput) -> InvoiceData:
    current = owned_invoice(ctx, args.invoice_id)
    row = ctx.session.scalar(
        select(Invoice).where(
            Invoice.owner_id == ctx.caller_id, Invoice.period == previous_period(current.period)
        )
    )
    if row is None:
        raise ExecutionError(
            "PREVIOUS_INVOICE_UNAVAILABLE",
            "No está disponible la factura del mes anterior.",
            status="escalated",
        )
    return invoice_data(row)


async def billing_knowledge(ctx: ExecutionContext, args: KnowledgeInput) -> KnowledgeResult:
    records = ctx.session.scalars(
        select(BillingKnowledge)
        .where(
            BillingKnowledge.status == "approved",
            BillingKnowledge.valid_from <= args.period,
            BillingKnowledge.valid_to >= args.period,
        )
        .order_by(BillingKnowledge.id, BillingKnowledge.version)
        .limit(10)
    ).all()
    if not records or not any(row.kind == "tariff" for row in records):
        raise ExecutionError(
            "KNOWLEDGE_UNAVAILABLE",
            "No hay información tarifaria aprobada y vigente para el período.",
            status="escalated",
        )
    return KnowledgeResult(items=[KnowledgeItem.model_validate(row) for row in records])


IMPLEMENTATIONS = {
    RAG_TOOL_ID: billing_retrieval,
    "invoice-lookup-v3": current_invoice,
    "invoice-previous-v1": previous_invoice,
    "billing-knowledge-v1": billing_knowledge,
}


async def execute_tool(ctx: ExecutionContext, tool_id: str, arguments: dict) -> dict:
    pinned = next((item for item in ctx.snapshot["tools"] if item["id"] == tool_id), None)
    max_retries = min(pinned["max_retries"], 3) if pinned else 0
    for attempt in range(1, max_retries + 2):
        if ctx.tool_count >= ctx.config.limits.max_tool_calls:
            raise ExecutionError("TOOL_LIMIT", "Se agotó el límite de llamadas a herramientas.")
        ctx.tool_count += 1
        started_at, start = datetime.now(UTC), monotonic()
        error = None
        result = None
        safe_arguments = {}
        try:
            timeout_ms = max(
                1,
                int(
                    min(pinned["timeout_seconds"] if pinned else 1, ctx.remaining_seconds()) * 1000
                ),
            )
            ctx.session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": str(timeout_ms)},
            )
            tool = authorize_tool(ctx, tool_id)
            descriptor = RAG_ADAPTER if tool_id == RAG_TOOL_ID else ADAPTERS.get(tool_id)
            if descriptor is None or tool_id not in IMPLEMENTATIONS:
                raise ExecutionError(
                    "ADAPTER_NOT_REGISTERED",
                    "La versión no tiene un adaptador de ejecución registrado.",
                )
            name, version, input_type, output_type = descriptor
            if (tool.name, tool.version) != (name, version):
                raise ExecutionError(
                    "ADAPTER_MISMATCH", "El adaptador no coincide con el contrato."
                )
            if (
                tool.input_schema != input_type.model_json_schema()
                or tool.output_schema != output_type.model_json_schema(mode="serialization")
            ):
                raise ExecutionError(
                    "ADAPTER_SCHEMA_MISMATCH", "El esquema no corresponde al adaptador registrado."
                )
            parsed = input_type.model_validate(arguments)
            safe_arguments = parsed.model_dump(mode="json")
            Draft202012Validator(tool.input_schema).validate(safe_arguments)
            async with asyncio.timeout(min(tool.timeout_seconds, ctx.remaining_seconds())):
                output = await IMPLEMENTATIONS[tool_id](ctx, parsed)
            result = output_type.model_validate(output).model_dump(mode="json")
            Draft202012Validator(tool.output_schema).validate(result)
        except ExecutionError as exc:
            error = exc
        except TimeoutError:
            error = ExecutionError(
                "TOOL_TIMEOUT", "La herramienta superó su tiempo máximo.", retryable=True
            )
        except ValidationError, SchemaValidationError, TypeError, ValueError:
            error = ExecutionError(
                "INVALID_TOOL_RESPONSE", "La herramienta devolvió datos inválidos."
            )
        except SQLAlchemyError as exc:
            ctx.session.rollback()
            if getattr(getattr(exc, "orig", None), "sqlstate", None) == "57014":
                error = ExecutionError(
                    "TOOL_TIMEOUT", "La consulta superó el tiempo máximo.", retryable=True
                )
            else:
                error = ExecutionError(
                    "TOOL_UNAVAILABLE", "El origen de datos no está disponible.", retryable=True
                )
        except asyncio.CancelledError:
            error = ExecutionError("RUN_TIMEOUT", "La ejecución alcanzó su tiempo máximo.")
            raise
        except Exception:
            error = ExecutionError(
                "TOOL_UNAVAILABLE", "La herramienta no está disponible.", retryable=True
            )
        finally:
            references = []
            if result:
                references = (
                    [result["invoice_id"]]
                    if "invoice_id" in result
                    else [item["reference"] for item in result["evidence"]]
                    if "evidence" in result
                    else [f"{item['id']}@{item['version']}" for item in result["items"]]
                )
            ctx.session.add(
                ToolCall(
                    id=f"call-{uuid4().hex}",
                    run_id=ctx.run.id,
                    tool_id=tool_id,
                    tool_version=pinned["version"] if pinned else "unknown",
                    arguments=safe_arguments,
                    result_references=references,
                    attempt=attempt,
                    status="completed"
                    if error is None
                    else "denied"
                    if error.status == "denied"
                    else "failed",
                    error_code=error.code if error else None,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    duration_ms=max(0, int((monotonic() - start) * 1000)),
                )
            )
            ctx.session.commit()
        if error is None:
            return result
        if not error.retryable or attempt > max_retries:
            raise error
        await asyncio.sleep(min(0.1 * 2 ** (attempt - 1), ctx.remaining_seconds()))
    raise ExecutionError("TOOL_UNAVAILABLE", "No se pudo completar la herramienta.")
