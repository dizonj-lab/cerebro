"""Knowledge Galaxy and Timeline.

Every route is scoped to the authenticated owner and serves only registered
knowledge. The graph loads progressively: the galaxy route returns clusters,
`expand` returns one cluster's fragments, and details are fetched per node.
"""
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.graph import (
    GalaxyResponse,
    LensRequest,
    LensResponse,
    NodeDetails,
    TimelineResponse,
)
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


@router.post("/lens", response_model=LensResponse)
def lens(current_user: CurrentUser, db: DbSession, body: LensRequest) -> LensResponse:
    """Where a piece of text would sit in the library: a what-if, nothing stored.

    Embedded with the owner's own model and compared with every topic and
    passage, so the answer is in the same space as the Galaxy itself.
    """
    try:
        return LensResponse(**graph.lens(db, current_user.id, body.text.strip()))
    except graph.LensUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The embedding model could not be reached, so the text cannot be placed.",
        ) from exc


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


@router.post("/revalidate")
def revalidate(current_user: CurrentUser, db: DbSession, apply: bool = False) -> dict:
    """Re-run the significance rule over knowledge already confirmed.

    Reports by default and changes nothing: the terms it finds were approved
    by a human, so removing them is an explicit act rather than a side effect
    of asking what is there. `?apply=true` performs it, touching only the
    concept fields and recording what it removed in the artifact's
    provenance. Artifacts, fragments, extractions and source bytes are never
    deleted.
    """
    result = graph.revalidate(db, current_user.id, apply=apply)
    # The route commits, as every other write route here does; the service
    # only flushes. A report commits nothing because it changed nothing.
    if apply:
        db.commit()
    return result
