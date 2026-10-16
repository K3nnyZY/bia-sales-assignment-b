from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentVersion
from app.agents.schemas import AgentConfiguration
from app.agents.service import configuration_hash, owner_for, validate_configuration
from app.billing.contracts import ADAPTERS
from app.billing.models import BillingKnowledge, Invoice
from app.catalogs.models import Model, Tool
from app.catalogs.schemas import ModelCreate, ToolCreate
from app.governance.models import Approval, EvaluationRun, EvaluationSuite, VersionGovernance
from app.governance.schemas import REQUIRED_CHECKS, RUNNER_VERSION, GateRead
from app.governance.seed import EVAL_PRINCIPALS, FIXTURES
from app.identity.models import User


def validate_snapshot(session: Session, version: AgentVersion) -> None:
    if (
        version.status != "snapshot"
        or not version.snapshot
        or configuration_hash(version.snapshot) != version.config_hash
    ):
        raise ValueError("EXACT_SNAPSHOT_REQUIRED")
    config = AgentConfiguration.model_validate(version.configuration)
    if config.workflow is None:
        raise ValueError("WORKFLOW_REQUIRED")
    agent = session.get(Agent, version.agent_id)
    if agent is None or agent.owner_id != version.snapshot["agent"]["owner_id"]:
        raise ValueError("AGENT_OWNER_CHANGED")
    owner = owner_for(session, version.snapshot["agent"]["owner_id"])
    _, model, tools = validate_configuration(session, config, owner)
    if ModelCreate.model_validate(model).model_dump(mode="json") != version.snapshot["model"]:
        raise ValueError("MODEL_DEFINITION_CHANGED")
    current = [ToolCreate.model_validate(t).model_dump(mode="json") for t in tools]
    if current != version.snapshot["tools"]:
        raise ValueError("TOOL_DEFINITION_CHANGED")
    from app.knowledge.runtime import RAG_ADAPTER, RAG_TOOL_ID

    adapters = {**ADAPTERS, RAG_TOOL_ID: RAG_ADAPTER}
    required = (
        (set(ADAPTERS) - {"billing-knowledge-v1"}) | {RAG_TOOL_ID}
        if config.knowledge
        else set(ADAPTERS)
    )
    if not required <= set(config.tool_ids):
        raise ValueError("BILLING_ADAPTERS_REQUIRED")
    for tool in tools:
        adapter = adapters.get(tool.id)
        if (
            adapter is None
            or (tool.name, tool.version) != adapter[:2]
            or tool.input_schema != adapter[2].model_json_schema()
            or tool.output_schema != adapter[3].model_json_schema(mode="serialization")
        ):
            raise ValueError("UNREGISTERED_ADAPTER")
    if config.limits.max_steps < 9 or config.limits.max_tool_calls < 3:
        raise ValueError("INSUFFICIENT_EXECUTION_BUDGET")


