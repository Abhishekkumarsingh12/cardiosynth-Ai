from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, Optional

import logging

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ECGAnalysis, ECGUpload, SyntheticECG, User
from app.schemas.ecg import AnalysisDetail, SyntheticOut
from app.services.analysis_cleanup import delete_analysis_bundle
from app.core.classifier_errors import ClassifierUnavailableError
from app.services import ecg_preprocessing
from app.services.chat_assistant_service import guidance_summary_plain_for_pdf
from app.services.ecg_explanation_service import build_explanation_payload, merge_class_index_into_prediction
from app.services.ecg_preprocessing_service import prepare_for_classifier
from app.services.pdf_report_service import build_analysis_pdf_bytes
from app.services.risk_score_service import compute_risk_assessment, enrich_prediction_dict
from app.utils.csv_ecg import CSVValidationError, parse_ecg_csv
from app.config import get_settings

router = APIRouter()
log = logging.getLogger(__name__)


def _status_from_prediction(pred: Optional[dict]) -> str:
    if not pred:
        return "failed"
    if pred.get("mock") is True:
        return "partial"
    if pred.get("label") in {"model_unavailable", "classifier_not_trained", "inference_error"}:
        return "failed"
    if pred.get("status"):
        return str(pred.get("status"))
    return "success"


@router.get("")
def list_reports(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(ECGAnalysis, ECGUpload)
        .join(ECGUpload, ECGUpload.id == ECGAnalysis.upload_id)
        .filter(ECGAnalysis.user_id == current.id)
        .order_by(ECGAnalysis.created_at.desc())
        .limit(200)
        .all()
    )
    out = []
    for a, u in rows:
        pred = enrich_prediction_dict(a.prediction_result or {}, a.preprocess_metadata)
        out.append(
            {
                "analysis_id": a.id,
                "upload_id": u.id,
                "filename": u.original_name or u.filename,
                "created_at": a.created_at,
                "label": pred.get("label"),
                "confidence": pred.get("confidence"),
                "status": _status_from_prediction(pred),
                "risk_level": pred.get("risk_level"),
                "risk_score": pred.get("risk_score"),
            }
        )
    return out


@router.get("/{analysis_id}", response_model=AnalysisDetail)
def report_detail(analysis_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Report not found")
    u = db.get(ECGUpload, a.upload_id)
    if not u:
        raise HTTPException(status_code=404, detail="Upload missing")

    path = Path(u.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=500, detail="Stored file missing")
    raw = path.read_bytes()
    try:
        samples, _, _ = parse_ecg_csv(io.BytesIO(raw))
    except CSVValidationError:
        samples = []
    pre = ecg_preprocessing.preprocess_signal(samples)
    chart = pre.get("normalized_series") or []

    synth = db.query(SyntheticECG).filter(SyntheticECG.analysis_id == a.id).order_by(SyntheticECG.created_at.desc()).all()

    pred_enriched = enrich_prediction_dict(a.prediction_result or {}, a.preprocess_metadata)

    return AnalysisDetail(
        analysis_id=a.id,
        upload={
            "id": u.id,
            "original_name": u.original_name or u.filename,
            "file_size": u.file_size,
            "created_at": u.created_at,
        },
        sampling_rate_hz=a.sampling_rate_hz,
        signal_stats=a.signal_stats,
        prediction_result=pred_enriched,
        preprocess_metadata=a.preprocess_metadata,
        chart_series=chart,
        created_at=a.created_at,
        synthetic_runs=[SyntheticOut.model_validate(s) for s in synth],
    )


@router.get("/{analysis_id}/export-pdf")
def export_report_pdf(analysis_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Report not found")
    u = db.get(ECGUpload, a.upload_id)
    if not u:
        raise HTTPException(status_code=404, detail="Upload missing")

    path = Path(u.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=500, detail="Stored file missing")

    raw = path.read_bytes()
    try:
        samples, _, _ = parse_ecg_csv(io.BytesIO(raw))
    except CSVValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    pre = ecg_preprocessing.preprocess_signal(samples)
    chart = pre.get("normalized_series") or []
    meta_pm = a.preprocess_metadata or {}
    pred = enrich_prediction_dict(a.prediction_result or {}, meta_pm)
    risk = compute_risk_assessment(pred, meta_pm)

    settings = get_settings()
    fs_used = float(a.sampling_rate_hz) if a.sampling_rate_hz is not None else float(settings.ecg_default_sampling_rate_hz)
    window = int(settings.ecg_classifier_input_length)
    arr = np.asarray(samples, dtype=np.float64).ravel()
    pred_m = merge_class_index_into_prediction(pred)

    explain_summary = "Explainability not computed."
    explain_text = ""
    important_regions = None
    window_wf: list[float] | None = None
    imp_norm: list[float] | None = None
    try:
        model_input, _ = prepare_for_classifier(arr, fs=fs_used, window=window)
        ex = build_explanation_payload(model_input=model_input, pred=pred_m)
        explain_summary = str(ex.get("explanation_summary") or "")
        explain_text = str(ex.get("explanation_text") or "")
        important_regions = ex.get("important_regions")
        window_wf = ex.get("window_waveform")
        imp_norm = ex.get("importance_normalized")
    except ClassifierUnavailableError as e:
        explain_summary = f"Saliency unavailable: {e.message}"
    except Exception as e:
        log.warning("PDF saliency skipped: %s", e)
        explain_summary = "Saliency computation failed for this export."

    guidance = guidance_summary_plain_for_pdf(prediction_result=pred, preprocess_metadata=meta_pm)

    pdf_bytes = build_analysis_pdf_bytes(
        analysis_id=a.id,
        created_at_str=a.created_at.isoformat() + "Z",
        filename=u.original_name or u.filename,
        signal_column=str(meta_pm.get("selected_signal_column") or meta_pm.get("source_column") or "—"),
        chart_series=chart,
        prediction=pred,
        risk_level=str(risk.get("risk_level") or pred.get("risk_level") or "uncertain"),
        risk_score=risk.get("risk_score", pred.get("risk_score", "—")),
        risk_rationale=str(risk.get("risk_rationale") or pred.get("risk_rationale") or ""),
        guidance_summary=guidance,
        explanation_summary=explain_summary,
        explanation_text=explain_text,
        important_regions=important_regions,
        window_waveform=window_wf,
        importance_normalized=imp_norm,
    )

    fname = f"cardiosynth_report_{a.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{analysis_id}/export")
def export_report_json(analysis_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Report not found")
    u = db.get(ECGUpload, a.upload_id)
    if not u:
        raise HTTPException(status_code=404, detail="Upload missing")

    payload: Dict[str, Any] = {
        "analysis_id": a.id,
        "created_at": a.created_at.isoformat(),
        "upload": {
            "id": u.id,
            "filename": u.filename,
            "original_name": u.original_name,
            "file_size": u.file_size,
            "mime_type": u.mime_type,
            "created_at": u.created_at.isoformat(),
        },
        "sampling_rate_hz": a.sampling_rate_hz,
        "signal_stats": a.signal_stats,
        "preprocess_metadata": a.preprocess_metadata,
        "prediction_result": a.prediction_result,
        "status": _status_from_prediction(a.prediction_result),
    }
    return JSONResponse(payload)


@router.delete("/{analysis_id}")
def delete_report(analysis_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Report not found")
    u = db.get(ECGUpload, a.upload_id)
    if not u:
        raise HTTPException(status_code=404, detail="Upload missing")

    delete_analysis_bundle(db, a, u)
    return {"ok": True, "deleted_analysis_id": analysis_id}

