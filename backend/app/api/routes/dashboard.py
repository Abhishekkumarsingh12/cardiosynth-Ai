from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ECGAnalysis, ECGUpload, User
from app.schemas.dashboard import DashboardSummary, RecentAnalysisRow

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
def summary(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_uploads = db.query(func.count(ECGUpload.id)).filter(ECGUpload.user_id == current.id).scalar() or 0
    total_analyses = db.query(func.count(ECGAnalysis.id)).filter(ECGAnalysis.user_id == current.id).scalar() or 0

    last = (
        db.query(ECGAnalysis)
        .filter(ECGAnalysis.user_id == current.id)
        .order_by(ECGAnalysis.created_at.desc())
        .first()
    )
    label = None
    last_updated = None
    if last:
        last_updated = last.created_at
        if last.prediction_result:
            label = last.prediction_result.get("label")

    return DashboardSummary(
        total_uploads=int(total_uploads),
        total_analyses=int(total_analyses),
        last_prediction_label=label,
        last_updated=last_updated,
    )


@router.get("/recent-analyses", response_model=list[RecentAnalysisRow])
def recent_analyses(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(ECGAnalysis, ECGUpload)
        .join(ECGUpload, ECGUpload.id == ECGAnalysis.upload_id)
        .filter(ECGAnalysis.user_id == current.id)
        .order_by(ECGAnalysis.created_at.desc())
        .limit(20)
        .all()
    )
    out: list[RecentAnalysisRow] = []
    for a, u in rows:
        pred = a.prediction_result or {}
        out.append(
            RecentAnalysisRow(
                analysis_id=a.id,
                upload_id=u.id,
                filename=u.original_name or u.filename,
                created_at=a.created_at,
                label=pred.get("label"),
                confidence=pred.get("confidence"),
                mock=pred.get("mock"),
            )
        )
    return out
