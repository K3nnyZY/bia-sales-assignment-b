from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.agents import service
from app.agents.models import Agent, AgentVersion
from app.agents.schemas import (
    AgentCreate,
    AgentRead,
    AgentStatus,
    AgentUpdate,
    RevisionCheck,
    VersionCreate,
    VersionRead,
    VersionUpdate,
)
from app.db.session import DatabaseSession
from app.governance.audit import record
from app.identity.auth import CurrentUser

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
def agents(
    session: DatabaseSession,
    user: CurrentUser,
    q: Annotated[str, Query(max_length=120)] = "",
    status: AgentStatus | None = None,
    owner_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(Agent).order_by(Agent.created_at.desc(), Agent.id)
    if q:
        query = query.where(Agent.name.icontains(q, autoescape=True))
    if status:
        query = query.where(Agent.status == status)
    if owner_id:
        query = query.where(Agent.owner_id == owner_id)
    return session.scalars(query.limit(limit).offset(offset)).all()


@router.post("", response_model=AgentRead, status_code=201)
def add_agent(data: AgentCreate, response: Response, session: DatabaseSession, user: CurrentUser):
    item = service.create_agent(session, data, user)
    record(session, user.id, "agent.created", resource_id=item.id, owner_id=item.owner_id)
    session.commit()
    response.headers["Location"] = f"/api/v1/agents/{item.id}"
    return item


@router.get("/{agent_id}", response_model=AgentRead)
def agent_detail(agent_id: str, session: DatabaseSession, user: CurrentUser):
    return service.get_agent(session, agent_id, user)


@router.patch("/{agent_id}", response_model=AgentRead)
def edit_agent(agent_id: str, data: AgentUpdate, session: DatabaseSession, user: CurrentUser):
    item = service.update_agent(
        session, service.get_agent(session, agent_id, user, edit=True), data, user
    )
    record(
        session,
        user.id,
        "agent.updated",
        resource_id=item.id,
        owner_id=item.owner_id,
        revision=item.revision,
    )
    session.commit()
    return item


@router.delete("/{agent_id}", status_code=204)
def delete_agent(
    agent_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    expected_revision: Annotated[int, Query(ge=1)],
):
    item = service.get_agent(session, agent_id, user, edit=True)
    service.check_revision(item.revision, expected_revision)
    if session.scalar(
        select(AgentVersion.number).where(AgentVersion.agent_id == agent_id).limit(1)
    ):
        service.fail(
            409, "HISTORY_EXISTS", "Agents with version history must be disabled, not deleted"
        )
    record(session, user.id, "agent.deleted", resource_id=item.id, owner_id=item.owner_id)
    session.delete(item)
    session.commit()
    return Response(status_code=204)


@router.get("/{agent_id}/versions", response_model=list[VersionRead])
def versions(agent_id: str, session: DatabaseSession, user: CurrentUser):
    service.get_agent(session, agent_id, user)
    return session.scalars(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.number.desc())
    ).all()


@router.post("/{agent_id}/versions", response_model=VersionRead, status_code=201)
def add_version(agent_id: str, data: VersionCreate, session: DatabaseSession, user: CurrentUser):
    agent = service.get_agent(session, agent_id, user, edit=True)
    version = service.create_version(session, agent, data, user)
    record(
        session,
        user.id,
        "version.created",
        agent_id,
        version.number,
        source_version=data.source_version,
    )
    session.commit()
    return version


@router.get("/{agent_id}/versions/{number}", response_model=VersionRead)
def version_detail(agent_id: str, number: int, session: DatabaseSession, user: CurrentUser):
    service.get_agent(session, agent_id, user)
    return service.get_version(session, agent_id, number)


@router.put("/{agent_id}/versions/{number}", response_model=VersionRead)
def edit_version(
    agent_id: str, number: int, data: VersionUpdate, session: DatabaseSession, user: CurrentUser
):
    agent = service.get_agent(session, agent_id, user, edit=True)
    version = service.editable_version(session, agent, number, data.expected_revision)
    service.store_configuration(
        session, version, data.configuration, service.owner_for(session, agent.owner_id)
    )
    version.revision += 1
    record(session, user.id, "version.updated", agent_id, number, revision=version.revision)
    session.commit()
    return version


@router.post("/{agent_id}/versions/{number}/snapshot", response_model=VersionRead)
def snapshot(
    agent_id: str, number: int, data: RevisionCheck, session: DatabaseSession, user: CurrentUser
):
    agent = service.get_agent(session, agent_id, user, edit=True)
    version = service.editable_version(session, agent, number, data.expected_revision)
    service.freeze_version(session, agent, version)
    record(session, user.id, "version.snapshot", agent_id, number, config_hash=version.config_hash)
    session.commit()
    return version
