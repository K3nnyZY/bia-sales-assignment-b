import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentTool, AgentVersion
from app.agents.schemas import (
    AgentConfiguration,
    AgentCreate,
    AgentUpdate,
    ModelSelection,
    VersionCreate,
)
from app.catalogs.models import Model, Tool
from app.catalogs.schemas import ModelCreate, ToolCreate
from app.identity.models import User


def fail(status: int, code: str, message: str) -> None:
    raise HTTPException(status, detail={"code": code, "message": message})


def require_creator(user: User) -> None:
    if user.role not in {"administrator", "creator"}:
        fail(403, "FORBIDDEN", "Creator or administrator role required")


def get_agent(session: Session, agent_id: str, user: User, *, edit: bool = False) -> Agent:
    query = select(Agent).where(Agent.id == agent_id)
    agent = session.scalar(query.with_for_update() if edit else query)
    if agent is None:
        fail(404, "NOT_FOUND", "Agent not found")
    if edit:
        require_creator(user)
        if user.role != "administrator" and agent.owner_id != user.id:
            fail(403, "FORBIDDEN", "Only the owner or an administrator may edit this agent")
    return agent


def check_revision(actual: int, expected: int) -> None:
    if actual != expected:
        fail(409, "STALE_REVISION", "The resource changed; reload before saving")


def get_version(session: Session, agent_id: str, number: int) -> AgentVersion:
    version = session.get(AgentVersion, (agent_id, number))
    if version is None:
        fail(404, "NOT_FOUND", "Agent version not found")
    return version


def owner_for(session: Session, owner_id: str) -> User:
    owner = session.scalar(select(User).where(User.id == owner_id).with_for_update(read=True))
    if owner is None or not owner.active or owner.role not in {"administrator", "creator"}:
        fail(422, "INVALID_OWNER", "Owner must be an active creator or administrator")
    return owner


def create_agent(session: Session, data: AgentCreate, user: User) -> Agent:
    require_creator(user)
    owner_id = data.owner_id or user.id
    if owner_id != user.id and user.role != "administrator":
        fail(403, "FORBIDDEN", "Only administrators may assign another owner")
    owner_for(session, owner_id)
    agent = Agent(
        id=data.id or f"agent-{uuid4().hex}",
        name=data.name,
        description=data.description,
        department=data.department,
        owner_id=owner_id,
    )
    session.add(agent)
    session.flush()
    if data.model_profile is not None:
        model = session.scalar(
            select(Model)
            .where(Model.profile == data.model_profile, Model.status == "approved")
            .with_for_update(read=True)
        )
        if model is None:
            fail(422, "MODEL_NOT_APPROVED", "Select an approved model profile")
        tool_ids = resolve_initial_tools(session, data.tools)
        configuration = AgentConfiguration(
            objective=data.description or data.name,
            instructions="Follow the declared objective using only approved capabilities "
            "and evidence authorized for the caller.",
            model=ModelSelection(
                model_id=model.id, max_output_tokens=min(1000, model.max_output_tokens)
            ),
            tool_ids=tool_ids,
        )
        create_version(session, agent, VersionCreate(configuration=configuration), user)
    return agent


def resolve_initial_tools(session: Session, references: list[str]) -> list[str]:
    tools = session.scalars(
        select(Tool).where(
            (Tool.id.in_(references) | Tool.name.in_(references)), Tool.status == "approved"
        )
    ).all()
    resolved = []
    for reference in references:
        matches = [tool for tool in tools if reference in {tool.id, tool.name}]
        if not matches:
            fail(422, "TOOL_NOT_APPROVED", "Every tool must be registered and approved")
        if len(matches) > 1:
            fail(409, "AMBIGUOUS_TOOL", "Multiple approved tool versions match; use a catalog ID")
        resolved.append(matches[0].id)
    if len(resolved) != len(set(resolved)):
        fail(422, "DUPLICATE_TOOL", "Tool names and IDs must not refer to the same tool twice")
    return resolved


def update_agent(session: Session, agent: Agent, data: AgentUpdate, user: User) -> Agent:
    check_revision(agent.revision, data.expected_revision)
    changes = data.model_dump(exclude={"expected_revision"}, exclude_unset=True)
    if agent.status == "deprecated" and changes.get("status", agent.status) != "deprecated":
        fail(409, "INVALID_TRANSITION", "Deprecated agents cannot be reactivated")
    if changes.get("owner_id", agent.owner_id) != agent.owner_id:
        if user.role != "administrator":
            fail(403, "FORBIDDEN", "Only administrators may transfer ownership")
        owner = owner_for(session, changes["owner_id"])
        versions = session.scalars(
            select(AgentVersion).where(AgentVersion.agent_id == agent.id)
        ).all()
        if any(version.status == "snapshot" for version in versions):
            fail(409, "IMMUTABLE_OWNER", "Ownership cannot change after a snapshot")
        for version in versions:
            validate_configuration(
                session, AgentConfiguration.model_validate(version.configuration), owner
            )
    for key, value in changes.items():
        setattr(agent, key, value)
    agent.revision += 1
    session.flush()
    return agent


