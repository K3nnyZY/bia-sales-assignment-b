from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvaluationSuite(Base):
    __tablename__ = "evaluation_suites"
    __table_args__ = (CheckConstraint("version > 0", name="version"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    checks: Mapped[list[str]] = mapped_column(JSONB)
    suite_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["suite_id", "suite_version"],
            ["evaluation_suites.id", "evaluation_suites.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('running','passed','failed','error')", name="status"),
        CheckConstraint("mode IN ('deterministic','provider')", name="mode"),
        CheckConstraint(
            "total > 0 AND passed_count >= 0 AND passed_count <= total "
            "AND critical_failures >= 0 AND critical_failures <= total",
            name="counts",
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) OR "
            "(status <> 'running' AND completed_at IS NOT NULL)",
            name="completion",
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64))
    suite_id: Mapped[str] = mapped_column(String(80))
    suite_version: Mapped[int] = mapped_column(Integer)
    suite_hash: Mapped[str] = mapped_column(String(64))
    environment_hash: Mapped[str] = mapped_column(String(64))
    runner_version: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(16))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="running")
    total: Mapped[int] = mapped_column(Integer)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_failures: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (CheckConstraint("duration_ms >= 0", name="duration"),)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT"), primary_key=True
    )
    check: Mapped[str] = mapped_column(String(40), primary_key=True)
    critical: Mapped[bool] = mapped_column(Boolean)
    passed: Mapped[bool] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSONB)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="RESTRICT"))
    duration_ms: Mapped[int] = mapped_column(Integer)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('pending','approved','rejected')", name="status"),
        CheckConstraint(
            "(status = 'pending' AND decided_by IS NULL AND decided_at IS NULL) OR "
            "(status <> 'pending' AND decided_by IS NOT NULL "
            "AND decided_at IS NOT NULL AND decided_by <> requested_by)",
            name="decision",
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT")
    )
    config_hash: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VersionGovernance(Base):
    __tablename__ = "version_governance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "stage IN ('draft','testing','pending_approval','approved',"
            "'published','deprecated','disabled')",
            name="stage",
        ),
        CheckConstraint("revision > 0", name="revision"),
    )
    agent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_hash: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(24), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    latest_evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="RESTRICT")
    )
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id", ondelete="RESTRICT"))
    ever_published: Mapped[bool] = mapped_column(Boolean, default=False)


class Publication(Base):
    __tablename__ = "agent_publications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["version_governance.agent_id", "version_governance.version_number"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision > 0", name="revision"),
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), primary_key=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(80))
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), index=True
    )
    version_number: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
