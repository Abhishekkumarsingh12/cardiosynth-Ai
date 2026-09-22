"""
Startup banner and /build-info payloads.

Set API_ADVERTISED_HOST / API_ADVERTISED_PORT to match uvicorn so logged URLs are correct.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import FastAPI

from app.config import get_settings
from app.services.prediction_service import get_classifier_debug_snapshot
from app.version_info import APP_VERSION, BUILD_ID

log = logging.getLogger("cardiosynth.startup")


def advertised_base_url() -> str:
    s = get_settings()
    return f"http://{s.api_advertised_host}:{s.api_advertised_port}"


def log_startup_banner(app: FastAPI) -> None:
    """Call once after classifier load — makes PID, port hint, and URLs obvious in logs."""
    settings = get_settings()
    dbg = get_classifier_debug_snapshot()
    base = advertised_base_url()
    pid = os.getpid()
    top = _top_level_paths(app)

    log.info("=" * 66)
    log.info(
        "CARDIOSYNTH BACKEND START | name=%s | build=%s | version=%s | pid=%s",
        settings.app_name,
        BUILD_ID,
        APP_VERSION,
        pid,
    )
    log.info(
        "Advertised URL base: %s (set API_ADVERTISED_HOST/PORT to match uvicorn --host/--port)",
        base,
    )
    log.info(
        "Classifier | path=%s | weights_exist=%s | model_loaded=%s | mock_inference=%s",
        dbg.get("resolved_model_path"),
        dbg.get("exists"),
        dbg.get("model_loaded"),
        dbg.get("mock_enabled"),
    )
    log.info("Docs %s/docs | Health %s/health | Debug model %s/debug/model | Build info %s/build-info", base, base, base, base)
    log.info(
        "Route check: /debug/model registered=%s | If another process on :8000 returns 404 for /debug/model, stop the old uvicorn.",
        "/debug/model" in top,
    )
    log.info("=" * 66)


def root_welcome_payload() -> Dict[str, Any]:
    settings = get_settings()
    base = advertised_base_url()
    return {
        "app": settings.app_name,
        "version": APP_VERSION,
        "build_id": BUILD_ID,
        "message": (
            "CardioSynth API — this JSON confirms this process includes /debug/model and /build-info. "
            "If you expected different behavior, verify you are not hitting an old uvicorn on the same port."
        ),
        "urls": {
            "docs": f"{base}/docs",
            "health": f"{base}/health",
            "debug_model": f"{base}/debug/model",
            "build_info": f"{base}/build-info",
            "openapi_json": f"{base}/openapi.json",
        },
    }


def _top_level_paths(app: FastAPI) -> List[str]:
    out: List[str] = []
    for r in app.routes:
        p = getattr(r, "path", None)
        if isinstance(p, str) and p:
            out.append(p)
    return sorted(set(out))


def get_build_info(app: FastAPI) -> Dict[str, Any]:
    settings = get_settings()
    dbg = get_classifier_debug_snapshot()
    top = _top_level_paths(app)
    openapi_paths: List[str] = []
    try:
        openapi_paths = sorted(app.openapi().get("paths", {}).keys())
    except Exception:
        pass
    return {
        "app_name": settings.app_name,
        "version": APP_VERSION,
        "build_id": BUILD_ID,
        "pid": os.getpid(),
        "advertised_base_url": advertised_base_url(),
        "api_advertised_host": settings.api_advertised_host,
        "api_advertised_port": settings.api_advertised_port,
        "debug_model_route_registered": "/debug/model" in top,
        "top_level_paths": top,
        "openapi_path_count": len(openapi_paths),
        "openapi_paths_sample": openapi_paths[:50],
        "classifier": dbg,
    }
