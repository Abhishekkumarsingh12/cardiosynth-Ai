from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.core.classifier_errors import ClassifierUnavailableError
from app.core.synthetic_errors import SyntheticGenerationError
from app.database import get_db
from app.models import ECGAnalysis, ECGUpload, SyntheticECG, User
from app.schemas.ecg import AnalysisDetail, ECGUploadOut, HistoryItem, SyntheticGenerateIn, SyntheticOut
from app.services import ecg_prediction, ecg_preprocessing, synthetic_ecg
from app.services.ecg_explanation_service import build_explanation_payload, merge_class_index_into_prediction
from app.services.ecg_preprocessing_service import prepare_for_classifier
from app.services.ecg_studio_service import analyze_for_studio
from app.services.risk_score_service import compute_risk_assessment, enrich_prediction_dict
from app.utils.csv_ecg import CSVValidationError, parse_ecg_csv, validate_csv_file
from app.services.universal_ecg_ingestion_service import (
    build_universal_analysis_payload,
    decide_ingestion,
    persist_upload_bytes,
)
from pydantic import BaseModel, Field

router = APIRouter()

_PREVIEW_MAX = 2000


def _preview_series(arr: np.ndarray) -> list[float]:
    w = np.asarray(arr, dtype=np.float64).ravel()
    if w.size <= _PREVIEW_MAX:
        return w.tolist()
    idx = np.linspace(0, w.size - 1, _PREVIEW_MAX, dtype=int)
    return w[idx].tolist()


def _uploads_base() -> Path:
    base = Path(__file__).resolve().parent.parent.parent.parent / get_settings().uploads_dir
    base.mkdir(parents=True, exist_ok=True)
    return base


