"""The 1282-character chunk, and the boundary that let it through.

The reported failure was:

    Ollama returned 400 embedding a 1282-character chunk with
    'mxbai-embed-large:latest'
    -> "input length exceeds the context length"

The guard added with token-aware chunking measured each chunk against the
model's **context** (512) and allowed an estimate equal to it. A wordpiece
model wraps every input in [CLS] … [SEP], so a chunk measured at exactly 512
arrives as 514 and is refused. At 2.5 characters per token that boundary is a
1280-character chunk: it passed every check CEREBRO had and failed at the
daemon. The chunker, splitting at the hard limit, produced chunks sitting
exactly there.

The fix separates the model's context from what may actually be *sent*, and
refuses or splits against the latter. These tests hold the boundary from both
sides, prove no content is lost when an oversized input is split, and register
a real PDF end to end against a daemon that enforces the real 512-token limit.
"""
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from sqlalchemy import select

from app.models import Artifact, FragmentEmbedding, KnowledgeFragment
from app.services.artifacts import tokens as token_budget
from app.services.embeddings import EmbeddingFailed
from app.services.embeddings.ollama import OllamaEmbedder, _Refused
from tests.fixtures import make_pdf

MODEL = "mxbai-embed-large:latest"
CONTEXT = 512
WIDTH = 1024


def chunk_of(length: int) -> str:
    """Slide-like text of exactly `length` characters.

    Dense with short fragments and capitalisation, which is what tokenises
    badly and what the failing document was made of.
    """
    words = [
        "Reasoning", "Systems", "Knowledge", "Graph", "Provenance", "Retrieval",
        "Embedding", "Context", "Pipeline", "Artifact", "Ingestion", "Vector",
    ]
    out: list[str] = []
    size = 0
    i = 0
    while size < length:
        word = words[i % len(words)]
        out.append(word)
        size += len(word) + 1
        i += 1
    text = " ".join(out)
    return text[:length] if len(text) >= length else text + "x" * (length - len(text))


# The exact size from the report.
FAILING_CHUNK = chunk_of(1282)
# The size that passed the old guard and still failed at the daemon: an
# estimate of exactly 512 against a context of exactly 512.
BOUNDARY_CHUNK = chunk_of(1280)


@pytest.fixture
def signed_in(client, valid_signup):
    client.post("/api/auth/signup", json=valid_signup)
    return valid_signup


# --- the boundary ----------------------------------------------------------

def test_the_fixture_is_the_size_that_was_reported():
    assert len(FAILING_CHUNK) == 1282
    assert len(BOUNDARY_CHUNK) == 1280


def test_the_old_rule_would_have_sent_the_boundary_chunk():
    """The root cause, stated as a test rather than as a comment.

    Measured against the context — the rule that was in place — a
    1280-character chunk is exactly at the limit and passes.
    """
    assert token_budget.estimate(BOUNDARY_CHUNK) <= token_budget.context_for(MODEL)


def test_neither_chunk_fits_what_may_actually_be_sent():
    """The fix: the text's share of the context is smaller than the context."""
    assert not token_budget.fits(BOUNDARY_CHUNK, MODEL)
    assert not token_budget.fits(FAILING_CHUNK, MODEL)

    limit = token_budget.payload_limit(MODEL)
    assert limit == CONTEXT - token_budget.SPECIAL_TOKENS - token_budget.SAFETY_TOKENS
    assert limit < CONTEXT


def test_the_special_tokens_are_counted_not_assumed_away():
    """A chunk at exactly the payload limit still leaves room for [CLS]/[SEP]."""
    limit = token_budget.payload_limit(MODEL)
    at_limit = chunk_of(int(limit * token_budget.DENSE_CHARS_PER_TOKEN))

    assert token_budget.estimate(at_limit) <= limit
    assert token_budget.estimate(at_limit) + token_budget.SPECIAL_TOKENS < CONTEXT


# --- splitting, without losing anything ------------------------------------

