"""
CardioSynth AI HTTP API.

Startup: see README "Run backend cleanly" — free port 8000 before uvicorn so an old process
cannot answer /health without /debug/model.

Classifier: strict mode by default (ENABLE_MOCK_INFERENCE=false) → HTTP 503 when model unavailable.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.api.routes import register_routes
from app.services.classifier_bootstrap import ensure_classifier_model
from app.services.prediction_service import get_classifier_debug_snapshot, startup_load_ecg_classifier
from app.startup_banner import get_build_info, log_startup_banner, root_welcome_payload
from app.api.routes.realtime import ws_router as realtime_ws_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_classifier_model()
    startup_load_ecg_classifier()
    log_startup_banner(app)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api")
    register_routes(api)
    app.include_router(api)
    # Root-level WebSocket route (no /api prefix) for monitor compatibility:
    # ws://127.0.0.1:8000/ws/ecg-stream/{analysis_id}
    app.include_router(realtime_ws_router)

    @app.get("/", include_in_schema=False)
    def root_welcome():
        """JSON welcome — confirms this build (includes /debug/model)."""
        return JSONResponse(root_welcome_payload())

    @app.get("/health")
    def health():
        return {"status": "ok", "app": settings.app_name}

    @app.get("/debug/model", include_in_schema=False)
    def debug_classifier_model():
        """Classifier path, file presence, load state (always registered in this project)."""
        return get_classifier_debug_snapshot()

    @app.get("/build-info", include_in_schema=False)
    def build_info():
        """Build id, route summary, classifier snapshot, /debug/model registration check."""
        return get_build_info(app)

    return app


app = create_app()
