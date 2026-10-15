"""Embedding providers, selected by configuration.

`hashing` is the default: deterministic, offline, and what the test suite
uses. `ollama` is a learned model running on the user's own machine.

There is deliberately no cloud provider. Adding one would require explicit
user consent per the AI privacy settings, and must never become a fallback
for a local provider that failed.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.embeddings.base import EmbeddingFailed, EmbeddingProvider
from app.services.embeddings.hashing import HashingEmbedder
from app.services.embeddings.ollama import OllamaEmbedder

_provider: EmbeddingProvider | None = None


def build_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "ollama":
        return OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embedding_model,
            dimensions=settings.ollama_embedding_dimensions,
        )
    if settings.embedding_provider == "hashing":
        return HashingEmbedder(dimensions=settings.embedding_dimensions)
    raise ValueError(
        f"Unknown CEREBRO_EMBEDDING_PROVIDER '{settings.embedding_provider}'. "
        "Known providers: hashing, ollama."
    )


def get_embedding_provider() -> EmbeddingProvider:
    """The configured provider, built once per process."""
    global _provider
    if _provider is None:
        _provider = build_provider()
    return _provider


def reset_embedding_provider() -> None:
    """Drop the cached provider. Used by tests."""
    global _provider
    _provider = None


__all__ = [
    "EmbeddingFailed",
    "EmbeddingProvider",
    "HashingEmbedder",
    "OllamaEmbedder",
    "build_provider",
    "get_embedding_provider",
    "reset_embedding_provider",
]
