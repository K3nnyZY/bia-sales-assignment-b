from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.agents.service import fail
from app.db.session import DatabaseSession
from app.governance.audit import record
from app.identity.auth import CurrentUser, require_admin
from app.identity.models import User
from app.knowledge import service
from app.knowledge.extract import MAX_BYTES
from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeGrant,
    KnowledgeSearch,
    KnowledgeVersion,
)
from app.knowledge.schemas import (
    ApprovalWrite,
    CollectionCreate,
    CollectionRead,
    CollectionStatus,
    DocumentCreate,
    DocumentRead,
    GrantWrite,
    SearchLogRead,
    SearchRead,
    SearchRequest,
    VersionRead,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/collections", response_model=list[CollectionRead])
def list_collections(session: DatabaseSession, user: CurrentUser):
    grants = select(KnowledgeGrant.collection_id).where(
        KnowledgeGrant.user_id == user.id, KnowledgeGrant.enabled.is_(True)
    )
    query = select(KnowledgeCollection)
    if user.role != "administrator":
        query = query.where(
            or_(KnowledgeCollection.owner_id == user.id, KnowledgeCollection.id.in_(grants))
        )
    return session.scalars(query.order_by(KnowledgeCollection.id)).all()


@router.post("/collections", response_model=CollectionRead, status_code=201)
def create_collection(data: CollectionCreate, session: DatabaseSession, user: CurrentUser):
    if user.role not in {"administrator", "creator"}:
        fail(403, "FORBIDDEN", "Creator role required")
    owner_id = data.owner_id or user.id
    if user.role != "administrator" and (owner_id != user.id or data.classification != "internal"):
        fail(403, "FORBIDDEN", "Only administrators assign ownership or restricted classification")
    owner = session.get(User, owner_id)
    if not owner or not owner.active or owner.role not in {"creator", "administrator"}:
        fail(422, "INVALID_OWNER", "Select an active creator or administrator")
    item = KnowledgeCollection(**data.model_dump(exclude={"owner_id"}), owner_id=owner_id)
    session.add(item)
    session.flush()
    session.add(KnowledgeGrant(collection_id=item.id, user_id=owner_id, clearance="internal"))
    record(
        session, user.id, "knowledge.collection.created", collection_id=item.id, owner_id=owner_id
    )
    session.commit()
    return item


@router.patch("/collections/{collection_id}/status", response_model=CollectionRead)
def collection_status(
    collection_id: str, data: CollectionStatus, session: DatabaseSession, user: CurrentUser
):
    require_admin(user)
    item = service.collection(session, collection_id, user)
    item.enabled = data.enabled
    record(
        session,
        user.id,
        "knowledge.collection.status",
        collection_id=collection_id,
        enabled=data.enabled,
    )
    session.commit()
    return item


@router.put("/collections/{collection_id}/grants", status_code=204)
def grant(collection_id: str, data: GrantWrite, session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    service.collection(session, collection_id, user)
    principal = session.get(User, data.user_id)
    if not principal or not principal.active:
        fail(422, "INVALID_PRINCIPAL", "Select an active principal")
    session.execute(
        insert(KnowledgeGrant)
        .values(collection_id=collection_id, **data.model_dump())
        .on_conflict_do_update(
            index_elements=[KnowledgeGrant.collection_id, KnowledgeGrant.user_id],
            set_=data.model_dump(exclude={"user_id"}),
        )
    )
    record(
        session,
        user.id,
        "knowledge.grant.changed",
        collection_id=collection_id,
        **data.model_dump(),
    )
    session.commit()


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentRead])
def documents(collection_id: str, session: DatabaseSession, user: CurrentUser):
    service.collection(session, collection_id, user)
    return session.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.collection_id == collection_id)
        .order_by(KnowledgeDocument.id)
    ).all()


