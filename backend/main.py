import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import APP_NAME, APP_VERSION, CORS_ORIGINS
from .database.connection import engine, log_database_error, safe_database_error

from .api.incidents import router as incidents_router
from .api.detection import router as detection_router
from .api.spill import router as spill_router
from .api.drift import get_drift
from .api.vessels import router as vessels_router
from .api.candidates import router as candidates_router
from .api.casc import router as casc_router
from .api.certificate import router as certificates_router
from .api.audit import router as audit_router


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION
)


# =========================================================
# API ROUTES
# =========================================================

app.include_router(incidents_router)
app.include_router(detection_router)
app.include_router(spill_router)

app.add_api_route(
    "/drift/{incident_id}",
    get_drift,
    methods=["GET"],
    tags=["Drift / Backtrack"]
)

app.include_router(vessels_router)
app.include_router(candidates_router)
app.include_router(casc_router)
app.include_router(certificates_router)
app.include_router(audit_router)


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {
        "status": "online",
        "service": APP_NAME,
        "version": APP_VERSION
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health(response: Response):

    try:

        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return {
            "status": "healthy",
            "database": "connected"
        }

    except Exception as error:
        log_database_error(error)
        response.status_code = 503
        details = safe_database_error(error)
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": details["message"],
            "error_type": details["type"],
            "error_category": details["category"],
        }


# Wrap the full ASGI application so CORS headers are present on unhandled
# 500/503 responses as well as successful responses. Browsers can then report
# backend failures as HTTP errors instead of opaque CORS/network failures.
app = CORSMiddleware(
    app=app,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
