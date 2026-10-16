from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.catalogs.schemas import Contract, Identifier, Name

CheckName = Literal[
    "configuration",
    "invoice",
    "comparison",
    "knowledge",
    "cross_customer",
    "prompt_injection",
    "missing_invoice",
    "tool_permission",
    "missing_previous",
]
REQUIRED_CHECKS = frozenset(
    {
        "configuration",
        "invoice",
        "comparison",
        "knowledge",
        "cross_customer",
        "prompt_injection",
        "missing_invoice",
        "tool_permission",
    }
)
RUNNER_VERSION = "billing-evaluator-v1"


class SuiteCreate(Contract):
    id: Identifier
    version: Annotated[int, Field(ge=1)]
    name: Name
    description: Annotated[str, Field(max_length=4000)] = ""
    checks: Annotated[list[CheckName], Field(min_length=1, max_length=12)]

    @model_validator(mode="after")
    def distinct_checks(self):
        if len(self.checks) != len(set(self.checks)):
            raise ValueError("Duplicate checks")
        return self


class SuiteRead(SuiteCreate):
    suite_hash: str
    created_by: str
    created_at: datetime


class EvaluateRequest(Contract):
    suite_id: Identifier = "billing-runtime"
    suite_version: Annotated[int, Field(ge=1)] = 1
    mode: Literal["deterministic", "provider"] = "deterministic"
    expected_config_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class GovernanceAction(Contract):
    expected_revision: Annotated[int, Field(ge=1)]
    expected_config_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class DecisionRequest(GovernanceAction):
    decision: Literal["approved", "rejected"]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class PublishRequest(GovernanceAction):
    expected_publication_revision: Annotated[int, Field(ge=0)]


class RollbackRequest(Contract):
    target_version: Annotated[int, Field(ge=1)]
    expected_publication_revision: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class InvocationRequest(Contract):
    user_id: Identifier
    enabled: bool
    reason: Annotated[str, Field(min_length=1, max_length=2000)]


class EvaluationRead(Contract):
    id: str
    agent_id: str
    version_number: int
    config_hash: str
    suite_id: str
    suite_version: int
    suite_hash: str
    environment_hash: str
    runner_version: str
    mode: str
    requested_by: str
    status: str
    total: int
    passed_count: int
    critical_failures: int
    started_at: datetime
    completed_at: datetime | None


class ResultRead(Contract):
    check: str
    critical: bool
    passed: bool
    error_code: str | None
    details: dict
    run_id: str | None
    duration_ms: int


class EvaluationDetail(Contract):
    evaluation: EvaluationRead
    results: list[ResultRead]


class ApprovalRead(Contract):
    id: str
    agent_id: str
    version_number: int
    evaluation_id: str
    config_hash: str
    requested_by: str
    status: str
    decided_by: str | None
    reason: str
    requested_at: datetime
    decided_at: datetime | None


class GateRead(Contract):
    eligible: bool
    reasons: list[str]
    config_hash: str
    evaluation_id: str | None
    runner_version: str = RUNNER_VERSION


class GovernanceRead(Contract):
    agent_id: str
    version_number: int
    config_hash: str
    stage: str
    revision: int
    latest_evaluation_id: str | None
    approval_id: str | None
    ever_published: bool
    publication_version: int | None
    publication_revision: int
    publication_enabled: bool
    gate: GateRead


class AuditRead(Contract):
    id: str
    actor_id: str
    action: str
    agent_id: str | None
    version_number: int | None
    details: dict
    created_at: datetime


class ModelMetrics(Contract):
    model_id: str
    mode: str
    runs: int
    input_tokens: int | None
    output_tokens: int | None
    input_tokens_known_runs: int
    output_tokens_known_runs: int
    estimated_cost_usd: str | None
    cost_known_runs: int


class MetricsRead(Contract):
    runs: int
    completed: int
    failed: int
    denied: int
    escalated: int
    running: int
    latency_avg_ms: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    tool_calls: int
    tool_errors: int
    models: list[ModelMetrics]
    scope: str
    evaluation_runs_excluded: bool
    cost_kind: str
    missing_values: str
