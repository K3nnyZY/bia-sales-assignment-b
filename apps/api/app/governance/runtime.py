from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import AgentVersion
from app.governance.models import EvaluationRun, Publication, VersionGovernance
from app.governance.policy import gate
from app.governance.seed import EVAL_PRINCIPALS
from app.runtime.errors import ExecutionError


def evaluation_allowed(
    session: Session, evaluation_id: str, caller_id: str, version: AgentVersion
) -> bool:
    item = session.get(EvaluationRun, evaluation_id)
    return bool(
        item
        and item.status == "running"
        and caller_id in EVAL_PRINCIPALS
        and (item.agent_id, item.version_number, item.config_hash)
        == (version.agent_id, version.number, version.config_hash)
    )


def published_allowed(session: Session, version: AgentVersion, mode: str) -> bool:
    pointer = session.scalar(
        select(Publication)
        .where(Publication.agent_id == version.agent_id)
        .with_for_update(read=True)
    )
    state = session.get(VersionGovernance, (version.agent_id, version.number))
    if (
        not pointer
        or not pointer.enabled
        or pointer.version_number != version.number
        or not state
        or state.stage != "published"
    ):
        return False
    result = gate(session, version, require_approval=True)
    evaluation = session.get(EvaluationRun, result.evaluation_id) if result.evaluation_id else None
    return bool(result.eligible and evaluation and evaluation.mode == mode)


def check_runtime_channel(session, run, caller_id, version, grant) -> None:
    if run.channel == "evaluation":
        if not evaluation_allowed(session, run.evaluation_id, caller_id, version):
            raise ExecutionError(
                "EVALUATION_FORBIDDEN",
                "La ejecución de evaluación no está autorizada.",
                status="denied",
            )
        return
    if not grant:
        raise ExecutionError(
            "INVOCATION_FORBIDDEN", "La invocación no tiene un grant activo.", status="denied"
        )
    state = session.get(VersionGovernance, (version.agent_id, version.number))
    if state and state.stage == "disabled":
        raise ExecutionError(
            "VERSION_DISABLED", "Esta versión está deshabilitada.", status="denied"
        )
    if run.channel == "published" and not published_allowed(session, version, run.mode):
        raise ExecutionError(
            "PUBLICATION_NOT_VALID",
            "La publicación o su evaluación ya no es válida.",
            status="denied",
        )
