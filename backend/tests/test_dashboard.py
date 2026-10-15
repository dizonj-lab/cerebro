"""Dashboard aggregates.

The load-bearing property: only approved, registered artifacts count as
knowledge. Everything else on the dashboard is either an action the user
still owes (Recent Ingestions) or a fact about storage.
"""
import pytest
from sqlalchemy import select

from app.models import Artifact

APPROVED = {"title": "Atlas Migration", "topics": ["Atlas", "Migration"]}
TEXT = (
    b"Acme Corp met with Globex about the Atlas migration. Atlas moves to Acme Corp "
    b"in March. Globex asked for a revised Atlas timeline for the migration.\n"
)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload(client, name="atlas.txt", content=TEXT):
    return client.post("/api/artifacts", files={"file": (name, content, "text/plain")}).json()


def register(client, artifact_id, metadata=None):
    return client.patch(
        f"/api/artifacts/{artifact_id}",
        json={"metadata": metadata or APPROVED, "approve": True},
    )


def test_an_empty_dashboard_reports_zero_not_nothing(client, signed_in):
    body = client.get("/api/dashboard").json()

    assert body["documents"] == {"total": 0, "new_this_week": 0}
    assert body["fragments"]["total"] == 0
    assert body["topics"]["total"] == 0
    assert body["storage"]["bytes"] == 0
    assert body["recent"] == []
    assert body["topic_distribution"]["slices"] == []
    assert body["knowledge_map"]["center"] is None
    assert body["recollection"] == []
    # Fourteen days of zeroes, not an empty chart.
    assert len(body["activity"]) == 14
    assert all(d["count"] == 0 for d in body["activity"])


def test_an_unapproved_artifact_is_not_counted_as_knowledge(client, signed_in):
    """It appears as work to do, never as a document, fragment or topic."""
    upload(client)
    body = client.get("/api/dashboard").json()

    assert body["documents"]["total"] == 0
    assert body["fragments"]["total"] == 0
    assert body["topics"]["total"] == 0
    assert body["topic_distribution"]["slices"] == []
    assert body["recollection"] == []
    # But the user still has to act on it.
    assert [r["filename"] for r in body["recent"]] == ["atlas.txt"]
    assert body["recent"][0]["status"] == "inspected"
    # The bytes are on disk whether or not it is approved.
    assert body["storage"]["bytes"] == len(TEXT)


def test_registering_moves_an_artifact_into_the_counts(client, signed_in):
    artifact = upload(client)
    assert register(client, artifact["id"]).status_code == 200

    body = client.get("/api/dashboard").json()
    assert body["documents"] == {"total": 1, "new_this_week": 1}
    assert body["fragments"]["total"] >= 1
    assert body["topics"]["total"] == 2
    assert body["recent"][0]["status"] == "registered"
    assert sum(d["count"] for d in body["activity"]) == 1


def test_storage_never_claims_a_percentage_without_a_quota(client, signed_in):
    """A percentage needs a denominator. There is no quota, so there is none."""
    upload(client)
    storage = client.get("/api/dashboard").json()["storage"]

    assert storage["bytes"] > 0
    assert storage["quota_bytes"] is None
    assert storage["percent"] is None


def test_topic_distribution_counts_only_registered_topics(client, signed_in):
    register(client, upload(client, "a.txt")["id"], {"title": "A", "topics": ["Atlas", "Risk"]})
    upload(client, "b.txt", TEXT + b"Unapproved and uncounted.\n")

    distribution = client.get("/api/dashboard").json()["topic_distribution"]
    assert {s["label"] for s in distribution["slices"]} == {"Atlas", "Risk"}
    assert distribution["total"] == 2


def test_the_knowledge_map_uses_co_occurrence_and_says_so(client, signed_in):
    register(client, upload(client, "a.txt")["id"], {"title": "A", "topics": ["Atlas", "Risk"]})
    register(
        client,
        upload(client, "b.txt", TEXT + b"Second document about the same work.\n")["id"],
        {"title": "B", "topics": ["Atlas", "Timeline"]},
    )

    graph = client.get("/api/dashboard").json()["knowledge_map"]
    assert graph["center"] == "Atlas"  # the most frequent topic
    assert {n["label"] for n in graph["nodes"]} == {"Atlas", "Risk", "Timeline"}
    # Edges are artifacts sharing a topic, not an inferred semantic relation.
    assert graph["basis"] == "topic_co_occurrence"
    assert {"Atlas", "Risk"} in [{e["source"], e["target"]} for e in graph["edges"]]


def test_recollection_carries_the_documents_that_evidence_it(client, signed_in):
    artifact = upload(client)
    register(client, artifact["id"])

    items = client.get("/api/dashboard").json()["recollection"]
    assert items
    first = items[0]
    assert first["document_count"] == 1
    # Every suggestion can be traced back to a source artifact.
    assert first["artifacts"][0]["id"] == artifact["id"]
    assert first["artifacts"][0]["filename"] == "atlas.txt"


def test_recent_ingestions_are_capped_and_newest_first(client, signed_in):
    for i in range(7):
        upload(client, f"doc-{i}.txt", TEXT + f"Unique body {i}.\n".encode())

    recent = client.get("/api/dashboard").json()["recent"]
    assert len(recent) == 5
    assert recent[0]["filename"] == "doc-6.txt"


def test_one_user_never_sees_another_users_dashboard(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    register(client, upload(client, "private.txt")["id"])
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/signup",
        json={
            "display_name": "Grace Hopper",
            "email": "grace@example.com",
            "password": "compiler-1952-nanoseconds",
        },
    )
    body = client.get("/api/dashboard").json()
    assert body["documents"]["total"] == 0
    assert body["storage"]["bytes"] == 0
    assert body["recent"] == []


def test_the_dashboard_requires_a_session(client):
    assert client.get("/api/dashboard").status_code == 401


def test_the_dashboard_is_one_request_not_six(client, signed_in, db):
    """A single endpoint, so the page does not fan out on every load."""
    register(client, upload(client)["id"])
    body = client.get("/api/dashboard").json()
    for panel in (
        "documents", "fragments", "topics", "storage",
        "recent", "activity", "topic_distribution", "knowledge_map", "recollection",
    ):
        assert panel in body
    assert db.scalars(select(Artifact)).all()
