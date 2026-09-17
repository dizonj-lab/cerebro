"""Test fixtures. These run against a real PostgreSQL database, not a stub."""
import os

# Point the application at the test database before any app module is imported,
# since settings are cached and the engine is created at import time.
os.environ.setdefault(
    "CEREBRO_DATABASE_URL",
    "postgresql+psycopg://cerebro:cerebro_dev_password@127.0.0.1:5432/cerebro_test",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402,F401


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_users():
    """Each test starts from an empty users table."""
    with SessionLocal() as db:
        db.query(User).delete()
        db.commit()
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def valid_signup():
    return {
        "display_name": "Ada Lovelace",
        "email": "ada@example.com",
        "password": "analytical-engine-1843",
    }
