"""Explicit offline provisioning for a synthetic deployment, never a public API."""

import argparse
import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentVersion
from app.billing.models import Invoice
from app.catalogs.models import Model, Tool
from app.core.config import Settings
from app.db.session import build_engine
from app.governance.audit import record
from app.governance.models import AuditEvent, EvaluationRun, EvaluationSuite
from app.governance.seed import (
    EVAL_PRINCIPALS,
    provision_evaluation_principals,
    seed_governance_data,
)
from app.identity.auth import hash_token
from app.identity.models import AccessToken, User
from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeVersion,
)
from app.knowledge.seed import SOURCES, seed_knowledge_data
from app.runtime.seed import seed_runtime_data
from app.seed import seed_catalogs

DATASET = "billing-demo-v1"
ROLES = frozenset(
    {"administrator", "creator", "viewer", "customer-b", "reviewer", "approver", "auditor"}
)
LOCK_ID = 398216401  # One transaction-scoped lock for this small bootstrap dataset.


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    user_id: str
    role: str
    permissions: list[str]
    token_hash: str
    expires_at: datetime

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not re.fullmatch(r"pat-[a-f0-9]{32}", value):
            raise ValueError("Invalid credential ID")
        return value

    @field_validator("token_hash")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("Invalid credential hash")
        return value


def require_private_auth(settings: Settings) -> None:
    if (
        not settings.enable_access_token_auth
        or settings.enable_demo_auth
        or settings.enable_local_runtime
    ):
        raise ValueError(
            "Private authentication with demo authentication/local runtime disabled is required"
        )


def receipt(session: Session, action: str) -> AuditEvent | None:
    return session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == action, AuditEvent.details["dataset"].astext == DATASET)
        .order_by(AuditEvent.created_at)
        .limit(1)
    )


def provision_identities(session: Session, settings: Settings, raw: dict) -> None:
    """Explicit operator action: fixed roles/permissions must be declared in the manifest."""
    require_private_auth(settings)
    if set(raw) != ROLES:
        raise ValueError("The manifest must explicitly declare all documented deployment roles")
    entries = {role: ManifestEntry.model_validate(data) for role, data in raw.items()}
    if len({item.id for item in entries.values()}) != len(entries) or len(
        {item.token_hash for item in entries.values()}
    ) != len(entries):
        raise ValueError("Credential IDs and hashes must be distinct")
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_ID})
    for role, item in entries.items():
        expected_role = "viewer" if role == "customer-b" else role
        expected_permissions = ["invoices:read"] if role in {"creator", "customer-b"} else []
        if (
            item.user_id != "demo-" + role
            or item.role != expected_role
            or item.permissions != expected_permissions
        ):
            raise ValueError(
                "Only explicitly declared least-privilege synthetic identities are allowed"
            )
        user = session.get(User, item.user_id)
        existing = session.get(AccessToken, item.id)
        if user or existing:
            if not (
                user
                and existing
                and existing.user_id == item.user_id
                and existing.token_hash == item.token_hash
                and existing.expires_at == item.expires_at
            ):
                raise ValueError(
                    "Existing identity/credential collision; use managed rotation, never overwrite"
                )
            continue  # Never reactivate, regrant, rotate or extend an existing credential.
        if item.expires_at.tzinfo is None or not datetime.now(
            UTC
        ) < item.expires_at <= datetime.now(UTC) + timedelta(days=7):
            raise ValueError("New bootstrap credentials must expire within seven days")
    # Complete preflight before creating any row, including internal evaluation identities.
    for uid in EVAL_PRINCIPALS:
        existing = session.get(User, uid)
        expected = [] if uid == "evaluation-no-permission" else ["invoices:read"]
        if existing and (existing.role != "viewer" or existing.permissions != expected):
            raise ValueError("Existing evaluation principal is incompatible; no privileges changed")
    for item in entries.values():
        if session.get(AccessToken, item.id):
            continue
        session.add(
            User(
                id=item.user_id,
                name="Synthetic " + item.role,
                role=item.role,
                permissions=item.permissions,
                token_hash=hash_token(secrets.token_urlsafe(32)),
                active=True,
            )
        )
        session.flush()
        session.add(AccessToken(**item.model_dump(exclude={"role", "permissions"})))
        record(
            session,
            item.user_id,
            "identity.token_issued",
            token_id=item.id,
            issuer="explicit-deployment-provisioning",
            expires_at=item.expires_at.isoformat(),
        )
    provision_evaluation_principals(session)
    if not receipt(session, "deployment.identities_provisioned"):
        record(
            session,
            "demo-administrator",
            "deployment.identities_provisioned",
            dataset=DATASET,
            user_ids=sorted(item.user_id for item in entries.values()),
        )
    session.flush()


