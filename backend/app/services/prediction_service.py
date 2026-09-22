"""
TensorFlow/Keras ECG beat-classifier inference.

Loads weights once (lazy). Training uses 5-way softmax on MIT-BIH beat morphologies (N,L,R,A,V).

The API surfaces an additional **clinical** 5-class view (Normal, AFib, PVC, Tachycardia, Bradycardia)
via ``app.services.clinical_multiclass`` — derived from beat probabilities + optional heart rate.

Default weights: backend/ml_models/arrhythmia_model.h5 (override with ECG_CLASSIFIER_MODEL_PATH).

When ENABLE_MOCK_INFERENCE is false (default), unavailable model or failed inference raises
ClassifierUnavailableError from predict_ecg (routes map to HTTP 503).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.config import get_settings
from app.core.classifier_errors import ClassifierUnavailableError
from app.datasets.paths import CLASSIFIER_MODEL_PATH
from app.services.clinical_multiclass import (
    clinical_prediction_from_beat_output,
    rhythm_hint_clinical,
)

log = logging.getLogger(__name__)

DEFAULT_CLASS_NAMES: List[str] = ["N", "L", "R", "A", "V"]

CLASSIFIER_TRAIN_SHELL_COMMAND = "cd backend && .venv/bin/python training/train_classifier.py"
CLASSIFIER_NOT_TRAINED_MESSAGE = (
    "The ECG classifier has not been trained yet. "
    f"Run: {CLASSIFIER_TRAIN_SHELL_COMMAND}"
)

_MODEL = None
_MODEL_LOAD_ERROR: Optional[str] = None
_MODEL_MISSING_WEIGHTS_FILE: bool = False


def _mock_inference_enabled() -> bool:
    return bool(get_settings().enable_mock_inference)


def reset_classifier_cache() -> None:
    global _MODEL, _MODEL_LOAD_ERROR, _MODEL_MISSING_WEIGHTS_FILE
    _MODEL = None
    _MODEL_LOAD_ERROR = None
    _MODEL_MISSING_WEIGHTS_FILE = False


def load_classifier_eager() -> bool:
    """Force load from disk; returns True if a Keras model is ready for inference."""
    reset_classifier_cache()
    return _load_keras_model(log_load_exception=False) is not None


def _classifier_path() -> Path:
    p = get_settings().ecg_classifier_model_path.strip()
    return Path(p) if p else CLASSIFIER_MODEL_PATH


def resolved_classifier_model_path() -> Path:
    """Absolute path: ECG_CLASSIFIER_MODEL_PATH if set, else backend/ml_models/arrhythmia_model.h5."""
    return _classifier_path().expanduser().resolve()


def is_classifier_model_file_present() -> bool:
    return resolved_classifier_model_path().is_file()


def is_ecg_classifier_loaded() -> bool:
    """True when Keras model is in memory (startup_load or lazy load succeeded)."""
    return _MODEL is not None


def get_classifier_debug_snapshot() -> Dict[str, Any]:
    """
    GET /debug/model — contract:
    resolved_model_path, exists, model_loaded, load_error, mock_enabled.
    Optional: input_shape when loaded.
    """
    path = resolved_classifier_model_path()
    path_s = str(path)
    exists = path.is_file()
    model_loaded = _MODEL is not None
    if model_loaded:
        load_error: Optional[str] = None
    elif _MODEL_LOAD_ERROR:
        load_error = _MODEL_LOAD_ERROR
    elif not exists:
        load_error = "weights file missing"
    else:
        load_error = "model not loaded"

    out: Dict[str, Any] = {
        "resolved_model_path": path_s,
        "exists": exists,
        "model_loaded": model_loaded,
        "load_error": load_error,
        "mock_enabled": bool(get_settings().enable_mock_inference),
    }
    if model_loaded and _MODEL is not None:
        try:
            if _MODEL.input_shape:
                out["input_shape"] = list(_MODEL.input_shape)
        except Exception:
            pass
    return out


def startup_load_ecg_classifier() -> None:
    """
    Run during app lifespan: log resolved path, existence, load outcome; log full traceback on failure.
    """
    global _MODEL, _MODEL_LOAD_ERROR, _MODEL_MISSING_WEIGHTS_FILE

    reset_classifier_cache()
    path = resolved_classifier_model_path()
    exists = path.is_file()
    win = int(get_settings().ecg_classifier_input_length)

    log.info("ECG classifier model path (resolved): %s", path)
    log.info("ECG classifier weights file exists: %s", exists)

    if not exists:
        _MODEL_LOAD_ERROR = "weights file missing"
        log.warning("ECG classifier weights not found — inference disabled until trained weights exist.")
        return

    try:
        import tensorflow as tf  # noqa: WPS433

        tf.keras.utils.disable_interactive_logging()
        m = tf.keras.models.load_model(path, compile=False)
    except ImportError:
        log.exception("TensorFlow is not installed — cannot load ECG classifier (pip install -r requirements-tensorflow.txt)")
        _MODEL_LOAD_ERROR = "tensorflow not installed (see backend/requirements-tensorflow.txt)"
        return
    except Exception:
        log.exception("ECG classifier load_model() failed for %s", path)
        _MODEL_LOAD_ERROR = "load_model failed (see server logs for traceback)"
        return

    _MODEL = m
    _MODEL_LOAD_ERROR = None
    _MODEL_MISSING_WEIGHTS_FILE = False

    log.info("ECG classifier model loaded successfully (input_shape=%s)", m.input_shape)

    if m.input_shape and len(m.input_shape) >= 2 and m.input_shape[1] is not None:
        expected = win
        got = int(m.input_shape[1])
        if got != expected:
            log.warning(
                "Classifier input length mismatch: model expects %s samples, settings ECG_CLASSIFIER_INPUT_LENGTH=%s",
                got,
                expected,
            )


def prediction_result_weights_missing(
    *,
    heart_rate_bpm: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "label": "classifier_not_trained",
        "predicted_class": "unknown",
        "confidence": 0.0,
        "class_index": None,
        "all_probabilities": None,
        "beat_model_class_index": None,
        "beat_model_label": None,
        "rhythm_hint": "unknown",
        "explanation_stub": f"{CLASSIFIER_NOT_TRAINED_MESSAGE} Not a medical diagnosis.",
        "mock": True,
        "heart_rate_bpm": heart_rate_bpm,
        "class_probabilities": None,
    }


def _maybe_clear_stale_missing_file_error() -> None:
    """If weights appeared after an earlier failed load, allow retry."""
    global _MODEL_LOAD_ERROR, _MODEL_MISSING_WEIGHTS_FILE
    path = resolved_classifier_model_path()
    if path.is_file() and _MODEL_MISSING_WEIGHTS_FILE:
        _MODEL_LOAD_ERROR = None
        _MODEL_MISSING_WEIGHTS_FILE = False


def _load_keras_model(*, log_load_exception: bool = False):
    """Lazy singleton load; returns None if file missing or load fails."""
    global _MODEL, _MODEL_LOAD_ERROR, _MODEL_MISSING_WEIGHTS_FILE

    if _MODEL is not None:
        return _MODEL

    _maybe_clear_stale_missing_file_error()

    if _MODEL_LOAD_ERROR is not None and not _MODEL_MISSING_WEIGHTS_FILE:
        return None

    path = resolved_classifier_model_path()
    if not path.is_file():
        _MODEL_LOAD_ERROR = f"No classifier weights file at {path}"
        _MODEL_MISSING_WEIGHTS_FILE = True
        log.warning(
            "ECG classifier weights missing at %s. Run: %s",
            path,
            CLASSIFIER_TRAIN_SHELL_COMMAND,
        )
        return None

    _MODEL_MISSING_WEIGHTS_FILE = False

    try:
        import tensorflow as tf  # noqa: WPS433

        tf.keras.utils.disable_interactive_logging()
        m = tf.keras.models.load_model(path, compile=False)
        _MODEL = m
        _MODEL_LOAD_ERROR = None
        log.info("Loaded ECG classifier from %s (lazy)", path)
        return _MODEL
    except ImportError:
        _MODEL_LOAD_ERROR = "tensorflow not installed (see backend/requirements-tensorflow.txt)"
        if log_load_exception:
            log.exception("TensorFlow import failed during lazy classifier load")
        else:
            log.warning("%s", _MODEL_LOAD_ERROR)
        return None
    except Exception as e:
        _MODEL_LOAD_ERROR = str(e)
        if log_load_exception:
            log.exception("Failed to load ECG classifier from %s", path)
        else:
            log.error("Failed to load ECG classifier from %s: %s", path, e)
        return None


def classify_from_tensor(
    model_input: np.ndarray,
    *,
    class_names: Optional[List[str]] = None,
    heart_rate_bpm: Optional[float] = None,
) -> Dict[str, Any]:
    """
    model_input: float32 (1, L, 1)

    If ENABLE_MOCK_INFERENCE is false and the model cannot run, raises ClassifierUnavailableError.
    """
    names = class_names or DEFAULT_CLASS_NAMES
    model = _load_keras_model(log_load_exception=False)

    if model is None:
        if _mock_inference_enabled():
            if _MODEL_MISSING_WEIGHTS_FILE:
                return prediction_result_weights_missing(heart_rate_bpm=heart_rate_bpm)
            detail = _MODEL_LOAD_ERROR or "unknown error"
            return {
                "label": "model_unavailable",
                "predicted_class": "unknown",
                "confidence": 0.0,
                "class_index": None,
                "all_probabilities": None,
                "beat_model_class_index": None,
                "beat_model_label": None,
                "rhythm_hint": "unknown",
                "explanation_stub": (
                    f"The ECG classifier could not be loaded ({detail}). "
                    f"If weights are missing, run: {CLASSIFIER_TRAIN_SHELL_COMMAND}. "
                    "Not a medical diagnosis."
                ),
                "mock": True,
                "heart_rate_bpm": heart_rate_bpm,
                "class_probabilities": None,
            }
        if _MODEL_MISSING_WEIGHTS_FILE:
            raise ClassifierUnavailableError(
                f"{CLASSIFIER_NOT_TRAINED_MESSAGE} "
                f"(expected weights at {resolved_classifier_model_path()})"
            )
        raise ClassifierUnavailableError(
            f"ECG classifier could not be loaded: {_MODEL_LOAD_ERROR or 'unknown error'}. "
            f"Install TensorFlow if needed (requirements-tensorflow.txt) or fix the model file."
        )

    if model_input.size == 0 or model_input.shape[1] < 8:
        if _mock_inference_enabled():
            return {
                "label": "insufficient_data",
                "predicted_class": "unknown",
                "confidence": 0.0,
                "class_index": None,
                "all_probabilities": None,
                "beat_model_class_index": None,
                "beat_model_label": None,
                "rhythm_hint": "unknown",
                "explanation_stub": "Signal too short for classifier input.",
                "mock": True,
                "heart_rate_bpm": heart_rate_bpm,
                "class_probabilities": None,
            }
        raise ClassifierUnavailableError("Signal too short for classifier input after preprocessing.")

    try:
        probs = model.predict(model_input, verbose=0)[0]
        probs = np.asarray(probs, dtype=np.float64)
        beat_idx = int(np.argmax(probs))
        beat_conf = float(probs[beat_idx])
        beat_name = names[beat_idx] if beat_idx < len(names) else str(beat_idx)
        prob_map = {names[i]: float(probs[i]) for i in range(min(len(names), len(probs)))}

        cname, cidx, cconf, all_probs, _ = clinical_prediction_from_beat_output(
            beat_probabilities=prob_map,
            heart_rate_bpm=heart_rate_bpm,
        )

        return {
            "label": cname,
            "predicted_class": cname,
            "class_index": cidx,
            "confidence": cconf,
            "all_probabilities": all_probs,
            "beat_model_class_index": beat_idx,
            "beat_model_label": beat_name,
            "beat_model_confidence": beat_conf,
            "rhythm_hint": rhythm_hint_clinical(cname),
            "explanation_stub": (
                f"Clinical view: «{cname}» (confidence {cconf:.2f}); "
                f"beat model peak «{beat_name}» ({beat_conf:.2f}). "
                "Research use only — not a medical diagnosis."
            ),
            "mock": False,
            "heart_rate_bpm": heart_rate_bpm,
            "class_probabilities": prob_map,
        }
    except Exception as e:
        log.exception("ECG classifier inference failed")
        if _mock_inference_enabled():
            return {
                "label": "inference_error",
                "predicted_class": "unknown",
                "confidence": 0.0,
                "class_index": None,
                "all_probabilities": None,
                "beat_model_class_index": None,
                "beat_model_label": None,
                "rhythm_hint": "unknown",
                "explanation_stub": (
                    f"Inference failed ({e}). If the model is missing or invalid, run: "
                    f"{CLASSIFIER_TRAIN_SHELL_COMMAND}. Not a medical diagnosis."
                ),
                "mock": True,
                "heart_rate_bpm": heart_rate_bpm,
                "class_probabilities": None,
            }
        raise ClassifierUnavailableError(f"ECG classifier inference failed: {e}") from e