def validate_configuration(
    session: Session, config: AgentConfiguration, owner: User
) -> tuple[dict, Model, list[Tool]]:
    selector = (
        Model.id == config.model.model_id
        if config.model.model_id
        else Model.profile == config.model.profile
    )
    model = session.scalar(
        select(Model).where(selector, Model.status == "approved").with_for_update(read=True)
    )
    if model is None:
        fail(422, "MODEL_NOT_APPROVED", "Select an approved model or profile")
    required = set(config.required_capabilities) | ({"tool_calling"} if config.tool_ids else set())
    if not required <= set(model.capabilities):
        fail(422, "MODEL_CAPABILITY", "The model does not support the required capabilities")
    if config.model.max_output_tokens > model.max_output_tokens:
        fail(422, "MODEL_LIMIT", "Requested output exceeds the model limit")
    tools = list(
        session.scalars(
            select(Tool)
            .where(Tool.id.in_(config.tool_ids))
            .order_by(Tool.id)
            .with_for_update(read=True)
        )
    )
    if len(tools) != len(config.tool_ids) or any(tool.status != "approved" for tool in tools):
        fail(422, "TOOL_NOT_APPROVED", "Every tool must be registered and approved")
    for tool in tools:
        if tool.operation != "read":
            fail(403, "WRITE_NOT_ALLOWED", "This milestone permits read-only tool configurations")
        if not set(tool.permissions) <= set(owner.permissions):
            fail(403, "TOOL_PERMISSION", "The owner lacks a required tool permission")
    if config.knowledge is not None:
        from app.knowledge.runtime import RAG_TOOL_ID
        from app.knowledge.service import pinned_documents

        if RAG_TOOL_ID not in config.tool_ids or "billing-knowledge-v1" in config.tool_ids:
            fail(
                422,
                "KNOWLEDGE_TOOL_REQUIRED",
                "Knowledge configurations require only the v2 retrieval adapter",
            )
        pinned_documents(session, config.knowledge, owner.id)
    elif "billing-knowledge-v2" in config.tool_ids:
        fail(422, "KNOWLEDGE_REQUIRED", "Pin approved document versions for retrieval")
    canonical = config.model_dump(mode="json", exclude_none=True)
    canonical["model"] = {"model_id": model.id, "max_output_tokens": config.model.max_output_tokens}
    canonical["tool_ids"] = sorted(config.tool_ids)
    return canonical, model, tools


def store_configuration(
    session: Session, version: AgentVersion, config: AgentConfiguration, owner: User
) -> None:
    canonical, model, tools = validate_configuration(session, config, owner)
    version.configuration = canonical
    version.model_id = model.id
    session.add(version)
    session.flush()
    old = session.scalars(
        select(AgentTool).where(
            AgentTool.agent_id == version.agent_id, AgentTool.version_number == version.number
        )
    ).all()
    for binding in old:
        session.delete(binding)
    session.flush()
    session.add_all(
        [
            AgentTool(agent_id=version.agent_id, version_number=version.number, tool_id=tool.id)
            for tool in tools
        ]
    )
    session.flush()


def create_version(session: Session, agent: Agent, data: VersionCreate, user: User) -> AgentVersion:
    if agent.status != "draft":
        fail(409, "AGENT_NOT_EDITABLE", "Only draft agents accept configuration changes")
    config = data.configuration
    if data.source_version is not None:
        source = get_version(session, agent.id, data.source_version)
        check_revision(source.revision, data.expected_source_revision)
        config = AgentConfiguration.model_validate(source.configuration)
    version = AgentVersion(
        agent_id=agent.id,
        number=agent.next_version,
        source_version=data.source_version,
        created_by=user.id,
    )
    agent.next_version += 1
    store_configuration(session, version, config, owner_for(session, agent.owner_id))
    return version


def editable_version(
    session: Session, agent: Agent, number: int, expected_revision: int
) -> AgentVersion:
    if agent.status != "draft":
        fail(409, "AGENT_NOT_EDITABLE", "Only draft agents accept configuration changes")
    version = get_version(session, agent.id, number)
    if version.status != "draft":
        fail(409, "IMMUTABLE_SNAPSHOT", "Create a new version from the snapshot")
    check_revision(version.revision, expected_revision)
    return version


def configuration_hash(snapshot: dict) -> str:
    serialized = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def freeze_version(session: Session, agent: Agent, version: AgentVersion) -> AgentVersion:
    owner = owner_for(session, agent.owner_id)
    canonical, model, tools = validate_configuration(
        session, AgentConfiguration.model_validate(version.configuration), owner
    )
    snapshot = {
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "department": agent.department,
            "owner_id": agent.owner_id,
        },
        "version": version.number,
        "configuration": canonical,
        "model": ModelCreate.model_validate(model).model_dump(mode="json"),
        "tools": [ToolCreate.model_validate(tool).model_dump(mode="json") for tool in tools],
        "policy": {
            "version": "management-v1",
            "permissions": sorted(
                {permission for tool in tools for permission in tool.permissions}
            ),
            "resource_scope": "caller_owned",
            "allow_financial_writes": False,
        },
    }
    if version.configuration.get("knowledge"):
        from app.knowledge.service import pinned_documents

        snapshot["knowledge"] = pinned_documents(
            session, AgentConfiguration.model_validate(version.configuration).knowledge, owner.id
        )
    version.snapshot = snapshot
    version.config_hash = configuration_hash(snapshot)
    version.status = "snapshot"
    version.revision += 1
    session.flush()
    return version