def bootstrap(session: Session, settings: Settings) -> dict:
    """Load data only. Caller commits; all nested seed commits stay in its transaction."""
    require_private_auth(settings)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_ID})
    if receipt(session, "deployment.synthetic_loaded"):
        return {"dataset": DATASET, "already_initialized": True}
    for uid, role in [("demo-creator", "creator"), ("demo-administrator", "administrator")]:
        user = session.get(User, uid)
        if not user or not user.active or user.role != role:
            raise ValueError(
                "Provision compatible active identities explicitly before loading data"
            )
    if not set(EVAL_PRINCIPALS | {"demo-customer-b"}) <= set(session.scalars(select(User.id))):
        raise ValueError("Provision isolated synthetic principals before loading data")
    # Reserved resource collisions require operator review, never repairs or new versions.
    if (
        session.get(Agent, "billing-assistant")
        or session.get(KnowledgeCollection, "billing-reference")
        or any(session.get(KnowledgeDocument, source[0]) for source in SOURCES)
    ):
        raise ValueError(
            "Reserved demo resources already exist without a bootstrap receipt; no data overwritten"
        )
    if session.scalar(
        select(Invoice.id)
        .where(
            Invoice.id.in_(
                [
                    "INV-1001",
                    "INV-1002",
                    "INV-2001",
                    "INV-2002",
                    "INV-9001",
                    "INV-9002",
                    "INV-9101",
                    "INV-9102",
                ]
            )
        )
        .limit(1)
    ):
        raise ValueError("Reserved synthetic invoices already exist; no data overwritten")

    try:
        # Existing service functions commit. Savepoints keep those commits inside our outer
        # transaction, so an embedding/ingestion failure rolls back the complete dataset.
        with Session(bind=session.connection(), join_transaction_mode="create_savepoint") as work:
            seed_catalogs(work)
            seed_runtime_data(work)
            seed_governance_data(work)
            seed_knowledge_data(work, settings)
            record(
                work,
                "demo-administrator",
                "deployment.synthetic_loaded",
                dataset=DATASET,
                agent_id_created="billing-assistant",
                grants_created=0,
                tokens_created=0,
            )
            work.commit()
    except Exception:
        session.rollback()
        raise
    return {"dataset": DATASET, "already_initialized": False}


def revoke_access(session: Session, settings: Settings) -> dict:
    require_private_auth(settings)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_ID})
    item = receipt(session, "deployment.identities_provisioned")
    if not item:
        raise ValueError("No managed demo identities found; refusing to revoke unrelated access")
    ids = item.details["user_ids"]
    changed = False
    for token in session.scalars(select(AccessToken).where(AccessToken.user_id.in_(ids))):
        if not token.revoked:
            token.revoked = True
            changed = True
    for user in session.scalars(select(User).where(User.id.in_(ids))):
        if user.active:
            user.active = False
            changed = True
    if changed:
        record(
            session,
            "demo-administrator",
            "deployment.access_revoked",
            dataset=DATASET,
            user_ids=ids,
        )
    session.flush()
    return {"dataset": DATASET, "access_revoked": True}


