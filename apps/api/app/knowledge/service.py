import hashlib
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents.service import fail
from app.core.config import Settings
from app.governance.audit import record
from app.identity.models import User
from app.knowledge.embeddings import EMBEDDING_VERSION, embed
from app.knowledge.extract import MAX_BYTES, chunks, safe_text
from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeGrant,
    KnowledgeObject,
    KnowledgeSearch,
    KnowledgeVersion,
)
from app.knowledge.schemas import Evidence, KnowledgeSelection, SearchRead, SearchRequest


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DatabaseObjectStore:
    """Small immutable object store (2 MiB/object) sharing transactional backups.

    Swappable boundary for external object storage; raw files never enter graph state.
    """

    def __init__(self, session: Session):
        self.session = session

    def put(self, data: bytes) -> str:
        if not data or len(data) > MAX_BYTES:
            fail(413, "FILE_SIZE", "Upload a non-empty file up to 2 MiB")
        key = digest(data)
        self.session.execute(
            insert(KnowledgeObject)
            .values(key=key, content=data)
            .on_conflict_do_nothing(index_elements=[KnowledgeObject.key])
        )
        return key

    def get(self, key: str) -> bytes:
        return self.session.get(KnowledgeObject, key).content


def collection(session: Session, collection_id: str, user: User, *, edit=False):
    item = session.get(KnowledgeCollection, collection_id)
    grant = session.get(KnowledgeGrant, (collection_id, user.id))
    if item is None or (
        item.owner_id != user.id and user.role != "administrator" and not (grant and grant.enabled)
    ):
        fail(404, "NOT_FOUND", "Knowledge collection not found")
    if edit and (
        user.role not in {"creator", "administrator"}
        or (item.owner_id != user.id and user.role != "administrator")
    ):
        fail(403, "FORBIDDEN", "Only the collection owner or administrator may edit")
    return item


def document(session: Session, document_id: str, user: User, *, edit=False):
    item = session.get(KnowledgeDocument, document_id)
    if item is None:
        fail(404, "NOT_FOUND", "Document not found")
    collection(session, item.collection_id, user, edit=edit)
    return item


def version(session: Session, document_id: str, number: int, user: User, *, edit=False):
    document(session, document_id, user, edit=edit)
    item = session.get(KnowledgeVersion, (document_id, number))
    if item is None:
        fail(404, "NOT_FOUND", "Document version not found")
    return item


def authorized_versions(session: Session, user_id: str, as_of: date, ids: list[str]):
    # All authorization/approval/date predicates are in the SQL base relation, before ranking.
    return (
        select(KnowledgeVersion.document_id, KnowledgeVersion.number)
        .join(KnowledgeCollection, KnowledgeVersion.collection_id == KnowledgeCollection.id)
        .join(KnowledgeGrant, KnowledgeGrant.collection_id == KnowledgeCollection.id)
        .join(User, User.id == KnowledgeGrant.user_id)
        .where(
            KnowledgeCollection.id.in_(ids),
            KnowledgeCollection.enabled.is_(True),
            KnowledgeGrant.user_id == user_id,
            KnowledgeGrant.enabled.is_(True),
            User.active.is_(True),
            or_(
                KnowledgeCollection.classification == "internal",
                KnowledgeGrant.clearance == "restricted",
            ),
            KnowledgeVersion.status == "ready",
            KnowledgeVersion.approval == "approved",
            KnowledgeVersion.valid_from <= as_of,
            KnowledgeVersion.valid_to >= as_of,
        )
    )


