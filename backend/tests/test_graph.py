"""The Knowledge Galaxy graph.

The properties that matter: only approved knowledge appears, every fragment
node resolves to its source, and no edge is presented as a verified semantic
relationship when it is only co-occurrence.
"""
import pytest
from sqlalchemy import select

from app.models import KnowledgeFragment

BODY = (
    b"Atlas migration notes. The Atlas migration covers the database and the "
    b"reporting pipeline. Atlas timelines are agreed. Database tests pass before "
    b"the Atlas migration completes.\n"
)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload(client, name="atlas.txt", content=BODY):
    return client.post("/api/artifacts", files={"file": (name, content, "text/plain")}).json()


def register(client, artifact, topics, **extra):
    return client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={
            "metadata": {**artifact["metadata"], "title": "Atlas Plan", "topics": topics, **extra},
            "approve": True,
        },
    )


def test_an_empty_galaxy_is_empty_not_invented(client, signed_in):
    body = client.get("/api/graph").json()
    assert body == {"nodes": [], "edges": [], "clusters": [], "truncated": False}


def test_an_unapproved_artifact_never_reaches_the_galaxy(client, signed_in):
    upload(client)
    assert client.get("/api/graph").json()["nodes"] == []
    assert client.get("/api/graph/timeline").json()["events"] == []


def test_registered_topics_become_clusters(client, signed_in):
    register(client, upload(client), ["Atlas", "Migration"])

    body = client.get("/api/graph").json()
    assert {n["label"] for n in body["nodes"]} == {"Atlas", "Migration"}
    assert all(n["type"] == "cluster" for n in body["nodes"])
    assert all(n["provenance"] == "registered" for n in body["nodes"])


def test_edges_say_what_they_are_and_never_claim_semantics(client, signed_in):
    register(client, upload(client, "a.txt"), ["Atlas", "Migration"])
    register(client, upload(client, "b.txt", BODY + b"Second Atlas document.\n"),
             ["Atlas", "Migration"])

    edge = client.get("/api/graph").json()["edges"][0]
    assert edge["kind"] == "co_occurrence"
    # Words, not a percentage dressed up as certainty.
    assert edge["relevance"] in ("Potential Connection", "Related", "Highly Related")
    assert edge["weight"] == 2
    assert edge["relevance"] == "Related"


def test_expanding_a_cluster_returns_fragments_with_their_provenance(client, signed_in, db):
    register(client, upload(client), ["Atlas"])

    body = client.get("/api/graph/expand", params={"topic": "Atlas"}).json()
    assert body["nodes"], "expected fragments inside the cluster"

    fragment = body["nodes"][0]
    assert fragment["type"] == "fragment"
    # Resolves to artifact, fragment and source location — the whole chain.
    assert fragment["source_artifact_id"]
    assert fragment["source_fragment_id"]
    assert "char_start" in fragment["source_location"]
    assert fragment["source_filename"] == "atlas.txt"

    stored = db.scalars(select(KnowledgeFragment)).all()
    assert str(stored[0].id) in {n["source_fragment_id"] for n in body["nodes"]}
    # Containment, not similarity.
    assert body["edges"][0]["kind"] == "contains"


def test_the_galaxy_does_not_load_the_whole_graph(client, signed_in):
    """Clusters first; fragments only when a cluster is opened."""
    register(client, upload(client), ["Atlas"])

    galaxy = client.get("/api/graph").json()
    assert all(n["type"] == "cluster" for n in galaxy["nodes"])
    assert all(n["source_fragment_id"] is None for n in galaxy["nodes"])


def test_cluster_details_explain_every_relationship(client, signed_in):
    register(client, upload(client, "a.txt"), ["Atlas", "Migration"])

    details = client.get("/api/graph/node", params={"id": "topic:Atlas"}).json()
    assert details["type"] == "cluster"
    assert details["document_count"] == 1
    related = details["related"][0]
    assert related["label"] == "Migration"
    # Says why, rather than asserting a relationship.
    assert "Appears together on" in related["explanation"]
    assert details["documents"][0]["filename"] == "a.txt"


def test_fragment_details_resolve_to_the_source_document(client, signed_in):
    register(client, upload(client), ["Atlas"])
    node_id = client.get("/api/graph/expand", params={"topic": "Atlas"}).json()["nodes"][0]["id"]

    details = client.get("/api/graph/node", params={"id": node_id}).json()
    assert details["source_artifact_id"]
    assert details["documents"][0]["filename"] == "atlas.txt"
    assert details["documents"][0]["excerpt"]
    assert "char_start" in details["source_location"]


def test_people_are_only_those_a_human_confirmed(client, signed_in):
    register(client, upload(client), ["Atlas"], people=["Ada Lovelace"])

    details = client.get("/api/graph/node", params={"id": "topic:Atlas"}).json()
    assert [p["name"] for p in details["people"]] == ["Ada Lovelace"]
    assert details["people"][0]["documents"] == ["atlas.txt"]


def test_no_people_are_invented_when_none_were_confirmed(client, signed_in):
    register(client, upload(client), ["Atlas"])
    assert client.get("/api/graph/node", params={"id": "topic:Atlas"}).json()["people"] == []


def test_the_timeline_says_where_each_date_came_from(client, signed_in):
    register(client, upload(client, "stated.txt"), ["Atlas"], created_date="2024-03-01")
    register(client, upload(client, "silent.txt", BODY + b"Another Atlas note.\n"), ["Atlas"])

    events = {e["filename"]: e for e in client.get("/api/graph/timeline").json()["events"]}
    assert events["stated.txt"]["date"] == "2024-03-01"
    assert events["stated.txt"]["basis"] == "document_metadata"
    # No date in the document, so the registration date is used and labelled.
    assert events["silent.txt"]["basis"] == "registered_at"


def test_an_unknown_node_is_not_found(client, signed_in):
    assert client.get("/api/graph/node", params={"id": "topic:Nope"}).status_code == 404
    assert client.get("/api/graph/node", params={"id": "nonsense"}).status_code == 404


def test_one_user_never_sees_another_users_galaxy(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    register(client, upload(client, "private.txt"), ["Confidential"])
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/signup",
        json={
            "display_name": "Grace Hopper",
            "email": "grace@example.com",
            "password": "compiler-1952-nanoseconds",
        },
    )
    assert client.get("/api/graph").json()["nodes"] == []
    assert client.get("/api/graph/node", params={"id": "topic:Confidential"}).status_code == 404


def test_the_galaxy_requires_a_session(client):
    for path in ("/api/graph", "/api/graph/timeline"):
        assert client.get(path).status_code == 401
