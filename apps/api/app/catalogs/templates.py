"""Registration contracts for implemented adapters; no data or permission changes."""

from app.billing.contracts import ADAPTERS
from app.catalogs.schemas import ToolCreate
from app.knowledge.runtime import RAG_ADAPTER, RAG_TOOL_ID


def tool_templates() -> list[ToolCreate]:
    descriptions = {
        "invoice-lookup-v3": "Consultar la factura autorizada del cliente autenticado.",
        "invoice-previous-v1": "Consultar el período anterior de una factura autorizada.",
        "billing-knowledge-v1": "Consultar tarifas y FAQ sintéticas aprobadas del catálogo legacy.",
        RAG_TOOL_ID: "Recuperar evidencia autorizada mediante RAG y referencias fijadas.",
    }
    result = []
    for tool_id, (name, version, input_type, output_type) in (
        ADAPTERS | {RAG_TOOL_ID: RAG_ADAPTER}
    ).items():
        rag = tool_id == RAG_TOOL_ID
        result.append(
            ToolCreate(
                id=tool_id,
                name=name,
                version=version,
                description=descriptions[tool_id],
                input_schema=input_type.model_json_schema(),
                output_schema=output_type.model_json_schema(mode="serialization"),
                permissions=["invoices:read"],
                operation="read",
                timeout_seconds=5 if rag else 1,
                max_retries=0 if rag else 1,
                requires_resource_authorization=True,
                audit_required=True,
                status="pending",
            )
        )
    return result
