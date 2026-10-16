import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException
from langgraph.errors import GraphRecursionError
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentVersion
from app.agents.schemas import AgentConfiguration
from app.core.config import Settings
from app.runtime.context import ExecutionContext
from app.runtime.errors import ExecutionError
from app.runtime.graph import BILLING_GRAPH, BillingState
from app.runtime.models import AgentRun, InvocationGrant, RunEvent
from app.runtime.schemas import RunCreate


def admission(session: Session, settings: Settings, user_id: str, data: RunCreate) -> AgentVersion:
    if not settings.enable_local_runtime or settings.app_env not in {"development", "test"}:
        raise HTTPException(
            503,
            detail={
                "code": "RUNTIME_DISABLED",
                "message": "Only the explicitly enabled local preview runtime is available",
            },
        )
    version = session.get(AgentVersion, (data.agent_id, data.version))
    if version is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Version not found"})
    grant = session.get(InvocationGrant, (data.agent_id, data.version, user_id))
    agent = session.get(Agent, data.agent_id)
    if grant is None or not grant.enabled or agent.status != "draft":
        raise HTTPException(
            403,
            detail={
                "code": "INVOCATION_FORBIDDEN",
                "message": "No explicit invocation entitlement for this version",
            },
        )
    if version.status != "snapshot" or not version.snapshot:
        raise HTTPException(
            409,
            detail={
                "code": "VERSION_NOT_EXECUTABLE",
                "message": "Freeze the version before local execution",
            },
        )
    config = AgentConfiguration.model_validate(version.configuration)
    if config.workflow is None:
        raise HTTPException(
            409,
            detail={
                "code": "WORKFLOW_REQUIRED",
                "message": "The version has no registered runtime workflow",
            },
        )
    return version


async def execute_run(
    session: Session, settings: Settings, caller_id: str, data: RunCreate
) -> AgentRun:
    version = admission(session, settings, caller_id, data)
    config = AgentConfiguration.model_validate(version.configuration)
    snapshot = version.snapshot
    run = AgentRun(
        id=f"run-{uuid4().hex}",
        agent_id=version.agent_id,
        version_number=version.number,
        caller_id=caller_id,
        model_id=version.model_id,
        config_hash=version.config_hash,
        mode=data.mode,
    )
    session.add(run)
    session.commit()  # The run ID survives handled tool/model failures.
    timeout = min(config.limits.timeout_seconds, settings.runtime_timeout_seconds)
    ctx = ExecutionContext(
        session=session,
        settings=settings,
        run=run,
        caller_id=caller_id,
        config=config,
        snapshot=snapshot,
        deadline=monotonic() + timeout,
    )
    state: BillingState = {
        "message": data.message,
        "task": data.task,
        "invoice_id": data.invoice_id,
        "period": data.period.isoformat(),
    }
    try:
        async with asyncio.timeout(timeout):
            result = await BILLING_GRAPH.ainvoke(
                state,
                context=ctx,
                config={"recursion_limit": config.limits.max_steps + 5, "callbacks": []},
            )
    except TimeoutError:
        result = {
            "error": ExecutionError(
                "RUN_TIMEOUT", "La ejecución alcanzó su tiempo máximo."
            ).as_dict()
        }
    except asyncio.CancelledError:
        result = {"error": ExecutionError("RUN_CANCELLED", "La ejecución fue cancelada.").as_dict()}
    except GraphRecursionError:
        result = {"error": ExecutionError("STEP_LIMIT", "Se agotó el límite de pasos.").as_dict()}
    except Exception:
        session.rollback()
        result = {
            "error": ExecutionError("INTERNAL_ERROR", "La ejecución no pudo completarse.").as_dict()
        }
    # Load the expired ORM row before assigning a terminal status: an autoflush
    # between status and completed_at would violate the atomic completion check.
    session.refresh(run)
    run_id = run.id
    error = result.get("error")
    if error:
        run.status, run.error_code, run.answer = error["status"], error["code"], error["message"]
        run.calculations, run.references = {}, []
        if not ctx.node_names or ctx.node_names[-1] != "failure":
            session.add(
                RunEvent(
                    id=f"evt-{uuid4().hex}",
                    run_id=run_id,
                    step=ctx.steps,
                    node="failure",
                    status="failed",
                    error_code=error["code"],
                    started_at=datetime.now(UTC),
                    duration_ms=0,
                )
            )
    else:
        run.status, run.answer = "completed", result["answer"]
        run.calculations, run.references = result.get("calculations", {}), result["references"]
    run.input_tokens, run.output_tokens = ctx.input_tokens, ctx.output_tokens
    run.estimated_cost_usd = (
        Decimal(ctx.estimated_cost_usd) if ctx.estimated_cost_usd is not None else None
    )
    run.completed_at = datetime.now(UTC)
    session.commit()
    session.refresh(run)
    return run
