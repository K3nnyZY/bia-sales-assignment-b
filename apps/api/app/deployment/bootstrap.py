"""Provision an isolated synthetic deployment from operator-supplied credential hashes."""

import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import build_engine
from app.governance.audit import record
from app.governance.seed import EVAL_PRINCIPALS, seed_governance
from app.identity.models import AccessToken, User
from app.knowledge.seed import seed_knowledge
from app.runtime.seed import seed_runtime
from app.seed import seed

ROLES = frozenset(
    {"administrator", "creator", "viewer", "customer-b", "reviewer", "approver", "auditor"}
)


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    user_id: str
    token_hash: str
    expires_at: datetime

    @field_validator("id")
    @classmethod
    def valid_id(cls, value):
        if not re.fullmatch(r"pat-[a-f0-9]{32}", value):
            raise ValueError("Invalid credential ID")
        return value

    @field_validator("token_hash")
    @classmethod
    def valid_hash(cls, value):
        if not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("Invalid credential hash")
        return value


def bootstrap(session: Session, settings: Settings, raw: dict) -> None:
    if not settings.enable_access_token_auth or settings.enable_demo_auth:
        raise ValueError("Private credential authentication is required")
    if set(raw) != ROLES:
        raise ValueError("The manifest must contain exactly the documented deployment roles")
    entries = {role: ManifestEntry.model_validate(data) for role, data in raw.items()}
    for role, item in entries.items():
        if item.user_id != "demo-" + role:
            raise ValueError("Unexpected synthetic principal")
        existing = session.get(AccessToken, item.id)
        if existing and (
            existing.token_hash != item.token_hash or existing.user_id != item.user_id
        ):
            raise ValueError("Credential ID conflict")
        if not existing and (
            item.expires_at.tzinfo is None
            or not datetime.now(UTC)
            < item.expires_at
            <= datetime.now(UTC) + timedelta(days=7, minutes=1)
        ):
            raise ValueError("New bootstrap credentials must expire within seven days")
    allowed = {"demo-" + role for role in ROLES} | set(EVAL_PRINCIPALS)
    if set(session.scalars(select(User.id))) - allowed:
        raise ValueError("Bootstrap is restricted to an isolated synthetic deployment")
    # Legacy token fields are random and discarded. Production authentication never reads them.
    seed(
        session,
        {role: secrets.token_urlsafe(32) for role in ["administrator", "creator", "viewer"]},
    )
    seed_runtime(session, secrets.token_urlsafe(32))
    seed_governance(
        session, {role: secrets.token_urlsafe(32) for role in ["reviewer", "approver", "auditor"]}
    )
    seed_knowledge(session, settings)
    for item in entries.values():
        if not session.get(AccessToken, item.id):
            session.add(AccessToken(**item.model_dump()))
            record(
                session,
                item.user_id,
                "identity.token_issued",
                token_id=item.id,
                issuer="deployment-bootstrap",
                expires_at=item.expires_at.isoformat(),
            )
    session.commit()


def main():
    raw = os.environ.get("BIA_BOOTSTRAP_MANIFEST")
    if not raw:
        print("No bootstrap manifest configured; no synthetic data or credentials provisioned.")
        return
    settings = Settings()
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            bootstrap(session, settings, json.loads(raw))
    finally:
        engine.dispose()
    print(
        "Synthetic deployment provisioned with expiring credentials; "
        "publication still requires independent approval."
    )


if __name__ == "__main__":
    main()
