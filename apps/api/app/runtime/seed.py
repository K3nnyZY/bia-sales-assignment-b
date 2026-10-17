"""Local runtime provisioning: explicit entitlements, synthetic invoices and frozen versions."""

import argparse
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentVersion
from app.agents.schemas import (
    AgentConfiguration,
    ExecutionLimits,
    ModelSelection,
    VersionCreate,
    WorkflowSelection,
)
from app.agents.service import create_version, freeze_version
from app.billing.contracts import ADAPTERS
from app.billing.models import BillingKnowledge, Invoice
from app.catalogs.models import Model, Tool
from app.catalogs.schemas import ToolCreate
from app.core.config import Settings
from app.db.session import build_engine
from app.identity.auth import hash_token
from app.identity.models import User
from app.runtime.models import InvocationGrant


def seed_runtime(
    session: Session, customer_b_token: str, model_id: str = "synthetic-balanced-v1"
) -> int:
    if len(customer_b_token) < 24:
        raise ValueError("Customer B demo token must contain at least 24 characters")
    owner = session.get(User, "demo-creator")
    if owner is None or not owner.active or "invoices:read" not in owner.permissions:
        raise ValueError("Seed base identities first; the creator needs invoices:read")
    session.execute(
        insert(User)
        .values(
            id="demo-customer-b",
            name="Synthetic customer B",
            role="viewer",
            permissions=["invoices:read"],
            token_hash=hash_token(customer_b_token),
            active=True,
        )
        .on_conflict_do_nothing(index_elements=[User.id])
    )
    number = seed_runtime_data(session, model_id)
    for user_id in [owner.id, "demo-customer-b"]:
        session.execute(
            insert(InvocationGrant)
            .values(
                agent_id="billing-assistant", version_number=number, user_id=user_id, enabled=True
            )
            .on_conflict_do_nothing(
                index_elements=[
                    InvocationGrant.agent_id,
                    InvocationGrant.version_number,
                    InvocationGrant.user_id,
                ]
            )
        )
    session.commit()
    return number


