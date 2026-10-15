"""Artifact ingestion, review and registration."""
import pytest
from sqlalchemy import select

from app.core.storage import get_object_store
from app.models import Artifact
from app.services.artifacts.inspection import inspect_artifact
from app.services.artifacts.registration import RegistrationRejected, register_artifact

APPROVED = {"title": "CEREBRO Digital Knowledge Twin", "topics": ["Provenance"]}


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def post(client, name, content, ctype="text/plain"):
    return client.post("/api/artifacts", files={"file": (name, content, ctype)})


# --- upload / inspection ---------------------------------------------------

def test_upload_inspects_and_stores(client, signed_in, db, text_file):
    name, content, ctype = text_file
    r = post(client, name, content, ctype)
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["status"] == "inspected"
    assert body["modality"] == "text"
    assert body["size_bytes"] == len(content)
    # Checksum is content-derived, matching the PoC contract.
    import hashlib
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    # Title is the filename stem, flagged as such — not a semantic read.
    assert body["metadata"]["title"] == "benchmark_001"
    assert body["field_methods"]["title"] == "filename_stem"
    assert body["integrity"]["human_approved"] is False

    row = db.scalars(select(Artifact)).one()
    assert get_object_store().get(row.storage_key) == content


def test_upload_rejects_empty_file(client, signed_in):
    assert post(client, "empty.txt", b"").status_code == 400


def test_upload_rejects_binary_in_this_phase(client, signed_in, db):
    r = post(client, "image.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png")
    assert r.status_code == 400
    assert "text" in r.json()["detail"].lower()
    # Nothing is stored when inspection refuses.
    assert db.scalars(select(Artifact)).all() == []


def test_upload_rejects_oversize(client, signed_in):
    from app.core.config import get_settings
    big = b"a" * (get_settings().max_upload_bytes + 1)
    assert post(client, "big.txt", big).status_code == 400


def test_duplicate_bytes_rejected(client, signed_in, db, text_file):
    name, content, ctype = text_file
    assert post(client, name, content, ctype).status_code == 201
    r = post(client, "different-name.txt", content, ctype)
    assert r.status_code == 409
    assert len(db.scalars(select(Artifact)).all()) == 1


def test_filename_cannot_influence_storage_key(client, signed_in, db):
    post(client, "../../escape.txt", b"harmless text\n")
    row = db.scalars(select(Artifact)).one()
    assert ".." not in row.storage_key
    assert row.storage_key.startswith(str(row.owner_id))


# --- library ---------------------------------------------------------------

def test_library_lists_own_artifacts(client, signed_in, upload):
    body = client.get("/api/artifacts").json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == upload["id"]


def test_detail_includes_preview(client, signed_in, upload):
    body = client.get(f"/api/artifacts/{upload['id']}").json()
    assert "Digital Knowledge Twin" in body["preview"]


# --- review and registration ----------------------------------------------

def test_review_without_approval_saves_but_does_not_register(client, signed_in, upload):
    r = client.patch(f"/api/artifacts/{upload['id']}",
                     json={"metadata": APPROVED, "approve": False})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "inspected"
    assert body["metadata"]["title"] == APPROVED["title"]
    assert body["integrity"]["human_reviewed"] is True
    assert body["integrity"]["human_approved"] is False
    assert body["registered_at"] is None


def test_approval_registers_with_full_provenance(client, signed_in, upload, db):
    body = client.patch(f"/api/artifacts/{upload['id']}",
                        json={"metadata": APPROVED, "approve": True}).json()

    assert body["status"] == "registered"
    assert body["registered_at"] is not None
    assert body["integrity"] == {
        **body["integrity"],
        "human_reviewed": True, "human_approved": True, "source_verified": True,
        "checksum_verified": True, "provenance_present": True,
        "human_approval_verified": True,
    }
    assert body["provenance"]["human_review"]
    assert body["provenance"]["registration"]["source_verified"] is True
    # AI has not touched this artifact.
    assert body["provenance"]["ai_enrichment"] is None

    row = db.scalars(select(Artifact)).one()
    db.refresh(row)
    assert row.status == "registered"
    assert row.field_methods["title"] == "human_confirmed"


def test_registered_artifact_cannot_be_reviewed_again(client, signed_in, upload):
    client.patch(f"/api/artifacts/{upload['id']}", json={"metadata": APPROVED, "approve": True})
    r = client.patch(f"/api/artifacts/{upload['id']}", json={"metadata": APPROVED, "approve": True})
    assert r.status_code == 400


def test_registration_refuses_when_stored_bytes_drift(client, signed_in, upload, db):
    """Approval alone must not register content that no longer matches."""
    row = db.scalars(select(Artifact)).one()
    get_object_store().put(row.storage_key, b"tampered content\n")

    r = client.patch(f"/api/artifacts/{upload['id']}",
                     json={"metadata": APPROVED, "approve": True})
    assert r.status_code == 409
    assert "checksum" in r.json()["detail"].lower()

    db.expire_all()
    assert db.scalars(select(Artifact)).one().status == "inspected"


# --- the registration gate itself (ported PoC contract) -------------------

@pytest.mark.parametrize("approved", [
    {"metadata": {}, "human_reviewed": False, "human_approved": True, "status": "APPROVED"},
    {"metadata": {}, "human_reviewed": True, "human_approved": False, "status": "APPROVED"},
    {"metadata": {}, "human_reviewed": True, "human_approved": True, "status": "DRAFT"},
])
def test_registration_fails_closed(approved):
    content = b"text\n"
    with pytest.raises(RegistrationRejected):
        register_artifact(
            filename="a.txt", content=content,
            inspection=inspect_artifact("a.txt", content),
            approved_metadata=approved,
        )


def test_registration_requires_a_checksum():
    with pytest.raises(RegistrationRejected):
        register_artifact(
            filename="a.txt", content=b"text\n", inspection={"file": {}},
            approved_metadata={"metadata": {}, "human_reviewed": True,
                               "human_approved": True, "status": "APPROVED"},
        )


# --- deletion --------------------------------------------------------------

def test_delete_removes_row_and_bytes(client, signed_in, upload, db):
    row = db.scalars(select(Artifact)).one()
    key = row.storage_key
    assert client.delete(f"/api/artifacts/{upload['id']}").status_code == 204

    db.expire_all()
    assert db.scalars(select(Artifact)).all() == []
    with pytest.raises(FileNotFoundError):
        get_object_store().get(key)


# --- security --------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/artifacts"), ("post", "/api/artifacts"),
])
def test_unauthenticated_rejected(client, method, path):
    client.cookies.clear()
    r = client.get(path) if method == "get" else client.post(path)
    assert r.status_code == 401


def test_one_user_cannot_reach_another_users_artifact(client, valid_signup, db):
    from app.core.config import get_settings
    cookie = get_settings().cookie_name

    client.post("/api/auth/signup", json=valid_signup)
    first = post(client, "mine.txt", b"my private notes\n").json()

    client.cookies.clear()
    client.post("/api/auth/signup", json={
        "display_name": "Second", "email": "second@example.com",
        "password": valid_signup["password"]})

    # The id is known, the session is not the owner: it simply does not exist.
    assert client.get(f"/api/artifacts/{first['id']}").status_code == 404
    assert client.patch(f"/api/artifacts/{first['id']}",
                        json={"metadata": APPROVED, "approve": True}).status_code == 404
    assert client.delete(f"/api/artifacts/{first['id']}").status_code == 404
    assert client.get("/api/artifacts").json()["total"] == 0

    assert db.scalars(select(Artifact)).one().filename == "mine.txt"
    assert cookie
