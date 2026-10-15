"""Assisted Recollection: answers grounded in the user's own library.

Retrieval first, always. The question is embedded and matched against the
owner's registered fragments; those passages are the only material an answer
may use. A local model is asked to phrase an answer from them, and when no
model is available the passages themselves are returned — which is still a
useful answer, just not a sentence.

Three rules hold:

* **Only registered knowledge is retrieved.** Nothing awaiting review is
  searched, quoted or cited.
* **Every answer carries its sources**, down to the page or slide. An answer
  without passages behind it is not produced at all; the service says it
  found nothing instead.
* **Nothing leaves the CEREBRO environment.** The model runs locally through
  Ollama. There is no cloud path, and a failing local model does not become
  one — it falls back to returning the passages.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.artifact import Artifact
from app.services.embeddings import EmbeddingFailed, get_embedding_provider
from app.services.retrieval import get_index

# Enough passages to answer from, few enough to keep the prompt small and
# the local model fast.
MAX_PASSAGES = 6
MAX_PASSAGE_CHARS = 700
_TIMEOUT_SECONDS = 120

_INSTRUCTION = """You answer strictly from the passages provided. They come \
from the user's own documents.

Rules:
- Use only the passages. If they do not contain the answer, say so plainly.
- Never add facts from your own knowledge.
- Cite the passages you used by their number, like [1] or [2].
- Be concise: at most four sentences.

Question: {question}

Passages:
{passages}

Answer:"""


def _passages(db: Session, owner_id: uuid.UUID, query: str, *, topic: str | None) -> list[dict]:
    """The owner's registered fragments most like the question."""
    provider = get_embedding_provider()
    # A selected cluster is extra context for the query, not a filter: the
    # user may be asking about something adjacent to what they clicked.
    enriched = f"{topic}. {query}" if topic else query
    vector = provider.embed([enriched])[0]

    matches = get_index().search(
        db,
        owner_id=owner_id,
        vector=vector,
        provider=provider.name,
        model=provider.model,
        dimensions=provider.dimensions,
        limit=MAX_PASSAGES,
    )

    if not matches:
        return []

    titles = dict(
        db.execute(
            select(Artifact.id, Artifact.artifact_metadata).where(
                Artifact.id.in_([m.artifact_id for m in matches])
            )
        ).all()
    )

    return [
        {
            "index": i + 1,
            "fragment_id": str(match.fragment_id),
            "artifact_id": str(match.artifact_id),
            "filename": match.artifact_filename,
            "title": (titles.get(match.artifact_id) or {}).get("title")
            or match.artifact_title,
            "source_location": match.source_location,
            "excerpt": match.content[:MAX_PASSAGE_CHARS],
            "score": round(match.score, 4),
        }
        for i, match in enumerate(matches)
    ]


def ask(
    db: Session,
    owner_id: uuid.UUID,
    *,
    question: str,
    topic: str | None = None,
    ai_suggestions: bool = True,
) -> dict:
    """Answer a question from the library, or say why it cannot."""
    try:
        passages = _passages(db, owner_id, question, topic=topic)
    except EmbeddingFailed as exc:
        return {
            "answer": str(exc),
            "sources": [],
            "grounded": False,
            "model": None,
            "note": "The question could not be matched against your library.",
        }

    if not passages:
        # No evidence, so no answer. Saying "I don't know" is the honest
        # result; inventing one from the model's own knowledge is not.
        return {
            "answer": "Nothing in your registered documents matches that question.",
            "sources": [],
            "grounded": False,
            "model": None,
            "note": "Only documents you have reviewed and registered are searched.",
        }

    settings = get_settings()
    if settings.recall_llm != "ollama" or not ai_suggestions:
        return {
            "answer": None,
            "sources": passages,
            "grounded": True,
            "model": None,
            "note": (
                "These are the passages from your library that match. Set "
                "CEREBRO_RECALL_LLM=ollama to have a local model summarise them."
                if settings.recall_llm != "ollama"
                else "AI suggestions are switched off in your preferences, so only "
                "the matching passages are shown."
            ),
        }

    answer = _ask_model(
        settings.ollama_base_url, settings.ollama_recall_model, question, passages
    )
    if answer is None:
        return {
            "answer": None,
            "sources": passages,
            "grounded": True,
            "model": None,
            "note": (
                f"The local model '{settings.ollama_recall_model}' could not be "
                "reached, so the matching passages are shown instead."
            ),
        }

    return {
        "answer": answer,
        "sources": passages,
        "grounded": True,
        "model": settings.ollama_recall_model,
        "note": None,
    }


def _ask_model(base_url: str, model: str, question: str, passages: list[dict]) -> str | None:
    rendered = "\n\n".join(
        f"[{p['index']}] ({p['filename']}) {p['excerpt']}" for p in passages
    )
    payload = json.dumps(
        {
            "model": model,
            "prompt": _INSTRUCTION.format(question=question, passages=rendered),
            "stream": False,
            # Deterministic, so the same question over the same library
            # answers the same way.
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - fixed http scheme, local daemon
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    text = body.get("response")
    if not isinstance(text, str) or not text.strip():
        return None
    return " ".join(text.split())[:2000]
