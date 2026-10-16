from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("owner_id", "period"),
        CheckConstraint(
            "consumption_kwh >= 0 AND unit_rate_cop >= 0 AND charge_cop >= 0",
            name="nonnegative_amounts",
        ),
        CheckConstraint("extract(day FROM period) = 1", name="monthly_period"),
        CheckConstraint(
            "charge_cop = round(consumption_kwh * unit_rate_cop, 2)", name="consumption_charge"
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    period: Mapped[date] = mapped_column(Date)
    consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_rate_cop: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    charge_cop: Mapped[Decimal] = mapped_column(Numeric(18, 2))


class BillingKnowledge(Base):
    __tablename__ = "billing_knowledge"
    __table_args__ = (
        CheckConstraint("kind IN ('tariff','faq')", name="kind"),
        CheckConstraint("status IN ('pending','approved','revoked')", name="status"),
        CheckConstraint("valid_to >= valid_from", name="validity"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
