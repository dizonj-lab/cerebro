"""The Performance Report: real measurements, and honest absences."""
import pytest

from tests.fixtures import make_pdf

CV_FREE = "Migration notes. The Atlas migration completed its cutover in March 2021.\n"


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload(client, name="notes.txt", content=CV_FREE.encode()):
    return client.post("/api/artifacts", files={"file": (name, content, "text/plain")}).json()


def register(client, artifact, metadata):
    return client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={"metadata": {**artifact["metadata"], **metadata}, "approve": True},
    )


def test_an_empty_report_reports_nothing_rather_than_zeroes_that_look_like_data(
    client, signed_in
):
    body = client.get("/api/performance").json()

    assert body["totals"]["operations"] == 0
    assert body["operations"] == []
    assert body["accuracy"]["fields"] == []
    # No median over no measurements.
    assert body["ingestion"]["median_ms"] is None


def test_an_upload_is_measured_with_the_units_that_explain_it(client, signed_in):
    upload(client)

    body = client.get("/api/performance").json()

    ingestion = body["ingestion"]
    assert ingestion["documents"] == 1
    assert ingestion["median_ms"] > 0
    row = next(r for r in body["operations"] if r["kind"] == "ingestion")
    assert row["units"]["bytes"] == len(CV_FREE.encode())
    assert row["units"]["characters"] > 0
    # Deterministic work is recorded as such rather than left blank.
    assert row["model"] is None
    assert row["algorithm"] == "deterministic extraction"


def test_a_search_is_measured_per_mode(client, signed_in):
    artifact = upload(client)
    register(client, artifact, {"title": "Notes", "topics": ["Migration"]})

    client.post("/api/search", json={"query": "migration", "mode": "keyword"})
    client.post("/api/search", json={"query": "migration", "mode": "hybrid"})

    body = client.get("/api/performance").json()
    modes = {r["operation"]: r for r in body["operations"] if r["kind"] == "search"}
    assert "search.keyword" in modes
    assert "search.hybrid" in modes
    # The algorithm is named, so two modes can be compared on the same library.
    assert modes["search.hybrid"]["algorithm"] == "reciprocal rank fusion (k=60)"


def test_a_question_is_measured_end_to_end_and_separates_a_refusal(client, signed_in):
    artifact = upload(client)
    register(client, artifact, {"title": "Notes", "topics": ["Migration"]})

    client.post("/api/recall", json={"question": "what happened to the migration"})
    client.post("/api/recall", json={"question": "zzz unrelated xylophone"})

    body = client.get("/api/performance").json()["recall"]
    assert body["questions"] == 2
    # An honest refusal is counted as a refusal, never averaged into answers.
    assert body["abstained"] >= 1
    assert body["answered"] + body["abstained"] == body["questions"]
    assert 0 <= body["abstention_rate"] <= 1
    assert body["median_ms"] > 0


def test_accuracy_compares_what_was_suggested_with_what_was_kept(client, signed_in):
    artifact = upload(client)
    suggested = artifact["metadata"].get("topics") or []
    # Keep one suggestion, drop the rest, and add one the model never offered.
    kept = suggested[:1]
    register(client, artifact, {"title": "Notes", "topics": [*kept, "A Topic Nobody Suggested"]})

    accuracy = client.get("/api/performance").json()["accuracy"]

    assert accuracy["scored_documents"] == 1
    topics = next(f for f in accuracy["fields"] if f["field"] == "topics")
    assert topics["kept"] == len(kept)
    assert topics["added_by_user"] >= 1
    if suggested:
        assert topics["dropped_by_user"] == len(suggested) - len(kept)
        assert 0 <= topics["precision"] <= 1
    # Recall catches an engine that proposes little and misses much.
    assert 0 <= topics["recall"] <= 1


def test_a_document_registered_before_snapshots_is_excluded_not_assumed_correct(
    client, signed_in, db_session=None
):
    """Counting it as perfect would invent the measurement this exists to avoid."""
    artifact = upload(client)
    register(client, artifact, {"title": "Notes", "topics": ["Migration"]})

    from app.models.artifact import Artifact
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.get(Artifact, artifact["id"])
        provenance = dict(row.provenance or {})
        provenance.pop("suggested_snapshot", None)
        row.provenance = provenance
        session.commit()

    accuracy = client.get("/api/performance").json()["accuracy"]
    assert accuracy["scored_documents"] == 0
    assert accuracy["unscored_documents"] == 1
    assert accuracy["fields"] == []


def test_one_user_never_sees_anothers_measurements(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    upload(client)
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json={**valid_signup, "email": "other@example.com"})

    body = client.get("/api/performance").json()
    assert body["totals"]["operations"] == 0


def test_the_report_requires_a_session(client):
    assert client.get("/api/performance").status_code == 401
