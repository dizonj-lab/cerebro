"""The CV as a timeline anchor: extraction, correction, approval, privacy."""
import pytest

from app.services import cv

CV_TEXT = """Joselito Dizon
Enterprise architect.

Experience
Senior Lead Architect | JPMorgan Chase    2021 - Present
Regional Enterprise Architect, MUFG Bank   Mar 2016 - Dec 2021
Led the payments programme and mentored the team.

Education
MTech Enterprise Business Analytics, NUS   2024 - 2026

Certifications
TOGAF 9 Certified, The Open Group   2015
"""


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload_cv(client, text=CV_TEXT, name="cv.pdf"):
    from tests.fixtures import make_pdf

    # make_pdf takes pages; one page is enough for a short CV.
    return client.post(
        "/api/cv", files={"file": (name, make_pdf([text]), "application/pdf")}
    )


# --- extraction -------------------------------------------------------------

def test_dated_entries_are_read_under_their_heading():
    found = {a.title: a for a in cv.extract(CV_TEXT)}

    assert found["Senior Lead Architect"].event_type == "employment"
    assert found["Senior Lead Architect"].organization == "JPMorgan Chase"
    assert found["MTech Enterprise Business Analytics"].event_type == "education"
    assert found["TOGAF 9 Certified"].event_type == "certification"


def test_an_open_range_has_no_end_date():
    """"Present" means still there — not that the role ended today."""
    current = next(a for a in cv.extract(CV_TEXT) if a.title == "Senior Lead Architect")

    assert current.start_date == "2021-01-01"
    assert current.end_date is None


def test_precision_records_how_exact_the_cv_actually_was():
    found = {a.title: a for a in cv.extract(CV_TEXT)}

    assert found["Regional Enterprise Architect"].date_precision == "month"
    # A year-only range stays a year, however it is stored.
    assert found["MTech Enterprise Business Analytics"].date_precision == "year"


def test_a_line_without_a_date_is_not_an_event():
    titles = [a.title for a in cv.extract(CV_TEXT)]

    assert not any("Led the payments programme" in t for t in titles)
    assert not any("Enterprise architect." == t for t in titles)


def test_every_anchor_carries_the_line_it_came_from():
    for anchor in cv.extract(CV_TEXT):
        assert anchor.evidence_text
        assert anchor.source_location.get("line")


# --- the API ----------------------------------------------------------------

def test_a_cv_upload_produces_suggestions_not_facts(client, signed_in):
    body = upload_cv(client).json()

    assert body["status"] == "needs_review"
    assert body["suggested"] >= 4
    assert body["approved"] == 0
    assert all(a["approval_status"] == "suggested" for a in body["anchors"])
    assert all(a["provenance_type"] == "cv_extraction" for a in body["anchors"])


def test_anchors_reach_the_timeline_only_once_approved(client, signed_in):
    upload_cv(client)
    assert client.get("/api/timeline").json()["anchors"] == []

    client.post("/api/cv/approve")

    anchors = client.get("/api/timeline").json()["anchors"]
    assert anchors
    assert all(a["approval_status"] == "approved" for a in anchors)


def test_a_correction_survives_reprocessing_the_same_cv(client, signed_in):
    body = upload_cv(client).json()
    anchor = next(a for a in body["anchors"] if a["title"] == "Senior Lead Architect")
    client.patch(f"/api/cv/anchors/{anchor['id']}", json={"title": "Executive Architect"})

    again = upload_cv(client).json()

    corrected = next(a for a in again["anchors"] if a["id"] == anchor["id"])
    assert corrected["title"] == "Executive Architect"
    assert corrected["user_edited"] is True
    # The CV's own words are still recorded beside the correction.
    assert corrected["extracted"]["title"] == "Senior Lead Architect"


def test_replacing_the_cv_does_not_duplicate_a_career(client, signed_in):
    first = upload_cv(client).json()
    extended = CV_TEXT + "\nAnalyst, Acme Corp   2010 - 2014\n"

    second = upload_cv(client, extended, name="cv-v2.pdf").json()

    assert second["extraction"]["added"] == 1
    assert len(second["anchors"]) == len(first["anchors"]) + 1
    titles = [a["title"] for a in second["anchors"]]
    assert len(titles) == len(set(titles))


def test_a_user_may_add_an_event_the_cv_never_mentioned(client, signed_in):
    upload_cv(client)

    added = client.post(
        "/api/cv/anchors",
        json={"title": "Started CEREBRO", "event_type": "personal_milestone",
              "start_date": "2026-01-01", "date_precision": "year"},
    ).json()

    assert added["provenance_type"] == "user_entered"
    # The user asserted it, so there is nobody left to approve it.
    assert added["approval_status"] == "approved"
    assert added["evidence_text"] is None


def test_a_rejected_anchor_never_reaches_the_timeline(client, signed_in):
    body = upload_cv(client).json()
    anchor = body["anchors"][0]
    client.patch(f"/api/cv/anchors/{anchor['id']}", json={"approval_status": "rejected"})

    client.post("/api/cv/approve")

    ids = [a["id"] for a in client.get("/api/timeline").json()["anchors"]]
    assert anchor["id"] not in ids


def test_a_non_document_is_refused_as_a_cv(client, signed_in):
    response = client.post(
        "/api/cv", files={"file": ("notes.txt", b"hello", "text/plain")}
    )

    assert response.status_code == 400
    assert "PDF or a Word" in response.json()["detail"]


# --- privacy ----------------------------------------------------------------

def test_one_user_never_sees_anothers_cv(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    upload_cv(client)
    client.post("/api/auth/logout")

    other = {**valid_signup, "email": "other@example.com"}
    client.post("/api/auth/signup", json=other)

    body = client.get("/api/cv").json()
    assert body["anchors"] == []
    assert body["filename"] is None
    assert client.get("/api/timeline").json()["anchors"] == []


def test_the_cv_requires_a_session(client):
    assert client.get("/api/cv").status_code == 401
    assert client.post("/api/cv/approve").status_code == 401
