from uuid import uuid4

from sqlalchemy.orm import Session

from app.governance.models import AuditEvent

AGENT_METADATA_ACTIONS = frozenset({"agent.created", "agent.updated", "agent.deleted"})


def record(
    session: Session,
    actor_id: str,
    action: str,
    agent_id: str | None = None,
    version: int | None = None,
    **details,
) -> None:
    session.add(
        AuditEvent(
            id=f"aud-{uuid4().hex}",
            actor_id=actor_id,
            action=action,
            agent_id=agent_id,
            version_number=version,
            details=details,
        )
    )
