"""The Performance Report: what the models and algorithms actually cost.

One route, because the page draws one picture. Everything is scoped to the
authenticated owner — these are measurements of someone's own library, and
another person's costs are not theirs to read.
"""
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.services import metrics

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("")
def report(
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    return metrics.report(db, current_user.id, days=days)
