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
    """The local model to enrich with, chosen from what is installed.

    "off" pins deterministic enrichment. "ollama" and "auto" both ask the
    daemon: an explicitly configured model is used when it is installed,
    otherwise the best installed one. Requiring a model to be named in
    configuration is how this feature came to look broken on a machine where
    Ollama was running the whole time.
    """
    settings = get_settings()
    if settings.enrichment_llm == "off":
        return None

    from app.services import ollama as ollama_client

    found = ollama_client.discover()
    if not found.reachable or found.base_url is None:
        return None

    configured = settings.ollama_enrichment_model
    model = next(
        (m for m in found.models if m == configured or m.split(":", 1)[0] == configured),
        None,
    ) or found.chat_model()
    if model is None:
        return None
    return OllamaEnricher(base_url=found.base_url, model=model)


def llm_available() -> bool:
    """Whether a local model is reachable and installed for enrichment."""
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