@router.post("/upload")
async def ecg_upload(
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload.")

    mime = file.content_type or "application/octet-stream"
    decision = decide_ingestion(raw=raw, filename=file.filename, mime_type=mime)

    try:
        safe_name, stored_path, size = persist_upload_bytes(
            user_id=current.id,
            original_name=file.filename,
            mime_type=mime,
            raw=raw,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store upload: {e}") from e

    upload = ECGUpload(
        user_id=current.id,
        filename=safe_name,
        stored_path=stored_path,
        file_size=size,
        mime_type=mime,
        original_name=file.filename,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    settings = get_settings()
    fs_used = float(settings.ecg_default_sampling_rate_hz)
    try:
        sig, meta, pred = build_universal_analysis_payload(decision=decision, raw=raw, assumed_fs=fs_used)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ClassifierUnavailableError as e:
        # CSV and waveform-derived paths can hit strict inference; keep contract.
        raise HTTPException(status_code=503, detail=e.message) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {e}") from e

    analysis = ECGAnalysis(
        upload_id=upload.id,
        user_id=current.id,
        sampling_rate_hz=fs_used,
        signal_stats=(meta.get("signal_stats") if isinstance(meta, dict) else None),
        prediction_result=pred,
        preprocess_metadata=meta,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return {
        "upload_id": upload.id,
        "analysis_id": analysis.id,
        "message": "Upload processed.",
        "file_type": decision.file_type,
        "content_type": decision.content_type,
    }


class ManualECGIn(BaseModel):
    heart_rate: Optional[float] = Field(default=None, ge=10, le=260)
    pr_interval: Optional[float] = Field(default=None, ge=40, le=400, description="ms")
    qrs_duration: Optional[float] = Field(default=None, ge=40, le=300, description="ms")
    qtc: Optional[float] = Field(default=None, ge=200, le=700, description="ms")
    symptoms: Optional[str] = Field(default=None, max_length=800)


@router.post("/manual/{analysis_id}")
def submit_manual_inputs(
    analysis_id: int,
    body: ManualECGIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fallback path: allow user-provided ECG values when extraction fails.
    This does NOT produce a medical diagnosis; it stores structured values and updates the analysis payload.
    """
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Analysis not found")

    meta = a.preprocess_metadata or {}
    meta["manual_input"] = body.model_dump()
    a.preprocess_metadata = meta

    pred = a.prediction_result or {}
    pred["manual_input"] = body.model_dump()
    pred["manual_input_required"] = False
    pred["status"] = pred.get("status") or "success"
    symptoms = (body.symptoms or "").strip()
    if symptoms:
        pred["explanation_stub"] = (pred.get("explanation_stub") or "") + f" Symptoms noted: {symptoms}. Research use only — not a medical diagnosis."
    a.prediction_result = pred

    db.add(a)
    db.commit()
    db.refresh(a)
    return {"analysis_id": a.id, "ok": True}


@router.get("/history", response_model=list[HistoryItem])
def history(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(ECGAnalysis, ECGUpload)
        .join(ECGUpload, ECGUpload.id == ECGAnalysis.upload_id)
        .filter(ECGAnalysis.user_id == current.id)
        .order_by(ECGAnalysis.created_at.desc())
        .limit(100)
        .all()
    )
    out: list[HistoryItem] = []
    for a, u in rows:
        pred = a.prediction_result or {}
        out.append(
            HistoryItem(
                analysis_id=a.id,
                upload_id=u.id,
                original_name=u.original_name or u.filename,
                created_at=a.created_at,
                prediction_label=pred.get("label"),
                confidence=pred.get("confidence"),
            )
        )
    return out


@router.get("/analysis/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(
    analysis_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Analysis not found")
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
        upload=ECGUploadOut.model_validate(u),
        sampling_rate_hz=a.sampling_rate_hz,
        signal_stats=a.signal_stats,
        prediction_result=pred_enriched,
        preprocess_metadata=a.preprocess_metadata,
        chart_series=chart,
        created_at=a.created_at,
        synthetic_runs=[SyntheticOut.model_validate(s) for s in synth],
    )


@router.post("/generate-synthetic/{analysis_id}")
def generate_synthetic(
    analysis_id: int,
    body: SyntheticGenerateIn = Body(default_factory=SyntheticGenerateIn),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    u = db.get(ECGUpload, a.upload_id)
    if not u:
        raise HTTPException(status_code=404, detail="Upload missing")

    path = Path(u.stored_path)
    raw = path.read_bytes()
    try:
        samples, _, _ = parse_ecg_csv(io.BytesIO(raw))
    except CSVValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    fs = float(a.sampling_rate_hz) if a.sampling_rate_hz is not None else float(get_settings().ecg_default_sampling_rate_hz)
    pre = ecg_preprocessing.preprocess_signal(samples, assumed_fs=fs)
    try:
        pred = a.prediction_result or ecg_prediction.predict_ecg(samples, fs)
    except ClassifierUnavailableError as e:
        raise HTTPException(status_code=503, detail=e.message) from e

    syn_dir = _uploads_base() / "synthetic" / str(current.id)
    try:
        stored_path, meta, waveform = synthetic_ecg.run_synthetic_generation(
            analysis_id=a.id,
            preprocess_output=pre,
            prediction=pred,
            out_dir=syn_dir,
            target_class=body.target_class,
            num_samples=body.num_samples,
            noise_scale=body.noise_scale,
            diversity_seed=body.diversity_seed,
            num_beats=body.num_beats,
        )
    except SyntheticGenerationError as e:
        raise HTTPException(status_code=503, detail=e.message) from e

    row = SyntheticECG(
        analysis_id=a.id,
        user_id=current.id,
        stored_path=stored_path,
        mock_metadata=meta,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    ref_z = synthetic_ecg.reference_waveform_for_compare(pre, waveform.shape[0])
    cmp_stats = synthetic_ecg.compare_reference_synthetic(ref_z, waveform)
    quality = dict(meta.get("procedural_quality") or {})
    quality["comparison_vs_reference_z"] = cmp_stats

    return {
        "run": SyntheticOut.model_validate(row),
        "metadata": meta,
        "preview_reference": _preview_series(ref_z),
        "preview_synthetic": _preview_series(waveform),
        "quality": quality,
    }


@router.get("/synthetic-file/{synthetic_id}")
def download_synthetic_csv(
    synthetic_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(SyntheticECG, synthetic_id)
    if not row or row.user_id != current.id:
        raise HTTPException(status_code=404, detail="Synthetic run not found")
    p = Path(row.stored_path or "")
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Synthetic CSV missing on disk")
    return FileResponse(
        str(p.resolve()),
        filename=p.name,
        media_type="text/csv",
    )


@router.post("/analyze/{analysis_id}")
def analyze_ecg_studio(
    analysis_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ECG Studio: re-parse the stored CSV using robust column selection, run preprocessing,
    beat segmentation, and per-beat classification inference.

    Strict mode: if classifier unavailable, returns HTTP 503 (no fake success).
    """
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    u = db.get(ECGUpload, a.upload_id)
    if not u:
        raise HTTPException(status_code=404, detail="Upload missing")

    path = Path(u.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=500, detail="Stored file missing")

    raw = path.read_bytes()
    try:
        samples, col_name, parse_meta = parse_ecg_csv(io.BytesIO(raw))
    except CSVValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    settings = get_settings()
    fs_used = float(a.sampling_rate_hz) if a.sampling_rate_hz is not None else float(settings.ecg_default_sampling_rate_hz)

    try:
        studio = analyze_for_studio(
            samples,
            fs=fs_used,
            selected_signal_column=col_name,
            inferred_fs=parse_meta.get("sampling_rate_hz_inferred"),
        )
    except ClassifierUnavailableError as e:
        raise HTTPException(status_code=503, detail=e.message) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Persist a report-like payload for the Reports module (no schema migration; store in JSON).
    meta = a.preprocess_metadata or {}
    meta["selected_signal_column"] = studio.get("selected_signal_column")
    meta["sampling_rate_hz_inferred"] = studio.get("sampling_rate_hz_inferred")
    meta["studio"] = {
        "beats_analyzed": studio.get("beats_analyzed"),
        "signal_quality": studio.get("signal_quality"),
        "window": studio.get("window"),
    }
    a.preprocess_metadata = meta

    pr = a.prediction_result or {}
    pr["studio_summary"] = studio.get("summary")
    pr["beats_analyzed"] = studio.get("beats_analyzed")
    pr["signal_quality"] = studio.get("signal_quality")
    pr["status"] = "success"
    pr.update(compute_risk_assessment(pr, meta))
    a.prediction_result = pr

    db.add(a)
    db.commit()
    db.refresh(a)

    risk_keys = ("risk_level", "risk_score", "risk_rationale", "recommendation")
    return {"analysis_id": a.id, "studio": studio, "risk": {k: pr[k] for k in risk_keys if k in pr}}


@router.get("/explain/{analysis_id}")
def explain_ecg(
    analysis_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Input-gradient saliency on the classifier’s 187-sample window (requires TensorFlow model).
    """
    a = db.get(ECGAnalysis, analysis_id)
    if not a or a.user_id != current.id:
        raise HTTPException(status_code=404, detail="Analysis not found")
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

    settings = get_settings()
    fs_used = float(a.sampling_rate_hz) if a.sampling_rate_hz is not None else float(settings.ecg_default_sampling_rate_hz)
    window = int(settings.ecg_classifier_input_length)

    arr = np.asarray(samples, dtype=np.float64).ravel()
    meta_pm = a.preprocess_metadata or {}
    pred = enrich_prediction_dict(a.prediction_result or {}, meta_pm)
    pred = merge_class_index_into_prediction(pred)
    model_input, _ = prepare_for_classifier(arr, fs=fs_used, window=window)

    try:
        payload = build_explanation_payload(model_input=model_input, pred=pred)
    except ClassifierUnavailableError as e:
        raise HTTPException(status_code=503, detail=e.message) from e

    payload["analysis_id"] = a.id
    return payload