def environment_hash(session: Session, version: AgentVersion) -> str:
    """Hash only the controlled test fixtures and actual catalog/source dependencies."""
    owner = session.get(User, version.snapshot["agent"]["owner_id"])
    model = session.get(Model, version.model_id)
    tools = session.scalars(
        select(Tool)
        .where(Tool.id.in_(version.configuration["tool_ids"]))
        .order_by(Tool.id)
        .with_for_update(read=True)
    ).all()
    invoices = session.scalars(
        select(Invoice)
        .where(Invoice.id.in_([row[0] for row in FIXTURES]))
        .order_by(Invoice.id)
        .with_for_update(read=True)
    ).all()
    principals = session.scalars(
        select(User)
        .where(User.id.in_(EVAL_PRINCIPALS))
        .order_by(User.id)
        .with_for_update(read=True)
    ).all()
    knowledge = session.scalars(
        select(BillingKnowledge)
        .where(
            BillingKnowledge.status == "approved",
            BillingKnowledge.valid_from <= date(2026, 9, 1),
            BillingKnowledge.valid_to >= date(2026, 9, 1),
        )
        .order_by(BillingKnowledge.id, BillingKnowledge.version)
        .with_for_update(read=True)
    ).all()
    payload = {
        "owner": None
        if owner is None
        else [owner.id, owner.active, owner.role, sorted(owner.permissions)],
        "model": None
        if model is None
        else ModelCreate.model_validate(model).model_dump(mode="json"),
        "tools": [ToolCreate.model_validate(t).model_dump(mode="json") for t in tools],
        "fixtures": [
            [
                i.id,
                i.owner_id,
                i.period.isoformat(),
                str(i.consumption_kwh),
                str(i.unit_rate_cop),
                str(i.charge_cop),
            ]
            for i in invoices
        ],
        "principals": [[u.id, u.active, u.role, sorted(u.permissions)] for u in principals],
        "knowledge": [
            [
                k.id,
                k.version,
                k.kind,
                k.title,
                k.content,
                k.valid_from.isoformat(),
                k.valid_to.isoformat(),
            ]
            for k in knowledge
        ],
    }
    if version.configuration.get("knowledge"):
        from app.knowledge.models import KnowledgeCollection, KnowledgeGrant
        from app.knowledge.service import pinned_documents

        selection = AgentConfiguration.model_validate(version.configuration).knowledge
        pinned = pinned_documents(session, selection, owner.id)
        if pinned != version.snapshot.get("knowledge"):
            raise ValueError("KNOWLEDGE_CHANGED")
        ids = sorted({d["collection_id"] for d in pinned})
        payload["rag"] = {
            "documents": pinned,
            "collections": [
                [c.id, c.enabled, c.classification]
                for c in session.scalars(
                    select(KnowledgeCollection)
                    .where(KnowledgeCollection.id.in_(ids))
                    .order_by(KnowledgeCollection.id)
                )
            ],
            "grants": [
                [g.collection_id, g.user_id, g.clearance, g.enabled]
                for g in session.scalars(
                    select(KnowledgeGrant)
                    .where(
                        KnowledgeGrant.collection_id.in_(ids),
                        KnowledgeGrant.user_id.in_(set(EVAL_PRINCIPALS) | {owner.id}),
                    )
                    .order_by(KnowledgeGrant.collection_id, KnowledgeGrant.user_id)
                )
            ],
        }
    return configuration_hash(payload)


def gate(session: Session, version: AgentVersion, *, require_approval: bool = False) -> GateRead:
    reasons = []
    try:
        validate_snapshot(session, version)
    except Exception:
        reasons.append("INVALID_OR_REVOKED_CONFIGURATION")
    lifecycle = session.get(VersionGovernance, (version.agent_id, version.number))
    evaluation = (
        session.get(EvaluationRun, lifecycle.latest_evaluation_id)
        if lifecycle and lifecycle.latest_evaluation_id
        else None
    )
    if evaluation is None:
        reasons.append("EVALUATION_REQUIRED")
    else:
        suite = session.get(EvaluationSuite, (evaluation.suite_id, evaluation.suite_version))
        if (evaluation.agent_id, evaluation.version_number, evaluation.config_hash) != (
            version.agent_id,
            version.number,
            version.config_hash,
        ):
            reasons.append("EVALUATION_HASH_MISMATCH")
        if (
            evaluation.status != "passed"
            or evaluation.critical_failures
            or evaluation.passed_count != evaluation.total
        ):
            reasons.append("EVALUATION_NOT_PASSED")
        if evaluation.runner_version != RUNNER_VERSION:
            reasons.append("EVALUATOR_VERSION_CHANGED")
        if (
            suite is None
            or suite.suite_hash != evaluation.suite_hash
            or not REQUIRED_CHECKS <= set(suite.checks)
        ):
            reasons.append("MANDATORY_CHECKS_MISSING")
        try:
            if evaluation.environment_hash != environment_hash(session, version):
                reasons.append("EVALUATED_DEPENDENCIES_CHANGED")
        except Exception:
            reasons.append("EVALUATED_DEPENDENCIES_UNAVAILABLE")
    if require_approval:
        approval = (
            session.get(Approval, lifecycle.approval_id)
            if lifecycle and lifecycle.approval_id
            else None
        )
        if not approval or approval.status != "approved":
            reasons.append("APPROVAL_REQUIRED")
        elif (
            evaluation is None
            or approval.evaluation_id != evaluation.id
            or approval.config_hash != version.config_hash
        ):
            reasons.append("APPROVAL_HASH_MISMATCH")
    return GateRead(
        eligible=not reasons,
        reasons=reasons,
        config_hash=version.config_hash or "",
        evaluation_id=evaluation.id if evaluation else None,
    )
