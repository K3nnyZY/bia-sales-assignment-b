from sqlalchemy import select

from app.agents.models import Agent, AgentVersion
from app.agents.service import configuration_hash
from app.catalogs.models import Model, Tool
from app.catalogs.schemas import ModelCreate, ToolCreate
from app.identity.models import User
from app.runtime.context import ExecutionContext
from app.runtime.errors import ExecutionError
from app.runtime.models import InvocationGrant


def deny(code: str, message: str) -> None:
    raise ExecutionError(code, message, status="denied")


def authorize_context(ctx: ExecutionContext) -> User:
    session = ctx.session
    session.expire_all()
    user = session.scalar(select(User).where(User.id == ctx.caller_id).with_for_update(read=True))
    if user is None or not user.active:
        deny("UNAUTHENTICATED", "La identidad ya no está activa.")
    grant = session.scalar(
        select(InvocationGrant)
        .where(
            InvocationGrant.agent_id == ctx.run.agent_id,
            InvocationGrant.version_number == ctx.run.version_number,
            InvocationGrant.user_id == ctx.caller_id,
            InvocationGrant.enabled.is_(True),
        )
        .with_for_update(read=True)
    )
    agent = session.scalar(
        select(Agent).where(Agent.id == ctx.run.agent_id).with_for_update(read=True)
    )
    version = session.get(AgentVersion, (ctx.run.agent_id, ctx.run.version_number))
    if not grant or agent is None or agent.status != "draft":
        deny("INVOCATION_FORBIDDEN", "La invocación está deshabilitada o no está autorizada.")
    if (
        version is None
        or version.status != "snapshot"
        or version.config_hash != ctx.run.config_hash
    ):
        deny("VERSION_NOT_EXECUTABLE", "Se requiere la versión congelada autorizada.")
    if configuration_hash(ctx.snapshot) != version.config_hash:
        deny("SNAPSHOT_MISMATCH", "La configuración efectiva no coincide con su hash.")
    model = session.scalar(
        select(Model).where(Model.id == ctx.run.model_id).with_for_update(read=True)
    )
    if model is None or model.status != "approved":
        deny("MODEL_NOT_APPROVED", "El modelo ya no está aprobado.")
    if ModelCreate.model_validate(model).model_dump(mode="json") != ctx.snapshot["model"]:
        deny("MODEL_MISMATCH", "La definición del modelo no coincide con la versión.")
    return user


def authorize_tool(ctx: ExecutionContext, tool_id: str) -> Tool:
    user = authorize_context(ctx)
    pinned = next((tool for tool in ctx.snapshot["tools"] if tool["id"] == tool_id), None)
    if pinned is None or tool_id not in ctx.config.tool_ids:
        deny("TOOL_NOT_ALLOWED", "La versión del agente no permite esta herramienta.")
    tool = ctx.session.scalar(select(Tool).where(Tool.id == tool_id).with_for_update(read=True))
    if tool is None or tool.status != "approved":
        deny("TOOL_NOT_APPROVED", "La herramienta ya no está aprobada.")
    if (
        ToolCreate.model_validate(tool).model_dump(mode="json") != pinned
        or tool.operation != "read"
    ):
        deny("TOOL_MISMATCH", "El contrato no coincide con la versión autorizada de lectura.")
    required = set(tool.permissions)
    granted = set(ctx.snapshot["policy"]["permissions"])
    if not required <= set(user.permissions) or not required <= granted:
        deny("TOOL_PERMISSION", "Faltan permisos del usuario o del agente para esta herramienta.")
    return tool
