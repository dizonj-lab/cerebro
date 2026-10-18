"""Ollama embedder — a learned model, running locally.

Ollama runs on the user's own machine, so content does not leave the CEREBRO
environment. It is opt-in because it needs a model pulled first:

    ollama pull nomic-embed-text

A failure here raises. It does not fall back to the hashing embedder: that
would put vectors from two different spaces in one index and make every
similarity between them meaningless. It does not fall back to a cloud
provider either, under any circumstances.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.request

from app.services.embeddings.base import EmbeddingFailed

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_DIMENSIONS = 768
_TIMEOUT_SECONDS = 30
# A batch is many texts through the model in one request, so it is allowed
# proportionally longer than a single embedding.
_BATCH_TIMEOUT_SECONDS = 300
# How many texts go in one request.
#
# "All of them" was the first attempt and it is what a thirty-two page deck
# turned into: eighty chunks in a single call, which Ollama answered with a
# 400 and no explanation, and registration stopped having done nothing.
# Embedding models have small contexts — mxbai-embed-large's is 512 tokens —
# and a daemon asked for far more than it can hold refuses the request
# rather than truncating it.
#
# Sixteen keeps the round trips low, which was the point of batching, while
# staying well inside what a daemon will accept.
MAX_BATCH = 16


class _BatchUnsupported(Exception):
    """This daemon has no /api/embed. Fall back to one call per text."""


class _Refused(Exception):
    """The daemon answered with an HTTP status rather than an embedding.

    Carries the daemon's own message. Discarding it is why three rounds of
    this were spent guessing at the cause from a bare status code: Ollama
    says exactly what it objected to, in the body of the very response that
    was being thrown away.
    """

    def __init__(self, code: int, endpoint: str, detail: str = "") -> None:
        super().__init__(f"{code} from {endpoint}: {detail}" if detail else f"{code} from {endpoint}")
        self.code = code
        self.endpoint = endpoint
        self.detail = detail


def _reason(exc: urllib.error.HTTPError) -> str:
    """Ollama's own explanation, read off the error response."""
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - a body that cannot be read is not an error
        return ""
    try:
        return str(json.loads(raw).get("error") or "")[:200]
    except json.JSONDecodeError:
        return raw.strip()[:200]


