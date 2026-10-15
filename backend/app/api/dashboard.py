"""Dashboard overview.

One request serves the whole dashboard, so the page makes a single call
rather than six. Every aggregate is scoped to the authenticated user; the
owner comes from the session and never from the request.
"""
from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.dashboard import DashboardOverview
from app.services import dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOverview)
def overview(current_user: CurrentUser, db: DbSession) -> DashboardOverview:
    return DashboardOverview(**dashboard.overview(db, current_user.id))
