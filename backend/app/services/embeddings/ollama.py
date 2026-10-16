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


class _BatchUnsupported(Exception):
    """This daemon has no /api/embed. Fall back to one call per text."""


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
        try:
            return self._batch(texts)
        except _BatchUnsupported:
            return [self._one(text) for text in texts]

    def _batch(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed http scheme, local daemon
            f"{self.base_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_BATCH_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 404 means this daemon predates /api/embed. Anything else is a
            # real failure and must not be silently retried one by one.
            if exc.code == 404:
                raise _BatchUnsupported from None
            raise EmbeddingFailed(
                f"Ollama returned {exc.code} embedding with '{self.model}'."
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EmbeddingFailed(
                f"Could not reach Ollama at {self.base_url}. Is it running, and has "
                f"'{self.model}' been pulled?"
            ) from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingFailed("Ollama returned a response that was not JSON.") from exc

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
        payload = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed http scheme, local daemon
            f"{self.base_url}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EmbeddingFailed(
                f"Could not reach Ollama at {self.base_url}. Is it running, and has "
                f"'{self.model}' been pulled?"
            ) from exc
        except json.JSONDecodeError as exc:
            raise EmbeddingFailed("Ollama returned a response that was not JSON.") from exc

        return self._normalise(body.get("embedding"), check_width=check_width)

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
