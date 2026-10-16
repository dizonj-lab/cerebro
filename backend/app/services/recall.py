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

import re
import time
import uuid
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.artifact import Artifact
from app.services import ollama, telemetry
from app.services.embeddings import EmbeddingFailed, get_embedding_provider
from app.services.retrieval import get_index

# Enough passages to answer from, few enough to keep the prompt small and
# the local model fast.
MAX_PASSAGES = 6
MAX_PASSAGE_CHARS = 700

# The exact words the product uses when the library cannot answer. Abstaining
# is a result, not a failure, and it must read the same every time.
INSUFFICIENT = "Insufficient evidence in your registered documents to answer that."

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
    started = time.perf_counter()
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

    telemetry.record(
        "recall.retrieve",
        model=f"{provider.name}/{provider.model}",
        duration_ms=int((time.perf_counter() - started) * 1000),
        algorithm="cosine similarity (exact scan)",
        detail=f"{len(matches)} passages, top score "
        + (f"{matches[0].score:.4f}" if matches else "n/a"),
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


def _cite_guard(answer: str, count: int) -> tuple[str, list[int]]:
    """Remove citations to passages that were never retrieved.

    A model asked to cite [1] and [2] will sometimes cite [7] when six
    passages were given. The number is not a mistake to be corrected — there
    is no seventh passage to point at — so the marker is removed rather than
    renumbered, and only the citations that resolve are reported.
    """
    kept: list[int] = []

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if 1 <= index <= count:
            if index not in kept:
                kept.append(index)
            return match.group(0)
        return ""

    cleaned = re.sub(r"\[(\d{1,2})\]", replace, answer)
    # Collapse the space left where a marker was dropped.
    return re.sub(r"\s{2,}", " ", cleaned).strip(), sorted(kept)


def _engine(ai_suggestions: bool) -> tuple[str | None, str | None, str | None]:
    """The local model to answer with, or why there is not one.

    Discovery decides, not configuration: CEREBRO used to need
    CEREBRO_RECALL_LLM=ollama before it would ask a model anything, so an
    unset variable looked exactly like a broken feature. If the daemon is
    running and has a usable model, it is used.
    """
    if not ai_suggestions:
        return None, None, (
            "AI suggestions are switched off in your preferences, so only the "
            "matching passages are shown."
        )

    settings = get_settings()
    if settings.recall_llm == "off":
        return None, None, "Local answering is switched off for this deployment."

    found = ollama.discover()
    if not found.reachable:
        return None, None, (
            "No local model is running, so the matching passages are shown instead. "
            "Start Ollama with `ollama serve` to have them summarised."
        )

    # An explicitly configured model wins, provided it is installed.
    configured = settings.ollama_recall_model
    chosen = next(
        (m for m in found.models if m == configured or m.split(":", 1)[0] == configured),
        None,
    ) or found.chat_model()

    if chosen is None:
        return None, None, (
            "Ollama is running but has no model that can answer. Pull one with "
            "`ollama pull llama3.2`."
        )
    return found.base_url, chosen, None


def _prompt(question: str, passages: list[dict]) -> str:
    rendered = "\n\n".join(
        f"[{p['index']}] ({p['filename']}) {p['excerpt']}" for p in passages
    )
    return _INSTRUCTION.format(question=question, passages=rendered)


def _abstained(answer: str) -> bool:
    """Whether the model said the passages do not answer the question."""
    lowered = answer.lower()
    return any(
        phrase in lowered
        for phrase in (
            "do not contain",
            "does not contain",
            "no information",
            "not mentioned",
            "cannot answer",
            "can't answer",
            "insufficient",
        )
    )


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
            "telemetry": None,
        }

    if not passages:
        # No evidence, so no answer. Abstaining is the honest result;
        # answering from the model's own knowledge is not.
        return {
            "answer": INSUFFICIENT,
            "sources": [],
            "grounded": False,
            "model": None,
            "note": "Only documents you have reviewed and registered are searched.",
            "telemetry": None,
        }

    base_url, model, note = _engine(ai_suggestions)
    if base_url is None or model is None:
        return {
            "answer": None,
            "sources": passages,
            "grounded": True,
            "model": None,
            "note": note,
            "telemetry": None,
        }

    try:
        generated = ollama.generate(
            base_url, model, _prompt(question, passages), operation="recall.answer"
        )
    except ollama.OllamaUnavailable as exc:
        # The passages still stand on their own. There is no cloud fallback.
        return {
            "answer": None,
            "sources": passages,
            "grounded": True,
            "model": None,
            "note": f"{exc} The matching passages are shown instead.",
            "telemetry": None,
        }

    answer, cited = _cite_guard(generated.text, len(passages))
    return {
        "answer": answer,
        "sources": passages,
        "grounded": True,
        "model": generated.model,
        "note": None,
        "cited": cited,
        "abstained": _abstained(answer),
        "telemetry": {
            "model": generated.model,
            "duration_ms": generated.duration_ms,
            "prompt_tokens": generated.prompt_tokens,
            "completion_tokens": generated.completion_tokens,
            "passages": len(passages),
            "top_score": passages[0]["score"],
        },
    }


def ask_stream(
    db: Session,
    owner_id: uuid.UUID,
    *,
    question: str,
    topic: str | None = None,
    ai_suggestions: bool = True,
) -> Iterator[dict]:
    """The same answer, as events: sources first, then words, then a summary.

    Sources are sent before the first word on purpose. The citations are the
    evidence, and they are known as soon as retrieval finishes; showing them
    first means the user can check what the answer is built on while it is
    still being written.
    """
    try:
        passages = _passages(db, owner_id, question, topic=topic)
    except EmbeddingFailed as exc:
        yield {"type": "error", "message": str(exc)}
        return

    yield {"type": "sources", "sources": passages}

    if not passages:
        yield {
            "type": "done",
            "answer": INSUFFICIENT,
            "grounded": False,
            "model": None,
            "note": "Only documents you have reviewed and registered are searched.",
            "abstained": True,
            "cited": [],
            "telemetry": None,
        }
        return

    base_url, model, note = _engine(ai_suggestions)
    if base_url is None or model is None:
        yield {
            "type": "done",
            "answer": None,
            "grounded": True,
            "model": None,
            "note": note,
            "abstained": False,
            "cited": [],
            "telemetry": None,
        }
        return

    collected: list[str] = []
    generation = None
    try:
        for item in ollama.generate_stream(
            base_url, model, _prompt(question, passages), operation="recall.answer"
        ):
            if isinstance(item, str):
                collected.append(item)
                yield {"type": "delta", "text": item}
            else:
                generation = item
    except ollama.OllamaUnavailable as exc:
        yield {
            "type": "done",
            "answer": None,
            "grounded": True,
            "model": None,
            "note": f"{exc} The matching passages are shown instead.",
            "abstained": False,
            "cited": [],
            "telemetry": None,
        }
        return

    # The guard runs on the whole answer, so a citation split across two
    # stream chunks is still checked. The client replaces the streamed text
    # with this one, which is why the final event carries it in full.
    answer, cited = _cite_guard("".join(collected), len(passages))
    yield {
        "type": "done",
        "answer": answer,
        "grounded": True,
        "model": generation.model if generation else model,
        "note": None,
        "abstained": _abstained(answer),
        "cited": cited,
        "telemetry": {
            "model": generation.model if generation else model,
            "duration_ms": generation.duration_ms if generation else None,
            "prompt_tokens": generation.prompt_tokens if generation else None,
            "completion_tokens": generation.completion_tokens if generation else None,
            "passages": len(passages),
            "top_score": passages[0]["score"],
        },
    }