def test_the_failing_chunk_is_split_and_nothing_is_lost():
    limit = token_budget.payload_limit(MODEL)
    pieces = token_budget.split_to_fit(FAILING_CHUNK, limit)

    assert len(pieces) > 1
    assert all(token_budget.estimate(p) <= limit for p in pieces)
    # Every word appears once, in order. Not truncated, not skipped.
    assert " ".join(pieces).split() == FAILING_CHUNK.split()


def test_a_chunk_that_fits_is_left_exactly_as_it_is():
    short = "CEREBRO preserves provenance to source artifacts."
    assert token_budget.split_to_fit(short, token_budget.payload_limit(MODEL)) == [short]


def test_a_single_unbreakable_word_is_never_cut():
    """Cutting a word loses content; refusing it is the honest outcome."""
    word = "x" * 4000
    assert token_budget.split_to_fit(word, token_budget.payload_limit(MODEL)) == [word]


# --- the guard, on every path ----------------------------------------------

def test_no_request_leaves_with_an_oversized_payload():
    """The guard sits in _post, so it covers every caller of every endpoint."""
    embedder = OllamaEmbedder(model=MODEL, dimensions=WIDTH, context_limit=CONTEXT)

    for payload in (
        {"model": MODEL, "input": [FAILING_CHUNK], "truncate": False},
        {"model": MODEL, "input": FAILING_CHUNK, "truncate": False},
        {"model": MODEL, "prompt": FAILING_CHUNK},
    ):
        with pytest.raises(EmbeddingFailed) as exc:
            embedder._post("/api/embed", payload, 5)
        assert "Nothing was sent" in str(exc.value)


def test_the_guard_respects_a_narrowed_limit():
    embedder = OllamaEmbedder(model=MODEL, dimensions=WIDTH, context_limit=128)
    with pytest.raises(EmbeddingFailed):
        embedder._post("/api/embed", {"model": MODEL, "input": chunk_of(400)}, 5)


# --- a daemon that enforces the real limit ---------------------------------

class _Daemon(BaseHTTPRequestHandler):
    """Ollama's behaviour for an over-long input, and nothing else.

    The token count is calibrated to the two facts the failure established,
    rather than invented: the daemon refused 1282 characters of this content
    as over 512 tokens, which puts the density at or below 2.5 characters per
    token, and a wordpiece model adds [CLS] and [SEP] on top of the text. A
    first attempt here counted per word and came to 382 for the chunk the real
    daemon refused — lenient enough that the test passed without the refusal
    path ever running, which is worse than no test.
    """

    received: list[int] = []
    refusals: list[str] = []

    @staticmethod
    def count(text: str) -> int:
        return token_budget.SPECIAL_TOKENS + math.ceil(
            len(text) / token_budget.DENSE_CHARS_PER_TOKEN
        )

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        raw = body.get("input", body.get("prompt"))
        texts = raw if isinstance(raw, list) else [raw]

        for text in texts:
            size = self.count(text)
            # type(self), not _Daemon: a subclass with a different token rule
            # must record against its own tally, or its test reads the parent's.
            type(self).received.append(size)
            if size > CONTEXT:
                type(self).refusals.append(text)
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "input length exceeds the context length"}).encode()
                )
                return

        out = json.dumps({"embeddings": [[0.0] * (WIDTH - 1) + [1.0] for _ in texts]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *args):  # keep the test output clean
        return


@pytest.fixture
def daemon():
    _Daemon.received = []
    _Daemon.refusals = []
    server = HTTPServer(("127.0.0.1", 0), _Daemon)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", _Daemon
    server.shutdown()
    server.server_close()


def test_the_daemon_stub_refuses_exactly_what_the_real_one_refused(daemon):
    """Calibration check: the harness must reproduce the reported failure.

    Without this, a lenient stub would let every other test here pass while
    proving nothing.
    """
    base_url, spy = daemon
    embedder = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )

    assert spy.count(FAILING_CHUNK) > CONTEXT
    assert spy.count(BOUNDARY_CHUNK) > CONTEXT

    # Sent whole — as the old rule did — and refused, with the daemon's words.
    # _post surfaces the daemon's own refusal; _batch and _one are what turn
    # it into an EmbeddingFailed for a caller.
    with pytest.raises(_Refused) as exc:
        embedder._post("/api/embed", {"model": MODEL, "input": [FAILING_CHUNK]}, 5, guard=False)
    assert "input length exceeds the context length" in str(exc.value)
    assert exc.value.code == 400
    assert spy.refusals == [FAILING_CHUNK]


