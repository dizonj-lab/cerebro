"""Test fixtures. These run against a real PostgreSQL database, not a stub."""
import os
import tempfile

# Point the application at the test database before any app module is imported,
# since settings are cached and the engine is created at import time.
os.environ.setdefault(
    "CEREBRO_DATABASE_URL",
    "postgresql+psycopg://cerebro:cerebro_dev_password@127.0.0.1:5432/cerebro_test",
)
# Artifact bytes go to a throwaway directory, never the development store.
_TEST_STORAGE = tempfile.mkdtemp(prefix="cerebro-test-artifacts-")
os.environ["CEREBRO_STORAGE_BACKEND"] = "filesystem"
os.environ["CEREBRO_STORAGE_PATH"] = _TEST_STORAGE
# The suite pins the deterministic embedder and switches local answering off,
# so no test depends on whether an Ollama daemon happens to be running on the
# machine running it. Tests that exercise the Ollama path start a fake daemon
# and point the settings at it explicitly.
os.environ["CEREBRO_EMBEDDING_PROVIDER"] = "hashing"
os.environ["CEREBRO_RECALL_LLM"] = "off"
os.environ["CEREBRO_ENRICHMENT_LLM"] = "off"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.storage import clear_filesystem_store  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402,F401
    Artifact,
    User,
    UserPreferences,
    UserProfile,
)


# Database fixtures are deliberately NOT autouse. Pure-logic suites —
# extraction, chunking, the registration gate — are then runnable with no
# PostgreSQL at all:
#
#     pytest tests/test_extraction.py
#
# Anything needing the database asks for `db` or `client`, which pull the
# schema and cleanup fixtures in behind them.
@pytest.fixture(scope="session")
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def _clean_users(_schema):
    """Each test starts from an empty database and an empty object store."""
    clear_filesystem_store(_TEST_STORAGE)
    with SessionLocal() as db:
        db.query(Artifact).delete()
        db.query(UserProfile).delete()
        db.query(UserPreferences).delete()
        db.query(User).delete()
        db.commit()
    yield


@pytest.fixture
def db(_clean_users):
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(_clean_users):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def valid_signup():
    return {
        "display_name": "Ada Lovelace",
        "email": "ada@example.com",
        "password": "analytical-engine-1843",
    }


@pytest.fixture
def text_file():
    """A small valid UTF-8 text artifact."""
    return (
        "benchmark_001.txt",
        b"CEREBRO is a Digital Knowledge Twin.\nIt preserves provenance to source artifacts.\n",
        "text/plain",
    )


@pytest.fixture
def upload(client, text_file):
    """Upload the sample artifact and return the response body."""
    name, content, ctype = text_file
    return client.post("/api/artifacts", files={"file": (name, content, ctype)}).json()
