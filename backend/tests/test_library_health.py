"""Library health: the read-only report behind `python -m app.tools.library_report`.

What matters: it measures only registered knowledge, only the owner's, finds a document naming
another with the sentence that does it, flags noise without acting on it, and writes nothing.
"""

import pytest
from sqlalchemy import String, func, select

from app.models import Artifact
from app.services import library_health, users
from app.services.library_health import _Doc, _needles, suspect_reason

PLAN = (
    b"Atlas Migration Plan. The database moves to the new cluster. Rollback is rehearsed twice.\n"
)
REVIEW = (
    b"Migration review. This review evaluates the Atlas Migration Plan against rollback criteria.\n"
)
OTHER = b"Allotment diary. Tomatoes went in late and the beans did well.\n"


@pytest.fixture
def owner(client, valid_signup, db):
    client.post("/api/auth/signup", json=valid_signup)
    return users.get_by_email(db, valid_signup["email"])


def add(client, name, content, title, topics, approve=True):
    a = client.post("/api/artifacts", files={"file": (name, content, "text/plain")}).json()
    r = client.patch(
        f"/api/artifacts/{a['id']}",
        json={"metadata": {**a["metadata"], "title": title, "topics": topics}, "approve": approve},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---- pure logic, no database


@pytest.mark.parametrize(
    "topic, severity",
    [
        ("2026", "noise"),
        ("September 2026", "noise"),
        ("Q3 2026", "noise"),
        ("Food-", "noise"),
        ("Top-", "noise"),
        ("Answer", "check"),
        ("Provenance", "check"),
        ("Knowledge Graphs", None),
        ("Retrieval-Augmented Generation", None),
        ("ONNX Runtime", None),
        ("EXP-002", None),
    ],
)
def test_suspect_topics_are_classified_not_removed(topic, severity):
    found = suspect_reason(topic, set())
    assert (found[0] if found else None) == severity


def test_a_name_confirmed_as_an_entity_is_flagged_as_a_topic():
    assert suspect_reason("Joselito Dizon", {"joselito dizon"})[0] == "noise"
    assert suspect_reason("Joselito Dizon", set()) is None


def test_needles_skip_the_kind_half_of_a_title_and_parentheticals():
    doc = _Doc(
        None, "07-group-7-minutes.docx", "Group 7 Meeting Minutes: Choosing the Local Models", []
    )
    needles = _needles(doc)
    assert "Choosing the Local Models" in needles
    assert "Group 7 Meeting Minutes" not in needles
    bench = _Doc(None, "b.pdf", "CEREBRO Ground Truth Benchmark (CEREBRO-GT v0.1)", [])
    assert "CEREBRO Ground Truth Benchmark" in _needles(bench)


# ---- against the database


def test_topics_report_what_the_galaxy_will_draw(client, owner, db):
    add(
        client,
        "plan.txt",
        PLAN,
        "Atlas Migration Plan",
        ["Database Migration", "Rollback Planning", "2026"],
    )
    add(
        client,
        "review.txt",
        REVIEW,
        "Migration Review",
        ["Database Migration", "Rollback Planning"],
    )
    add(client, "diary.txt", OTHER, "Allotment Diary", ["Vegetable Gardening"])

    t = library_health.topic_health(db, owner.id)
    assert t["documents"] == 3 and t["distinct_topics"] == 4
    assert t["single_document_topics"] == 2  # "2026" and "Vegetable Gardening"
    assert {x["topic"]: x["severity"] for x in t["suspect_topics"]} == {"2026": "noise"}
    assert (
        t["galaxy_now"]["recurring_edges"] == 1
    )  # Database Migration with Rollback Planning, on two documents


def test_a_document_naming_another_is_a_stated_link_with_its_sentence(client, owner, db):
    add(client, "plan.txt", PLAN, "Atlas Migration Plan", ["Database Migration"])
    add(client, "review.txt", REVIEW, "Migration Review", ["Database Migration"])

    [link] = library_health.stated_links(db, owner.id)
    assert (link["source"], link["target"], link["relation"]) == (
        "Migration Review",
        "Atlas Migration Plan",
        "evaluates",
    )
    assert "evaluates the Atlas Migration Plan" in link["evidence"]
    assert link["fragment_id"]


def test_only_registered_knowledge_is_measured(client, owner, db):
    add(client, "plan.txt", PLAN, "Atlas Migration Plan", ["Database Migration"])
    add(client, "review.txt", REVIEW, "Migration Review", ["Database Migration"], approve=False)

    assert library_health.topic_health(db, owner.id)["documents"] == 1
    assert library_health.stated_links(db, owner.id) == []


def test_embeddings_are_reported_in_the_active_space(client, owner, db):
    add(client, "plan.txt", PLAN, "Atlas Migration Plan", ["Database Migration"])
    add(client, "review.txt", REVIEW, "Migration Review", ["Database Migration"])

    e = library_health.embedding_health(db, owner.id)
    assert e["active"]["provider"] == "hashing"
    assert (
        e["fragments"] > 0 and e["fragments_invisible"] == 0 and e["documents_not_searchable"] == []
    )
    for pair in library_health.similar_documents(db, owner.id):
        assert -1.0 <= pair["score"] <= 1.0 and pair["shared_topics"] == ["database migration"]


def test_another_owner_sees_nothing_and_the_report_writes_nothing(client, owner, db):
    add(client, "plan.txt", PLAN, "Atlas Migration Plan", ["Database Migration"])
    snapshot = select(
        func.count(),
        func.max(Artifact.updated_at),
        func.md5(func.string_agg(Artifact.artifact_metadata.cast(String), "")),
    )
    before = db.execute(snapshot).one()

    stranger = users.create_user(
        db, display_name="Stranger", email="stranger@example.com", password="correct-horse-battery"
    )
    db.commit()
    r = library_health.report(db, stranger.id)
    assert (
        r["topics"]["documents"] == 0 and r["stated_links"] == [] and r["similar_documents"] == []
    )
    assert r["embeddings"]["fragments"] == 0

    library_health.report(db, owner.id)
    assert not db.dirty and not db.new and not db.deleted
    db.commit()
    assert db.execute(snapshot).one() == before