def test_a_correctly_sized_chunk_is_accepted_by_the_same_daemon(daemon):
    """The other side of the boundary: the fix has to leave room to work in."""
    base_url, spy = daemon
    embedder = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )
    at_limit = chunk_of(int(token_budget.payload_limit(MODEL, CONTEXT) * 2.5))

    assert spy.count(at_limit) <= CONTEXT
    assert len(embedder.embed([at_limit])) == 1
    assert spy.refusals == []


def test_the_failing_chunk_now_embeds_against_a_real_limit(daemon):
    """End to end on the reported failure: one vector out, no refusal."""
    base_url, spy = daemon
    embedder = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )

    vectors = embedder.embed([FAILING_CHUNK, BOUNDARY_CHUNK, "A short line."])

    assert len(vectors) == 3
    assert all(len(v) == WIDTH for v in vectors)
    assert spy.refusals == []
    assert max(spy.received) <= CONTEXT
    # The two oversized inputs were sent in pieces; the short one was not.
    assert len(spy.received) > 3


def test_a_pooled_vector_is_a_unit_vector_of_the_right_width(daemon):
    base_url, _ = daemon
    embedder = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )

    vector = embedder.embed([FAILING_CHUNK])[0]

    assert len(vector) == WIDTH
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


# --- the whole pipeline ----------------------------------------------------

def test_a_dense_pdf_registers_end_to_end_against_the_real_limit(
    client, signed_in, db, daemon, monkeypatch
):
    """The document that could not be registered, registered.

    A multi-page PDF of the dense text that broke ingestion, through upload,
    inspection, approval, chunking and embedding, against a daemon that
    refuses anything over 512 tokens the way the real one does.
    """
    base_url, spy = daemon
    embedder = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )
    monkeypatch.setattr("app.services.artifacts.fragments.provider_for", lambda _s: embedder)

    pages = ["\n".join(chunk_of(1282)[i : i + 90] for i in range(0, 1282, 90))] * 6
    pdf = make_pdf(pages, title="Intelligent Reasoning Systems")

    upload = client.post(
        "/api/artifacts", files={"file": ("irs-deck.pdf", pdf, "application/pdf")}
    ).json()
    body = client.patch(
        f"/api/artifacts/{upload['id']}",
        json={"metadata": {"title": "Intelligent Reasoning Systems"}, "approve": True},
    ).json()

    assert body["status"] == "registered", body
    assert spy.refusals == []
    assert max(spy.received) <= CONTEXT

    artifact = db.scalars(select(Artifact)).one()
    fragments = db.scalars(
        select(KnowledgeFragment).where(KnowledgeFragment.artifact_id == artifact.id)
    ).all()
    assert fragments, "a registered document must have fragments"

    # Every fragment carries a vector of the right width, and none of them was
    # ever too large to send.
    vectors = db.scalars(
        select(FragmentEmbedding).where(
            FragmentEmbedding.fragment_id.in_([f.id for f in fragments])
        )
    ).all()
    assert len(vectors) == len(fragments)
    assert {v.dimensions for v in vectors} == {WIDTH}
    assert all(
        token_budget.fits(f.content, MODEL, CONTEXT) for f in fragments
    ), "the chunker must not produce a fragment the guard would refuse"

    # Provenance survived, and approval state is intact.
    assert artifact.provenance["chunking"]["limit_tokens"] == token_budget.payload_limit(
        MODEL, CONTEXT
    )
    assert artifact.status == "registered"


# --- a failure must not leave half a registration --------------------------

