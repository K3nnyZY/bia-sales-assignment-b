import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.db.session import DatabaseSession
from app.identity.models import User

bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(
    request: Request,
    session: DatabaseSession,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if not request.app.state.settings.enable_demo_auth:
        raise HTTPException(
            503,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Local demo authentication is disabled",
            },
        )
    if not credential or len(credential.credentials) > 512:
        raise HTTPException(
            401,
            detail={"code": "UNAUTHENTICATED", "message": "A valid bearer token is required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = session.scalar(select(User).where(User.token_hash == hash_token(credential.credentials)))
    if user is None or not user.active:
        raise HTTPException(
            401,
            detail={"code": "UNAUTHENTICATED", "message": "Invalid or inactive identity"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: User) -> None:
    if user.role != "administrator":
        raise HTTPException(
            403, detail={"code": "FORBIDDEN", "message": "Administrator role required"}
        )