class OllamaEmbedder:
    name = "ollama"
    # Ollama is a local daemon. Content stays in the CEREBRO environment.
    is_local = True

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch in as few round trips as possible.

        Ollama's /api/embed takes a list and runs it through the model in one
        request. One HTTP call per chunk meant 87 round trips for a 29-page
        PDF, which is most of what made registering a real document feel
        broken. Older daemons have only /api/embeddings, which is one text
        per call, so that stays as the fallback.
        """
        if not texts:
            return []
        # An empty chunk has no meaning to embed and Ollama refuses the whole
        # request over one of them, so it is caught here, named, and not sent.
        blank = [i for i, text in enumerate(texts) if not text.strip()]
        if blank:
            raise EmbeddingFailed(
                f"{len(blank)} of {len(texts)} chunks were empty, which cannot be embedded."
            )

        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            group = texts[start : start + MAX_BATCH]
            try:
                vectors.extend(self._batch(group))
            except _BatchUnsupported:
                vectors.extend(self._one(text) for text in group)
            except EmbeddingFailed:
                # A refused group is retried one text at a time. One chunk
                # the daemon will not take should cost that chunk, not the
                # whole document — and doing it singly names which one.
                vectors.extend(self._one(text) for text in group)
        return vectors

    def _post(self, endpoint: str, payload: dict, timeout: float) -> dict:
        """One request to the daemon, with its failures told apart.

        HTTPError is checked before URLError, which it subclasses. Without
        that a daemon answering 400 was reported as a daemon that could not
        be reached, and the remedy offered — start Ollama, pull the model —
        addressed a problem the user did not have.
        """
        request = urllib.request.Request(  # noqa: S310 - fixed http scheme, local daemon
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _Refused(exc.code, endpoint, _reason(exc)) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EmbeddingFailed(
                f"Could not reach Ollama at {self.base_url}. Is it running, and has "
                f"'{self.model}' been pulled?"
            ) from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingFailed("Ollama returned a response that was not JSON.") from exc

    def _batch(self, texts: list[str]) -> list[list[float]]:
        try:
            body = self._post(
                "/api/embed",
                # `truncate` asked for explicitly rather than left to the
                # daemon's default, which has not been the same across
                # versions. An embedding model's context is small —
                # mxbai-embed-large's is 512 tokens — and a chunk that
                # tokenises longer than it looks is common in slide decks,
                # which are dense with symbols, URLs and short fragments. A
                # daemon that refuses such a chunk fails the whole
                # registration; one that truncates embeds the part that
                # fits, which is the lesser loss and is recoverable by
                # re-registering with smaller chunks.
                {"model": self.model, "input": texts, "truncate": True},
                _BATCH_TIMEOUT_SECONDS,
            )
        except _Refused as exc:
            # 404 means this daemon predates /api/embed. Anything else is a
            # real failure and must not be silently retried one by one.
            if exc.code == 404:
                raise _BatchUnsupported from None
            raise EmbeddingFailed(
                f"Ollama returned {exc.code} embedding a batch of {len(texts)} "
                f"with '{self.model}'" + (f": {exc.detail}" if exc.detail else ".")
            ) from None

        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingFailed(
                f"Ollama returned {len(vectors) if isinstance(vectors, list) else 0} "
                f"embeddings for {len(texts)} texts."
            )
        return [self._normalise(v) for v in vectors]

    def measure(self, text: str) -> list[float]:
        """Embed without the width check, to learn an unknown model's width."""
        return self._one(text, check_width=False)

    def _one(self, text: str, *, check_width: bool = True) -> list[float]:
        """One text, through the modern endpoint, falling back to the old one.

        `/api/embed` takes a single string as happily as a list, and it is
        the endpoint Ollama maintains. `/api/embeddings` is the deprecated
        one, and current daemons answer 500 to it for some embedding models
        — which is what turned a retry meant to isolate one awkward chunk
        into a registration that failed on every chunk it tried.
        """
        try:
            body = self._post(
                "/api/embed",
                {"model": self.model, "input": text, "truncate": True},
                _TIMEOUT_SECONDS,
            )
        except _Refused as modern:
            if modern.code != 404:
                raise EmbeddingFailed(
                    f"Ollama returned {modern.code} embedding a "
                    f"{len(text)}-character chunk with '{self.model}'"
                    + (f": {modern.detail}" if modern.detail else ".")
                ) from None
            # Genuinely old daemon: no /api/embed at all.
            try:
                legacy = self._post(
                    "/api/embeddings",
                    {"model": self.model, "prompt": text},
                    _TIMEOUT_SECONDS,
                )
            except _Refused as old:
                raise EmbeddingFailed(
                    f"Ollama returned {old.code} embedding a "
                    f"{len(text)}-character chunk with '{self.model}'"
                    + (f": {old.detail}" if old.detail else ".")
                ) from None
            return self._normalise(legacy.get("embedding"), check_width=check_width)

        vectors = body.get("embeddings")
        vector = vectors[0] if isinstance(vectors, list) and vectors else body.get("embedding")
        return self._normalise(vector, check_width=check_width)

    def _normalise(self, vector: object, *, check_width: bool = True) -> list[float]:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingFailed(f"Ollama returned no embedding for model '{self.model}'.")
        if check_width and len(vector) != self.dimensions:
            # Configured width and actual width must agree, or this provider
            # would write two incompatible spaces under one model name.
            raise EmbeddingFailed(
                f"Ollama model '{self.model}' returned {len(vector)} dimensions, "
                f"but {self.dimensions} were configured."
            )
        norm = math.sqrt(sum(float(v) * float(v) for v in vector))
        return [float(v) / norm for v in vector] if norm else [float(v) for v in vector]
