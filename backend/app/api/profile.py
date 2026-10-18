"""Profile, preferences and account endpoints.

Every route resolves the user from the session via get_current_user. No route
accepts a user id in its path, query or body, so one user cannot address
another's record by manipulating the request.
"""
from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.core.security import hash_password, verify_password
from app.models.profile import UserProfile
from app.schemas.auth import MessageResponse
from app.schemas.profile import (
    AccountResponse,
    EffectiveIngestSettings,
    PasswordChangeRequest,
    PreferencesResponse,
    PreferencesUpdate,
    ProfileResponse,
    ProfileUpdate,
)
from app.services import ingest_settings
from app.services import profiles as profile_service

router = APIRouter(prefix="/api", tags=["profile"])


def _to_response(profile: UserProfile) -> ProfileResponse:
    percent, done, total = profile_service.completion(profile)
    return ProfileResponse.model_validate(profile).model_copy(
        update={
            "completion_percent": percent,
            "completed_fields": done,
            "total_fields": total,
        }
    )


@router.get("/profile", response_model=ProfileResponse)
def read_profile(current_user: CurrentUser, db: DbSession) -> ProfileResponse:
    profile = profile_service.get_profile(db, current_user.id)
    db.commit()
    db.refresh(profile)
    return _to_response(profile)


@router.patch("/profile", response_model=ProfileResponse)
def write_profile(
    payload: ProfileUpdate, current_user: CurrentUser, db: DbSession
) -> ProfileResponse:
    profile = profile_service.update_profile(db, current_user.id, payload.model_dump())
    db.commit()
    db.refresh(profile)
    return _to_response(profile)


def _with_effective(prefs) -> PreferencesResponse:
    """The stored row plus the budget actually in force.

    A null column means "inherit", so the stored row alone cannot tell the
    settings screen what a document will be chunked at. The resolved values
    are computed on every read rather than stored, so they cannot drift from
    the deployment defaults they are merged with.
    """
    resolved = ingest_settings.resolve(prefs)
    response = PreferencesResponse.model_validate(prefs)
    response.effective = EffectiveIngestSettings(
        embedding_model=resolved.embedding_model,
        embedding_dimensions=resolved.embedding_dimensions,
        embedding_context_limit=resolved.context_limit,
        chunk_target_tokens=resolved.target_tokens,
        chunk_overlap_tokens=resolved.overlap_tokens,
        chunk_target_chars=resolved.target_chars,
        overridden=sorted(resolved.overrides),
    )
    return response


@router.get("/preferences", response_model=PreferencesResponse)
def read_preferences(current_user: CurrentUser, db: DbSession) -> PreferencesResponse:
    prefs = profile_service.get_preferences(db, current_user.id)
    db.commit()
    db.refresh(prefs)
    return _with_effective(prefs)


@router.patch("/preferences", response_model=PreferencesResponse)
def write_preferences(
    payload: PreferencesUpdate, current_user: CurrentUser, db: DbSession
) -> PreferencesResponse:
    # exclude_unset so an omitted field is left alone rather than nulled.
    prefs = profile_service.update_preferences(
        db, current_user.id, payload.model_dump(exclude_unset=True)
    )
    # Checked on the merged row, before the commit. A chunk target and a
    # context limit are each valid alone and impossible together, so one
    # field at a time is exactly how an unembeddable library gets written.
    try:
        ingest_settings.check(prefs)
    except ingest_settings.InvalidIngestSettings as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    db.commit()
    db.refresh(prefs)
    return _with_effective(prefs)


@router.get("/account", response_model=AccountResponse)
def read_account(current_user: CurrentUser) -> AccountResponse:
    return AccountResponse.model_validate(current_user)


@router.post("/account/password", response_model=MessageResponse)
def change_password(
    payload: PasswordChangeRequest, current_user: CurrentUser, db: DbSession
) -> MessageResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current one",
        )
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return MessageResponse(message="Password updated")
