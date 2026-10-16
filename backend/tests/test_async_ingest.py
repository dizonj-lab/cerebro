"""Deferred ingestion and deletion.

A large upload is answered for as soon as its bytes are stored, and read
afterwards. A deleted artifact takes its knowledge with it.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Artifact, FragmentEmbedding, KnowledgeFragment
from app.services.artifacts import service

SMALL = b"A short note about ledger retention.\n"


def big_text(size: int = 1_200_000) -> bytes:
    """Over the inline limit, and with real sentences so extraction works."""
    sentence = "The retention schedule for ledger exports is seven years. "
    return (sentence * (size // len(sentence) + 1)).encode()


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload(client, name: str, content: bytes):
    return client.post("/api/artifacts", files={"file": (name, content, "text/plain")})


def test_a_small_file_is_read_inside_the_request(client, signed_in):
    body = upload(client, "note.txt", SMALL).json()

    # Nothing to poll for: the round trip is simpler than a poll at this size.
    assert body["status"] == "inspected"
    assert body["extraction"]["block_count"] >= 1


def test_a_large_file_returns_before_it_is_read(client, signed_in):
    """The browser is not held while a big document is extracted."""
    response = upload(client, "big.txt", big_text())

    assert response.status_code == 201
    body = response.json()
    # Stored, and honest that it has not been read yet: no metadata is
    # proposed and no text exists.
    assert body["status"] == "processing"
    assert body["extraction"] == {}
    assert body["metadata"]["title"] is None


def test_a_large_file_is_read_in_the_background(client, signed_in):
    """TestClient runs background tasks after the response, as the server does."""
    artifact = upload(client, "big.txt", big_text()).json()

    later = client.get(f"/api/artifacts/{artifact['id']}").json()

    assert later["status"] == "inspected"
    assert later["extraction"]["character_count"] > 1_000_000
    assert later["preview"]


def test_a_large_file_can_still_be_refused_in_the_request(client, signed_in):
    """Cheap refusals do not wait for the background: the bytes decide."""
    response = client.post(
        "/api/artifacts",
        files={"file": ("claims.pdf", big_text(), "application/pdf")},
    )

    # The extension says PDF, the bytes say otherwise.
    assert response.status_code == 400
    assert "pdf" in response.json()["detail"].lower()


def test_a_duplicate_is_refused_before_anything_is_stored(client, signed_in):
    upload(client, "big.txt", big_text())
    again = upload(client, "copy.txt", big_text())

    assert again.status_code == 409


def test_processing_can_be_retried_and_is_idempotent(client, signed_in, db):
    """An artifact stuck at processing — the API restarted — can be read again."""
    artifact = upload(client, "big.txt", big_text()).json()
    row = db.get(Artifact, artifact["id"])
    db.refresh(row)
    assert row.status == "inspected"

    # Put it back to processing, as an interrupted task would have left it.
    row.status = "processing"
    row.extraction = {}
    db.commit()

    client.post(f"/api/artifacts/{artifact['id']}/process")
    body = client.get(f"/api/artifacts/{artifact['id']}").json()
    assert body["status"] == "inspected"

    # Asking again changes nothing: a review in progress cannot be clobbered.
    client.post(f"/api/artifacts/{artifact['id']}/process")
    assert client.get(f"/api/artifacts/{artifact['id']}").json()["status"] == "inspected"


def test_a_background_refusal_is_recorded_on_the_artifact(client, signed_in, db, monkeypatch):
    """The request has answered, so the reason has to live somewhere."""
    from app.services.artifacts.extraction.base import ExtractionFailed

    def refuse(self, content, *, filename):  # noqa: ANN001, ARG001
        raise ExtractionFailed("This PDF has no text layer.")

    monkeypatch.setattr(
        "app.services.artifacts.extraction.plain_text.PlainTextAdapter.extract", refuse
    )
    artifact = upload(client, "big.txt", big_text()).json()

    body = client.get(f"/api/artifacts/{artifact['id']}").json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "This PDF has no text layer."


# --- deletion ---------------------------------------------------------------

def test_deleting_an_artifact_removes_its_knowledge_too(client, signed_in, db):
    artifact = upload(client, "note.txt", SMALL).json()
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={"metadata": {"title": "Ledger note", "topics": ["Records"]}, "approve": True},
    )
    assert db.scalars(select(KnowledgeFragment)).all()

    assert client.delete(f"/api/artifacts/{artifact['id']}").status_code == 204

    # A deleted document must not leave retrievable passages behind.
    assert db.scalars(select(KnowledgeFragment)).all() == []
    assert db.scalars(select(FragmentEmbedding)).all() == []
    assert db.scalars(select(Artifact)).all() == []
    assert client.post("/api/search", json={"query": "ledger"}).json()["total"] == 0


def test_deleting_removes_the_stored_bytes(client, signed_in, db):
    from app.core.storage import get_object_store

    artifact = upload(client, "note.txt", SMALL).json()
    row = db.get(Artifact, artifact["id"])
    key = row.storage_key

    client.delete(f"/api/artifacts/{artifact['id']}")

    with pytest.raises(OSError):
        get_object_store().get(key)


def test_deleting_the_same_artifact_twice_is_not_found(client, signed_in):
    artifact = upload(client, "note.txt", SMALL).json()

    assert client.delete(f"/api/artifacts/{artifact['id']}").status_code == 204
    assert client.delete(f"/api/artifacts/{artifact['id']}").status_code == 404


def test_one_user_cannot_delete_anothers_artifact(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    artifact = upload(client, "note.txt", SMALL).json()
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json=dict(valid_signup, email="other@example.com"))
    # Not found rather than forbidden: the endpoint must not reveal what
    # exists in another library.
    assert client.delete(f"/api/artifacts/{artifact['id']}").status_code == 404

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": valid_signup["email"], "password": valid_signup["password"]},
    )
    assert client.get(f"/api/artifacts/{artifact['id']}").status_code == 200


def test_deletion_requires_a_session(client):
    import uuid

    assert client.delete(f"/api/artifacts/{uuid.uuid4()}").status_code == 401


def test_the_inline_limit_is_what_decides(client, signed_in):
    """Just under the limit is read inline; just over is deferred."""
    just_under = b"x" * (service.INLINE_BYTES - 1024)
    assert upload(client, "under.txt", just_under).json()["status"] == "inspected"

    just_over = b"y" * (service.INLINE_BYTES + 1024)
    assert upload(client, "over.txt", just_over).json()["status"] == "processing"
