"""Explicit model registration for Alembic and the application."""

from app.agents.models import Agent, AgentTool, AgentVersion
from app.billing.models import BillingKnowledge, Invoice
from app.catalogs.models import Model, Tool
from app.governance.models import (
    Approval,
    AuditEvent,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    Publication,
    VersionGovernance,
)
from app.identity.models import AccessToken, User
from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeGrant,
    KnowledgeObject,
    KnowledgeSearch,
    KnowledgeVersion,
)
from app.runtime.models import AgentRun, InvocationGrant, RunEvent, ToolCall

__all__ = [
    "KnowledgeCollection",
    "KnowledgeDocument",
    "KnowledgeGrant",
    "KnowledgeVersion",
    "KnowledgeChunk",
    "KnowledgeObject",
    "KnowledgeSearch",
    "Agent",
    "AgentTool",
    "AgentVersion",
    "Model",
    "Tool",
    "User",
    "AccessToken",
    "Invoice",
    "BillingKnowledge",
    "AgentRun",
    "InvocationGrant",
    "RunEvent",
    "ToolCall",
    "Approval",
    "AuditEvent",
    "EvaluationResult",
    "EvaluationRun",
    "EvaluationSuite",
    "Publication",
    "VersionGovernance",
]
