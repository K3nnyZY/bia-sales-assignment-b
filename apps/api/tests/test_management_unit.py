import copy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agents.schemas import AgentConfiguration, VersionCreate
from app.agents.service import check_revision, configuration_hash, require_creator
from app.catalogs.schemas import ToolCreate
from app.core.config import Settings
from app.identity.auth import require_admin
from app.identity.models import User

CONFIG = {
    "objective": "Explain synthetic invoices",
    "instructions": "Use only approved evidence.",
    "model": {"profile": "balanced", "max_output_tokens": 1000},
    "tool_ids": ["invoice-read-v1"],
}


@pytest.mark.parametrize(
    "injection",
    [
        {"permissions": ["admin:all"]},
        {"role": "administrator"},
        {"owner_id": "demo-administrator"},
        {"security": {"permissions": ["invoices:write"]}},
        {"security": {"require_authentication": False}},
        {"security": {"resource_scope": "all"}},
        {"security": {"allow_financial_writes": True}},
        {"model": {"model_id": "synthetic-balanced-v1", "approved": True}},
        {"model": {"model_id": "synthetic-balanced-v1", "profile": "balanced"}},
        {"model": {"profile": "balanced", "max_output_tokens": 0}},
        {"tool_ids": ["invoice-read-v1", "invoice-read-v1"]},
        {"limits": {"max_steps": 500}},
        {"workflow": {"id": "arbitrary-execution"}},
    ],
)
def test_configuration_rejects_privilege_and_invalid_fields(injection):
    with pytest.raises(ValidationError):
        AgentConfiguration.model_validate(CONFIG | injection)


def test_valid_declarative_configuration():
    config = AgentConfiguration.model_validate(CONFIG)
    assert config.security.require_authentication is True
    assert config.security.allow_financial_writes is False
    assert config.model.profile == "balanced"


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"source_version": 1},
        {"configuration": CONFIG, "source_version": 1, "expected_source_revision": 1},
    ],
)
def test_version_creation_requires_unambiguous_source(value):
    with pytest.raises(ValidationError):
        VersionCreate.model_validate(value)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "not-a-type"},
        {"type": "array"},
        {"type": "object", "$ref": "https://untrusted.example/schema"},
        {"type": "object", "properties": {"item": {"$ref": "file:///etc/passwd"}}},
    ],
)
def test_invalid_or_external_tool_schemas(schema):
    with pytest.raises(ValidationError):
        ToolCreate(
            id="test-tool-v1",
            name="test_tool",
            version="1.0.0",
            description="Test",
            input_schema=schema,
            output_schema={"type": "object"},
            permissions=[],
        )


def test_demo_auth_is_blocked_in_production():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", enable_demo_auth=True)


def test_hash_is_canonical_and_changes_with_content():
    assert configuration_hash({"a": 1, "b": 2}) == configuration_hash({"b": 2, "a": 1})
    assert configuration_hash({"a": 1}) != configuration_hash({"a": 2})
    assert len(configuration_hash(copy.deepcopy(CONFIG))) == 64


@pytest.mark.parametrize("role", ["viewer", "reviewer", "approver", "auditor"])
def test_read_only_roles_cannot_create_or_administer(role):
    user = User(role=role)
    with pytest.raises(HTTPException) as exc:
        require_creator(user)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        require_admin(user)


def test_stale_revision_is_rejected():
    with pytest.raises(HTTPException) as exc:
        check_revision(2, 1)
    assert exc.value.status_code == 409
