"""What actually ran: a short in-memory log of AI/ML operations.

GOD MODE is supposed to show real execution, which means something has to
record it. Every model call writes one entry here with the model it used,
how long it took and the token counts the daemon reported.

Deliberately in memory and deliberately small. These are observations about
this process, not user data: they must not accumulate, must not be persisted
alongside the knowledge, and must not become a second place where document
content lives — so no prompts and no passages are recorded, only what ran
and what it cost.

It is a ring buffer, so a long session cannot grow it without bound.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass

CAPACITY = 50


@dataclass(frozen=True)
class Operation:
    operation: str
    model: str | None
    duration_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Algorithm or engine, where it is not a model: "cosine (brute force)",
    # "postgresql full-text", "keyphrase statistics".
    algorithm: str | None = None
    # Free text for a failure reason. Never prompt or document content.
    detail: str | None = None
    at: float = 0.0


_entries: deque[Operation] = deque(maxlen=CAPACITY)
_lock = threading.Lock()


def record(
    operation: str,
    *,
    model: str | None,
    duration_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    algorithm: str | None = None,
    detail: str | None = None,
) -> None:
    entry = Operation(
        operation=operation,
        model=model,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        algorithm=algorithm,
        detail=detail,
        at=time.time(),
    )
    with _lock:
        _entries.append(entry)


def recent(limit: int = 12) -> list[dict]:
    """Most recent first."""
    with _lock:
        entries = list(_entries)
    return [asdict(e) for e in reversed(entries[-limit:])]


def clear() -> None:
    with _lock:
        _entries.clear()
