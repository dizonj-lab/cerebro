"""Enrichment as a queued background job, one or two at a time."""
import pytest

from app.services import enrichment_queue as queue

MEMO = b"Project Atlas migration memo. The ledger cutover is owned by Maria Santos.\n"


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload(client, name="a.txt"):
    return client.post("/api/artifacts", files={"file": (name, MEMO, "text/plain")}).json()


def test_asking_for_suggestions_returns_at_once_rather_than_blocking(client, signed_in):
    """The request used to hold open for minutes; now it queues and returns."""
    artifact = upload(client)

    response = client.post(f"/api/artifacts/{artifact['id']}/suggest")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["progress"] == 0


def test_the_job_survives_the_request_that_asked_for_it(client, signed_in):
    """Navigating away used to abort the fetch and lose the work."""
    artifact = upload(client)
    client.post(f"/api/artifacts/{artifact['id']}/suggest")

    # A different request entirely, as a different page would make.
    again = client.get(f"/api/artifacts/{artifact['id']}").json()

    assert again["enrichment_job"]["status"] in ("queued", "running", "done")


def test_the_queue_reports_what_is_waiting_and_in_what_order(client, signed_in):
    first = upload(client, "first.txt")
    second = client.post(
        "/api/artifacts", files={"file": ("second.txt", MEMO + b"Second.", "text/plain")}
    ).json()
    client.post(f"/api/artifacts/{first['id']}/suggest")
    client.post(f"/api/artifacts/{second['id']}/suggest")

    body = client.get("/api/artifacts/enrichment/queue").json()

    assert len(body["jobs"]) == 2
    assert body["waiting"] + body["running"] == 2
    # Its place in the line, so "waiting" has a number attached.
    assert [job["position"] for job in body["jobs"]] == [0, 1]
    assert body["jobs"][0]["filename"] == "first.txt"
    # The UI can explain why the rest are waiting rather than looking stuck.
    assert body["max_concurrent"] == 2


def test_a_registered_artifact_is_not_queued(client, signed_in):
    artifact = upload(client)
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={"metadata": {"title": "Atlas"}, "approve": True},
    )

    response = client.post(f"/api/artifacts/{artifact['id']}/suggest")

    assert response.status_code == 400


def test_one_user_never_sees_anothers_queue(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    artifact = upload(client)
    client.post(f"/api/artifacts/{artifact['id']}/suggest")
    client.post("/api/auth/logout")

    client.post("/api/auth/signup", json={**valid_signup, "email": "other@example.com"})

    assert client.get("/api/artifacts/enrichment/queue").json()["jobs"] == []


# --- the adaptive limit -----------------------------------------------------

def test_a_single_document_never_runs_two_workers(db):
    """Two workers on one document is not faster, only hotter."""
    assert queue._desired_workers(db) == 1  # noqa: SLF001


def test_a_backlog_admits_a_second_worker_only_when_jobs_have_been_quick(
    client, signed_in, db, monkeypatch
):
    """The evidence for a second worker is a job that finished quickly."""
    for name in ("one.txt", "two.txt", "three.txt"):
        artifact = client.post(
            "/api/artifacts",
            files={"file": (name, MEMO + name.encode(), "text/plain")},
        ).json()
        client.post(f"/api/artifacts/{artifact['id']}/suggest")

    monkeypatch.setattr(queue, "_last_durations", [120.0, 150.0])
    assert queue._desired_workers(db) == 1  # noqa: SLF001

    monkeypatch.setattr(queue, "_last_durations", [8.0, 9.0])
    assert queue._desired_workers(db) == queue.MAX_WORKERS  # noqa: SLF001


def test_the_ceiling_is_two_whatever_the_backlog(client, signed_in, db, monkeypatch):
    """A local model is one daemon; twenty at once helps nobody."""
    for index in range(6):
        artifact = client.post(
            "/api/artifacts",
            files={"file": (f"f{index}.txt", MEMO + str(index).encode(), "text/plain")},
        ).json()
        client.post(f"/api/artifacts/{artifact['id']}/suggest")

    monkeypatch.setattr(queue, "_last_durations", [1.0])

    assert queue._desired_workers(db) <= 2  # noqa: SLF001
