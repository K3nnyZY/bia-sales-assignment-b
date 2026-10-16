from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select

from app.agents.models import Agent, AgentVersion
from app.db.session import DatabaseSession
from app.governance.models import Publication, VersionGovernance
from app.governance.observability import metrics, visibility
from app.governance.schemas import MetricsRead
from app.identity.auth import CurrentUser
from app.knowledge.models import KnowledgeSearch
from app.runtime.models import AgentRun, InvocationGrant, RunEvent, ToolCall
from app.runtime.schemas import ExecutableVersion, RunCreate, RunRead, TraceRead
from app.runtime.service import execute_run

router = APIRouter(prefix="/api/v1", tags=["runtime"])


@router.get("/runtime/agents", response_model=list[ExecutableVersion])
def executable_versions(session: DatabaseSession, user: CurrentUser, request: Request):
    settings = request.app.state.settings
    local = settings.enable_local_runtime and settings.app_env in {"development", "test"}
    if not local and not settings.enable_published_runtime:
        return []
    rows = session.execute(
        select(Agent, AgentVersion)
        .join(AgentVersion, AgentVersion.agent_id == Agent.id)
        .join(
            InvocationGrant,
            (InvocationGrant.agent_id == Agent.id)
            & (InvocationGrant.version_number == AgentVersion.number),
        )
        .where(
            InvocationGrant.user_id == user.id,
            InvocationGrant.enabled.is_(True),
            AgentVersion.status == "snapshot",
            Agent.status == "draft",
        )
        .order_by(Agent.id, AgentVersion.number)
    ).all()
    return [
        {
            "agent_id": agent.id,
            "name": agent.name,
            "version": version.number,
            "model_id": version.model_id,
            "model_provider": version.snapshot["model"]["provider"],
            "config_hash": version.config_hash,
            "local_preview": local,
            "published": bool(
                (pointer := session.get(Publication, agent.id))
                and pointer.enabled
                and pointer.version_number == version.number
            ),
            "available_modes": ["deterministic"]
            if version.snapshot["model"]["provider"] == "synthetic"
            else (
                ["provider"]
                if request.app.state.settings.enable_provider_runtime
                and (
                    (
                        version.snapshot["model"]["provider"] == "openai"
                        and request.app.state.settings.openai_api_key is not None
                    )
                    or (
                        version.snapshot["model"]["provider"] == "anthropic"
                        and request.app.state.settings.anthropic_api_key is not None
                    )
                )
                else []
            ),
        }
        for agent, version in rows
        if (
            not (state := session.get(VersionGovernance, (agent.id, version.number)))
            or state.stage != "disabled"
        )
        and (
            local
            or (
                (published := session.get(Publication, agent.id))
                and published.enabled
                and published.version_number == version.number
            )
        )
    ]


@router.post("/runs", response_model=RunRead, status_code=201)
async def create_run(
    data: RunCreate,
    response: Response,
    request: Request,
    session: DatabaseSession,
    user: CurrentUser,
):
    run = await execute_run(session, request.app.state.settings, user.id, data)
    response.headers["Location"] = f"/api/v1/runs/{run.id}"
    return run


@router.get("/runs", response_model=list[RunRead])
def list_runs(
    session: DatabaseSession, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=100)] = 30
):
    return session.scalars(
        select(AgentRun)
        .where(visibility(user))
        .order_by(AgentRun.started_at.desc(), AgentRun.id)
        .limit(limit)
    ).all()


def own_run(session, user, run_id):
    run = session.scalar(select(AgentRun).where(AgentRun.id == run_id, visibility(user)))
    if run is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Run not found"})
    return run


@router.get("/metrics", response_model=MetricsRead)
def runtime_metrics(session: DatabaseSession, user: CurrentUser):
    return metrics(session, user)


@router.get("/runs/{run_id}", response_model=RunRead)
def run_detail(run_id: str, session: DatabaseSession, user: CurrentUser):
    return own_run(session, user, run_id)


@router.get("/runs/{run_id}/trace", response_model=TraceRead)
def run_trace(run_id: str, session: DatabaseSession, user: CurrentUser):
    run = own_run(session, user, run_id)
    return {
        "run": run,
        "events": session.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == run.id)
            .order_by(RunEvent.started_at, RunEvent.id)
        ).all(),
        "knowledge_searches": session.scalars(
            select(KnowledgeSearch)
            .where(KnowledgeSearch.run_id == run.id)
            .order_by(KnowledgeSearch.created_at)
        ).all(),
        "tool_calls": session.scalars(
            select(ToolCall)
            .where(ToolCall.run_id == run.id)
            .order_by(ToolCall.started_at, ToolCall.id)
        ).all(),
    }
