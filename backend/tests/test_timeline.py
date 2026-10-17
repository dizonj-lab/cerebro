"""The timeline: events dated by the documents, not by CEREBRO's filing."""
from __future__ import annotations

import pytest

from app.services import temporal

MEMO = (
    "The Atlas migration project completed its cutover in March 2021. "
    "Governance approved the data retention policy on 2023-09-12. "
    "Maria Santos was appointed to lead the platform team in June 2021. "
    "Q3 2024 is the target for the edge computing rollout. "
    "This closing sentence carries no date whatsoever.\n"
)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


@pytest.fixture
def registered(client, signed_in):
    artifact = client.post(
        "/api/artifacts", files={"file": ("atlas.txt", MEMO.encode(), "text/plain")}
    ).json()
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={
            "metadata": {
                "title": "Atlas Memo",
                "topics": ["Migration"],
                "people": ["Maria Santos"],
                "projects": ["Atlas"],
            },
            "approve": True,
        },
    )
    return artifact


# --- extraction -------------------------------------------------------------

def test_dates_are_read_from_the_text_with_their_precision():
    events = temporal.extract_from_text(MEMO)
    found = {(e["date"], e["precision"]) for e in events}

    assert ("2021-03-01", "month") in found
    assert ("2023-09-12", "day") in found
    assert ("2024-07-01", "quarter") in found
    # A sentence with no date is not an event with a guessed one.
    assert all("no date whatsoever" not in e["title"] for e in events)


def test_every_event_carries_the_expression_and_the_sentence():
    events = temporal.extract_from_text(MEMO)
    event = next(e for e in events if e["date"] == "2023-09-12")

    assert event["expression"] == "2023-09-12"
    assert "Governance approved" in event["evidence"]
    # The title is the document's own words, not a generated summary.
    assert event["title"] in event["evidence"] or event["title"].rstrip("…") in event["evidence"]


def test_a_lane_is_assigned_only_on_evidence():
    events = temporal.extract_from_text(MEMO)
    governance = next(e for e in events if e["date"] == "2023-09-12")
    assert governance["category"] == "Governance"
    assert governance["category_basis"] in ("governance", "policy")

    # Nothing matches a lane word, so it is Other rather than forced into one.
    orphan = temporal.extract_from_text("Something happened in 1999.")[0]
    assert orphan["category"] == "Other"
    assert orphan["category_basis"] is None


def test_an_impossible_date_falls_back_to_what_the_text_does_say():
    """There is no 31 February, but "2024" is still in the sentence."""
    events = temporal.extract_from_text("Due 31 February 2024 at the latest.")

    assert len(events) == 1
    # The day is impossible, the month is not: precision degrades to what the
    # text supports rather than inventing a day or dropping the sentence.
    assert events[0]["precision"] == "month"
    assert events[0]["expression"] == "February 2024"
    assert events[0]["date"] == "2024-02-01"


def test_entities_are_attached_only_where_the_sentence_names_them():
    events = temporal.extract_from_text(
        MEMO, entities={"people": ["Maria Santos"], "projects": ["Atlas"]}
    )
    appointment = next(e for e in events if e["date"] == "2021-06-01")
    cutover = next(e for e in events if e["date"] == "2021-03-01")

    assert appointment["entities"]["people"] == ["Maria Santos"]
    assert "people" not in cutover["entities"]
    assert cutover["entities"]["projects"] == ["Atlas"]


# --- the API ----------------------------------------------------------------

def test_the_timeline_is_built_from_registered_knowledge(client, registered):
    body = client.get("/api/timeline").json()

    assert body["total"] >= 4
    dates = {e["date"] for e in body["events"]}
    assert {"2021-03-01", "2023-09-12", "2024-07-01"} <= dates
    # Each event resolves to the fragment and document it came from.
    first = body["events"][0]
    assert first["artifact_id"] == registered["id"]
    assert first["fragment_id"]
    assert first["filename"] == "atlas.txt"


def test_an_unregistered_document_places_no_events(client, signed_in):
    client.post("/api/artifacts", files={"file": ("draft.txt", MEMO.encode(), "text/plain")})

    body = client.get("/api/timeline").json()

    assert body["events"] == []
    assert body["range"]["earliest"] is None


def test_the_upload_date_is_never_used_as_an_event_date(client, registered):
    """A document arriving today does not make today an event."""
    from datetime import date

    body = client.get("/api/timeline").json()

    assert all(e["date"] != date.today().isoformat() for e in body["events"])
    assert all(e["expression"] for e in body["events"])


def test_lanes_are_the_library_own_confirmed_topics(client, registered):
    """A topic was approved by a human, so grouping by it guesses nothing."""
    body = client.get("/api/timeline").json()

    lanes = {lane["name"]: lane["count"] for lane in body["lanes"]}
    assert "Migration" in lanes
    assert body["lane_source"] == "confirmed topics"
    assert sum(lanes.values()) == body["total"]
    # Someone else's taxonomy is not imposed on a library that has its own.
    assert "Governance" not in lanes


