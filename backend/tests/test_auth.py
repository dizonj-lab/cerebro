"""Authentication API tests — covers work-package TESTs 2, 3, 4, 5, 7 and 8."""
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_password
from app.models import User

settings = get_settings()


# --- TEST 2: sign-up -------------------------------------------------------

def test_signup_creates_user(client, db, valid_signup):
    r = client.post("/api/auth/signup", json=valid_signup)
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["display_name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"
    uuid.UUID(body["id"])  # id is a UUID
    assert "password" not in body and "password_hash" not in body


def test_signup_persists_hashed_password_in_postgres(client, db, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)

    user = db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None, "user row must exist in PostgreSQL"
    assert user.password_hash != valid_signup["password"], "password stored in plaintext"
    assert user.password_hash.startswith("$argon2id$"), "expected an Argon2id hash"
    assert verify_password(valid_signup["password"], user.password_hash)
    assert user.created_at is not None and user.updated_at is not None


def test_signup_sets_session_cookie(client, valid_signup):
    r = client.post("/api/auth/signup", json=valid_signup)
    assert settings.cookie_name in r.cookies
    set_cookie = r.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie


@pytest.mark.parametrize(
    "patch,field",
    [
        ({"display_name": ""}, "display_name"),
        ({"display_name": "   "}, "display_name"),
        ({"email": "not-an-email"}, "email"),
        ({"password": "short1"}, "password"),
        ({"password": "abcdefghijkl"}, "password"),   # no digit
        ({"password": "123456789012"}, "password"),   # no letter
    ],
)
def test_signup_rejects_invalid_input(client, valid_signup, patch, field):
    r = client.post("/api/auth/signup", json={**valid_signup, **patch})
    assert r.status_code == 422
    assert any(field in str(d["loc"]) for d in r.json()["detail"])


def test_signup_normalises_email_case(client, db, valid_signup):
    client.post("/api/auth/signup", json={**valid_signup, "email": "Ada@Example.COM"})
    assert db.scalar(select(User).where(User.email == "ada@example.com")) is not None


# --- TEST 3: duplicate account --------------------------------------------

def test_duplicate_email_rejected_gracefully(client, db, valid_signup):
    assert client.post("/api/auth/signup", json=valid_signup).status_code == 201

    r = client.post("/api/auth/signup", json={**valid_signup, "display_name": "Impostor"})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]

    assert len(db.scalars(select(User)).all()) == 1, "duplicate must not create a second row"


def test_duplicate_email_is_case_insensitive(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    r = client.post("/api/auth/signup", json={**valid_signup, "email": "ADA@EXAMPLE.COM"})
    assert r.status_code == 409


# --- TEST 4: login ---------------------------------------------------------

def test_login_succeeds_and_establishes_session(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    client.cookies.clear()

    r = client.post(
        "/api/auth/login",
        json={"email": valid_signup["email"], "password": valid_signup["password"]},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "ada@example.com"
    assert settings.cookie_name in r.cookies


def test_login_email_is_case_insensitive(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    r = client.post(
        "/api/auth/login",
        json={"email": "ADA@EXAMPLE.COM", "password": valid_signup["password"]},
    )
    assert r.status_code == 200


# --- TEST 5: invalid login -------------------------------------------------

def test_login_wrong_password_rejected(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    client.cookies.clear()

    r = client.post(
        "/api/auth/login",
        json={"email": valid_signup["email"], "password": "wrong-password-123"},
    )
    assert r.status_code == 401
    assert settings.cookie_name not in r.cookies


def test_login_failure_does_not_leak_account_existence(client, valid_signup):
    """The message for an unknown email must match the one for a bad password."""
    client.post("/api/auth/signup", json=valid_signup)

    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"}
    )
    wrong = client.post(
        "/api/auth/login", json={"email": valid_signup["email"], "password": "whatever-123"}
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"] == "Invalid email or password"


def test_login_error_never_exposes_hash(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    r = client.post(
        "/api/auth/login",
        json={"email": valid_signup["email"], "password": "nope123456"},
    )
    assert "argon2" not in r.text.lower() and "hash" not in r.text.lower()


# --- TEST 7: session -------------------------------------------------------

def test_me_returns_current_user_with_cookie(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)

    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "ada@example.com"


def test_me_requires_authentication(client):
    client.cookies.clear()
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_rejects_tampered_token(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    client.cookies.set(settings.cookie_name, "not.a.valid.jwt")
    assert client.get("/api/auth/me").status_code == 401


def test_me_accepts_bearer_token(client, valid_signup):
    signup = client.post("/api/auth/signup", json=valid_signup)
    token = signup.cookies[settings.cookie_name]
    client.cookies.clear()

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_token_for_deleted_user_is_rejected(client, db, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    db.query(User).delete()
    db.commit()

    assert client.get("/api/auth/me").status_code == 401


# --- TEST 8: logout --------------------------------------------------------

def test_logout_clears_session(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    assert client.get("/api/auth/me").status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code == 200

    assert client.get("/api/auth/me").status_code == 401, "session survived logout"


def test_logout_without_session_is_not_an_error(client):
    client.cookies.clear()
    assert client.post("/api/auth/logout").status_code == 200


# --- system ----------------------------------------------------------------

def test_health_reports_database_up(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up"}
