from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.catalogs.schemas import Contract, Identifier, Name


class CollectionCreate(Contract):
    id: Identifier
    name: Name
    owner_id: Identifier | None = None
    classification: Literal["internal", "restricted"] = "internal"


class CollectionRead(Contract):
    id: str
    name: str
    owner_id: str
    classification: str
    enabled: bool


class CollectionStatus(Contract):
    enabled: bool


class GrantWrite(Contract):
    user_id: Identifier
    clearance: Literal["internal", "restricted"] = "internal"
    enabled: bool = True


class DocumentCreate(Contract):
    id: Identifier
    title: Name

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str) -> str:
        from app.knowledge.extract import safe_text

        return safe_text(value)


class DocumentRead(Contract):
    id: str
    collection_id: str
    title: str
    owner_id: str


class VersionRead(Contract):
    document_id: str
    number: int
    collection_id: str
    content_hash: str
    filename: str
    source: str
    valid_from: date
    valid_to: date
    status: str
    approval: str
    embedding_version: str
    pipeline_version: str
    chunk_count: int
    error_code: str | None
    created_by: str
    approved_by: str | None
    created_at: datetime


class ApprovalWrite(Contract):
    approval: Literal["approved", "revoked"]


class KnowledgeReference(Contract):
    document_id: Identifier
    version: Annotated[int, Field(ge=1)]


class KnowledgeSelection(Contract):
    documents: Annotated[list[KnowledgeReference], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def unique(self):
        keys = [d.document_id for d in self.documents]
        if len(keys) != len(set(keys)):
            raise ValueError("Select exactly one version per document")
        return self


class SearchRequest(Contract):
    query: Annotated[str, Field(min_length=1, max_length=1000)]
    collection_ids: Annotated[list[Identifier], Field(min_length=1, max_length=20)]
    as_of: date
    limit: Annotated[int, Field(ge=1, le=6)] = 4


class Evidence(Contract):
    reference: str
    collection_id: str
    document_id: str
    version: int
    chunk: int
    title: str
    source: str
    # Evidence must retain exact offsets and hashes; Contract normally strips strings.
    content: Annotated[str, StringConstraints(strip_whitespace=False)]
    content_hash: str
    char_start: int
    char_end: int
    valid_from: date
    valid_to: date
    semantic_similarity: float
    lexical_rank: float
    score: float


class SearchRead(Contract):
    id: str
    mode: Literal["hybrid-semantic"] = "hybrid-semantic"
    embedding_version: str
    duration_ms: int
    evidence: list[Evidence]


class SearchLogRead(Contract):
    id: str
    run_id: str | None
    caller_id: str
    as_of: date
    collection_ids: list[str]
    references: list[dict]
    embedding_version: str
    mode: str
    duration_ms: int
    error_code: str | None
    created_at: datetime
