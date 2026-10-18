"""Enrichment as a background job, one or two at a time.

Enrichment used to run inside the HTTP request that asked for it. That one
decision caused three separate complaints: the request blocked for minutes,
there was nowhere to report progress to, and navigating away aborted the
fetch and abandoned the work. Moving it here fixes all three, because the
job no longer belongs to a request at all.

**Why one or two and not all of them.** A local model is a single daemon on
somebody's laptop. Asking it to enrich twenty documents at once does not
make twenty documents arrive sooner — it makes all twenty slow, the machine
hot, and the first one no longer finishes early enough to be reviewed while
the rest run. So the queue admits one by default and a second only when the
evidence says the machine can take it: a recent job that finished quickly.
Everything else waits, visibly, in order.

**Why the state is on the row.** Progress in memory dies with the process
and cannot be polled from another page. On the artifact it survives a
restart, and the Library can show a queue that is really there.

Claiming uses `FOR UPDATE SKIP LOCKED`, so two workers — in this process or
another — can never take the same artifact.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact

logger = logging.getLogger(__name__)

# The ceiling. Two is a deliberate maximum rather than a starting point: see
# the module docstring.
MAX_WORKERS = 2
# A job that finished in under this had room to spare, so a second worker is
# unlikely to make either of them unbearable.
FAST_JOB_SECONDS = 45.0
# How long a worker sleeps when it finds nothing to do.
IDLE_SECONDS = 1.0
# A job running longer than this is assumed abandoned — the process that
# claimed it died — and becomes claimable again.
STALE_AFTER_SECONDS = 1800

_lock = threading.Lock()
_workers: list[threading.Thread] = []
_last_durations: list[float] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_of(artifact: Artifact) -> dict:
    return artifact.enrichment_job or {}


def enqueue(artifact: Artifact, *, ai_suggestions: bool) -> dict:
    """Mark an artifact as waiting for enrichment. The caller commits."""
    job = {
        "status": "queued",
        "progress": 0,
        "total": None,
        "queued_at": _now(),
        "started_at": None,
        "finished_at": None,
        "error": None,
        "model": None,
        "ai_suggestions": ai_suggestions,
    }
    artifact.enrichment_job = job
    return job


def _queue_depth(db: Session) -> int:
    return len(
        list(
            db.execute(
                select(Artifact.id).where(
                    Artifact.enrichment_job["status"].astext == "queued"
                )
            ).scalars()
        )
    )


def _desired_workers(db: Session) -> int:
    """One, or two when there is both a backlog and evidence of headroom.

    Deliberately not a thread pool sized to the CPU. The bottleneck is a
    single local model, and the question is not how many cores exist but
    whether the last job came back quickly enough that running two would
    still leave each of them usable.
    """
    if _queue_depth(db) <= 1:
        return 1
    with _lock:
        recent = list(_last_durations[-3:])
    if recent and sum(recent) / len(recent) <= FAST_JOB_SECONDS:
        return MAX_WORKERS
    return 1


def _claim(db: Session) -> Artifact | None:
    """Take the oldest queued artifact, or reclaim one whose worker died."""
    stale_before = time.time() - STALE_AFTER_SECONDS
    candidates = db.execute(
        select(Artifact)
        .where(Artifact.enrichment_job["status"].astext.in_(("queued", "running")))
        .order_by(Artifact.created_at)
        .with_for_update(skip_locked=True)
    ).scalars()

    for artifact in candidates:
        job = artifact.enrichment_job or {}
        if job.get("status") == "running":
            started = job.get("started_at")
            try:
                age = datetime.fromisoformat(started).timestamp() if started else 0
            except ValueError:
                age = 0
            if age > stale_before:
                continue  # Someone is working on it.
        artifact.enrichment_job = {
            **job,
            "status": "running",
            "started_at": _now(),
            "progress": 0,
        }
        db.flush()
        return artifact
    return None


def _run_one(db: Session, artifact: Artifact) -> None:
    from app.services.artifacts import service

    owner_id = artifact.owner_id
    artifact_id = artifact.id
    job = artifact.enrichment_job or {}
    started = time.perf_counter()

    def progress(done: int, total: int, model: str | None) -> None:
        # Written through its own session so the number is visible to the
        # page polling it, rather than sitting in an uncommitted transaction
        # until the whole job ends.
        from app.db.session import SessionLocal

        with SessionLocal() as side:
            row = side.get(Artifact, artifact_id)
            if row is None:
                return
            row.enrichment_job = {
                **(row.enrichment_job or {}),
                "progress": done,
                "total": total,
                "model": model,
            }
            side.commit()

    try:
        result = service.suggest_with_model(
            db,
            artifact,
            ai_suggestions=bool(job.get("ai_suggestions", True)),
            on_progress=progress,
            # Without this the job computed suggestions and discarded them.
            # The request that used to carry them back no longer exists, so
            # storing is the only way they reach the review screen at all —
            # and the symptom was exact: fields deterministic enrichment had
            # already filled at upload looked fine, while the ones only a
            # model proposes stayed empty for ever.
            store=True,
        )
        # `suggest_with_model` returns a dict. Reading it with getattr
        # silently produced empty notes and a null model, which is how "No
        # local model is configured" stopped reaching the review screen.
        artifact.enrichment_job = {
            **(artifact.enrichment_job or {}),
            "status": "done",
            "finished_at": _now(),
            "model": result.get("model"),
            "ai_used": bool(result.get("ai_used")),
            "notes": list(result.get("notes") or []),
        }
        # The job's own result is committed first, and measured second.
        # The other order cost an afternoon: `metrics.record` rolls back on
        # failure to protect the caller's work, and rolling back here threw
        # away the job state written in the same transaction — so a finished
        # job reported no notes and no model.
        db.commit()
        _record(
            db,
            owner_id=owner_id,
            artifact_id=artifact_id,
            duration_ms=(time.perf_counter() - started) * 1000,
            result=result,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - a failed job must say so, not vanish
        logger.exception("Enrichment job failed for artifact %s", artifact_id)
        db.rollback()
        row = db.get(Artifact, artifact_id)
        if row is not None:
            row.enrichment_job = {
                **(row.enrichment_job or {}),
                "status": "failed",
                "finished_at": _now(),
                "error": str(exc)[:300],
            }
            db.commit()
    finally:
        with _lock:
            _last_durations.append(time.perf_counter() - started)
            del _last_durations[:-5]
        del owner_id


def _record(db: Session, *, owner_id, artifact_id, duration_ms: float, result: dict) -> None:
    from app.services import metrics

    metrics.record(
        db,
        owner_id=owner_id,
        kind="enrichment",
        operation="enrichment.job",
        duration_ms=duration_ms,
        model=result.get("model"),
        algorithm="local model proposes, human confirms",
        artifact_id=artifact_id,
        status="ok" if result.get("ai_used") else "fallback",
        units={
            "suggested": sum(
                len(v) if isinstance(v, list) else 1
                for v in (result.get("suggestions") or {}).values()
            ),
            "notes": len(result.get("notes") or []),
            "ai_used": bool(result.get("ai_used")),
        },
    )


def _loop(index: int) -> None:
    from app.db.session import SessionLocal

    while True:
        try:
            with SessionLocal() as db:
                # Worker 2 stands down whenever the evidence stops supporting
                # it, so a slow machine converges back to one at a time.
                if index >= _desired_workers(db):
                    db.rollback()
                    time.sleep(IDLE_SECONDS * 3)
                    continue
                artifact = _claim(db)
                if artifact is None:
                    db.rollback()
                    time.sleep(IDLE_SECONDS)
                    continue
                db.commit()
                _run_one(db, artifact)
        except Exception:  # noqa: BLE001 - a worker that dies stops the queue
            logger.exception("Enrichment worker %s recovered from an error", index)
            time.sleep(IDLE_SECONDS * 5)


def start() -> None:
    """Start the workers once, lazily, on the first enqueue.

    Lazy rather than at import: a test suite and a migration both import the
    application, and neither should quietly start background threads that
    reach for a model.
    """
    with _lock:
        alive = [t for t in _workers if t.is_alive()]
        _workers[:] = alive
        for index in range(len(alive), MAX_WORKERS):
            thread = threading.Thread(
                target=_loop, args=(index,), name=f"cerebro-enrichment-{index}", daemon=True
            )
            thread.start()
            _workers.append(thread)


def pending(db: Session, owner_id: uuid.UUID) -> list[dict]:
    """This owner's jobs that are queued or running, oldest first."""
    rows = db.execute(
        select(Artifact)
        .where(
            Artifact.owner_id == owner_id,
            Artifact.enrichment_job["status"].astext.in_(("queued", "running")),
        )
        .order_by(Artifact.created_at)
    ).scalars()
    out = []
    for position, artifact in enumerate(rows):
        job = artifact.enrichment_job or {}
        out.append(
            {
                "artifact_id": str(artifact.id),
                "filename": artifact.filename,
                "status": job.get("status"),
                "progress": job.get("progress") or 0,
                "total": job.get("total"),
                "model": job.get("model"),
                # Its place in the line, so "waiting" has a number attached.
                "position": position,
            }
        )
    return out
