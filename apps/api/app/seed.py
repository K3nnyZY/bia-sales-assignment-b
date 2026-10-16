"""Explicit, idempotent local synthetic identities and catalogs; never production data."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.catalogs.models import Model, Tool
from app.catalogs.schemas import ModelCreate, ToolCreate
from app.core.config import Settings
from app.db.session import build_engine
from app.identity.auth import hash_token
from app.identity.models import User

MODEL_DEFAULT = {
    "provider": "synthetic",
    "release": "demo-1",
    "capabilities": ["chat", "tool_calling", "structured_output"],
    "context_window": 16000,
    "max_output_tokens": 4000,
    "data_policy": "Synthetic catalog entry only; no provider is connected.",
}
INVOICE_SCHEMA = {
    "type": "object",
    "properties": {"invoice_id": {"type": "string", "minLength": 1}},
    "required": ["invoice_id"],
    "additionalProperties": False,
}


def seed(session: Session, tokens: dict[str, str]) -> None:
    if len(set(tokens.values())) != len(tokens) or any(
        len(token) < 24 for token in tokens.values()
    ):
        raise ValueError("Demo tokens must be distinct and contain at least 24 characters")
    for role, token in tokens.items():
        session.execute(
            insert(User)
            .values(
                id=f"demo-{role}",
                name=f"Demo {role}",
                role=role,
                permissions=[] if role == "viewer" else ["invoices:read"],
                token_hash=hash_token(token),
                active=True,
            )
            .on_conflict_do_nothing(index_elements=[User.id])
        )
    seed_catalogs(session)
    session.commit()


def seed_catalogs(session: Session) -> None:
    """Synthetic definitions only; never creates identities or access grants."""
    for profile, status in [
        ("economy", "approved"),
        ("balanced", "approved"),
        ("advanced", "pending"),
        ("restricted", "revoked"),
    ]:
        data = ModelCreate(
            **MODEL_DEFAULT,
            id=f"synthetic-{profile}-v1",
            name=f"Synthetic {profile}",
            model_identifier=f"synthetic/{profile}-v1",
            profile=profile,
            status=status,
        )
        session.execute(
            insert(Model)
            .values(**data.model_dump())
            .on_conflict_do_nothing(index_elements=[Model.id])
        )
    for tool_id, name, version, status, permission, operation in [
        ("invoice-read-v1", "get_customer_invoice", "1.0.0", "approved", "invoices:read", "read"),
        ("invoice-read-v2", "get_customer_invoice", "2.0.0", "pending", "invoices:read", "read"),
        ("invoice-export-v1", "export_invoice", "1.0.0", "approved", "invoices:export", "read"),
        ("invoice-write-v1", "write_invoice", "1.0.0", "approved", "invoices:write", "write"),
        ("invoice-legacy-v1", "legacy_invoice", "1.0.0", "revoked", "invoices:read", "read"),
    ]:
        data = ToolCreate(
            id=tool_id,
            name=name,
            version=version,
            description="Synthetic contract only; no tool execution is implemented.",
            input_schema=INVOICE_SCHEMA,
            output_schema=INVOICE_SCHEMA,
            permissions=[permission],
            operation=operation,
            status=status,
        )
        session.execute(
            insert(Tool)
            .values(**data.model_dump())
            .on_conflict_do_nothing(index_elements=[Tool.id])
        )


def main() -> None:
    settings = Settings()
    if settings.app_env not in {"development", "test"} or not settings.enable_demo_auth:
        raise SystemExit("Seeding requires development/test and ENABLE_DEMO_AUTH=true")
    secrets = {
        "administrator": settings.demo_admin_token,
        "creator": settings.demo_creator_token,
        "viewer": settings.demo_viewer_token,
    }
    if any(value is None for value in secrets.values()):
        raise SystemExit("Set all DEMO_*_TOKEN variables before seeding")
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            seed(session, {role: value.get_secret_value() for role, value in secrets.items()})
    finally:
        engine.dispose()
    print("Synthetic identities and catalogs seeded; existing records preserved.")


if __name__ == "__main__":
    main()
