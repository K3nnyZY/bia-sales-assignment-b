from datetime import datetime
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, model_validator

from app.catalogs.schemas import Capability, Contract, Identifier, Name, Profile

AgentStatus = Literal["draft", "disabled", "deprecated"]


class ModelSelection(Contract):
    model_id: Identifier | None = None
    profile: Profile | None = None
    max_output_tokens: Annotated[int, Field(ge=1, le=1_000_000)] = 1000

    @model_validator(mode="after")
    def single_selector(self):
        if (self.model_id is None) == (self.profile is None):
            raise ValueError("Select exactly one model_id or profile")
        return self


class ExecutionLimits(Contract):
    max_steps: Annotated[int, Field(ge=1, le=50)] = 6
    max_tool_calls: Annotated[int, Field(ge=0, le=20)] = 5
    timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 30


class SecurityPolicy(Contract):
    require_authentication: Literal[True] = True
    resource_scope: Literal["caller_owned"] = "caller_owned"
    allow_financial_writes: Literal[False] = False


class WorkflowSelection(Contract):
    id: Literal["billing_workflow_v1"]
    version: Literal["1.0.0"] = "1.0.0"


class AgentConfiguration(Contract):
    api_version: Literal["bia.ai/v1"] = "bia.ai/v1"
    kind: Literal["AgentConfiguration"] = "AgentConfiguration"
    objective: Annotated[str, Field(min_length=1, max_length=4000)]
    instructions: Annotated[str, Field(min_length=1, max_length=12000)]
    model: ModelSelection
    tool_ids: Annotated[list[Identifier], Field(max_length=20)] = []
    required_capabilities: Annotated[list[Capability], Field(max_length=4)] = ["chat"]
    limits: ExecutionLimits = ExecutionLimits()
    security: SecurityPolicy = SecurityPolicy()
    workflow: WorkflowSelection | None = None

    @model_validator(mode="after")
    def unique_references(self):
        for values in [self.tool_ids, self.required_capabilities]:
            if len(values) != len(set(values)):
                raise ValueError("Duplicate references or capabilities")
        if self.tool_ids and self.limits.max_tool_calls == 0:
            raise ValueError("Tools require a positive max_tool_calls limit")
        return self


class AgentCreate(Contract):
    id: Identifier | None = None
    name: Name
    description: Annotated[str, Field(max_length=4000)] = ""
    department: Annotated[str, Field(min_length=1, max_length=120)]
    owner_id: Identifier | None = Field(
        default=None, validation_alias=AliasChoices("owner_id", "owner")
    )
    model_profile: Profile | None = None
    tools: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,119}$")]],
        Field(max_length=20),
    ] = []

    @model_validator(mode="after")
    def initial_configuration_selection(self):
        if self.tools and self.model_profile is None:
            raise ValueError("tools require model_profile for the initial configuration")
        if len(self.tools) != len(set(self.tools)):
            raise ValueError("Duplicate tool references")
        return self


class AgentUpdate(Contract):
    expected_revision: Annotated[int, Field(ge=1)]
    name: Name | None = None
    description: Annotated[str, Field(max_length=4000)] | None = None
    department: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    owner_id: Identifier | None = Field(
        default=None, validation_alias=AliasChoices("owner_id", "owner")
    )
    status: AgentStatus | None = None

    @model_validator(mode="after")
    def require_non_null_changes(self):
        changes = self.model_fields_set - {"expected_revision"}
        if not changes or any(getattr(self, key) is None for key in changes):
            raise ValueError("Provide at least one non-null metadata change")
        return self


class AgentRead(Contract):
    id: str
    name: str
    description: str
    department: str
    owner_id: str
    status: AgentStatus
    state: Literal["DRAFT", "DISABLED", "DEPRECATED"]
    initial_configuration: str | None
    revision: int
    created_at: datetime


class VersionCreate(Contract):
    configuration: AgentConfiguration | None = None
    source_version: Annotated[int, Field(ge=1)] | None = None
    expected_source_revision: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def choose_source(self):
        if (self.configuration is None) == (self.source_version is None):
            raise ValueError("Provide either configuration or source_version")
        if (self.source_version is None) != (self.expected_source_revision is None):
            raise ValueError("Cloning requires the source revision")
        return self


class RevisionCheck(Contract):
    expected_revision: Annotated[int, Field(ge=1)]


class VersionUpdate(RevisionCheck):
    configuration: AgentConfiguration


class VersionRead(Contract):
    agent_id: str
    number: int
    source_version: int | None
    status: Literal["draft", "snapshot"]
    revision: int
    model_id: str
    configuration: AgentConfiguration
    snapshot: dict | None
    config_hash: str | None
    created_by: str
    created_at: datetime
