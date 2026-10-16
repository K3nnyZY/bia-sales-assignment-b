from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeCollection(Base):
    __tablename__ = "knowledge_collections"
    __table_args__ = (
        CheckConstraint("classification IN ('internal','restricted')", name="classification"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    classification: Mapped[str] = mapped_column(String(20), default="internal")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeGrant(Base):
    __tablename__ = "knowledge_grants"
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_collections.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    clearance: Mapped[str] = mapped_column(String(20), default="internal")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("clearance IN ('internal','restricted')", name="clearance"),)


class KnowledgeObject(Base):
    __tablename__ = "knowledge_objects"
    __table_args__ = (CheckConstraint("octet_length(content) <= 2097152", name="size"),)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("id", "collection_id"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("knowledge_collections.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    next_version: Mapped[int] = mapped_column(Integer, default=1)


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "number", "collection_id", name="uq_knowledge_version_scope"
        ),
        UniqueConstraint(
            "collection_id",
            "content_hash",
            "valid_from",
            "valid_to",
            name="uq_knowledge_collection_content",
        ),
        ForeignKeyConstraint(
            ["document_id", "collection_id"],
            ["knowledge_documents.id", "knowledge_documents.collection_id"],
        ),
        CheckConstraint("number >= 1 AND valid_to >= valid_from", name="version_dates"),
        CheckConstraint("status IN ('pending','ready','failed','rejected')", name="status"),
        CheckConstraint("approval IN ('pending','approved','revoked')", name="approval"),
        CheckConstraint("approval <> 'approved' OR status = 'ready'", name="ready_approval"),
    )
    document_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[str] = mapped_column(String(80), index=True)
    object_key: Mapped[str] = mapped_column(ForeignKey("knowledge_objects.key"))
    content_hash: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(240))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approval: Mapped[str] = mapped_column(String(20), default="pending")
    embedding_version: Mapped[str] = mapped_column(String(200))
    pipeline_version: Mapped[str] = mapped_column(String(40), default="text-v1-900-120")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "version_number", "collection_id"],
            [
                "knowledge_versions.document_id",
                "knowledge_versions.number",
                "knowledge_versions.collection_id",
            ],
        ),
        CheckConstraint(
            "ordinal >= 0 AND char_start >= 0 AND char_end > char_start", name="offsets"
        ),
        Index(
            "ix_knowledge_chunks_lexical",
            text("to_tsvector('spanish', content)"),
            postgresql_using="gin",
        ),
    )
    document_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(256))


class KnowledgeSearch(Base):
    __tablename__ = "knowledge_searches"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    caller_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    query_hash: Mapped[str] = mapped_column(String(64))
    as_of: Mapped[date] = mapped_column(Date)
    collection_ids: Mapped[list] = mapped_column(JSONB)
    references: Mapped[list] = mapped_column(JSONB, default=list)
    embedding_version: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(40), default="hybrid-semantic")
    duration_ms: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
