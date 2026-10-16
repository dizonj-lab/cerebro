"""Assisted Recollection: grounded answers, or none.

The properties that matter: only registered knowledge is searched, every
answer carries its sources, and no model is asked anything until passages
have been retrieved.
"""
import pytest

CONTENT = (
    b"The Atlas migration moves forty database clusters in March. "
    b"Atlas reporting runs in parallel for two weeks during the migration. "
    b"Database tests must pass before Atlas cutover.\n"
)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


def upload(client, name="atlas.txt", content=CONTENT):
    return client.post("/api/artifacts", files={"file": (name, content, "text/plain")}).json()


def register(client, artifact, topics=("Atlas",)):
    return client.patch(
        f"/api/artifacts/{artifact['id']}",
        json={
            "metadata": {**artifact["metadata"], "title": "Atlas Plan", "topics": list(topics)},
            "approve": True,
        },
    )


def ask(client, question, topic=None):
    return client.post("/api/recall", json={"question": question, "topic": topic})


def test_a_question_with_no_matching_knowledge_is_answered_honestly(client, signed_in):
    body = ask(client, "What is the capital of France?").json()

    assert body["sources"] == []
    assert body["grounded"] is False
    # The product's exact words for abstaining, which must not drift.
    assert body["answer"].startswith("Insufficient evidence")


def test_unapproved_documents_are_never_searched(client, signed_in):
    upload(client)  # uploaded, not registered

    body = ask(client, "Atlas migration database clusters").json()
    assert body["sources"] == []
    assert body["grounded"] is False


def test_an_answer_is_grounded_in_registered_passages(client, signed_in):
    register(client, upload(client))

    body = ask(client, "Atlas migration database clusters").json()
    assert body["grounded"] is True
    assert body["sources"], "expected passages from the library"

    source = body["sources"][0]
    # Every passage resolves to a document and a place inside it.
    assert source["filename"] == "atlas.txt"
    assert source["artifact_id"]
    assert source["fragment_id"]
    assert "char_start" in source["source_location"]
    assert "Atlas" in source["excerpt"]


def test_without_a_local_model_the_passages_are_the_answer(client, signed_in):
    """Answering switched off: return evidence rather than nothing, and say so.

    The suite pins CEREBRO_RECALL_LLM=off so it never depends on whether a
    daemon happens to be running on the machine running it.
    """
    register(client, upload(client))

    body = ask(client, "Atlas migration database clusters").json()
    assert body["answer"] is None
    assert body["model"] is None
    assert body["sources"]
    assert "switched off for this deployment" in body["note"]


def test_with_no_daemon_running_the_note_says_how_to_start_one(client, signed_in):
    """A missing daemon is a degraded feature with an instruction, not a dead one."""
    from app.core.config import get_settings
    from app.services import ollama

    register(client, upload(client))
    settings = get_settings()
    settings.recall_llm = "auto"
    ollama.reset_discovery()
    try:
        body = ask(client, "Atlas migration database clusters").json()
    finally:
        settings.recall_llm = "off"
        ollama.reset_discovery()

    assert body["answer"] is None
    assert body["sources"]
    assert body["grounded"] is True
    assert "ollama serve" in body["note"]


def test_an_unreachable_model_falls_back_to_the_passages(client, signed_in):
    """Never a cloud fallback, and never an ungrounded answer."""
    from app.core.config import get_settings

    register(client, upload(client))
    settings = get_settings()
    from app.services import ollama

    settings.recall_llm = "auto"
    # Every candidate URL points at a port with nothing on it, so discovery
    # fails the way it does on a machine without Ollama.
    settings.ollama_base_url = "http://127.0.0.1:1"
    ollama.reset_discovery()
    try:
        body = ask(client, "Atlas migration database clusters").json()
    finally:
        settings.recall_llm = "off"
        settings.ollama_base_url = "http://localhost:11434"
        ollama.reset_discovery()

    assert body["answer"] is None
    assert body["sources"]
    # Degraded to the passages, with an instruction. Never a cloud call.
    assert "ollama" in body["note"].lower()


def test_the_model_is_only_asked_after_retrieval_finds_something(client, signed_in):
    """No passages, no model call — and no answer invented from thin air."""
    from app.core.config import get_settings
    from app.services import ollama

    settings = get_settings()
    settings.recall_llm = "auto"
    # A port with nothing on it: if this were reached the test would hang or
    # the note would say unreachable. It stays untouched because retrieval
    # returned nothing first.
    settings.ollama_base_url = "http://127.0.0.1:1"
    ollama.reset_discovery()
    try:
        body = ask(client, "Nothing in this library mentions this at all").json()
    finally:
        settings.recall_llm = "off"
        settings.ollama_base_url = "http://localhost:11434"
        ollama.reset_discovery()

    assert body["grounded"] is False
    assert body["sources"] == []
    assert "could not be reached" not in (body["note"] or "")


def test_a_selected_cluster_is_context_not_a_filter(client, signed_in):
    register(client, upload(client))

    body = ask(client, "when does cutover happen", topic="Atlas").json()
    assert body["grounded"] is True
    assert body["sources"]


def test_one_user_never_recalls_another_users_library(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    register(client, upload(client, "private.txt"))
    client.post("/api/auth/logout")

    client.post(
        "/api/auth/signup",
        json={
            "display_name": "Grace Hopper",
            "email": "grace@example.com",
            "password": "compiler-1952-nanoseconds",
        },
    )
    body = ask(client, "Atlas migration database clusters").json()
    assert body["sources"] == []
    assert body["grounded"] is False


def test_recall_requires_a_session(client):
    assert client.post("/api/recall", json={"question": "anything"}).status_code == 401


def test_an_empty_question_is_rejected(client, signed_in):
    assert client.post("/api/recall", json={"question": ""}).status_code == 422