def test_a_library_without_topics_falls_back_to_the_named_lanes(client, signed_in):
    artifact = client.post(
        "/api/artifacts", files={"file": ("plain.txt", MEMO.encode(), "text/plain")}
    ).json()
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        # Registered, with no topic confirmed.
        json={"metadata": {"title": "Plain"}, "approve": True},
    )

    body = client.get("/api/timeline").json()

    lanes = {lane["name"]: lane["count"] for lane in body["lanes"]}
    expected = {"Strategy", "Architecture", "Governance", "Technology", "Projects", "People"}
    assert expected <= set(lanes)
    assert body["lane_source"] == "keyword fallback"
    # The keyword lanes still say what matched.
    governance = next(e for e in body["events"] if e["category"] == "Governance")
    assert governance["category_basis"] in ("governance", "policy")


def test_filters_narrow_the_events(client, registered):
    everything = client.get("/api/timeline").json()["total"]

    by_topic = client.get("/api/timeline", params={"categories": ["Migration"]}).json()
    assert by_topic["total"] == everything
    assert {e["category"] for e in by_topic["events"]} == {"Migration"}

    nothing = client.get("/api/timeline", params={"categories": ["Governance"]}).json()
    assert nothing["total"] == 0

    window = client.get("/api/timeline", params={"start": "2023-01-01"}).json()
    assert all(e["date"] >= "2023-01-01" for e in window["events"])

    person = client.get(
        "/api/timeline", params={"entity_type": "people", "entity": "Maria Santos"}
    ).json()
    assert person["total"] == 1


def test_the_histogram_counts_months_and_keeps_the_whole_range(client, registered):
    body = client.get("/api/timeline").json()

    months = {bucket["month"]: bucket["count"] for bucket in body["histogram"]}
    assert months.get("2021-03") == 1
    assert body["range"]["earliest"] == "2021-03-01"
    assert body["range"]["latest"] == "2024-07-01"


def test_related_events_say_why_they_are_related(client, registered):
    body = client.get("/api/timeline").json()
    anchor = next(e for e in body["events"] if e["date"] == "2021-06-01")

    related = client.get("/api/timeline/related", params={"event": anchor["id"]}).json()

    assert related["related"]
    assert all(item["relationship"] for item in related["related"])
    # Co-occurrence, explained — never an asserted semantic relationship.
    assert any("same document" in item["relationship"] for item in related["related"])


def test_overlapping_chunks_do_not_duplicate_an_event(client, signed_in):
    # Long enough to be chunked more than once, with the dated sentence in
    # the overlap between two chunks.
    filler = "The programme continued steadily with no notable change. " * 60
    text = f"{filler} The migration completed in March 2021. {filler}"
    artifact = client.post(
        "/api/artifacts", files={"file": ("long.txt", text.encode(), "text/plain")}
    ).json()
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={"metadata": {"title": "Long"}, "approve": True},
    )

    body = client.get("/api/timeline").json()

    march = [e for e in body["events"] if e["date"] == "2021-03-01"]
    assert len(march) == 1
    assert body["extraction"]["duplicates_dropped"] >= 0


def test_the_journey_follows_one_entity_in_order(client, registered):
    body = client.get(
        "/api/timeline/journey", params={"entity": "Atlas", "field": "projects"}
    ).json()

    assert body["total"] >= 1
    assert [s["date"] for s in body["steps"]] == sorted(s["date"] for s in body["steps"])


def test_extraction_is_reported_for_telemetry_window(client, registered):
    client.get("/api/timeline")

    operations = {o["operation"] for o in client.get("/api/ml/status").json()["operations"]}
    assert "timeline.extract" in operations
    assert "timeline.query" in operations


def test_the_timeline_requires_a_session(client):
    assert client.get("/api/timeline").status_code == 401
    assert client.get("/api/timeline/related", params={"event": "x"}).status_code == 401


def test_one_user_never_sees_anothers_events(client, registered, valid_signup):
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json=dict(valid_signup, email="other@example.com"))

    assert client.get("/api/timeline").json()["events"] == []


def test_an_event_carries_its_document_size_and_dates(client, registered):
    """The hover card's three dates, each with where it came from."""
    body = client.get("/api/timeline").json()

    document = body["events"][0]["document"]
    # A plain text file asserts no dates of its own, and absent stays absent
    # rather than borrowing the upload time.
    assert document["created"] is None
    assert document["modified"] is None
    assert document["created_basis"] is None
    # The one date CEREBRO itself knows.
    assert document["registered"]
    assert document["registered_basis"] == "CEREBRO record"
    assert document["characters"] > 0


def test_the_histogram_reports_volume_in_pages_by_category(client, registered):
    """Bar height is how much document there is, not how many dates it names."""
    body = client.get("/api/timeline").json()

    bars = [bucket for bucket in body["histogram"] if bucket["count"]]
    assert bars
    for bucket in bars:
        # A document with no page count still has presence, never zero.
        assert bucket["pages"] >= bucket["documents"] >= 1
        assert bucket["pages"] == sum(bucket["by_category"].values())
        # Categories are the lanes, so the bar can be coloured by them.
        assert set(bucket["by_category"]) <= {lane["name"] for lane in body["lanes"]}


def test_one_document_is_counted_once_however_many_dates_it_names(client, registered):
    """Otherwise a date-dense document inflates its own apparent size."""
    body = client.get("/api/timeline").json()

    for bucket in body["histogram"]:
        in_month = {e["artifact_id"] for e in body["events"] if e["date"][:7] == bucket["month"]}
        if in_month:
            assert bucket["documents"] == len(in_month)
