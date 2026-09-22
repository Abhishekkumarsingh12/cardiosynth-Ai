"""
ECG prediction facade: preprocessing for inference + TensorFlow classifier.

Offline training: training/train_classifier.py.
Weights: backend/ml_models/arrhythmia_model.h5 (or ECG_CLASSIFIER_MODEL_PATH).

Preprocessing matches training (prepare_pipeline beat windows): bandpass → fixed-length window
(center crop or zero-pad) → per-window z-score → float32 (1, L, 1) for Keras.

When ENABLE_MOCK_INFERENCE is false, missing model or inference errors raise ClassifierUnavailableError.
"""

from __future__ import annotations

from typing import Any, List, Optional

import numpy as np

from app.config import get_settings
from app.core.classifier_errors import ClassifierUnavailableError
from app.services.ecg_preprocessing_service import estimate_heart_rate_bpm, prepare_for_classifier
from app.services.risk_score_service import compute_risk_assessment
from app.services.prediction_service import (
    CLASSIFIER_TRAIN_SHELL_COMMAND,
    classify_from_tensor,
    is_classifier_model_file_present,
    is_ecg_classifier_loaded,
    prediction_result_weights_missing,
    resolved_classifier_model_path,
)


def predict_ecg(samples: List[float], sampling_rate_hz: Optional[float] = None) -> dict[str, Any]:
    settings = get_settings()
    mock_mode = bool(settings.enable_mock_inference)
    fs = float(sampling_rate_hz) if sampling_rate_hz is not None else float(settings.ecg_default_sampling_rate_hz)
    window = int(settings.ecg_classifier_input_length)
    arr = np.asarray(samples, dtype=np.float64).ravel()

    if arr.size < 64:
        base = {
            "label": "insufficient_data",
            "predicted_class": "unknown",
            "confidence": 0.0,
            "class_index": None,
            "all_probabilities": None,
            "beat_model_class_index": None,
            "beat_model_label": None,
            "rhythm_hint": "unknown",
            "explanation_stub": "Need at least ~64 samples for filtering and windowing.",
            "mock": False,
            "heart_rate_bpm": None,
            "class_probabilities": None,
        }
        base.update(compute_risk_assessment(base, None))
        return base

    if mock_mode and not is_classifier_model_file_present():
        return prediction_result_weights_missing()

    if not mock_mode and not is_classifier_model_file_present():
        raise ClassifierUnavailableError(
            f"The ECG classifier has not been trained yet (no weights at {resolved_classifier_model_path()}). "
            f"Run: {CLASSIFIER_TRAIN_SHELL_COMMAND}"
        )

    if not mock_mode and not is_ecg_classifier_loaded():
        raise ClassifierUnavailableError(
            "ECG classifier weights exist but the model did not load (TensorFlow missing, incompatible environment, or corrupt .h5). "
            "Check server logs and GET /debug/model. "
            f"Then: pip install a supported TensorFlow build for your platform; or run: {CLASSIFIER_TRAIN_SHELL_COMMAND}"
        )

    model_input, meta = prepare_for_classifier(arr, fs=fs, window=window)
    hr = estimate_heart_rate_bpm(meta["filtered"], fs)
    out = classify_from_tensor(model_input, heart_rate_bpm=hr)
    if isinstance(out, dict):
        out = {**out, **compute_risk_assessment(out, None)}
    return out


def mock_predict(preprocess_output: dict[str, Any]) -> dict[str, Any]:
    """
    Back-compat shim: older callers passed chart preprocess dict only (no raw mV).
    """
    series = preprocess_output.get("normalized_series") or []
    if not series:
        return predict_ecg([], preprocess_output.get("sampling_rate_hz"))
    raw_like = np.asarray(series, dtype=np.float64)
    return predict_ecg(raw_like.tolist(), preprocess_output.get("sampling_rate_hz"))
