import json
from decimal import Decimal
from typing import Annotated, Literal

from jsonschema import Draft202012Validator, SchemaError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,79}$")]
Name = Annotated[str, Field(min_length=1, max_length=120)]
ApprovalStatus = Literal["pending", "approved", "revoked"]
Profile = Literal["economy", "balanced", "advanced", "restricted"]
Capability = Literal["chat", "tool_calling", "structured_output", "vision"]
Permission = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$", max_length=80)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)


class ModelCreate(Contract):
    id: Identifier
    name: Name
    provider: Annotated[str, Field(min_length=1, max_length=80)]
    model_identifier: Annotated[str, Field(min_length=1, max_length=160)]
    release: Annotated[str, Field(min_length=1, max_length=80)]
    profile: Profile
    capabilities: Annotated[list[Capability], Field(min_length=1, max_length=4)]
    context_window: Annotated[int, Field(ge=1, le=10_000_000)]
    max_output_tokens: Annotated[int, Field(ge=1, le=1_000_000)]
    input_cost_per_million: Annotated[Decimal, Field(ge=0, le=1_000_000, decimal_places=6)] = (
        Decimal(0)
    )
    output_cost_per_million: Annotated[Decimal, Field(ge=0, le=1_000_000, decimal_places=6)] = (
        Decimal(0)
    )
    data_policy: Annotated[str, Field(min_length=1, max_length=2000)]
    status: ApprovalStatus = "pending"

    @model_validator(mode="after")
    def token_limits(self):
        if self.max_output_tokens > self.context_window:
            raise ValueError("Output limit exceeds context window")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Duplicate capabilities")
        return self


class ToolCreate(Contract):
    id: Identifier
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{2,119}$")]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$", max_length=32)]
    description: Annotated[str, Field(min_length=1, max_length=4000)]
    input_schema: dict
    output_schema: dict
    permissions: Annotated[list[Permission], Field(max_length=30)]
    operation: Literal["read", "write"] = "read"
    timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 5
    max_retries: Annotated[int, Field(ge=0, le=3)] = 0
    requires_resource_authorization: bool = True
    audit_required: bool = True
    status: ApprovalStatus = "pending"

    @field_validator("input_schema", "output_schema")
    @classmethod
    def valid_schema(cls, value: dict) -> dict:
        if len(json.dumps(value)) > 32768 or value.get("type") != "object":
            raise ValueError("Tool schemas must be object schemas of at most 32 KiB")
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError("Invalid JSON Schema 2020-12") from exc

        def local_references(node):
            if isinstance(node, dict):
                for key, item in node.items():
                    if key in {"$ref", "$dynamicRef"} and not str(item).startswith("#"):
                        raise ValueError("External schema references are not allowed")
                    local_references(item)
            elif isinstance(node, list):
                for item in node:
                    local_references(item)

        local_references(value)
        return value

    @field_validator("permissions")
    @classmethod
    def distinct_permissions(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Duplicate permissions")
        return value


class StatusUpdate(Contract):
    status: ApprovalStatus


class UserRead(Contract):
    id: str
    name: str
    role: str
    permissions: list[str]
    active: bool
