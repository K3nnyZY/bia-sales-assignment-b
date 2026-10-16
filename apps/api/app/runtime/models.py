from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InvocationGrant(Base):
    """Trusted local execution entitlement, independent of editable agent manifests."""

    __tablename__ = "agent_invocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
    )
    agent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('running','completed','denied','failed','escalated')", name="status"
        ),
        CheckConstraint("mode IN ('deterministic','provider')", name="mode"),
        CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="input_tokens"),
        CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="output_tokens"),
        CheckConstraint("estimated_cost_usd IS NULL OR estimated_cost_usd >= 0", name="cost"),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) OR "
            "(status <> 'running' AND completed_at IS NOT NULL)",
            name="completion",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80))
    version_number: Mapped[int] = mapped_column(Integer)
    caller_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id", ondelete="RESTRICT"))
    config_hash: Mapped[str] = mapped_column(String(64))
    workflow_version: Mapped[str] = mapped_column(String(40), default="billing_workflow_v1:1.0.0")
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="running")
    answer: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    calculations: Mapped[dict] = mapped_column(JSONB, default=dict)
    references: Mapped[list[str]] = mapped_column(JSONB, default=list)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint("status IN ('completed','denied','failed')", name="status"),
        CheckConstraint("duration_ms >= 0 AND attempt > 0", name="measurements"),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), index=True
    )
    tool_id: Mapped[str] = mapped_column(ForeignKey("tools.id", ondelete="RESTRICT"))
    tool_version: Mapped[str] = mapped_column(String(32))
    arguments: Mapped[dict] = mapped_column(JSONB)
    result_references: Mapped[list[str]] = mapped_column(JSONB, default=list)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (CheckConstraint("duration_ms >= 0 AND step >= 0", name="measurements"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), index=True
    )
    step: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
