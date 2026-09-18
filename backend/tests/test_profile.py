"""Phase 1.5 — profile, preferences, account."""
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_password
from app.models import User, UserPreferences, UserProfile

settings = get_settings()


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def other_user(client, valid_signup):
    """Create a second account and return its cookie, restoring the first."""
    original = client.cookies.get(settings.cookie_name)
    client.cookies.clear()
    client.post("/api/auth/signup", json={
        "display_name": "Second Person", "email": "second@example.com",
        "password": valid_signup["password"],
    })
    second = client.cookies.get(settings.cookie_name)
    client.cookies.clear()
    if original:
        client.cookies.set(settings.cookie_name, original)
    return second


# --- profile ---------------------------------------------------------------

def test_empty_profile_is_created_on_first_read(client, signed_in, db):
    r = client.get("/api/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] is None
    assert body["expertise"] == []
    assert body["completion_percent"] == 0
    assert body["total_fields"] > 0
    assert db.scalars(select(UserProfile)).all()


def test_profile_update_persists(client, signed_in, db):
    r = client.patch("/api/profile", json={
        "full_name": "Ada Lovelace", "role_title": "Analyst",
        "expertise": ["Mathematics", "Computing"], "years_experience": 12,
    })
    assert r.status_code == 200
    assert r.json()["full_name"] == "Ada Lovelace"

    stored = db.scalars(select(UserProfile)).one()
    db.refresh(stored)
    assert stored.full_name == "Ada Lovelace"
    assert stored.expertise == ["Mathematics", "Computing"]


def test_profile_survives_logout_and_login(client, signed_in):
    client.patch("/api/profile", json={"full_name": "Ada Lovelace", "location": "London"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login",
                json={"email": signed_in["email"], "password": signed_in["password"]})

    body = client.get("/api/profile").json()
    assert body["full_name"] == "Ada Lovelace"
    assert body["location"] == "London"


def test_completion_is_deterministic(client, signed_in):
    empty = client.get("/api/profile").json()
    assert empty["completion_percent"] == 0

    filled = client.patch("/api/profile", json={
        "full_name": "A", "bio": "B", "location": "C", "timezone": "UTC",
        "role_title": "D", "organization": "E", "industry": "F",
        "years_experience": 3, "expertise": ["x"], "interests": ["y"],
        "current_topics": ["z"], "learning_goals": "G",
    }).json()
    assert filled["completion_percent"] == 100
    assert filled["completed_fields"] == filled["total_fields"]

    # Same input, same answer.
    assert client.get("/api/profile").json()["completion_percent"] == 100


def test_tags_are_normalised(client, signed_in):
    body = client.patch("/api/profile", json={
        "expertise": ["  AI  ", "ai", "Systems", ""],
    }).json()
    assert body["expertise"] == ["AI", "Systems"]


@pytest.mark.parametrize("payload", [
    {"years_experience": -1},
    {"years_experience": 200},
    {"full_name": "x" * 200},
    {"bio": "x" * 2000},
])
def test_invalid_profile_input_rejected(client, signed_in, payload):
    assert client.patch("/api/profile", json=payload).status_code == 422


# --- preferences -----------------------------------------------------------

def test_preferences_defaults_are_private_and_local(client, signed_in):
    body = client.get("/api/preferences").json()
    assert body["ai_processing_mode"] == "local"
    assert body["knowledge_visibility"] == "private"
    assert body["cloud_ai_consent"] is False
    assert body["cloud_ai_consent_at"] is None


def test_preferences_persist(client, signed_in, db):
    client.patch("/api/preferences", json={"response_style": "concise", "ai_suggestions": False})
    body = client.get("/api/preferences").json()
    assert body["response_style"] == "concise"
    assert body["ai_suggestions"] is False
    assert db.scalars(select(UserPreferences)).all()


def test_cloud_mode_requires_consent(client, signed_in):
    """Selecting cloud without consent must not move processing off local."""
    body = client.patch("/api/preferences", json={"ai_processing_mode": "cloud"}).json()
    assert body["ai_processing_mode"] == "local"
    assert body["cloud_ai_consent"] is False


def test_cloud_mode_with_consent_is_recorded(client, signed_in):
    body = client.patch("/api/preferences", json={
        "ai_processing_mode": "cloud", "cloud_ai_consent": True,
    }).json()
    assert body["ai_processing_mode"] == "cloud"
    assert body["cloud_ai_consent"] is True
    assert body["cloud_ai_consent_at"] is not None


def test_switching_back_to_local_works(client, signed_in):
    client.patch("/api/preferences", json={"ai_processing_mode": "cloud", "cloud_ai_consent": True})
    body = client.patch("/api/preferences", json={"ai_processing_mode": "local"}).json()
    assert body["ai_processing_mode"] == "local"
    # Consent stays recorded; it is a fact about what the user agreed to.
    assert body["cloud_ai_consent"] is True


def test_withdrawing_consent_forces_local(client, signed_in):
    client.patch("/api/preferences", json={"ai_processing_mode": "cloud", "cloud_ai_consent": True})
    body = client.patch("/api/preferences", json={"cloud_ai_consent": False}).json()
    assert body["cloud_ai_consent"] is False
    assert body["cloud_ai_consent_at"] is None
    assert body["ai_processing_mode"] == "local"


def test_invalid_preference_values_rejected(client, signed_in):
    assert client.patch("/api/preferences", json={"response_style": "shouty"}).status_code == 422
    assert client.patch(
        "/api/preferences", json={"ai_processing_mode": "quantum"}).status_code == 422


def test_preferences_never_expose_credentials(client, signed_in):
    text = client.get("/api/preferences").text.lower()
    for leak in ("api_key", "apikey", "secret", "token", "password"):
        assert leak not in text


# --- account ---------------------------------------------------------------

def test_account_returns_safe_fields_only(client, signed_in):
    body = client.get("/api/account").json()
    assert body["email"] == signed_in["email"]
    assert body["created_at"]
    assert "password_hash" not in body and "password" not in body
    assert "argon2" not in client.get("/api/account").text.lower()


def test_last_login_recorded(client, signed_in):
    assert client.get("/api/account").json()["last_login_at"] is None
    client.post("/api/auth/logout")
    client.post("/api/auth/login",
                json={"email": signed_in["email"], "password": signed_in["password"]})
    assert client.get("/api/account").json()["last_login_at"] is not None


def test_password_change(client, signed_in, db):
    r = client.post("/api/account/password", json={
        "current_password": signed_in["password"], "new_password": "brand-new-secret-2026",
    })
    assert r.status_code == 200

    user = db.scalars(select(User)).one()
    db.refresh(user)
    assert verify_password("brand-new-secret-2026", user.password_hash)

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={
        "email": signed_in["email"], "password": "brand-new-secret-2026"}).status_code == 200


def test_password_change_requires_correct_current(client, signed_in):
    assert client.post("/api/account/password", json={
        "current_password": "wrong-one-12345", "new_password": "brand-new-secret-2026",
    }).status_code == 400


def test_weak_new_password_rejected(client, signed_in):
    assert client.post("/api/account/password", json={
        "current_password": signed_in["password"], "new_password": "short1",
    }).status_code == 422


# --- security --------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/profile"), ("patch", "/api/profile"),
    ("get", "/api/preferences"), ("patch", "/api/preferences"),
    ("get", "/api/account"), ("post", "/api/account/password"),
])
def test_unauthenticated_requests_rejected(client, method, path):
    client.cookies.clear()
    r = getattr(client, method)(path) if method == "get" else getattr(client, method)(path, json={})
    assert r.status_code == 401


