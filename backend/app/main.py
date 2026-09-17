"""CEREBRO API — application entry point."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
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

app.include_router(auth_router)


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
