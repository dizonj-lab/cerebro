"""Recording what AI/ML work cost, and reporting on it.

Two halves. `record` writes one row per operation; everything else reads
those rows back as a report.

The reason this exists separately from `telemetry` is scope: telemetry
answers "what is happening right now" from an in-memory ring, and a report
has to answer "how is this model doing" across days. Neither can do the
other's job.

What is *not* here matters as much. No prompt, no passage, no document text
— a metrics table must not become a second place where knowledge lives. And
no score invented to look complete: where CEREBRO cannot measure something,
the report says so rather than printing a number nobody can defend.
"""
from __future__ import annotations

import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.fragment import FragmentEmbedding, KnowledgeFragment
from app.models.metric import OperationMetric

# Fields enrichment proposes and a human confirms. Author and created_date
# are deliberately absent: no engine may propose them, so there is no
# proposal to score.
SCORED_FIELDS = ("topics", "tags", "people", "organizations", "projects", "technologies")
MAX_ROWS = 500


def record(
    db: Session,
    *,
    owner_id: uuid.UUID,
    kind: str,
    operation: str,
    duration_ms: float,
    model: str | None = None,
    algorithm: str | None = None,
    artifact_id: uuid.UUID | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    status: str = "ok",
    units: dict | None = None,
) -> None:
    """One operation's cost. Never raises: measurement must not break work.

    A metrics write that fails is a lost row. A metrics write that propagates
    is a lost upload, which is the user's actual document. The asymmetry is
    the whole argument for the try.
    """
    try:
        db.add(
            OperationMetric(
                owner_id=owner_id,
                artifact_id=artifact_id,
                kind=kind,
                operation=operation,
                model=model,
                algorithm=algorithm,
                duration_ms=round(float(duration_ms), 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                status=status,
                units=units or {},
            )
        )
        db.flush()
    except Exception:  # noqa: BLE001 - see the docstring
        db.rollback()


def _percentile(values: list[float], fraction: float) -> float | None:
    """A percentile that is honest about small samples.

    Two measurements do not have a 95th percentile worth printing; this
    returns the max instead of interpolating between two points and calling
    the result a tail.
    """
    if not values:
        return None
    if len(values) < 4:
        return round(max(values), 1)
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 1)


def _summary(rows: list[OperationMetric]) -> dict:
    durations = [row.duration_ms for row in rows]
    prompt = [r.prompt_tokens for r in rows if r.prompt_tokens]
    completion = [r.completion_tokens for r in rows if r.completion_tokens]
    failures = sum(1 for r in rows if r.status != "ok")
    return {
        "runs": len(rows),
        "failures": failures,
        "failure_rate": round(failures / len(rows), 3) if rows else None,
        "median_ms": round(statistics.median(durations), 1) if durations else None,
        "p95_ms": _percentile(durations, 0.95),
        "slowest_ms": round(max(durations), 1) if durations else None,
        "total_ms": round(sum(durations), 1) if durations else 0.0,
        "prompt_tokens": sum(prompt) or None,
        "completion_tokens": sum(completion) or None,
    }


def _accuracy(db: Session, owner_id: uuid.UUID) -> dict:
    """How often what a model proposed survived human review.

    This is the only accuracy figure CEREBRO can compute without a separate
    annotation exercise, because the review screen already produces it: a
    human confirms, edits or drops every suggestion as a matter of course.

    Precision is suggestions kept ÷ suggestions offered. Recall is the other
    direction — of everything the user ended up with, how much did the model
    find — and it is the number that catches an engine which proposes two
    safe topics and misses six.

    Counts are reported beside the rates on purpose. With a library of thirty
    documents a percentage implies a population that does not exist.
    """
    artifacts = list(
        db.execute(
            select(Artifact).where(
                Artifact.owner_id == owner_id, Artifact.status == "registered"
            )
        ).scalars()
    )

    per_field: dict[str, dict] = {
        field: {"suggested": 0, "confirmed": 0, "final": 0, "kept": 0} for field in SCORED_FIELDS
    }
    scored_documents = 0

    for artifact in artifacts:
        snapshot = (artifact.provenance or {}).get("suggested_snapshot") or {}
        before = snapshot.get("metadata")
        if not isinstance(before, dict):
            # Registered before the snapshot existed. Excluded rather than
            # guessed at — counting it as a perfect score would be inventing
            # the measurement this whole report exists to avoid.
            continue
        scored_documents += 1
        after = artifact.artifact_metadata or {}
        for field in SCORED_FIELDS:
            proposed = {v.strip().lower() for v in (before.get(field) or []) if isinstance(v, str)}
            final = {v.strip().lower() for v in (after.get(field) or []) if isinstance(v, str)}
            bucket = per_field[field]
            bucket["suggested"] += len(proposed)
            bucket["final"] += len(final)
            bucket["kept"] += len(proposed & final)

    fields = []
    for field, bucket in per_field.items():
        if not bucket["suggested"] and not bucket["final"]:
            continue
        precision = bucket["kept"] / bucket["suggested"] if bucket["suggested"] else None
        recall = bucket["kept"] / bucket["final"] if bucket["final"] else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall and (precision + recall)
            else None
        )
        fields.append(
            {
                "field": field,
                "suggested": bucket["suggested"],
                "kept": bucket["kept"],
                "final": bucket["final"],
                "added_by_user": max(0, bucket["final"] - bucket["kept"]),
                "dropped_by_user": max(0, bucket["suggested"] - bucket["kept"]),
                "precision": round(precision, 3) if precision is not None else None,
                "recall": round(recall, 3) if recall is not None else None,
                "f1": round(f1, 3) if f1 is not None else None,
            }
        )

    suggested_total = sum(f["suggested"] for f in fields)
    kept_total = sum(f["kept"] for f in fields)
    return {
        "scored_documents": scored_documents,
        "unscored_documents": len(artifacts) - scored_documents,
        "fields": fields,
        "precision": round(kept_total / suggested_total, 3) if suggested_total else None,
        "basis": (
            "Suggestions kept at human review, per field. Documents registered "
            "before suggestion snapshots were kept are excluded rather than assumed correct."
        ),
    }