def test_user_cannot_read_or_write_another_users_profile(client, valid_signup, db):
    """Identity comes from the session, so there is no id to tamper with."""
    client.post("/api/auth/signup", json=valid_signup)
    client.patch("/api/profile", json={"full_name": "First Person"})
    first_id = str(db.scalars(select(User).where(User.email == valid_signup["email"])).one().id)

    second_cookie = other_user(client, valid_signup)
    client.cookies.clear()
    client.cookies.set(settings.cookie_name, second_cookie)

    # The second user sees only their own, empty, profile.
    assert client.get("/api/profile").json()["full_name"] is None

    # Supplying the first user's id in the payload changes nothing.
    client.patch("/api/profile", json={"full_name": "Hijacked", "user_id": first_id})

    profiles = {str(p.user_id): p.full_name for p in db.scalars(select(UserProfile)).all()}
    db.expire_all()
    profiles = {str(p.user_id): p.full_name for p in db.scalars(select(UserProfile)).all()}
    assert profiles[first_id] == "First Person", "another user's profile was modified"


def test_user_id_in_payload_is_ignored(client, signed_in, db):
    import uuid
    client.patch("/api/profile", json={"full_name": "Mine", "user_id": str(uuid.uuid4())})
    rows = db.scalars(select(UserProfile)).all()
    assert len(rows) == 1
