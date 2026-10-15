"""User persistence and authentication logic, independent of the HTTP layer."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, needs_rehash, verify_password
from app.models.user import User


def normalise_email(email: str) -> str:
    """Emails are compared case-insensitively; store and look up lowercased."""
    return email.strip().lower()


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalise_email(email)))


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, *, display_name: str, email: str, password: str) -> User:
    """Persist a new user with an Argon2id password hash.

    Callers must handle IntegrityError: the unique index on email is the
    authority on duplicates, not a prior existence check, which would race.
    """
    user = User(
        display_name=display_name.strip(),
        email=normalise_email(email),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, *, email: str, password: str) -> User | None:
    """Return the user when the credentials are valid, otherwise None.

    The caller must not distinguish "no such user" from "wrong password" in
    its response.
    """
    user = get_by_email(db, email)
    if user is None:
        # Spend comparable time on a miss so the endpoint does not leak account
        # existence through response timing.
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.flush()
    return user


# Precomputed once at import so authenticate() has a realistic hash to burn time on.
_DUMMY_HASH = hash_password("cerebro-timing-equalisation-placeholder")
