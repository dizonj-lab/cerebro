"""Bulk upload and bulk registration.

The property that matters: a batch is a set of independent files. One bad
file costs the user that file, never the batch — and registration is the
same path a single approval takes, so fragments and embeddings are built
exactly as they would be one at a time.
"""
import pytest
from sqlalchemy import select

from app.models import Artifact, FragmentEmbedding, KnowledgeFragment

TEXT = (
    b"The Atlas migration moves forty database clusters in March. Atlas reporting "
    b"runs in parallel during the migration. Database tests precede Atlas cutover.\n"
)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def files(*entries):
    return [("files", entry) for entry in entries]


def text(name, extra=b""):
    return (name, TEXT + extra, "text/plain")


def test_several_files_are_accepted_in_one_request(client, signed_in, db):
    r = client.post(
        "/api/artifacts/bulk",
        files=files(text("a.txt"), text("b.txt", b"Second.\n"), text("c.txt", b"Third.\n")),
    )
    assert r.status_code == 207
    body = r.json()

    assert body["accepted"] == 3
    assert body["rejected"] == 0
    assert all(item["accepted"] for item in body["items"])
    # Each is inspected and awaiting review, exactly like a single upload.
    assert {a.status for a in db.scalars(select(Artifact)).all()} == {"inspected"}


def test_one_bad_file_does_not_cost_the_batch(client, signed_in, db):
    r = client.post(
        "/api/artifacts/bulk",
        files=files(
            text("good.txt"),
            ("image.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "image/png"),
            text("also-good.txt", b"Another.\n"),
        ),
    )
    body = r.json()

    assert body["accepted"] == 2
    assert body["rejected"] == 1
    refused = next(item for item in body["items"] if not item["accepted"])
    assert refused["filename"] == "image.png"
    # The same message a single upload gives, not a generic batch failure.
    assert "cannot read this file type" in refused["error"]
    assert len(db.scalars(select(Artifact)).all()) == 2


def test_a_duplicate_inside_a_batch_is_named(client, signed_in):
    client.post("/api/artifacts", files={"file": text("first.txt")})

    body = client.post("/api/artifacts/bulk", files=files(text("copy.txt"))).json()
    assert body["rejected"] == 1
    assert "already in your library as 'first.txt'" in body["items"][0]["error"]


def test_a_batch_has_a_limit(client, signed_in):
    too_many = files(*[text(f"f{i}.txt", f"Body {i}.\n".encode()) for i in range(26)])
    r = client.post("/api/artifacts/bulk", files=too_many)

    assert r.status_code == 400
    assert "25 files at a time" in r.json()["detail"]


# --- registering a batch ---------------------------------------------------

def test_registering_a_batch_chunks_and_embeds_every_artifact(client, signed_in, db):
    uploaded = client.post(
        "/api/artifacts/bulk",
        files=files(text("a.txt"), text("b.txt", b"Second document body.\n")),
    ).json()
    ids = [item["artifact"]["id"] for item in uploaded["items"]]

    r = client.patch(
        "/api/artifacts/bulk",
        json={
            "items": [
                {"id": artifact_id, "metadata": {"title": f"Doc {i}", "topics": ["Atlas"]}}
                for i, artifact_id in enumerate(ids)
            ],
            "approve": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["registered"] == 2
    assert body["failed"] == 0

    # The same pipeline as a single approval: fragments and vectors exist.
    assert {a.status for a in db.scalars(select(Artifact)).all()} == {"registered"}
    fragments = db.scalars(select(KnowledgeFragment)).all()
    embeddings = db.scalars(select(FragmentEmbedding)).all()
    assert len(fragments) >= 2
    assert len(embeddings) == len(fragments)


def test_bulk_registration_records_human_confirmation(client, signed_in, db):
    uploaded = client.post("/api/artifacts/bulk", files=files(text("a.txt"))).json()
    artifact_id = uploaded["items"][0]["artifact"]["id"]

    client.patch(
        "/api/artifacts/bulk",
        json={
            "items": [{"id": artifact_id, "metadata": {"title": "Confirmed", "topics": ["Atlas"]}}],
            "approve": True,
        },
    )
    row = db.scalars(select(Artifact)).one()
    assert row.field_methods["title"] == "human_confirmed"
    assert row.integrity["human_approved"] is True
    assert row.integrity["source_verified"] is True


def test_one_failure_leaves_the_others_registered(client, signed_in, db):
    uploaded = client.post(
        "/api/artifacts/bulk", files=files(text("a.txt"), text("b.txt", b"Second.\n"))
    ).json()
    ids = [item["artifact"]["id"] for item in uploaded["items"]]

    body = client.patch(
        "/api/artifacts/bulk",
        json={
            "items": [
                {"id": ids[0], "metadata": {"title": "Fine", "topics": ["Atlas"]}},
                {
                    "id": "00000000-0000-0000-0000-000000000000",
                    "metadata": {"title": "Missing", "topics": []},
                },
                {"id": ids[1], "metadata": {"title": "Also fine", "topics": ["Atlas"]}},
            ],
            "approve": True,
        },
    ).json()

    assert body["registered"] == 2
    assert body["failed"] == 1
    assert next(i for i in body["items"] if not i["registered"])["error"] == "Artifact not found"


def test_a_batch_can_be_saved_as_drafts_without_registering(client, signed_in, db):
    uploaded = client.post("/api/artifacts/bulk", files=files(text("a.txt"))).json()
    artifact_id = uploaded["items"][0]["artifact"]["id"]

    body = client.patch(
        "/api/artifacts/bulk",
        json={
            "items": [{"id": artifact_id, "metadata": {"title": "Draft", "topics": []}}],
            "approve": False,
        },
    ).json()

    assert body["registered"] == 0
    assert db.scalars(select(Artifact)).one().status == "inspected"
    # Nothing unapproved reaches retrieval.
    assert db.scalars(select(KnowledgeFragment)).all() == []


def test_one_user_cannot_register_another_users_artifact(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    uploaded = client.post("/api/artifacts/bulk", files=files(text("private.txt"))).json()
    artifact_id = uploaded["items"][0]["artifact"]["id"]
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/signup",
        json={
            "display_name": "Grace Hopper",
            "email": "grace@example.com",
            "password": "compiler-1952-nanoseconds",
        },
    )
    body = client.patch(
        "/api/artifacts/bulk",
        json={"items": [{"id": artifact_id, "metadata": {"title": "Stolen", "topics": []}}]},
    ).json()

    assert body["registered"] == 0
    assert body["items"][0]["error"] == "Artifact not found"


def test_bulk_routes_require_a_session(client):
    assert client.post("/api/artifacts/bulk", files=files(text("a.txt"))).status_code == 401
    assert client.patch("/api/artifacts/bulk", json={"items": []}).status_code in (401, 422)
