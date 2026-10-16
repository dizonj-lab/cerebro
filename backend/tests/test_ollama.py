"""The Ollama path, against a real HTTP daemon.

A stand-in daemon is started on a real socket and the application talks to it
over real HTTP, so discovery, model selection, streaming, token accounting
and failure handling are all exercised as written. What this cannot test is
the quality of a model's answer — that needs the user's own Ollama and their
own documents, and no fixture can stand in for it.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.core.config import get_settings
from app.services import ollama, telemetry
from app.services.embeddings import reset_embedding_provider

# What the fake daemon reports and returns. Set per test.
STATE: dict = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: ANN002 - quiet test server
        pass

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        if self.path == "/api/tags":
            self._json(200, {"models": [{"name": n} for n in STATE.get("models", [])]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/generate":
            STATE["last_prompt"] = request.get("prompt", "")
            STATE["last_request"] = request
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            # Streamed as the daemon streams it: one JSON object per line,
            # the last carrying the counts.
            for piece in STATE.get("pieces", ["ok"]):
                self.wfile.write(json.dumps({"response": piece, "done": False}).encode() + b"\n")
                self.wfile.flush()
            self.wfile.write(
                json.dumps(
                    {
                        "response": "",
                        "done": True,
                        "prompt_eval_count": 321,
                        "eval_count": 42,
                    }
                ).encode()
                + b"\n"
            )
        elif self.path == "/api/embed":
            if STATE.get("no_batch"):
                # An older daemon, which has only the one-at-a-time endpoint.
                self._json(404, {"error": "not found"})
                return
            STATE["batch_calls"] = STATE.get("batch_calls", 0) + 1
            texts = request.get("input", [])
            if STATE.get("short_batch"):
                texts = texts[:-1]
            width = STATE.get("dimensions", 768)
            self._json(
                200,
                {
                    "embeddings": [
                        [(sum(t.encode()) % (i + 7)) / 7 for i in range(width)] for t in texts
                    ]
                },
            )
        elif self.path == "/api/embeddings":
            STATE["single_calls"] = STATE.get("single_calls", 0) + 1
            width = STATE.get("dimensions", 768)
            # A deterministic but model-shaped vector; the width is what the
            # application has to agree with.
            seed = sum(request.get("prompt", "").encode()) or 1
            self._json(200, {"embedding": [(seed % (i + 7)) / 7 for i in range(width)]})
        else:
            self._json(404, {"error": "not found"})


@pytest.fixture
def daemon(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    STATE.clear()
    STATE["models"] = ["llama3.2:3b", "nomic-embed-text:latest"]
    settings = get_settings()
    monkeypatch.setattr(settings, "ollama_base_url", base_url)
    ollama.reset_discovery()
    reset_embedding_provider()
    telemetry.clear()
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        ollama.reset_discovery()
        reset_embedding_provider()


# --- discovery and model selection -----------------------------------------

def test_discovery_reports_what_is_installed(daemon):
    found = ollama.discover(force=True)
    assert found.reachable
    assert found.base_url == daemon
    assert found.models == ["llama3.2:3b", "nomic-embed-text:latest"]


def test_an_answering_model_and_an_embedder_are_told_apart(daemon):
    found = ollama.discover(force=True)
    # The embedder must never be chosen to answer with, or the reverse.
    assert found.chat_model() == "llama3.2:3b"
    assert found.embedding_model() == "nomic-embed-text:latest"


def test_preference_order_decides_between_installed_models(daemon):
    STATE["models"] = ["mistral:7b", "llama3.2:1b", "qwen2.5:3b"]
    found = ollama.discover(force=True)
    assert found.chat_model() == "llama3.2:1b"


def test_an_unlisted_model_is_still_usable(daemon):
    """A user with one unusual model gets a working feature, not an error."""
    STATE["models"] = ["deepseek-r1:7b"]
    found = ollama.discover(force=True)
    assert found.chat_model() == "deepseek-r1:7b"
    assert found.embedding_model() is None


def test_an_absent_daemon_is_reported_not_raised(monkeypatch):
    # A port with nothing on it, and no other candidate reachable.
    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:1")
    monkeypatch.setattr(ollama, "candidate_urls", lambda: ["http://127.0.0.1:1"])
    ollama.reset_discovery()
    found = ollama.discover(force=True)
    assert found.reachable is False
    assert "ollama serve" in (found.error or "")


# --- generation -------------------------------------------------------------

def test_generation_streams_and_reports_the_daemons_own_counts(daemon):
    STATE["pieces"] = ["The ", "retention ", "schedule ", "is ", "seven years."]
    pieces = []
    final = None
    for item in ollama.generate_stream(daemon, "llama3.2:3b", "question"):
        if isinstance(item, str):
            pieces.append(item)
        else:
            final = item

    # The text arrives incrementally and adds up to the answer. Chunk
    # boundaries are deliberately not asserted: the filter that removes a
    # reasoning model's <think> tags holds a few characters back to catch a
    # tag split across chunks, so where the breaks fall is its business.
    assert "".join(pieces) == "".join(STATE["pieces"])
    assert len(pieces) > 1
    assert final is not None
    assert final.text == "The retention schedule is seven years."
    # Counted by the daemon, not estimated here.
    assert (final.prompt_tokens, final.completion_tokens) == (321, 42)
    assert final.duration_ms >= 0


def test_every_call_is_recorded_for_telemetry_window(daemon):
    ollama.generate(daemon, "llama3.2:3b", "question")
    operations = telemetry.recent()
    assert operations[0]["operation"] == "ollama.generate"
    assert operations[0]["model"] == "llama3.2:3b"
    assert operations[0]["completion_tokens"] == 42


def test_an_unreachable_model_raises_rather_than_inventing_an_answer():
    with pytest.raises(ollama.OllamaUnavailable):
        ollama.generate("http://127.0.0.1:1", "llama3.2", "question")


# --- embeddings -------------------------------------------------------------

def test_auto_selects_the_pretrained_embedder_when_one_is_installed(daemon, monkeypatch):
    from app.services import embeddings

    monkeypatch.setattr(get_settings(), "embedding_provider", "auto")
    embeddings.reset_embedding_provider()
    provider = embeddings.get_embedding_provider()

    assert provider.name == "ollama"
    assert provider.model == "nomic-embed-text:latest"
    assert provider.dimensions == 768


def test_auto_falls_back_to_hashing_without_a_daemon(monkeypatch):
    from app.services import embeddings

    monkeypatch.setattr(get_settings(), "embedding_provider", "auto")
    monkeypatch.setattr(ollama, "candidate_urls", lambda: ["http://127.0.0.1:1"])
    ollama.reset_discovery()
    embeddings.reset_embedding_provider()
    provider = embeddings.get_embedding_provider()

    # Deterministic, offline, and honestly labelled as not pretrained.
    assert provider.name == "hashing"


def test_an_unknown_embedder_has_its_width_measured(daemon, monkeypatch):
    from app.services import embeddings

    STATE["models"] = ["some-new-embed:latest"]
    STATE["dimensions"] = 512
    monkeypatch.setattr(get_settings(), "embedding_provider", "auto")
    ollama.reset_discovery()
    embeddings.reset_embedding_provider()
    provider = embeddings.get_embedding_provider()

    # Not assumed from a table: asked of the model.
    assert provider.dimensions == 512


def test_embeddings_are_unit_length(daemon, monkeypatch):
    from app.services import embeddings

    monkeypatch.setattr(get_settings(), "embedding_provider", "auto")
    ollama.reset_discovery()
    embeddings.reset_embedding_provider()
    vector = embeddings.get_embedding_provider().embed(["provenance"])[0]

    # Normalised on write, so cosine similarity is a dot product.
    assert abs(sum(v * v for v in vector) ** 0.5 - 1.0) < 1e-6


def test_a_batch_is_one_request_not_one_per_text(daemon, monkeypatch):
    """87 round trips for one PDF is what made registering feel broken."""
    from app.services import embeddings

    monkeypatch.setattr(get_settings(), "embedding_provider", "auto")
    ollama.reset_discovery()
    embeddings.reset_embedding_provider()
    provider = embeddings.get_embedding_provider()

    vectors = provider.embed([f"chunk number {i}" for i in range(40)])

    assert len(vectors) == 40
    assert STATE.get("batch_calls") == 1
    assert STATE.get("single_calls", 0) == 0


def test_an_older_daemon_still_works_one_text_at_a_time(daemon, monkeypatch):
    """/api/embed is recent; a 404 is a capability answer, not a failure."""
    from app.services import embeddings

    STATE["no_batch"] = True
    monkeypatch.setattr(get_settings(), "embedding_provider", "auto")
    ollama.reset_discovery()
    embeddings.reset_embedding_provider()
    provider = embeddings.get_embedding_provider()

    vectors = provider.embed(["one", "two", "three"])

    assert len(vectors) == 3
    assert STATE.get("single_calls") == 3


def test_a_short_batch_is_refused_rather_than_misaligned(daemon):
    """Fewer vectors than texts would attach embeddings to the wrong chunks."""
    from app.services.embeddings import EmbeddingFailed
    from app.services.embeddings.ollama import OllamaEmbedder

    STATE["short_batch"] = True
    provider = OllamaEmbedder(
        base_url=daemon, model="nomic-embed-text:latest", dimensions=768
    )

    with pytest.raises(EmbeddingFailed):
        provider.embed(["a", "b", "c"])
