import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select

from app.db.session import DatabaseSession
from app.identity.models import AccessToken, User

bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(
    request: Request,
    session: DatabaseSession,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    settings = request.app.state.settings
    if not settings.enable_demo_auth and not settings.enable_access_token_auth:
        raise HTTPException(
            503,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Authentication has not been configured",
            },
        )
    if not credential or len(credential.credentials) > 512:
        raise HTTPException(
            401,
            detail={"code": "UNAUTHENTICATED", "message": "A valid bearer token is required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    digest = hash_token(credential.credentials)
    if settings.enable_access_token_auth:
        user = session.scalar(
            select(User)
            .join(AccessToken, AccessToken.user_id == User.id)
            .where(
                AccessToken.token_hash == digest,
                AccessToken.revoked.is_(False),
                AccessToken.expires_at > func.now(),
            )
        )
    else:
        user = session.scalar(select(User).where(User.token_hash == digest))
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
