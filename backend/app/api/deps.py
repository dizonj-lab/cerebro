"""Shared FastAPI dependencies."""
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services import users as user_service

settings = get_settings()

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> User:
    """Resolve the session cookie to a User, or raise 401.

    Accepts a bearer token as a fallback so non-browser clients can use the
    same API without a cookie jar.
    """
    token = request.cookies.get(settings.cookie_name)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header.removeprefix("Bearer ").strip()
    if not token:
        raise CREDENTIALS_ERROR

    user_id = decode_access_token(token)
    if user_id is None:
        raise CREDENTIALS_ERROR

    user = user_service.get_by_id(db, user_id)
    if user is None:
        # Token is well-formed but the account is gone.
        raise CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