def test_a_failed_embedding_leaves_no_orphans_and_retries_without_re_upload(
    client, signed_in, db, daemon, monkeypatch
):
    """Requirement 8, as behaviour: refuse cleanly, then succeed on retry.

    The document survives, nothing half-written is left in retrieval, and the
    second attempt needs no new upload. The successful chunks of the failed
    attempt are rolled back with it rather than kept: an orphan fragment is
    content the library would treat as retrievable evidence while no vector
    can reach it, which is the worse of the two costs.
    """
    base_url, _ = daemon
    working = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )

    class Broken(OllamaEmbedder):
        def embed(self, texts):
            raise EmbeddingFailed("the daemon went away mid-document")

    broken = Broken(base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT)
    monkeypatch.setattr("app.services.artifacts.fragments.provider_for", lambda _s: broken)

    pdf = make_pdf([chunk_of(900), chunk_of(900)], title="Reasoning Systems")
    upload = client.post(
        "/api/artifacts", files={"file": ("deck.pdf", pdf, "application/pdf")}
    ).json()

    refused = client.patch(
        f"/api/artifacts/{upload['id']}",
        json={"metadata": {"title": "Reasoning Systems"}, "approve": True},
    )
    assert refused.status_code == 503
    assert "Registration stopped before completing" in refused.json()["detail"]

    # The document is still there and still unregistered, with nothing of it
    # in retrieval.
    artifact = db.scalars(select(Artifact)).one()
    db.refresh(artifact)
    assert artifact.status != "registered"
    assert artifact.registered_at is None
    assert db.scalars(select(KnowledgeFragment)).all() == []

    # Same artifact, same upload, working daemon: registers completely.
    monkeypatch.setattr("app.services.artifacts.fragments.provider_for", lambda _s: working)
    second = client.patch(
        f"/api/artifacts/{upload['id']}",
        json={"metadata": {"title": "Reasoning Systems"}, "approve": True},
    )
    assert second.status_code == 200, second.json()
    assert second.json()["status"] == "registered"

    fragments = db.scalars(select(KnowledgeFragment)).all()
    assert fragments
    vectors = db.scalars(select(FragmentEmbedding)).all()
    assert len(vectors) == len(fragments)


# --- when the estimate itself is wrong -------------------------------------

class _DenseDaemon(_Daemon):
    """A daemon for text that tokenises far worse than 2.5 characters a token.

    Symbol soup, unbroken URLs and CJK all tokenise denser than the estimate
    assumes, so a chunk the guard believes is inside the limit can still
    overrun it. This daemon counts one token per character, which no estimate
    here would predict, and refuses accordingly.
    """

    @staticmethod
    def count(text: str) -> int:
        return token_budget.SPECIAL_TOKENS + len(text)


@pytest.fixture
def dense_daemon():
    _DenseDaemon.received = []
    _DenseDaemon.refusals = []
    server = HTTPServer(("127.0.0.1", 0), _DenseDaemon)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", _DenseDaemon
    server.shutdown()
    server.server_close()


def test_a_refusal_the_estimate_did_not_predict_is_re_split_not_failed(dense_daemon):
    """The daemon's own answer drives the retry, so density need not be known."""
    base_url, spy = dense_daemon
    embedder = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )

    # 900 characters: well inside the guard's 502-token estimate, and far
    # outside this daemon's one-token-per-character reality.
    text = chunk_of(900)
    assert token_budget.fits(text, MODEL, CONTEXT)
    assert spy.count(text) > CONTEXT

    vectors = embedder.embed([text])

    assert len(vectors) == 1
    assert len(vectors[0]) == WIDTH
    # It was refused at first, then accepted once split smaller.
    assert spy.refusals
    assert any(size <= CONTEXT for size in spy.received)


def test_an_unbreakable_input_fails_honestly_rather_than_being_cut(dense_daemon):
    """A single word over the limit cannot be split without losing content."""
    base_url, _ = dense_daemon
    embedder = OllamaEmbedder(
        base_url=base_url, model=MODEL, dimensions=WIDTH, context_limit=CONTEXT
    )

    with pytest.raises(EmbeddingFailed) as exc:
        embedder.embed(["x" * 900])

    # The daemon's reason survives to the caller, rather than a cut vector
    # being written as though it were the whole text.
    assert "context" in str(exc.value).lower()
