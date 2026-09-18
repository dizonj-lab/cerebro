"""Profile and preferences persistence, keyed by the authenticated user."""
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.profile import UserPreferences, UserProfile

# The fields that count toward profile completion. Deterministic and explicit:
# a field counts when it holds a value, nothing is weighted, nothing inferred.
COMPLETION_FIELDS = (
    "full_name",
    "bio",
    "location",
    "timezone",
    "role_title",
    "organization",
    "industry",
    "years_experience",
    "expertise",
    "interests",
    "current_topics",
    "learning_goals",
)


def _is_set(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def completion(profile: UserProfile) -> tuple[int, int, int]:
    """Return (percent, completed, total) over COMPLETION_FIELDS."""
    total = len(COMPLETION_FIELDS)
    done = sum(1 for f in COMPLETION_FIELDS if _is_set(getattr(profile, f, None)))
    return round(done / total * 100), done, total


def get_profile(db: Session, user_id: uuid.UUID) -> UserProfile:
    """Return the user's profile, creating an empty one on first access.

    Lazy creation keeps signup unchanged and means a profile row always exists
    for an authenticated user, so reads never have to handle a missing record.
    """
    profile = db.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id, expertise=[], interests=[], current_topics=[])
        db.add(profile)
        db.flush()
    return profile


def update_profile(db: Session, user_id: uuid.UUID, data: dict) -> UserProfile:
    profile = get_profile(db, user_id)
    for field, value in data.items():
        setattr(profile, field, value)
    db.flush()
    return profile


def get_preferences(db: Session, user_id: uuid.UUID) -> UserPreferences:
    prefs = db.get(UserPreferences, user_id)
    if prefs is None:
        # Model defaults apply: local AI, private knowledge, no cloud consent.
        prefs = UserPreferences(user_id=user_id)
        db.add(prefs)
        db.flush()
    return prefs


def update_preferences(db: Session, user_id: uuid.UUID, data: dict) -> UserPreferences:
    prefs = get_preferences(db, user_id)

    consent = data.pop("cloud_ai_consent", None)
    if consent is not None and consent != prefs.cloud_ai_consent:
        prefs.cloud_ai_consent = consent
        # Timestamp is server-set, never taken from the client.
        prefs.cloud_ai_consent_at = datetime.now(UTC) if consent else None

    for field, value in data.items():
        setattr(prefs, field, value)

    # Cloud processing requires recorded consent. Without it the mode stays
    # local — CEREBRO never silently moves processing outside the environment.
    if prefs.ai_processing_mode == "cloud" and not prefs.cloud_ai_consent:
        prefs.ai_processing_mode = "local"

    db.flush()
    return prefs