def pinned_documents(session: Session, selection: KnowledgeSelection, user_id: str) -> list[dict]:
    """Freeze exact approved documents and embedding pipeline, never a mutable collection alias."""
    result = []
    for ref in sorted(selection.documents, key=lambda d: d.document_id):
        row = session.get(KnowledgeVersion, (ref.document_id, ref.version))
        if row is None:
            fail(422, "KNOWLEDGE_NOT_APPROVED", "Select approved, readable document versions")
        readable = session.execute(
            authorized_versions(session, user_id, row.valid_from, [row.collection_id]).where(
                KnowledgeVersion.document_id == ref.document_id,
                KnowledgeVersion.number == ref.version,
            )
        ).first()
        if not readable or row.embedding_version != EMBEDDING_VERSION:
            fail(403, "KNOWLEDGE_NOT_APPROVED", "Select approved, readable document versions")
        result.append(
            {
                "document_id": row.document_id,
                "version": row.number,
                "collection_id": row.collection_id,
                "content_hash": row.content_hash,
                "embedding_version": row.embedding_version,
                "pipeline_version": row.pipeline_version,
                "valid_from": row.valid_from.isoformat(),
                "valid_to": row.valid_to.isoformat(),
            }
        )
    return result


def upload(
    session: Session,
    doc: KnowledgeDocument,
    data: bytes,
    filename: str,
    source: str,
    valid_from: date,
    valid_to: date,
    user: User,
):
    if valid_to < valid_from:
        fail(422, "INVALID_DATES", "valid_to must not precede valid_from")
    try:
        safe_text(source)
    except ValueError:
        fail(422, "UNSAFE_INSTRUCTIONS", "Source must identify a document, not instructions")
    filename = Path(filename).name
    if len(filename) > 160 or Path(filename).suffix.lower() not in {".pdf", ".txt", ".md"}:
        fail(422, "UNSUPPORTED_FORMAT", "Upload PDF, UTF-8 TXT or Markdown")
    session.refresh(doc, with_for_update=True)
    existing = session.scalar(
        select(KnowledgeVersion).where(
            KnowledgeVersion.collection_id == doc.collection_id,
            KnowledgeVersion.content_hash == digest(data),
            KnowledgeVersion.valid_from == valid_from,
            KnowledgeVersion.valid_to == valid_to,
        )
    )
    if existing:
        if existing.document_id != doc.id:
            fail(
                409,
                "DUPLICATE_DOCUMENT",
                "Identical content and validity already exist in collection",
            )
        return existing
    key = DatabaseObjectStore(session).put(data)
    item = KnowledgeVersion(
        document_id=doc.id,
        number=doc.next_version,
        collection_id=doc.collection_id,
        object_key=key,
        content_hash=key,
        filename=filename,
        source=source,
        valid_from=valid_from,
        valid_to=valid_to,
        embedding_version=EMBEDDING_VERSION,
        created_by=user.id,
    )
    doc.next_version += 1
    session.add(item)
    record(
        session,
        user.id,
        "knowledge.uploaded",
        document_id=doc.id,
        version=item.number,
        collection_id=doc.collection_id,
        content_hash=key,
    )
    session.commit()
    return item