def seed_runtime_data(
    session: Session,
    model_id: str = "synthetic-balanced-v1",
) -> int:
    """Load synthetic billing data, without identities or invocation grants."""
    owner = session.get(User, "demo-creator")
    if owner is None or not owner.active or "invoices:read" not in owner.permissions:
        raise ValueError("Provision an active creator with invoices:read explicitly first")
    if session.get(User, "demo-customer-b") is None:
        raise ValueError("Provision synthetic customer B explicitly first")
    for tool_id, (name, version, input_type, output_type) in ADAPTERS.items():
        data = ToolCreate(
            id=tool_id,
            name=name,
            version=version,
            description="Synthetic billing adapter; scoped to the authenticated customer.",
            input_schema=input_type.model_json_schema(),
            output_schema=output_type.model_json_schema(mode="serialization"),
            permissions=["invoices:read"],
            operation="read",
            timeout_seconds=1,
            max_retries=1,
            requires_resource_authorization=True,
            audit_required=True,
            status="approved",
        )
        session.execute(
            insert(Tool)
            .values(**data.model_dump())
            .on_conflict_do_nothing(index_elements=[Tool.id])
        )
    for invoice_id, user_id, period, consumption, rate in [
        ("INV-1001", "demo-creator", date(2026, 8, 1), "350", "800"),
        ("INV-1002", "demo-creator", date(2026, 9, 1), "420", "820"),
        ("INV-2001", "demo-customer-b", date(2026, 8, 1), "120", "800"),
        ("INV-2002", "demo-customer-b", date(2026, 9, 1), "150", "820"),
    ]:
        session.execute(
            insert(Invoice)
            .values(
                id=invoice_id,
                owner_id=user_id,
                period=period,
                consumption_kwh=Decimal(consumption),
                unit_rate_cop=Decimal(rate),
                charge_cop=Decimal(consumption) * Decimal(rate),
            )
            .on_conflict_do_nothing(index_elements=[Invoice.id])
        )
    for doc_id, kind, title, content in [
        (
            "tariffs-2026-09",
            "tariff",
            "Tarifas sintéticas agosto/septiembre",
            "En este ejemplo hipotético la tarifa es 800 COP/kWh en agosto y "
            "820 COP/kWh en septiembre de 2026. Solo se incluyen cargos por consumo.",
        ),
        (
            "billing-faq",
            "faq",
            "Cómo cambia el cargo por consumo",
            "El cargo por consumo combina los kWh consumidos y la tarifa del período. "
            "Esta demostración no incluye impuestos, cargos fijos ni otros conceptos.",
        ),
    ]:
        session.execute(
            insert(BillingKnowledge)
            .values(
                id=doc_id,
                version="1.0.0",
                kind=kind,
                title=title,
                content=content,
                status="approved",
                valid_from=date(2026, 8, 1),
                valid_to=date(2026, 9, 30),
            )
            .on_conflict_do_nothing(index_elements=[BillingKnowledge.id, BillingKnowledge.version])
        )
    agent = session.scalar(select(Agent).where(Agent.id == "billing-assistant").with_for_update())
    if agent is None:
        agent = Agent(
            id="billing-assistant",
            name="Billing Assistant",
            description="Explica facturas sintéticas autorizadas con evidencia y cálculos Python.",
            department="customer_service",
            owner_id=owner.id,
        )
        session.add(agent)
        session.flush()
    if agent.owner_id != owner.id or agent.status != "draft":
        raise ValueError(
            "The existing billing-assistant must belong to demo-creator and be enabled as draft"
        )
    model = session.get(Model, model_id)
    if model is None or model.status != "approved":
        raise ValueError("Runtime seed requires an approved catalog model")
    config = AgentConfiguration(
        objective="Explicar facturas sintéticas autorizadas, comparar períodos "
        "y citar tarifas/FAQ vigentes.",
        instructions="Usar solo las herramientas aprobadas. Los cálculos monetarios "
        "los realiza Python y la identidad se resuelve en backend.",
        model=ModelSelection(
            model_id=model_id, max_output_tokens=min(2000, model.max_output_tokens)
        ),
        tool_ids=sorted(ADAPTERS),
        limits=ExecutionLimits(max_steps=12, max_tool_calls=5, timeout_seconds=30),
        workflow=WorkflowSelection(id="billing_workflow_v1"),
    )
    canonical = config.model_dump(mode="json", exclude_none=True)
    version = next(
        (
            row
            for row in session.scalars(
                select(AgentVersion)
                .where(AgentVersion.agent_id == agent.id, AgentVersion.status == "snapshot")
                .order_by(AgentVersion.number.desc())
            )
            if row.configuration == canonical
        ),
        None,
    )
    if version is None:
        source = session.scalar(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id, AgentVersion.status == "snapshot")
            .order_by(AgentVersion.number.desc())
            .limit(1)
        )
        spec = VersionCreate(
            configuration=config,
            **(
                {
                    "source_version": source.number,
                    "expected_source_revision": source.revision,
                }
                if source
                else {}
            ),
        )
        version = create_version(session, agent, spec, owner)
        freeze_version(session, agent, version)
    return version.number


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="synthetic-balanced-v1")
    args = parser.parse_args()
    settings = Settings()
    if (
        not settings.enable_local_runtime
        or not settings.enable_demo_auth
        or settings.app_env not in {"development", "test"}
    ):
        raise SystemExit("Explicit local runtime and demo authentication are required")
    if settings.demo_customer_b_token is None:
        raise SystemExit("Set DEMO_CUSTOMER_B_TOKEN before provisioning")
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            number = seed_runtime(
                session, settings.demo_customer_b_token.get_secret_value(), args.model_id
            )
    finally:
        engine.dispose()
    print(f"Local billing-assistant version {number} provisioned. Existing records preserved.")


if __name__ == "__main__":
    main()
