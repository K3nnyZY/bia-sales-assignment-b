from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.catalogs.models import Model, Tool
from app.catalogs.schemas import ModelCreate, StatusUpdate, ToolCreate, UserRead
from app.db.session import DatabaseSession
from app.identity.auth import CurrentUser, require_admin
from app.identity.models import User

router = APIRouter(prefix="/api/v1", tags=["catalogs"])


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return user


@router.get("/users", response_model=list[UserRead])
def users(session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    return session.scalars(select(User).order_by(User.id)).all()


def catalog_item(session, entity, item_id):
    item = session.get(entity, item_id)
    if item is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Catalog item not found"})
    return item


@router.get("/models", response_model=list[ModelCreate])
def models(session: DatabaseSession, user: CurrentUser, approved_only: bool = True):
    if not approved_only:
        require_admin(user)
    query = select(Model).order_by(Model.id)
    return session.scalars(
        query.where(Model.status == "approved") if approved_only else query
    ).all()


@router.get("/models/{item_id}", response_model=ModelCreate)
def model_detail(item_id: str, session: DatabaseSession, user: CurrentUser):
    item = catalog_item(session, Model, item_id)
    if item.status != "approved":
        require_admin(user)
    return item


@router.post("/models", response_model=ModelCreate, status_code=201)
def add_model(data: ModelCreate, session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    item = Model(**data.model_dump())
    session.add(item)
    session.commit()
    return item


@router.patch("/models/{item_id}", response_model=ModelCreate)
def approve_model(item_id: str, data: StatusUpdate, session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    item = catalog_item(session, Model, item_id)
    item.status = data.status
    session.commit()
    return item


@router.delete("/models/{item_id}", status_code=204)
def delete_model(item_id: str, session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    session.delete(catalog_item(session, Model, item_id))
    session.commit()
    return Response(status_code=204)


@router.get("/tools", response_model=list[ToolCreate])
def tools(session: DatabaseSession, user: CurrentUser, approved_only: bool = True):
    if not approved_only:
        require_admin(user)
    query = select(Tool).order_by(Tool.id)
    return session.scalars(query.where(Tool.status == "approved") if approved_only else query).all()


@router.get("/tools/{item_id}", response_model=ToolCreate)
def tool_detail(item_id: str, session: DatabaseSession, user: CurrentUser):
    item = catalog_item(session, Tool, item_id)
    if item.status != "approved":
        require_admin(user)
    return item


@router.post("/tools", response_model=ToolCreate, status_code=201)
def add_tool(data: ToolCreate, session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    item = Tool(**data.model_dump())
    session.add(item)
    session.commit()
    return item


@router.patch("/tools/{item_id}", response_model=ToolCreate)
def approve_tool(item_id: str, data: StatusUpdate, session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    item = catalog_item(session, Tool, item_id)
    item.status = data.status
    session.commit()
    return item


@router.delete("/tools/{item_id}", status_code=204)
def delete_tool(item_id: str, session: DatabaseSession, user: CurrentUser):
    require_admin(user)
    session.delete(catalog_item(session, Tool, item_id))
    session.commit()
    return Response(status_code=204)
