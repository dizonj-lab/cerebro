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
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
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

        vector = body.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise EmbeddingFailed(f"Ollama returned no embedding for model '{self.model}'.")
        if len(vector) != self.dimensions:
            # Configured width and actual width must agree, or this provider
            # would write two incompatible spaces under one model name.
            raise EmbeddingFailed(
                f"Ollama model '{self.model}' returned {len(vector)} dimensions, "
                f"but {self.dimensions} were configured."
            )

        norm = math.sqrt(sum(v * v for v in vector))
        return [float(v) / norm for v in vector] if norm else [float(v) for v in vector]
