from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.billing.contracts import InvoiceId
from app.catalogs.schemas import Contract, Identifier


class RunCreate(Contract):
    agent_id: Identifier = "billing-assistant"
    version: Annotated[int, Field(ge=1)] = 1
    message: Annotated[str, Field(min_length=1, max_length=4000)]
    invoice_id: InvoiceId | None = None
    task: Literal["auto", "invoice", "compare", "knowledge"] = "auto"
    period: date = date(2026, 9, 1)
    mode: Literal["deterministic", "provider"] = "deterministic"


class RunRead(Contract):
    id: str
    agent_id: str
    version_number: int
    caller_id: str
    model_id: str
    config_hash: str
    workflow_version: str
    mode: Literal["deterministic", "provider"]
    status: Literal["running", "completed", "denied", "failed", "escalated"]
    answer: str | None
    error_code: str | None
    calculations: dict
    references: list[str]
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: Decimal | None
    started_at: datetime
    completed_at: datetime | None


class ToolCallRead(Contract):
    id: str
    tool_id: str
    tool_version: str
    arguments: dict
    result_references: list[str]
    attempt: int
    status: str
    error_code: str | None
    started_at: datetime
    completed_at: datetime
    duration_ms: int


class EventRead(Contract):
    step: int
    node: str
    status: str
    error_code: str | None
    started_at: datetime
    duration_ms: int


class TraceRead(Contract):
    run: RunRead
    events: list[EventRead]
    tool_calls: list[ToolCallRead]


class ExecutableVersion(Contract):
    agent_id: str
    name: str
    version: int
    model_id: str
    model_provider: str
    config_hash: str
    local_preview: Literal[True] = True
    available_modes: list[Literal["deterministic", "provider"]]
