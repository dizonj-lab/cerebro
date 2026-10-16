"""What actually ran: a short in-memory log of AI/ML operations.

Telemetry is supposed to show real execution, which means something has to
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

import os
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass

CAPACITY = 50


@dataclass(frozen=True)
class Operation:
    operation: str
    model: str | None
    duration_ms: int
    # STARTED | COMPLETED | FAILED. One execution emits a start and an end,
    # tied together by execution_id, so a long run is visible while it runs
    # rather than only after it finishes.
    status: str = "COMPLETED"
    execution_id: str = ""
    stage: str | None = None
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
    status: str = "COMPLETED",
    execution_id: str = "",
    stage: str | None = None,
) -> None:
    entry = Operation(
        operation=operation,
        model=model,
        duration_ms=duration_ms,
        status=status,
        execution_id=execution_id or uuid.uuid4().hex[:8],
        stage=stage,
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


@contextmanager
def execution(operation: str, *, model: str | None = None, algorithm: str | None = None):
    """Bracket an operation with STARTED and COMPLETED or FAILED.

    Yields a dict the body can fill in — token counts, how many things were
    processed — which is written out with the closing event. A failure is
    recorded with its type and message before the exception continues on its
    way: Telemetry's job is to show what happened, including when it broke.
    """
    execution_id = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    record(
        operation,
        model=model,
        duration_ms=0,
        algorithm=algorithm,
        status="STARTED",
        execution_id=execution_id,
    )
    context: dict = {}
    try:
        yield context
    except Exception as exc:
        record(
            operation,
            model=context.get("model", model),
            duration_ms=int((time.perf_counter() - started) * 1000),
            algorithm=algorithm,
            status="FAILED",
            execution_id=execution_id,
            detail=f"{type(exc).__name__}: {exc}"[:200],
        )
        raise
    record(
        operation,
        model=context.get("model", model),
        duration_ms=int((time.perf_counter() - started) * 1000),
        algorithm=context.get("algorithm", algorithm),
        prompt_tokens=context.get("prompt_tokens"),
        completion_tokens=context.get("completion_tokens"),
        detail=context.get("detail"),
        status="COMPLETED",
        execution_id=execution_id,
    )


def resources() -> dict:
    """What this process is actually using, or N/A where it cannot be known.

    Read from /proc, which is the container's own view — no agent, no
    monitoring platform. GPU figures are reported as unavailable rather than
    guessed: nothing here can see one, and a fabricated utilisation bar in a
    window reporting measurements would be exactly the wrong thing to invent.
    """
    out: dict = {
        "cpu_percent": None,
        "memory_mb": None,
        "memory_percent": None,
        "gpu_percent": None,
        "gpu_memory_mb": None,
        "source": "/proc",
    }
    try:
        with open("/proc/self/status") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    out["memory_mb"] = round(int(line.split()[1]) / 1024, 1)
                    break
    except OSError:
        pass

    try:
        with open("/proc/meminfo") as handle:
            info = {}
            for line in handle:
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0])
        total = info.get("MemTotal")
        available = info.get("MemAvailable")
        if total and available is not None:
            out["memory_percent"] = round((total - available) / total * 100, 1)
    except (OSError, ValueError, IndexError):
        pass

    try:
        out["cpu_percent"] = round(os.getloadavg()[0] / (os.cpu_count() or 1) * 100, 1)
        out["cpu_note"] = "1-minute load average over available cores"
    except OSError:
        pass

    return out
