"""Explicit synthetic quality fixtures and local governance identities."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents.service import configuration_hash
from app.billing.models import Invoice
from app.core.config import Settings
from app.db.session import build_engine
from app.governance.models import EvaluationSuite
from app.governance.schemas import REQUIRED_CHECKS, SuiteCreate
from app.identity.auth import hash_token
from app.identity.models import User

EVAL_A = "evaluation-customer-a"
EVAL_B = "evaluation-customer-b"
EVAL_NO_PERMISSION = "evaluation-no-permission"
EVAL_PRINCIPALS = frozenset({EVAL_A, EVAL_B, EVAL_NO_PERMISSION})
FIXTURES = [
    ("INV-9001", EVAL_A, date(2026, 8, 1), "350", "800"),
    ("INV-9002", EVAL_A, date(2026, 9, 1), "420", "820"),
    ("INV-9101", EVAL_B, date(2026, 8, 1), "120", "800"),
    ("INV-9102", EVAL_B, date(2026, 9, 1), "150", "820"),
]


def provision_fixtures(session: Session) -> None:
    for uid in sorted(EVAL_PRINCIPALS):
        session.execute(
            insert(User)
            .values(
                id=uid,
                name="Isolated synthetic evaluation principal",
                role="viewer",
                permissions=[] if uid == EVAL_NO_PERMISSION else ["invoices:read"],
                token_hash=hash_token(uuid4().hex + uuid4().hex),
                active=True,
            )
            .on_conflict_do_nothing(index_elements=[User.id])
        )
    for iid, uid, period, consumption, rate in FIXTURES:
        session.execute(
            insert(Invoice)
            .values(
                id=iid,
                owner_id=uid,
                period=period,
                consumption_kwh=Decimal(consumption),
                unit_rate_cop=Decimal(rate),
                charge_cop=Decimal(consumption) * Decimal(rate),
            )
            .on_conflict_do_nothing(index_elements=[Invoice.id])
        )


def seed_governance(session: Session, tokens: dict[str, str]) -> None:
    for role, token in tokens.items():
        if role not in {"reviewer", "approver", "auditor"} or len(token) < 24:
            raise ValueError("Valid governance role and at least 24 token characters required")
        session.execute(
            insert(User)
            .values(
                id=f"demo-{role}",
                name=f"Synthetic {role}",
                role=role,
                permissions=[],
                token_hash=hash_token(token),
                active=True,
            )
            .on_conflict_do_nothing(index_elements=[User.id])
        )
    provision_fixtures(session)
    owner = session.scalar(select(User).where(User.id == "demo-administrator"))
    if owner is None:
        raise ValueError("Run the base identity seed first")
    spec = SuiteCreate(
        id="billing-runtime",
        version=1,
        name="Billing runtime and security baseline",
        description="Real StateGraph against isolated synthetic customers; "
        "deterministic checks, no LLM grader.",
        checks=sorted(REQUIRED_CHECKS | {"missing_previous"}),
    )
    data = spec.model_dump(mode="json")
    session.execute(
        insert(EvaluationSuite)
        .values(**data, suite_hash=configuration_hash(data), created_by=owner.id)
        .on_conflict_do_nothing(index_elements=[EvaluationSuite.id, EvaluationSuite.version])
    )
    session.commit()


def main() -> None:
    settings = Settings()
    if not settings.enable_demo_auth or settings.app_env not in {"development", "test"}:
        raise SystemExit(
            "Governance demo seeding requires explicit development/test authentication"
        )
    values = {
        "reviewer": settings.demo_reviewer_token,
        "approver": settings.demo_approver_token,
        "auditor": settings.demo_auditor_token,
    }
    if any(value is None for value in values.values()):
        raise SystemExit("Set DEMO_REVIEWER_TOKEN, DEMO_APPROVER_TOKEN and DEMO_AUDITOR_TOKEN")
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            seed_governance(
                session, {role: value.get_secret_value() for role, value in values.items()}
            )
    finally:
        engine.dispose()
    print(
        "Governance roles, immutable baseline suite and isolated fixtures seeded; "
        "existing records preserved."
    )


if __name__ == "__main__":
    main()
