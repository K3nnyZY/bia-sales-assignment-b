from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider", "model_identifier", "release"),
        CheckConstraint("status IN ('pending','approved','revoked')", name="status"),
        CheckConstraint(
            "profile IN ('economy','balanced','advanced','restricted')", name="profile"
        ),
        CheckConstraint(
            "max_output_tokens > 0 AND context_window >= max_output_tokens", name="token_limits"
        ),
        CheckConstraint(
            "input_cost_per_million >= 0 AND output_cost_per_million >= 0", name="nonnegative_cost"
        ),
        CheckConstraint("jsonb_typeof(capabilities) = 'array'", name="capabilities_array"),
        Index(
            "uq_models_approved_profile",
            "profile",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(80))
    model_identifier: Mapped[str] = mapped_column(String(160))
    release: Mapped[str] = mapped_column(String(80))
    profile: Mapped[str] = mapped_column(String(24))
    capabilities: Mapped[list[str]] = mapped_column(JSONB)
    context_window: Mapped[int] = mapped_column(Integer)
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    input_cost_per_million: Mapped[Decimal] = mapped_column(Numeric(16, 6))
    output_cost_per_million: Mapped[Decimal] = mapped_column(Numeric(16, 6))
    data_policy: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")


class Tool(Base):
    __tablename__ = "tools"
    __table_args__ = (
        UniqueConstraint("name", "version"),
        CheckConstraint("status IN ('pending','approved','revoked')", name="status"),
        CheckConstraint("operation IN ('read','write')", name="operation"),
        CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 120 AND max_retries BETWEEN 0 AND 3",
            name="execution_limits",
        ),
        CheckConstraint(
            "jsonb_typeof(input_schema) = 'object' AND jsonb_typeof(output_schema) = 'object'",
            name="schemas_object",
        ),
        CheckConstraint("jsonb_typeof(permissions) = 'array'", name="permissions_array"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    input_schema: Mapped[dict] = mapped_column(JSONB)
    output_schema: Mapped[dict] = mapped_column(JSONB)
    permissions: Mapped[list[str]] = mapped_column(JSONB)
    operation: Mapped[str] = mapped_column(String(8))
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    requires_resource_authorization: Mapped[bool] = mapped_column(Boolean, default=True)
    audit_required: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