def report(db: Session, owner_id: uuid.UUID, *, days: int = 30) -> dict:
    """Everything the report page draws, in one request."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = list(
        db.execute(
            select(OperationMetric)
            .where(OperationMetric.owner_id == owner_id, OperationMetric.at >= since)
            .order_by(OperationMetric.at.desc())
        ).scalars()
    )

    by_kind: dict[str, list[OperationMetric]] = defaultdict(list)
    for row in rows:
        by_kind[row.kind].append(row)

    # Per model, so a slow one is attributable rather than averaged away.
    by_model: dict[str, list[OperationMetric]] = defaultdict(list)
    for row in rows:
        by_model[row.model or "deterministic (no model)"].append(row)

    ingestion = by_kind.get("ingestion", [])
    pages = sum((r.units or {}).get("pages") or 0 for r in ingestion)
    bytes_in = sum((r.units or {}).get("bytes") or 0 for r in ingestion)

    recall_rows = by_kind.get("recall", [])
    answered = [r for r in recall_rows if (r.units or {}).get("answered")]
    abstained = [r for r in recall_rows if (r.units or {}).get("abstained")]
    cited = sum((r.units or {}).get("citations") or 0 for r in recall_rows)

    fragments = db.scalar(
        select(KnowledgeFragment).where(KnowledgeFragment.owner_id == owner_id).limit(1)
    )
    fragment_count = len(
        list(
            db.execute(
                select(KnowledgeFragment.id).where(KnowledgeFragment.owner_id == owner_id)
            ).scalars()
        )
    )
    vector_count = len(
        list(
            db.execute(
                select(FragmentEmbedding.fragment_id)
                .join(KnowledgeFragment, KnowledgeFragment.id == FragmentEmbedding.fragment_id)
                .where(KnowledgeFragment.owner_id == owner_id)
            ).scalars()
        )
    )

    return {
        "window_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "operations": len(rows),
            "model_calls": sum(1 for r in rows if r.model),
            "deterministic_calls": sum(1 for r in rows if not r.model),
            "total_seconds": round(sum(r.duration_ms for r in rows) / 1000, 1),
            "prompt_tokens": sum(r.prompt_tokens or 0 for r in rows) or None,
            "completion_tokens": sum(r.completion_tokens or 0 for r in rows) or None,
        },
        "stages": [
            {"kind": kind, **_summary(items)}
            for kind, items in sorted(by_kind.items(), key=lambda kv: -len(kv[1]))
        ],
        "models": [
            {"model": model, **_summary(items)}
            for model, items in sorted(by_model.items(), key=lambda kv: -len(kv[1]))
        ],
        "ingestion": {
            **_summary(ingestion),
            "documents": len(ingestion),
            "pages": pages,
            "bytes": bytes_in,
            "ms_per_page": (
                round(sum(r.duration_ms for r in ingestion) / pages, 1) if pages else None
            ),
            "fragments": fragment_count,
            "vectors": vector_count,
            # A fragment without a vector is not searchable semantically.
            # Reported because the gap is invisible otherwise.
            "unvectorised": max(0, fragment_count - vector_count),
            "has_fragments": fragments is not None,
        },
        "recall": {
            **_summary(recall_rows),
            "questions": len(recall_rows),
            "answered": len(answered),
            "abstained": len(abstained),
            # An honest refusal is a correct behaviour, not a failure — but
            # whether each one was *right* needs a human, so the rate is
            # reported and never scored.
            "abstention_rate": (
                round(len(abstained) / len(recall_rows), 3) if recall_rows else None
            ),
            "citations": cited,
            "citations_per_answer": (
                round(cited / len(answered), 2) if answered else None
            ),
        },
        "search": _summary(by_kind.get("search", [])),
        "accuracy": _accuracy(db, owner_id),
        # The raw rows, for anyone who wants to do their own arithmetic.
        "operations": [
            {
                "at": row.at.isoformat(),
                "kind": row.kind,
                "operation": row.operation,
                "model": row.model,
                "algorithm": row.algorithm,
                "duration_ms": row.duration_ms,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "status": row.status,
                "units": row.units or {},
            }
            for row in rows[:MAX_ROWS]
        ],
        "truncated": len(rows) > MAX_ROWS,
    }
