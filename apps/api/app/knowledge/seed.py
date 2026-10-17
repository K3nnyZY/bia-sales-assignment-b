"""Idempotent local synthetic RAG demo. Never restores revoked grants or documents."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentVersion
from app.agents.schemas import AgentConfiguration, VersionCreate
from app.agents.service import create_version, freeze_version
from app.catalogs.models import Tool
from app.core.config import Settings
from app.db.session import build_engine
from app.governance.seed import EVAL_PRINCIPALS
from app.identity.models import User
from app.knowledge.models import (
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeGrant,
    KnowledgeVersion,
)
from app.knowledge.runtime import RAG_ADAPTER, RAG_TOOL_ID
from app.knowledge.service import ingest, upload
from app.runtime.models import InvocationGrant

SOURCES = [
    (
        "billing-tariffs-rag",
        "Tarifas sintéticas 2026",
        "# Tarifas sintéticas\nEn agosto de 2026 la tarifa es 800 COP/kWh y en septiembre "
        "820 COP/kWh. El cargo por consumo es kWh multiplicado por tarifa. "
        "Estos valores son exclusivamente de demostración.",
    ),
    (
        "billing-faq-rag",
        "FAQ de facturación sintética",
        "# Preguntas frecuentes\nEl cargo por consumo combina consumo y tarifa del período. "
        "Más consumo o una tarifa mayor pueden aumentar la factura. Esta demostración "
        "no incluye impuestos, cargos fijos ni otros conceptos. Para comparar se usa "
        "la factura del mes calendario anterior. No existen escrituras financieras.",
    ),
]


def seed_knowledge(session: Session, settings: Settings) -> int:
    owner = session.get(User, "demo-creator")
    admin = session.get(User, "demo-administrator")
    if not owner or not admin:
        raise ValueError("Run base, runtime and governance seeds first")
    coll = session.get(KnowledgeCollection, "billing-reference")
    if coll is None:
        session.add(
            KnowledgeCollection(
                id="billing-reference",
                name="Billing · tarifas y FAQ sintéticas",
                owner_id=owner.id,
                classification="internal",
            )
        )
        session.flush()
    for uid in sorted({owner.id, admin.id, "demo-customer-b"} | set(EVAL_PRINCIPALS)):
        if session.get(User, uid):
            session.execute(
                insert(KnowledgeGrant)
                .values(
                    collection_id="billing-reference",
                    user_id=uid,
                    clearance="internal",
                    enabled=True,
                )
                .on_conflict_do_nothing(
                    index_elements=[KnowledgeGrant.collection_id, KnowledgeGrant.user_id]
                )
            )
    references = seed_knowledge_data(session, settings, preserve_existing=False)
    session.flush()
    agent = session.scalar(select(Agent).where(Agent.id == "billing-assistant").with_for_update())
    base = session.scalar(
        select(AgentVersion)
        .where(
            AgentVersion.agent_id == agent.id,
            AgentVersion.status == "snapshot",
            AgentVersion.model_id == "synthetic-balanced-v1",
        )
        .order_by(AgentVersion.number)
        .limit(1)
    )
    config = dict(base.configuration)
    config["tool_ids"] = sorted(["invoice-lookup-v3", "invoice-previous-v1", RAG_TOOL_ID])
    config["knowledge"] = {"documents": references}
    found = next(
        (
            v
            for v in session.scalars(
                select(AgentVersion).where(
                    AgentVersion.agent_id == agent.id, AgentVersion.status == "snapshot"
                )
            )
            if v.configuration == config
        ),
        None,
    )
    if found is None:
        found = create_version(
            session,
            agent,
            VersionCreate(
                configuration=AgentConfiguration.model_validate(config),
                source_version=base.number,
                expected_source_revision=base.revision,
            ),
            owner,
        )
        freeze_version(session, agent, found)
    for uid in [owner.id, "demo-customer-b"]:
        session.execute(
            insert(InvocationGrant)
            .values(agent_id=agent.id, version_number=found.number, user_id=uid, enabled=True)
            .on_conflict_do_nothing(
                index_elements=[
                    InvocationGrant.agent_id,
                    InvocationGrant.version_number,
                    InvocationGrant.user_id,
                ]
            )
        )
    number = found.number
    session.commit()
    return number


def seed_knowledge_data(
    session: Session, settings: Settings, *, preserve_existing: bool = True
) -> list[dict]:
    """Ingest synthetic documents/tool definition; never grant retrieval or invocation."""
    owner = session.get(User, "demo-creator")
    admin = session.get(User, "demo-administrator")
    if not owner or not admin:
        raise ValueError("Provision owner and administrative identity explicitly first")
    coll = session.get(KnowledgeCollection, "billing-reference")
    if coll is None:
        session.add(
            KnowledgeCollection(
                id="billing-reference",
                name="Billing · tarifas y FAQ sintéticas",
                owner_id=owner.id,
                classification="internal",
            )
        )
        session.flush()
    references = []
    for docid, title, content in SOURCES:
        doc = session.get(KnowledgeDocument, docid)
        if doc is None:
            doc = KnowledgeDocument(
                id=docid, collection_id="billing-reference", title=title, owner_id=owner.id
            )
            session.add(doc)
            session.flush()
        if preserve_existing and doc.next_version > 1:
            ver = session.get(KnowledgeVersion, (docid, 1))
            if not ver or ver.status != "ready" or ver.approval != "approved":
                raise ValueError("Existing demo documents are preserved; review them explicitly")
            references.append({"document_id": docid, "version": ver.number})
            continue
        ver = upload(
            session,
            doc,
            content.encode(),
            docid + ".md",
            "synthetic://billing/" + docid,
            date(2026, 8, 1),
            date(2026, 12, 31),
            owner,
        )
        if ver.status in {"pending", "failed"}:
            ver = ingest(session, ver, settings, owner)
        if ver.status != "ready" or ver.approval == "revoked":
            raise ValueError(f"Document {docid} is unavailable ({ver.status}/{ver.approval})")
        if ver.approval == "pending":
            ver.approval, ver.approved_by = "approved", admin.id
            session.commit()
        references.append({"document_id": docid, "version": ver.number})
    name, toolversion, input_type, output_type = RAG_ADAPTER
    session.execute(
        insert(Tool)
        .values(
            id=RAG_TOOL_ID,
            name=name,
            version=toolversion,
            description="Retrieval híbrido autorizado de documentos fijados en el snapshot.",
            input_schema=input_type.model_json_schema(),
            output_schema=output_type.model_json_schema(mode="serialization"),
            permissions=["invoices:read"],
            operation="read",
            timeout_seconds=5,
            max_retries=0,
            requires_resource_authorization=True,
            audit_required=True,
            status="approved",
        )
        .on_conflict_do_nothing(index_elements=[Tool.id])
    )
    session.flush()
    return references


def main():
    settings = Settings()
    if (
        settings.app_env not in {"development", "test"}
        or not settings.enable_local_runtime
        or not settings.enable_demo_auth
    ):
        raise SystemExit("Explicit local demo/runtime configuration required")
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            number = seed_knowledge(session, settings)
    finally:
        engine.dispose()
    print(
        f"Knowledge demo ready: billing-assistant v{number}, "
        "local semantic embeddings; no LLM call."
    )


if __name__ == "__main__":
    main()
