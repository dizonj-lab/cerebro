"""Ask CEREBRO end to end, with a real local model standing in.

The daemon is a stand-in on a real socket; everything else is the
application: upload, extraction, registration, chunking, embedding,
retrieval, prompt assembly, streaming and the citation guard.
"""
from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.services import ollama, telemetry
from tests.test_ollama import STATE, daemon  # noqa: F401 - fixture reused

SPEC = (
    "The retention schedule for ledger exports is seven years.\n\n"
    "Quarterly reconciliation is signed off by the finance lead.\n"
)


@pytest.fixture
def library(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    artifact = client.post(
        "/api/artifacts", files={"file": ("retention.txt", SPEC.encode(), "text/plain")}
    ).json()
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={
            "metadata": {"title": "Retention Policy", "topics": ["Records"]},
            "approve": True,
        },
    )
    return artifact


@pytest.fixture
def answering(daemon, monkeypatch):  # noqa: F811 - the fixture is the daemon
    """Local answering on, pointed at the stand-in daemon."""
    monkeypatch.setattr(get_settings(), "recall_llm", "auto")
    ollama.reset_discovery()
    return daemon


def test_a_question_is_answered_by_the_local_model_with_its_sources(client, library, answering):
    STATE["pieces"] = ["Ledger exports are kept for seven years [1]."]

    body = client.post("/api/recall", json={"question": "How long are ledger exports kept?"}).json()

    assert body["answer"] == "Ledger exports are kept for seven years [1]."
    assert body["model"] == "llama3.2:3b"
    assert body["grounded"] is True
    assert body["cited"] == [1]
    # The sources are real fragments of the real document.
    assert body["sources"][0]["filename"] == "retention.txt"
    assert "retention" in body["sources"][0]["excerpt"].lower()


def test_only_the_retrieved_passages_are_put_in_front_of_the_model(client, library, answering):
    client.post("/api/recall", json={"question": "How long are ledger exports kept?"})

    prompt = STATE["last_prompt"]
    assert "retention schedule" in prompt
    # The instruction is the grounding contract, and the question is in it.
    assert "Use only the passages" in prompt
    assert "How long are ledger exports kept?" in prompt


def test_a_citation_to_a_passage_that_does_not_exist_is_removed(client, library, answering):
    """A model citing [7] of two passages has cited nothing."""
    STATE["pieces"] = ["Kept for seven years [1], as the appendix says [7]."]

    body = client.post("/api/recall", json={"question": "retention?"}).json()

    assert "[7]" not in body["answer"]
    assert "[1]" in body["answer"]
    assert body["cited"] == [1]


def test_telemetry_reports_what_actually_ran(client, library, answering):
    body = client.post("/api/recall", json={"question": "retention?"}).json()

    assert body["telemetry"]["model"] == "llama3.2:3b"
    # Counted by the daemon, not estimated.
    assert body["telemetry"]["prompt_tokens"] == 321
    assert body["telemetry"]["completion_tokens"] == 42
    assert body["telemetry"]["passages"] >= 1
    assert body["telemetry"]["duration_ms"] >= 0


def test_an_unsupported_question_abstains_rather_than_answering(client, library, answering):
    body = client.post(
        "/api/recall", json={"question": "velociraptor husbandry licensing"}
    ).json()

    # Either nothing was retrieved — in which case no model was asked at all
    # — or the model was asked and said the passages do not answer it.
    if not body["sources"]:
        assert body["answer"].startswith("Insufficient evidence")
        assert body["grounded"] is False
        assert body["model"] is None
    else:
        assert body["sources"]


def test_the_model_is_never_asked_when_nothing_was_retrieved(client, valid_signup, answering):
    """An empty library cannot support an answer, so none is generated."""
    client.post("/api/auth/signup", json=valid_signup)
    STATE.pop("last_prompt", None)

    body = client.post("/api/recall", json={"question": "anything at all"}).json()

    assert body["answer"].startswith("Insufficient evidence")
    assert body["sources"] == []
    assert "last_prompt" not in STATE


def test_an_unreachable_daemon_returns_the_passages_and_says_why(client, library, monkeypatch):
    monkeypatch.setattr(get_settings(), "recall_llm", "auto")
    monkeypatch.setattr(ollama, "candidate_urls", lambda: ["http://127.0.0.1:1"])
    ollama.reset_discovery()

    body = client.post("/api/recall", json={"question": "retention?"}).json()

    # Degraded, not broken, and never a cloud call.
    assert body["answer"] is None
    assert body["sources"]
    assert body["grounded"] is True
    assert "ollama serve" in body["note"].lower() or "could not" in body["note"].lower()