def ingest(session: Session, item: KnowledgeVersion, settings: Settings, user: User):
    session.refresh(item, with_for_update=True)
    if item.status == "ready":
        return item  # Idempotent; never replace vectors of an approved/pinned version.
    if item.status == "rejected" or item.approval != "pending":
        fail(409, "IMMUTABLE_DOCUMENT", "Upload a new document version")
    start = monotonic()
    try:
        data = DatabaseObjectStore(session).get(item.object_key)
        completed = subprocess.run(
            [sys.executable, "-m", "app.knowledge.extract", Path(item.filename).suffix.lower()],
            input=data,
            capture_output=True,
            timeout=10,
            check=True,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])},
        )
        parsed = json.loads(completed.stdout)
        if parsed.get("error"):
            raise ValueError(parsed["error"])
        parts = chunks(safe_text(parsed["text"]))
        vectors = embed([part[2] for part in parts], settings.knowledge_model_path)
        for number, ((begin, end, content), vector) in enumerate(zip(parts, vectors, strict=True)):
            session.add(
                KnowledgeChunk(
                    document_id=item.document_id,
                    version_number=item.number,
                    collection_id=item.collection_id,
                    ordinal=number,
                    content=content,
                    content_hash=digest(content.encode()),
                    char_start=begin,
                    char_end=end,
                    embedding=vector,
                )
            )
        session.flush()
        item.status, item.error_code, item.chunk_count = "ready", None, len(parts)
    except (ValueError, UnicodeError) as exc:
        code = str(exc)
        item.status = "rejected" if code == "UNSAFE_INSTRUCTIONS" else "failed"
        item.error_code = (
            code
            if code
            in {
                "UNSAFE_INSTRUCTIONS",
                "INVALID_TEXT",
                "INVALID_PDF",
                "PDF_LIMIT",
                "TEXT_LIMIT",
                "EMPTY_OR_LARGE_TEXT",
                "EXTRACTION_FAILED",
                "FILE_SIZE",
            }
            else "INGESTION_FAILED"
        )
    except OSError, subprocess.SubprocessError, KeyError:
        item.status, item.error_code = "failed", "INGESTION_UNAVAILABLE"
    record(
        session,
        user.id,
        "knowledge.ingestion." + item.status,
        document_id=item.document_id,
        version=item.number,
        collection_id=item.collection_id,
        error_code=item.error_code,
        duration_ms=int((monotonic() - start) * 1000),
        embedding_version=EMBEDDING_VERSION,
    )
    session.commit()
    return item


