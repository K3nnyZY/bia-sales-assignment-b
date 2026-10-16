from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, case, exists, or_, select

from app.agents.models import Agent
from app.agents.service import fail
from app.db.session import DatabaseSession
from app.governance import service
from app.governance.audit import AGENT_METADATA_ACTIONS
from app.governance.evaluator import evaluate
from app.governance.models import (
    Approval,
    AuditEvent,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
)
from app.governance.schemas import (
    ApprovalRead,
    AuditRead,
    DecisionRequest,
    EvaluateRequest,
    EvaluationDetail,
    EvaluationRead,
    GovernanceAction,
    GovernanceRead,
    InvocationRequest,
    PublishRequest,
    RollbackRequest,
    SuiteCreate,
    SuiteRead,
)
from app.identity.auth import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["governance"])
VERSION = "/agents/{agent_id}/versions/{number}"


@router.get("/evaluation-suites", response_model=list[SuiteRead])
def suites(session: DatabaseSession, user: CurrentUser):
    return session.scalars(
        select(EvaluationSuite).order_by(EvaluationSuite.id, EvaluationSuite.version.desc())
    ).all()


@router.post("/evaluation-suites", response_model=SuiteRead, status_code=201)
def add_suite(data: SuiteCreate, session: DatabaseSession, user: CurrentUser):
    return service.create_suite(session, data, user)


@router.get(VERSION + "/governance", response_model=GovernanceRead)
def governance(agent_id: str, number: int, session: DatabaseSession, user: CurrentUser):
    return service.info(session, agent_id, number, user)


@router.post(VERSION + "/evaluations", response_model=EvaluationRead, status_code=201)
async def start_evaluation(
    agent_id: str,
    number: int,
    data: EvaluateRequest,
    request: Request,
    session: DatabaseSession,
    user: CurrentUser,
):
    return await evaluate(session, request.app.state.settings, agent_id, number, data, user)


@router.get("/evaluations", response_model=list[EvaluationRead])
def evaluations(
    session: DatabaseSession,
    user: CurrentUser,
    agent_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    query = select(EvaluationRun).join(Agent, Agent.id == EvaluationRun.agent_id)
    if user.role not in service.STAFF:
        query = query.where(Agent.owner_id == user.id)
    if agent_id:
        query = query.where(EvaluationRun.agent_id == agent_id)
    return session.scalars(
        query.order_by(EvaluationRun.started_at.desc(), EvaluationRun.id).limit(limit)
    ).all()


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDetail)
def evaluation_detail(evaluation_id: str, session: DatabaseSession, user: CurrentUser):
    item = session.get(EvaluationRun, evaluation_id)
    if item is None:
        fail(404, "NOT_FOUND", "Evaluation not found")
    service.own_or_staff(session, item.agent_id, user)
    return {
        "evaluation": item,
        "results": session.scalars(
            select(EvaluationResult)
            .where(EvaluationResult.evaluation_id == evaluation_id)
            .order_by(EvaluationResult.check)
        ).all(),
    }


@router.post(VERSION + "/submit", response_model=ApprovalRead, status_code=201)
def submit(
    agent_id: str, number: int, data: GovernanceAction, session: DatabaseSession, user: CurrentUser
):
    return service.submit(session, agent_id, number, data, user)


@router.post(VERSION + "/approve", response_model=ApprovalRead)
def decide(
    agent_id: str, number: int, data: DecisionRequest, session: DatabaseSession, user: CurrentUser
):
    return service.decide(session, agent_id, number, data, user)


@router.get("/approvals", response_model=list[ApprovalRead])
def approvals(
    session: DatabaseSession, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=100)] = 30
):
    query = select(Approval).join(Agent, Agent.id == Approval.agent_id)
    if user.role not in service.STAFF:
        query = query.where(Agent.owner_id == user.id)
    return session.scalars(
        query.order_by(Approval.requested_at.desc(), Approval.id).limit(limit)
    ).all()


@router.post(VERSION + "/publish", response_model=GovernanceRead)
def publish(
    agent_id: str, number: int, data: PublishRequest, session: DatabaseSession, user: CurrentUser
):
    service.publish(session, agent_id, number, data, user)
    return service.info(session, agent_id, number, user)


@router.post(VERSION + "/disable", response_model=GovernanceRead)
def disable(
    agent_id: str, number: int, data: GovernanceAction, session: DatabaseSession, user: CurrentUser
):
    service.disable(session, agent_id, number, data, user)
    return service.info(session, agent_id, number, user)


@router.post("/agents/{agent_id}/rollback", response_model=GovernanceRead)
def rollback(agent_id: str, data: RollbackRequest, session: DatabaseSession, user: CurrentUser):
    service.rollback(session, agent_id, data, user)
    return service.info(session, agent_id, data.target_version, user)


@router.post(VERSION + "/invocations", status_code=204)
def grant(
    agent_id: str, number: int, data: InvocationRequest, session: DatabaseSession, user: CurrentUser
):
    service.grant_invocation(session, agent_id, number, data, user)


@router.get("/audit-events", response_model=list[AuditRead])
def audit_events(
    session: DatabaseSession,
    user: CurrentUser,
    agent_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    # Detached metadata references survive deletion; only these server-owned actions
    # may resolve resource_id as an agent. Catalog resource IDs are a separate domain.
    metadata = and_(AuditEvent.agent_id.is_(None), AuditEvent.action.in_(AGENT_METADATA_ACTIONS))
    subject = case(
        (metadata, AuditEvent.details["resource_id"].as_string()), else_=AuditEvent.agent_id
    )
    query = select(AuditEvent, subject)
    if user.role not in service.STAFF:
        recorded_owner = AuditEvent.details["owner_id"].as_string()
        current_owner = exists(
            select(Agent.id).where(
                Agent.id == subject,
                Agent.owner_id == user.id,
                # A recreated ID must not expose legacy history belonging to an older agent.
                Agent.created_at <= AuditEvent.created_at,
            )
        )
        query = query.where(
            or_(
                and_(metadata, recorded_owner == user.id),
                and_(metadata, recorded_owner.is_(None), current_owner),
                and_(~metadata, current_owner),
            )
        )
    if agent_id:
        query = query.where(subject == agent_id)
    rows = session.execute(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(limit)
    ).all()
    # Resolve the API/UI subject without changing the immutable persisted event or FK.
    return [
        {**AuditRead.model_validate(event).model_dump(), "agent_id": resolved}
        for event, resolved in rows
    ]