@router.post("/collections/{collection_id}/documents", response_model=DocumentRead, status_code=201)
def create_document(
    collection_id: str, data: DocumentCreate, session: DatabaseSession, user: CurrentUser
):
    coll = service.collection(session, collection_id, user, edit=True)
    item = KnowledgeDocument(
        **data.model_dump(), collection_id=collection_id, owner_id=coll.owner_id
    )
    session.add(item)
    record(
        session,
        user.id,
        "knowledge.document.created",
        collection_id=collection_id,
        document_id=data.id,
    )
    session.commit()
    return item


@router.get("/documents/{document_id}/versions", response_model=list[VersionRead])
def versions(document_id: str, session: DatabaseSession, user: CurrentUser):
    service.document(session, document_id, user)
    return session.scalars(
        select(KnowledgeVersion)
        .where(KnowledgeVersion.document_id == document_id)
        .order_by(KnowledgeVersion.number.desc())
    ).all()


@router.post("/documents/{document_id}/versions", response_model=VersionRead, status_code=201)
async def upload(
    document_id: str,
    session: DatabaseSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    valid_from: Annotated[date, Form()],
    valid_to: Annotated[date, Form()],
    source: Annotated[str, Form(min_length=1, max_length=240)],
):
    doc = service.document(session, document_id, user, edit=True)
    try:
        content = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    return service.upload(
        session, doc, content, file.filename or "", source, valid_from, valid_to, user
    )


@router.post("/documents/{document_id}/versions/{number}/ingest", response_model=VersionRead)
def ingest(
    document_id: str, number: int, request: Request, session: DatabaseSession, user: CurrentUser
):
    item = service.version(session, document_id, number, user, edit=True)
    return service.ingest(session, item, request.app.state.settings, user)


@router.patch("/documents/{document_id}/versions/{number}", response_model=VersionRead)
def approve(
    document_id: str, number: int, data: ApprovalWrite, session: DatabaseSession, user: CurrentUser
):
    if user.role not in {"administrator", "reviewer"}:
        fail(403, "FORBIDDEN", "Reviewer or administrator required")
    # Reviewers need explicit collection access; administrator management is not retrieval access.
    item = service.version(session, document_id, number, user)
    session.refresh(item, with_for_update=True)
    if data.approval == "approved" and (item.status != "ready" or item.approval == "revoked"):
        fail(
            409,
            "INVALID_TRANSITION",
            "Only ready pending documents can be approved; revocation is terminal",
        )
    item.approval, item.approved_by = data.approval, user.id
    record(
        session,
        user.id,
        "knowledge.document." + data.approval,
        document_id=document_id,
        version=number,
        content_hash=item.content_hash,
    )
    session.commit()
    return item


@router.post("/search", response_model=SearchRead)
def search(data: SearchRequest, request: Request, session: DatabaseSession, user: CurrentUser):
    return service.search(session, request.app.state.settings, user, data)


@router.get("/searches", response_model=list[SearchLogRead])
def searches(session: DatabaseSession, user: CurrentUser):
    query = select(KnowledgeSearch)
    if user.role != "auditor":
        query = query.where(KnowledgeSearch.caller_id == user.id)
    return session.scalars(query.order_by(KnowledgeSearch.created_at.desc()).limit(100)).all()


@router.get("/documents/{document_id}/versions/{number}/chunks/{ordinal}")
def evidence(
    document_id: str,
    number: int,
    ordinal: int,
    as_of: date,
    session: DatabaseSession,
    user: CurrentUser,
):
    row = session.get(KnowledgeChunk, (document_id, number, ordinal))
    if row is None:
        fail(404, "NOT_FOUND", "Evidence not found")
    source = {
        "collection_id": row.collection_id,
        "document_id": document_id,
        "version": number,
        "chunk": ordinal,
        "content_hash": row.content_hash,
        "content": row.content,
    }
    service.verify_evidence(session, user, [source], as_of)
    return {
        **source,
        "reference": f"{document_id}@{number}#chunk-{ordinal}",
        "char_start": row.char_start,
        "char_end": row.char_end,
    }
