from __future__ import annotations

import csv
import io
from typing import Optional

import numpy as np
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.core.classifier_errors import ClassifierUnavailableError
from app.database import get_db
from app.models import User
from app.schemas.ecg import SyntheticPlaygroundIn, SyntheticPlaygroundOut
from app.services import ecg_prediction
from app.services.ecg_explanation_service import build_explanation_payload, merge_class_index_into_prediction
from app.services.ecg_preprocessing_service import prepare_for_classifier
from app.services.procedural_synthetic_ecg import resolve_class_id, generate_procedural_strip


router = APIRouter()


def _normalize_condition_label(condition: str) -> str:
    s = (condition or "").strip().lower()
    if s in {"normal", "sinus", "nsr"}:
        return "N"
    if s in {"afib", "a-fib", "atrial_fibrillation", "atrial fibrillation"}:
        # closest beat label bucket for this demo scaffold
        return "A"
    if s in {"pvc", "ventricular", "ventricular_ectopic"}:
        return "V"
    # allow passing beat labels directly
    if s.upper() in {"N", "A", "V", "L", "R"}:
        return s.upper()
    return "N"


def _to_csv_text(waveform: np.ndarray) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["index", "ecg"])
    for i, v in enumerate(waveform.tolist()):
        w.writerow([i, f"{float(v):.8f}"])
    return buf.getvalue()


@router.post("/generate", response_model=SyntheticPlaygroundOut)
def generate_synthetic_playground(
    body: SyntheticPlaygroundIn = Body(...),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Synthetic Data Playground: generate a condition-labeled ECG strip and run prediction on it.

    Notes:
    - Uses procedural generator (no DDPM weights required).
    - Returns a CSV text payload for download in the UI.
    """
    _ = db  # reserved for future persistence
    settings = get_settings()
    fs = float(settings.ecg_default_sampling_rate_hz)

    label = _normalize_condition_label(body.condition)
    pred_stub = {"label": label}
    class_id, class_label = resolve_class_id(label, pred_stub)
    waveform, quality = generate_procedural_strip(
        num_samples=body.num_samples,
        class_id=class_id,
        class_label=class_label,
        noise_scale=body.noise_scale,
        diversity_seed=body.diversity_seed,
        num_beats=None,
    )
    _ = quality

    try:
        pred = ecg_prediction.predict_ecg(waveform.tolist(), fs)
    except ClassifierUnavailableError as e:
        raise HTTPException(status_code=503, detail=e.message) from e

    explanation = None
    try:
        window = int(settings.ecg_classifier_input_length)
        model_input, _meta = prepare_for_classifier(np.asarray(waveform, dtype=np.float64), fs=fs, window=window)
        pred_m = merge_class_index_into_prediction(dict(pred))
        explanation = build_explanation_payload(model_input=model_input, pred=pred_m)
    except Exception:
        explanation = None

    csv_text = _to_csv_text(waveform)

    return SyntheticPlaygroundOut(
        condition=body.condition,
        num_samples=int(waveform.size),
        sampling_rate_hz=fs,
        waveform=waveform.astype(float).tolist(),
        prediction=pred,
        explanation=explanation,
        csv_text=csv_text,
    )

