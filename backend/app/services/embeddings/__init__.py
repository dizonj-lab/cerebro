"""Embedding providers, selected by configuration or by what is installed.

`auto` is the default: a pretrained embedder from the local Ollama daemon
when one is installed, the deterministic hashing embedder when it is not.
`hashing` and `ollama` pin the choice; the test suite pins hashing so its
vectors are reproducible.

Provider, model and width travel with every vector and search filters on all
three, so **switching provider orphans the vectors written under the old
one**. Under `auto` that can happen because a daemon was not running, which
is why the active provider and the count of fragments missing a vector for it
are reported by /api/ml/status and fixable with a backfill, rather than
showing up as search quietly returning nothing.

There is deliberately no cloud provider. Adding one would require explicit
user consent per the AI privacy settings, and must never become a fallback
for a local provider that failed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.services.embeddings.base import EmbeddingFailed, EmbeddingProvider
from app.services.embeddings.hashing import HashingEmbedder
from app.services.embeddings.ollama import OllamaEmbedder

if TYPE_CHECKING:
    from app.services.ingest_settings import IngestSettings

_provider: EmbeddingProvider | None = None
# Providers built for a user-pinned model, keyed by what makes them different.
# A provider is a base URL, a model name and a width; two users who pinned the
# same three share one. Bounded by the number of distinct pinned models, not by
# the number of users or requests.
_pinned: dict[tuple[str, str, int, int], EmbeddingProvider] = {}


def build_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "auto":
        return _discovered() or HashingEmbedder(dimensions=settings.embedding_dimensions)
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
        "Known providers: auto, hashing, ollama."
    )


def _discovered() -> EmbeddingProvider | None:
    """A pretrained embedder from the local daemon, if it has one.

    The width comes from the model, not from configuration: a wrong width is
    not a smaller vector, it is a provider that refuses every embedding. Known
    models use the published width; anything else is measured once, by
    embedding a single word, rather than assumed.
    """
    from app.services import ollama as ollama_client

    found = ollama_client.discover()
    if not found.reachable or found.base_url is None:
        return None
    model = found.embedding_model()
    if model is None:
        return None

    family = model.split(":", 1)[0]
    dimensions = ollama_client.EMBEDDING_DIMENSIONS.get(family)
    if dimensions is None:
        probe = OllamaEmbedder(base_url=found.base_url, model=model, dimensions=0)
        try:
            dimensions = len(probe.measure("cerebro"))
        except EmbeddingFailed:
            return None

    return OllamaEmbedder(base_url=found.base_url, model=model, dimensions=dimensions)


def get_embedding_provider() -> EmbeddingProvider:
    """The configured provider, built once per process."""
    global _provider
    if _provider is None:
        _provider = build_provider()
    return _provider


def provider_for(settings: IngestSettings) -> EmbeddingProvider:
    """The provider for one owner's resolved settings.

    A user who pinned no model gets the deployment's provider, built once per
    process as before. A user who pinned one gets an embedder for exactly that
    model and width: pinning is the whole point, so it is not second-guessed
    against what the daemon happens to have discovered. The width comes with
    it, because a wrong width is not a smaller vector — it is a provider that
    refuses every embedding.

    Both paths write provider, model and width onto every vector, so the two
    users' vectors never mix in a search.
    """
    default = get_embedding_provider()
    if settings.embedding_model is None:
        return default

    dimensions = settings.embedding_dimensions
    if not dimensions:
        # Nothing stated and nothing published for this family: measure it
        # once rather than guess, same as discovery does.
        dimensions = 0

    base_url = getattr(default, "base_url", None) or get_settings().ollama_base_url
    limit = settings.context_limit
    key = (base_url, settings.embedding_model, dimensions, limit)
    found = _pinned.get(key)
    if found is not None:
        return found

    built = OllamaEmbedder(
        base_url=base_url,
        model=settings.embedding_model,
        dimensions=dimensions,
        context_limit=limit,
    )
    if not dimensions:
        # measure() raises EmbeddingFailed if the model cannot be reached,
        # which is the right error for the caller: nothing is cached and the
        # next request tries again rather than being stuck with a bad width.
        built = OllamaEmbedder(
            base_url=base_url,
            model=settings.embedding_model,
            dimensions=len(built.measure("cerebro")),
            context_limit=limit,
        )
        key = (base_url, settings.embedding_model, built.dimensions, limit)
    _pinned[key] = built
    return built


def reset_embedding_provider() -> None:
    """Drop the cached providers. Used by tests, and when settings change."""
    global _provider
    _provider = None
    _pinned.clear()


__all__ = [
    "EmbeddingFailed",
    "EmbeddingProvider",
    "HashingEmbedder",
    "OllamaEmbedder",
    "build_provider",
    "get_embedding_provider",
    "provider_for",
    "reset_embedding_provider",
]
