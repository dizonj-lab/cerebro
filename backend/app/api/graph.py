"""Knowledge Galaxy and Timeline.

Every route is scoped to the authenticated owner and serves only registered
knowledge. The graph loads progressively: the galaxy route returns clusters,
`expand` returns one cluster's fragments, and details are fetched per node.
"""
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.graph import GalaxyResponse, NodeDetails, TimelineResponse
from app.services import graph

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("", response_model=GalaxyResponse)
def galaxy(current_user: CurrentUser, db: DbSession) -> GalaxyResponse:
    return GalaxyResponse(**graph.galaxy(db, current_user.id))


@router.get("/expand", response_model=GalaxyResponse)
def expand(
    current_user: CurrentUser,
    db: DbSession,
    topic: str = Query(min_length=1, max_length=200),
) -> GalaxyResponse:
    """One cluster's fragments. Called when a cluster is opened, not before."""
    return GalaxyResponse(**graph.expand(db, current_user.id, topic))


@router.get("/node", response_model=NodeDetails)
def node(
    current_user: CurrentUser,
    db: DbSession,
    id: str = Query(min_length=1, max_length=200),
) -> NodeDetails:
    details = graph.node_details(db, current_user.id, id)
    if details is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return NodeDetails(**details)


@router.get("/timeline", response_model=TimelineResponse)
def timeline(current_user: CurrentUser, db: DbSession) -> TimelineResponse:
    return TimelineResponse(**graph.timeline(db, current_user.id))
