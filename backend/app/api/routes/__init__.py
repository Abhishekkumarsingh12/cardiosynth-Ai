from fastapi import APIRouter

from app.api.routes import assistant, auth, dashboard, ecg, realtime, reports, synthetic_playground, uploads


def register_routes(api: APIRouter) -> None:
    api.include_router(auth.router, prefix="/auth", tags=["auth"])
    api.include_router(ecg.router, prefix="/ecg", tags=["ecg"])
    api.include_router(realtime.router, prefix="/ecg", tags=["realtime"])
    api.include_router(synthetic_playground.router, prefix="/synthetic", tags=["synthetic"])
    api.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
    api.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
    api.include_router(reports.router, prefix="/reports", tags=["reports"])
    api.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
