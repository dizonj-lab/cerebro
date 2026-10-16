"""CEREBRO API — application entry point."""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.artifacts import router as artifacts_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.graph import router as graph_router
from app.api.ml import router as ml_router
from app.api.profile import router as profile_router
from app.api.recall import router as recall_router
from app.api.search import router as search_router
from app.api.timeline import router as timeline_router
from app.core.config import get_settings
from app.db.session import engine

logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="CEREBRO API",
    description="Digital Knowledge Twin — Capture, Connect, Reason, Recall",
    version="0.1.0",
)

# Credentialed requests carry the session cookie, so the origin list must be
# explicit — "*" is not permitted alongside allow_credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Answer an unhandled failure in the shape the client can read.

    FastAPI's default is a plain-text "Internal Server Error", which the
    browser client cannot parse — so every bug of this class reached the user
    as a bare "Something went wrong." with nothing to go on and nothing to
    correlate against the log. This returns JSON with a reference the same
    log line carries, so the next one names itself.

    The message deliberately says nothing about the failure: the detail is
    in the log, not in the browser, because it can name server paths and
    query values.
    """
    reference = uuid.uuid4().hex[:8]
    logger.exception(
        "Unhandled error %s on %s %s", reference, request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "CEREBRO hit an unexpected error. The API log has the details, "
                f"under reference {reference}."
            ),
            "reference": reference,
        },
    )


app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(artifacts_router)
app.include_router(dashboard_router)
app.include_router(graph_router)
app.include_router(ml_router)
app.include_router(recall_router)
app.include_router(search_router)
app.include_router(timeline_router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness/readiness probe, including database reachability."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "up"
    except Exception:
        logger.exception("health check: database unreachable")
        database = "down"
    return {"status": "ok" if database == "up" else "degraded", "database": database}