def status(session: Session) -> dict:
    """Counts/IDs only: never prints credential hashes or tokens."""
    return {
        "dataset": DATASET,
        "initialized": receipt(session, "deployment.synthetic_loaded") is not None,
        "principals_provisioned": receipt(session, "deployment.identities_provisioned") is not None,
        "catalog_models": session.scalar(select(func.count()).select_from(Model)),
        "catalog_tools": session.scalar(select(func.count()).select_from(Tool)),
        "knowledge_vectors": session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id.in_([s[0] for s in SOURCES]))
        ),
        "embedding_dimensions": session.scalar(
            select(func.min(func.vector_dims(KnowledgeChunk.embedding))).where(
                KnowledgeChunk.document_id.in_([s[0] for s in SOURCES])
            )
        ),
        "valid_demo_tokens": session.scalar(
            select(func.count())
            .select_from(AccessToken)
            .join(User)
            .where(
                User.id.in_(["demo-" + role for role in ROLES]),
                User.active.is_(True),
                AccessToken.revoked.is_(False),
                AccessToken.expires_at > func.now(),
            )
        ),
        "billing_versions": session.scalar(
            select(func.count())
            .select_from(AgentVersion)
            .where(AgentVersion.agent_id == "billing-assistant")
        ),
        "synthetic_invoices": session.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(
                Invoice.id.in_(
                    [
                        "INV-1001",
                        "INV-1002",
                        "INV-2001",
                        "INV-2002",
                        "INV-9001",
                        "INV-9002",
                        "INV-9101",
                        "INV-9102",
                    ]
                )
            )
        ),
        "evaluation_suites": session.scalar(
            select(func.count())
            .select_from(EvaluationSuite)
            .where(EvaluationSuite.id == "billing-runtime")
        ),
        "evaluation_runs": session.scalar(
            select(func.count())
            .select_from(EvaluationRun)
            .where(EvaluationRun.agent_id == "billing-assistant")
        ),
        "documents": [
            {
                "id": row.document_id,
                "version": row.number,
                "status": row.status,
                "approval": row.approval,
                "chunks": row.chunk_count,
                "embedding_version": row.embedding_version,
            }
            for row in session.scalars(
                select(KnowledgeVersion)
                .where(KnowledgeVersion.document_id.in_([s[0] for s in SOURCES]))
                .order_by(KnowledgeVersion.document_id, KnowledgeVersion.number)
            )
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["provision-identities", "load", "status", "revoke-access"]
    )
    parser.add_argument("--confirm-synthetic-demo", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.action != "status" and not args.confirm_synthetic_demo:
        parser.error(
            "Mutations require --confirm-synthetic-demo and trusted operator database access"
        )
    engine = None
    try:
        settings = Settings()
        engine = build_engine(settings)
        with Session(engine) as session:
            if args.action == "provision-identities":
                raw = (
                    args.manifest.read_text()
                    if args.manifest
                    else os.environ.get("BIA_BOOTSTRAP_MANIFEST")
                )
                if not raw:
                    parser.error("Provide a hash-only --manifest or BIA_BOOTSTRAP_MANIFEST")
                provision_identities(session, settings, json.loads(raw))
                result = {"identities_provisioned": True, "tokens_logged": False}
            elif args.action == "load":
                result = bootstrap(session, settings)
            elif args.action == "revoke-access":
                result = revoke_access(session, settings)
            else:
                result = status(session)
            session.commit()
    except ValidationError, json.JSONDecodeError:
        raise SystemExit(
            "Invalid configuration/hash-only manifest; plaintext credentials are not accepted"
        ) from None
    except HTTPException as exc:
        code = (
            exc.detail.get("code", "VALIDATION_FAILED")
            if isinstance(exc.detail, dict)
            else "VALIDATION_FAILED"
        )
        raise SystemExit("Bootstrap rejected by existing backend policy: " + code) from None
    except SQLAlchemyError:
        raise SystemExit(
            "Bootstrap database operation failed; verify migrations and reserved resource conflicts"
        ) from None
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