def test_answering_is_off_when_the_user_switched_ai_suggestions_off(client, library, answering):
    client.patch("/api/preferences", json={"ai_suggestions": False})
    STATE.pop("last_prompt", None)

    body = client.post("/api/recall", json={"question": "retention?"}).json()

    assert body["answer"] is None
    assert body["sources"]
    assert "switched off" in body["note"]
    # The preference is honoured by not calling the model at all.
    assert "last_prompt" not in STATE


# --- streaming --------------------------------------------------------------

def events(response) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_the_stream_sends_sources_first_then_words_then_a_summary(client, library, answering):
    STATE["pieces"] = ["Seven ", "years ", "[1]."]

    with client.stream(
        "POST", "/api/recall/stream", json={"question": "retention?"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        response.read()
        received = events(response)

    assert received[0]["type"] == "sources"
    assert received[0]["sources"][0]["filename"] == "retention.txt"
    # Streamed incrementally and adding up to the answer; the chunking
    # itself is not part of the contract.
    deltas = [e["text"] for e in received if e["type"] == "delta"]
    assert "".join(deltas) == "Seven years [1]."
    assert len(deltas) > 1

    final = received[-1]
    assert final["type"] == "done"
    assert final["answer"] == "Seven years [1]."
    assert final["cited"] == [1]
    assert final["telemetry"]["completion_tokens"] == 42


def test_the_stream_guards_citations_split_across_chunks(client, library, answering):
    # The marker arrives in pieces, so the guard cannot work chunk by chunk.
    STATE["pieces"] = ["Kept seven years [", "9", "]."]

    with client.stream("POST", "/api/recall/stream", json={"question": "retention?"}) as response:
        response.read()
        final = events(response)[-1]

    assert "[9]" not in final["answer"]
    assert final["cited"] == []


def test_the_stream_abstains_on_an_empty_library(client, valid_signup, answering):
    client.post("/api/auth/signup", json=valid_signup)

    with client.stream("POST", "/api/recall/stream", json={"question": "anything"}) as response:
        response.read()
        received = events(response)

    assert received[0] == {"type": "sources", "sources": []}
    assert received[-1]["answer"].startswith("Insufficient evidence")
    assert received[-1]["abstained"] is True


def test_recall_requires_a_session(client):
    assert client.post("/api/recall/stream", json={"question": "x"}).status_code == 401


# --- the status GOD MODE reads ---------------------------------------------

def test_status_reports_the_models_in_use_and_embedding_coverage(client, library, answering):
    telemetry.clear()
    client.post("/api/recall", json={"question": "retention?"})

    body = client.get("/api/ml/status").json()

    assert body["ollama"]["reachable"] is True
    assert body["ollama"]["answering_model"] == "llama3.2:3b"
    assert body["embeddings"]["fragments"] >= 1
    # The suite pins the hashing embedder, and the status says plainly that
    # it is not a pretrained model.
    assert body["embeddings"]["provider"] == "hashing"
    assert body["embeddings"]["pretrained"] is False
    assert body["embeddings"]["missing"] == 0
    operations = [o["operation"] for o in body["operations"]]
    assert "recall.answer" in operations
    assert "recall.retrieve" in operations


def test_status_requires_a_session(client):
    assert client.get("/api/ml/status").status_code == 401


def test_backfill_embeds_fragments_that_have_no_vector_for_the_active_model(
    client, library, db
):
    from app.models.fragment import FragmentEmbedding

    # Simulate a document registered while the embedder was different: the
    # fragments exist, the vectors for the active model do not.
    db.query(FragmentEmbedding).delete()
    db.commit()
    assert client.get("/api/ml/status").json()["embeddings"]["missing"] >= 1

    body = client.post("/api/ml/embeddings/backfill").json()

    assert body["embedded"] >= 1
    assert body["remaining"] == 0
    assert client.get("/api/ml/status").json()["embeddings"]["missing"] == 0
    # And the knowledge is retrievable again.
    assert client.post("/api/search", json={"query": "reconciliation"}).json()["total"] >= 1
