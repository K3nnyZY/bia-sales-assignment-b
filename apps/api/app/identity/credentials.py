"""Offline credential rotation. Requires operator database access; no public issuer API."""

import argparse
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import build_engine
from app.governance.audit import record
from app.identity.auth import hash_token
from app.identity.models import AccessToken, User


def private_json(path: Path, data: dict) -> None:
    """Do not overwrite or follow an existing path; restrict access from creation."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(data, output, indent=2)
        output.write("\n")


def issue(session: Session, user_id: str, hours: int = 24) -> dict:
    if not 1 <= hours <= 168:
        raise ValueError("Credential lifetime must be between 1 and 168 hours")
    user = session.get(User, user_id)
    if not user or not user.active or user_id.startswith("evaluation-"):
        raise ValueError("An active, non-evaluation principal is required")
    token = "bia_" + secrets.token_urlsafe(32)
    token_id = "pat-" + uuid4().hex
    expiry = datetime.now(UTC) + timedelta(hours=hours)
    session.add(
        AccessToken(id=token_id, user_id=user_id, token_hash=hash_token(token), expires_at=expiry)
    )
    record(
        session,
        user.id,
        "identity.token_issued",
        token_id=token_id,
        issuer="operator-cli",
        expires_at=expiry.isoformat(),
    )
    session.flush()
    return {"id": token_id, "user_id": user.id, "token": token, "expires_at": expiry.isoformat()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("issue")
    create.add_argument("--user-id", required=True)
    create.add_argument("--hours", type=int, default=24)
    create.add_argument("--output", type=Path, required=True)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("--id", required=True)
    args = parser.parse_args()
    settings = Settings()
    if not settings.enable_access_token_auth:
        raise SystemExit("ENABLE_ACCESS_TOKEN_AUTH=true is required")
    engine = build_engine(settings)
    try:
        with Session(engine) as session:
            if args.command == "issue":
                data = issue(session, args.user_id, args.hours)
                private_json(args.output, data)
            else:
                item = session.get(AccessToken, args.id)
                if not item:
                    raise SystemExit("Credential not found")
                item.revoked = True
                record(
                    session,
                    item.user_id,
                    "identity.token_revoked",
                    token_id=item.id,
                    issuer="operator-cli",
                )
            session.commit()
    finally:
        engine.dispose()
    print("Credential operation completed. Plaintext credentials are never logged.")


if __name__ == "__main__":
    main()
