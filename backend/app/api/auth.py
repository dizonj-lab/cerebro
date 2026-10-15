"""Authentication endpoints: signup, login, me, logout."""
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import LoginRequest, MessageResponse, SignupRequest, UserResponse
from app.services import users as user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

settings = get_settings()


def _set_session_cookie(response: Response, user_id) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=create_access_token(user_id),
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,  # not readable from JavaScript
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
    )


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: DbSession) -> User:
    """Register a new account and start an authenticated session."""
    try:
        user = user_service.create_user(
            db,
            display_name=payload.display_name,
            email=payload.email,
            password=payload.password,
        )
        db.commit()
    except IntegrityError:
        # The unique index rejected the email — another account already owns it.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        ) from None

    db.refresh(user)
    _set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> User:
    """Exchange credentials for a session cookie."""
    user = user_service.authenticate(db, email=payload.email, password=payload.password)
    if user is None:
        # One message for both "unknown email" and "wrong password": the client
        # must not be able to enumerate registered accounts.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    from datetime import UTC, datetime

    user.last_login_at = datetime.now(UTC)
    db.commit()
    _set_session_cookie(response, user.id)
    return user


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return current_user


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response) -> MessageResponse:
    """Clear the session cookie.

    Unconditionally successful: logging out of an already-dead session is not
    an error, and the endpoint must not require a valid token to clean up.
    """
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        domain=settings.cookie_domain,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    return MessageResponse(message="Signed out")
