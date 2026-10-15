"""Enrichment, composed in order of authority.

    document metadata  ->  local language model  ->  statistics

The order is the point. What the document asserts about itself can never be
overwritten by a model, and the statistical fallbacks only fill what is still
empty. Author and creation date are reachable by the first stage alone.

A language model runs only when all of this holds:

* the user has AI suggestions enabled in their preferences;
* `CEREBRO_ENRICHMENT_LLM` names a configured local engine;
* that engine is reachable.

Nothing here sends content to a cloud service, and a local model that fails
is not replaced by one that would — enrichment simply falls back to the
deterministic engine, which is also local. Processing mode is never switched
silently: a cloud engine does not exist, so there is nothing to switch to.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.services.artifacts.enrichment.base import Enrichment, EnrichmentEngine
from app.services.artifacts.enrichment.deterministic import DeterministicEnricher
from app.services.artifacts.enrichment.llm import OllamaEnricher


def _llm_engine() -> EnrichmentEngine | None:
    settings = get_settings()
    if settings.enrichment_llm == "ollama":
        return OllamaEnricher(
            base_url=settings.ollama_base_url, model=settings.ollama_enrichment_model
        )
    return None


def llm_available() -> bool:
    """Whether a local model is configured. Says nothing about reachability."""
    return _llm_engine() is not None


def enrich(
    *,
    text: str,
    properties: dict,
    filename: str,
    ai_suggestions: bool = True,
    use_llm: bool = False,
) -> Enrichment:
    """Suggestions for a human to confirm. Nothing here establishes a value.

    `use_llm` is off by default because a local model takes tens of seconds
    on a laptop, and an upload must not block on it. Upload runs the
    deterministic engine; the model is asked when the user explicitly asks
    for it at review.
    """
    deterministic = DeterministicEnricher()
    result = deterministic.from_properties(properties=properties)

    if use_llm:
        engine = _llm_engine()
        if engine is None:
            result.notes.append(
                "No local model is configured. Set CEREBRO_ENRICHMENT_LLM=ollama "
                "to enable one."
            )
        elif not ai_suggestions:
            # The user's own setting wins. Nothing is run behind their back.
            result.notes.append(
                "AI suggestions are switched off in your preferences, so the local "
                "model was not asked."
            )
        else:
            result = result.merge(
                engine.enrich(text=text, properties=properties, filename=filename)
            )

    return result.merge(
        deterministic.from_statistics(text=text, properties=properties, filename=filename)
    )


__all__ = [
    "DeterministicEnricher",
    "llm_available",
    "Enrichment",
    "EnrichmentEngine",
    "OllamaEnricher",
    "enrich",
]
