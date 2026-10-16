"""The deployed configuration: qwen3 for answering and enrichment,
mxbai-embed-large for embeddings.

The daemon is a stand-in on a real socket that behaves the way qwen3 does —
it wraps its deliberation in <think> tags — so the handling of a reasoning
model is exercised rather than assumed. What this still cannot test is
whether qwen3 answers well; that needs the real model.
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services import ollama, telemetry
from app.services.artifacts import enrichment
from app.services.embeddings import reset_embedding_provider
from tests.test_ollama import STATE, daemon  # noqa: F401 - fixture reused

MEMO = (
    "Project Atlas migration memo.\n\n"
    "Maria Santos of Acme Inc. owns the ledger cutover. "
    "The retention schedule for ledger exports is seven years. "
    "Quarterly reconciliation is signed off by the finance lead.\n"
)


@pytest.fixture
def deployed(daemon, monkeypatch):  # noqa: F811 - the fixture is the daemon
    """What the user has installed, named the way Ollama names it."""
    STATE["models"] = ["qwen3:4b", "mxbai-embed-large:latest"]
    STATE["dimensions"] = 1024
    settings = get_settings()
    monkeypatch.setattr(settings, "recall_llm", "auto")
    monkeypatch.setattr(settings, "enrichment_llm", "auto")
    monkeypatch.setattr(settings, "ollama_recall_model", "qwen3")
    monkeypatch.setattr(settings, "ollama_enrichment_model", "qwen3")
    ollama.reset_discovery()
    enrichment.llm_available()
    reset_embedding_provider()
    return daemon


def test_the_installed_pair_is_selected_for_its_proper_job(deployed):
    found = ollama.discover(force=True)
    # qwen3 answers; the embedder is never asked to.
    assert found.chat_model() == "qwen3:4b"
    assert found.embedding_model() == "mxbai-embed-large:latest"


def test_mxbai_is_used_at_its_own_width(deployed, monkeypatch):
    from app.services import embeddings

    monkeypatch.setattr(get_settings(), "embedding_provider", "auto")
    embeddings.reset_embedding_provider()
    provider = embeddings.get_embedding_provider()

    assert (provider.name, provider.model) == ("ollama", "mxbai-embed-large:latest")
    # 1024, from the model — not the 768 the old configuration assumed.
    assert provider.dimensions == 1024


def test_a_reasoning_models_deliberation_never_reaches_the_user(deployed):
    """qwen3 thinks out loud in <think> tags. That is not the answer."""
    STATE["pieces"] = [
        "<think>The user asks about retention. ",
        "Passage 1 says seven years.</think>",
        "Ledger exports are kept for seven years [1].",
    ]

    generated = ollama.generate(deployed, "qwen3:4b", "question")

    assert generated.text == "Ledger exports are kept for seven years [1]."
    assert "<think>" not in generated.text


def test_thinking_is_not_streamed_either(deployed):
    STATE["pieces"] = ["<th", "ink>delib", "erating</thi", "nk>Seven ", "years [1]."]

    streamed = [
        item for item in ollama.generate_stream(deployed, "qwen3:4b", "q") if isinstance(item, str)
    ]

    # The user sees the answer forming, never the deliberation.
    assert "".join(streamed) == "Seven years [1]."


def test_thinking_is_turned_off_at_the_daemon_as_well(deployed):
    """Suppressing the output is the guard; not producing it is the saving."""
    ollama.generate(deployed, "qwen3:4b", "question")
    assert STATE["last_request"]["think"] is False


# --- Ask CEREBRO, end to end -----------------------------------------------

@pytest.fixture
def approved(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    artifact = client.post(
        "/api/artifacts", files={"file": ("atlas.txt", MEMO.encode(), "text/plain")}
    ).json()
    client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={"metadata": {"title": "Atlas Memo", "topics": ["Records"]}, "approve": True},
    )
    return artifact


def test_a_grounded_answer_from_an_approved_document(client, approved, deployed):
    STATE["pieces"] = [
        "<think>Passage 1 mentions seven years.</think>",
        "Ledger exports are retained for seven years [1].",
    ]

    body = client.post(
        "/api/recall", json={"question": "How long are ledger exports retained?"}
    ).json()

    assert body["answer"] == "Ledger exports are retained for seven years [1]."
    assert body["model"] == "qwen3:4b"
    assert body["grounded"] is True
    assert body["cited"] == [1]
    assert body["sources"][0]["filename"] == "atlas.txt"
    assert body["telemetry"]["completion_tokens"] == 42


def test_an_unapproved_document_is_never_the_evidence(client, valid_signup, deployed):
    """The approval workflow still gates retrieval, model or no model."""
    client.post("/api/auth/signup", json=valid_signup)
    client.post("/api/artifacts", files={"file": ("draft.txt", MEMO.encode(), "text/plain")})
    STATE.pop("last_prompt", None)

    body = client.post("/api/recall", json={"question": "retention schedule"}).json()

    assert body["answer"].startswith("Insufficient evidence")
    assert body["sources"] == []
    # No passages, so the model was not asked anything at all.
    assert "last_prompt" not in STATE


# --- Suggest with Local AI --------------------------------------------------

def test_people_organizations_and_projects_populate(client, valid_signup, deployed):
    client.post("/api/auth/signup", json=valid_signup)
    artifact = client.post(
        "/api/artifacts", files={"file": ("atlas.txt", MEMO.encode(), "text/plain")}
    ).json()

    # A reply shaped the way a model actually replies: a person with a title
    # appended, a company with punctuation the document spells differently,
    # and one invented name.
    STATE["pieces"] = [
        '<think>Reading the memo.</think>',
        '{"title": "Project Atlas migration memo", "description": null, '
        '"topics": ["ledger cutover"], "tags": ["reconciliation"], '
        '"people": ["Maria Santos (owner)", "Dr. Nobody Here"], '
        '"organizations": ["Acme, Inc."], "projects": ["Project Atlas"]}',
    ]

    body = client.post(f"/api/artifacts/{artifact['id']}/suggest").json()

    assert body["ai_used"] is True
    assert body["model"] == "qwen3:4b"
    suggestions = body["suggestions"]
    # The title in parentheses is not in the document; the name is.
    assert suggestions["people"] == ["Maria Santos"]
    # Punctuation differs from the document, which is not grounds to drop it.
    assert suggestions["organizations"] == ["Acme, Inc."]
    assert suggestions["projects"] == ["Project Atlas"]
    # The invented person is dropped, and the drop is recorded rather than
    # hidden.
    assert any("people" in note for note in body["notes"])
    # And each accepted entity carries the sentence it was found in.
    assert "Maria Santos" in body["evidence"]
    assert "Acme" in body["evidence"]["Maria Santos"]


def test_suggestions_are_never_saved_without_review(client, valid_signup, deployed):
    client.post("/api/auth/signup", json=valid_signup)
    artifact = client.post(
        "/api/artifacts", files={"file": ("atlas.txt", MEMO.encode(), "text/plain")}
    ).json()
    STATE["pieces"] = ['{"people": ["Maria Santos"], "projects": ["Project Atlas"]}']

    client.post(f"/api/artifacts/{artifact['id']}/suggest")
    stored = client.get(f"/api/artifacts/{artifact['id']}").json()

    # Proposed, not established. The form shows them; the artifact does not
    # carry them until a human approves.
    assert stored["metadata"]["people"] == []
    assert stored["metadata"]["projects"] == []
    assert stored["status"] != "registered"


def test_prose_around_the_json_is_recovered(client, valid_signup, deployed):
    """Models wrap JSON in a code fence even when told not to."""
    client.post("/api/auth/signup", json=valid_signup)
    artifact = client.post(
        "/api/artifacts", files={"file": ("atlas.txt", MEMO.encode(), "text/plain")}
    ).json()
    STATE["pieces"] = ['Here you go:\n```json\n{"projects": ["Project Atlas"]}\n```']

    body = client.post(f"/api/artifacts/{artifact['id']}/suggest").json()

    assert body["suggestions"]["projects"] == ["Project Atlas"]


# --- verification, not availability ----------------------------------------

def test_the_probe_runs_the_models_rather_than_listing_them(client, valid_signup, deployed):
    client.post("/api/auth/signup", json=valid_signup)
    STATE["pieces"] = ["<think>checking</think>ready"]

    body = client.post("/api/ml/probe").json()

    assert body["generation"]["ok"] is True
    assert body["generation"]["model"] == "qwen3:4b"
    # The model's own words came back, with the deliberation stripped.
    assert body["generation"]["sample"] == "ready"
    assert body["generation"]["completion_tokens"] == 42
    assert body["embedding"]["ok"] is True
    assert body["embedding"]["dimensions"] == body["embedding"]["declared_dimensions"]


def test_the_probe_says_so_when_the_daemon_is_absent(client, valid_signup, monkeypatch):
    client.post("/api/auth/signup", json=valid_signup)
    monkeypatch.setattr(ollama, "candidate_urls", lambda: ["http://127.0.0.1:1"])
    ollama.reset_discovery()

    response = client.post("/api/ml/probe")

    assert response.status_code == 503
    assert "ollama serve" in response.json()["detail"]


# --- the spec's wider entity set -------------------------------------------

def test_technologies_and_concepts_are_suggested_and_grounded(client, valid_signup, deployed):
    client.post("/api/auth/signup", json=valid_signup)
    text = (
        "The Atlas platform runs on PostgreSQL and Kubernetes. "
        "Retrieval augmented generation underpins the assistant. "
        "Maria Santos of Acme Inc. owns the rollout.\n"
    )
    artifact = client.post(
        "/api/artifacts", files={"file": ("atlas.txt", text.encode(), "text/plain")}
    ).json()
    STATE["pieces"] = [
        '{"technologies": ["PostgreSQL", "Kubernetes", "Redis"], '
        '"concepts": ["Retrieval augmented generation"], '
        '"people": ["Maria Santos"], "organizations": ["Acme Inc."]}'
    ]

    body = client.post(f"/api/artifacts/{artifact['id']}/suggest").json()

    assert body["suggestions"]["technologies"] == ["PostgreSQL", "Kubernetes"]
    assert body["suggestions"]["concepts"] == ["Retrieval augmented generation"]
    # Redis is not in the document, however plausible for this stack.
    assert "Redis" not in body["suggestions"]["technologies"]


def test_a_long_document_is_read_in_windows_not_truncated(client, valid_signup, deployed):
    """The people in a 29-page deck are mostly not in its first 6000 characters."""
    from app.services.artifacts.enrichment.llm import MAX_PROMPT_CHARS

    filler = "This paragraph discusses the migration in general terms. " * 200
    assert len(filler) > MAX_PROMPT_CHARS
    text = filler + "\nThe closing section names Priya Raman as the accountable owner.\n"

    client.post("/api/auth/signup", json=valid_signup)
    artifact = client.post(
        "/api/artifacts", files={"file": ("long.txt", text.encode(), "text/plain")}
    ).json()
    STATE["pieces"] = ['{"people": ["Priya Raman"]}']

    body = client.post(f"/api/artifacts/{artifact['id']}/suggest").json()

    # A name only in the tail is still found, and still checked against the
    # text that was actually read.
    assert body["suggestions"]["people"] == ["Priya Raman"]


def test_god_mode_sees_a_call_while_it_is_still_running(client, valid_signup, deployed):
    client.post("/api/auth/signup", json=valid_signup)
    telemetry.clear()
    STATE["pieces"] = ["ready"]

    client.post("/api/ml/probe")
    body = client.get("/api/ml/status").json()

    statuses = {(o["operation"], o["status"]) for o in body["operations"]}
    assert ("ml.probe.generate", "STARTED") in statuses
    assert ("ml.probe.generate", "COMPLETED") in statuses
    # Both halves of one execution share an id, so a long run can be followed.
    ids = {o["execution_id"] for o in body["operations"] if o["operation"] == "ml.probe.generate"}
    assert len(ids) == 1


def test_resources_are_measured_or_reported_as_unavailable(client, valid_signup, deployed):
    client.post("/api/auth/signup", json=valid_signup)

    resources = client.get("/api/ml/status").json()["resources"]

    # Memory is readable from /proc; a GPU is not visible from here and is
    # null rather than invented.
    assert resources["memory_mb"] is not None
    assert resources["gpu_percent"] is None