def search(
    session: Session,
    settings: Settings,
    user: User,
    request: SearchRequest,
    *,
    pinned: list[dict] | None = None,
    run_id: str | None = None,
) -> SearchRead:
    start, error_code, evidence = monotonic(), None, []
    search_id = f"search-{uuid4().hex}"
    try:
        safe_text(request.query)
        # Explicitly requested collections must all be readable, even if empty.
        for cid in request.collection_ids:
            grant = session.get(KnowledgeGrant, (cid, user.id))
            coll = session.get(KnowledgeCollection, cid)
            if (
                not coll
                or not coll.enabled
                or not user.active
                or not grant
                or not grant.enabled
                or (coll.classification == "restricted" and grant.clearance != "restricted")
            ):
                fail(403, "KNOWLEDGE_FORBIDDEN", "Knowledge access is not authorized")
        vector = embed([request.query], settings.knowledge_model_path)[0]
        allowed = authorized_versions(session, user.id, request.as_of, request.collection_ids)
        if pinned is not None:
            predicates = [
                (
                    (KnowledgeVersion.document_id == d["document_id"])
                    & (KnowledgeVersion.number == d["version"])
                    & (KnowledgeVersion.content_hash == d["content_hash"])
                )
                for d in pinned
            ]
            allowed = allowed.where(or_(*predicates))
        if pinned is None:
            eligible = allowed.subquery()
            allowed = select(
                eligible.c.document_id, func.max(eligible.c.number).label("number")
            ).group_by(eligible.c.document_id)
        allowed = allowed.subquery()
        # Exact scan over the authorized subset: avoids ANN post-filter starvation/leaks for MVP.
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        lexical = func.ts_rank_cd(
            func.to_tsvector("spanish", KnowledgeChunk.content),
            func.plainto_tsquery("spanish", request.query),
        )
        base = (
            select(
                KnowledgeChunk,
                KnowledgeVersion,
                KnowledgeDocument,
                (1 - distance).label("semantic"),
                lexical.label("lexical"),
            )
            .join(
                allowed,
                (allowed.c.document_id == KnowledgeChunk.document_id)
                & (allowed.c.number == KnowledgeChunk.version_number),
            )
            .join(
                KnowledgeVersion,
                (KnowledgeVersion.document_id == KnowledgeChunk.document_id)
                & (KnowledgeVersion.number == KnowledgeChunk.version_number),
            )
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(KnowledgeVersion.embedding_version == EMBEDDING_VERSION)
        )
        semantic_rows = session.execute(
            base.where(distance < 0.75)
            .order_by(distance, KnowledgeChunk.document_id, KnowledgeChunk.ordinal)
            .limit(24)
        ).all()
        lexical_rows = session.execute(
            base.where(lexical > 0)
            .order_by(lexical.desc(), KnowledgeChunk.document_id, KnowledgeChunk.ordinal)
            .limit(24)
        ).all()
        merged = {}
        for rows in [semantic_rows, lexical_rows]:
            for rank, row in enumerate(rows, 1):
                chunk, ver, doc, similarity, lex = row
                key = (chunk.document_id, chunk.version_number, chunk.ordinal)
                if key not in merged:
                    merged[key] = [row, 0.0]
                merged[key][1] += 1 / (60 + rank)
        for (chunk, ver, doc, similarity, lex), score in sorted(
            merged.values(), key=lambda x: (-x[1], x[0][0].document_id, x[0][0].ordinal)
        )[: request.limit]:
            safe_text(chunk.content)  # Independent check before evidence enters the graph.
            evidence.append(
                Evidence(
                    reference=f"{doc.id}@{ver.number}#chunk-{chunk.ordinal}",
                    collection_id=chunk.collection_id,
                    document_id=doc.id,
                    version=ver.number,
                    chunk=chunk.ordinal,
                    title=doc.title,
                    source=ver.source,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    valid_from=ver.valid_from,
                    valid_to=ver.valid_to,
                    semantic_similarity=float(similarity),
                    lexical_rank=float(lex),
                    score=score,
                )
            )
        verify_evidence(
            session, user, [item.model_dump(mode="json") for item in evidence], request.as_of
        )
    except HTTPException as exc:
        error_code = exc.detail["code"]
        raise
    except ValueError as exc:
        error_code = (
            "UNSAFE_INSTRUCTIONS" if str(exc) == "UNSAFE_INSTRUCTIONS" else "EMBEDDING_UNAVAILABLE"
        )
        fail(
            422 if error_code == "UNSAFE_INSTRUCTIONS" else 503,
            error_code,
            "Search could not be completed safely",
        )
    except Exception:
        error_code = "RETRIEVAL_UNAVAILABLE"
        session.rollback()
        fail(503, error_code, "Knowledge search is unavailable")
    finally:
        duration = max(0, int((monotonic() - start) * 1000))
        session.add(
            KnowledgeSearch(
                id=search_id,
                caller_id=user.id,
                run_id=run_id,
                query_hash=digest(request.query.encode()),
                as_of=request.as_of,
                collection_ids=request.collection_ids,
                references=[
                    e.model_dump(mode="json", exclude={"content", "title", "source"})
                    for e in evidence
                ]
                if error_code is None
                else [],
                embedding_version=EMBEDDING_VERSION,
                duration_ms=duration,
                error_code=error_code,
            )
        )
        session.commit()
    return SearchRead(
        id=search_id, embedding_version=EMBEDDING_VERSION, duration_ms=duration, evidence=evidence
    )


def verify_evidence(session: Session, user: User, items: list[dict], as_of: date) -> None:
    for item in items:
        allowed = authorized_versions(session, user.id, as_of, [item["collection_id"]]).subquery()
        chunk = session.scalar(
            select(KnowledgeChunk)
            .join(
                allowed,
                (allowed.c.document_id == KnowledgeChunk.document_id)
                & (allowed.c.number == KnowledgeChunk.version_number),
            )
            .where(
                KnowledgeChunk.document_id == item["document_id"],
                KnowledgeChunk.version_number == item["version"],
                KnowledgeChunk.ordinal == item["chunk"],
            )
        )
        if (
            chunk is None
            or chunk.content_hash != item["content_hash"]
            or chunk.content != item["content"]
        ):
            fail(403, "KNOWLEDGE_CHANGED", "Evidence is no longer authorized")
        safe_text(chunk.content)
