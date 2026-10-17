from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalogs.models import Model, Tool
from app.db.base import Base
from app.identity.models import User


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('draft','disabled','deprecated')", name="status"),
        CheckConstraint("next_version > 0 AND revision > 0", name="positive_counters"),
        CheckConstraint("deleted_at IS NULL OR status = 'deprecated'", name="deleted_state"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    department: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    owner: Mapped[User] = relationship()
    status: Mapped[str] = mapped_column(String(16), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    next_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def state(self) -> str:
        return self.status.upper()

    @property
    def initial_configuration(self) -> str | None:
        # Version numbers start at 1 and the API preserves version history.
        if self.next_version > 1:
            return f"/api/v1/agents/{self.id}/versions/1"
        return None


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "source_version"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("number > 0 AND revision > 0", name="positive_counters"),
        CheckConstraint(
            "source_version IS NULL OR source_version < number", name="source_precedes_version"
        ),
        CheckConstraint("status IN ('draft','snapshot','discarded')", name="status"),
        Index(
            "uq_agent_versions_active_draft",
            "agent_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
        CheckConstraint(
            "(status = 'discarded' AND discarded_at IS NOT NULL AND discard_reason IS NOT NULL) OR "
            "(status <> 'discarded' AND discarded_at IS NULL AND discard_reason IS NULL)",
            name="discard_state",
        ),
        CheckConstraint("jsonb_typeof(configuration) = 'object'", name="configuration_object"),
        CheckConstraint(
            "(status IN ('draft','discarded') AND snapshot IS NULL AND config_hash IS NULL) OR "
            "(status = 'snapshot' AND jsonb_typeof(snapshot) = 'object' "
            "AND snapshot IS NOT NULL AND config_hash IS NOT NULL "
            "AND config_hash ~ '^[a-f0-9]{64}$')",
            name="snapshot_state",
        ),
    )

    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id", ondelete="RESTRICT"), index=True)
    model: Mapped[Model] = relationship()
    configuration: Mapped[dict] = mapped_column(JSONB)
    snapshot: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discard_reason: Mapped[str | None] = mapped_column(String(80))


class AgentTool(Base):
    __tablename__ = "agent_tools"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "version_number"],
            ["agent_versions.agent_id", "agent_versions.number"],
            ondelete="RESTRICT",
        ),
    )

    agent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_id: Mapped[str] = mapped_column(
        ForeignKey("tools.id", ondelete="RESTRICT"), primary_key=True
    )
    tool: Mapped[Tool] = relationship()
