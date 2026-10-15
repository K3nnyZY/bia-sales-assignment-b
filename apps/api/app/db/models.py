"""Explicit model registration for Alembic and the application."""

from app.agents.models import Agent, AgentTool, AgentVersion
from app.catalogs.models import Model, Tool
from app.identity.models import User

__all__ = ["Agent", "AgentTool", "AgentVersion", "Model", "Tool", "User"]
