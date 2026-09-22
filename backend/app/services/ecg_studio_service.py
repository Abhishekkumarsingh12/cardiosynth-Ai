"""
ECG Studio: end-to-end analysis for arbitrary uploaded ECG CSVs.

Goals:
- Use the selected signal column from parse_ecg_csv consistently.
- Produce raw + processed previews (payload-capped).
- Extract beat-centered windows (187) for classifier inference.
- Return a rich summary (beats analyzed, quality, class distribution).

This is not clinical-grade. Outputs are for research/education only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.signal import find_peaks

from app.config import get_settings
from app.core.classifier_errors import ClassifierUnavailableError
from app.services.ecg_preprocessing_service import bandpass_filter, estimate_heart_rate_bpm, zscore_1d
from app.services.prediction_service import classify_from_tensor, is_ecg_classifier_loaded

log = logging.getLogger(__name__)


def _cap_series(x: np.ndarray, cap: int = 5000) -> List[float]:
    if x.size <= cap:
        return x.astype(np.float64).tolist()
    return x[:cap].astype(np.float64).tolist()


def _extract_windows_around_peaks(
    filtered: np.ndarray,
    *,
    fs: float,
    window: int,
    max_beats: int = 32,
) -> Tuple[np.ndarray, List[int]]:
    """
    Returns:
      segments: float32 (n, window) z-scored per-window
      peak_indices: indices into filtered used for each segment center
    """
    sig = np.asarray(filtered, dtype=np.float64).ravel()
    if sig.size == 0:
        return np.zeros((0, window), dtype=np.float32), []

    if sig.size < window:
        seg = np.zeros(window, dtype=np.float64)
        seg[: sig.size] = sig
        seg = zscore_1d(seg).astype(np.float32)
        return seg.reshape(1, window), [int(sig.size // 2)]

    x = zscore_1d(sig)
    min_dist = max(1, int(0.25 * fs))
    # prominence tuned for generic CSV strips; keep permissive but avoid noise-only series
    peaks, _ = find_peaks(x, distance=min_dist, prominence=0.25)
    if peaks.size == 0:
        # fall back to evenly spaced windows (center-crop segments)
        centers = np.linspace(window // 2, sig.size - window // 2 - 1, num=min(max_beats, 8)).astype(int)
    else:
        # pick up to max_beats peaks, spread across the trace
        if peaks.size > max_beats:
            idx = np.linspace(0, peaks.size - 1, num=max_beats).astype(int)
            centers = peaks[idx]
        else:
            centers = peaks

    segs: List[np.ndarray] = []
    used: List[int] = []
    half = window // 2
    for c in centers.tolist():
        lo = int(c) - half
        hi = lo + window
        if lo < 0 or hi > sig.size:
            continue
        w = sig[lo:hi]
        w = zscore_1d(w).astype(np.float32)
        segs.append(w)
        used.append(int(c))
    if not segs:
        return np.zeros((0, window), dtype=np.float32), []
    return np.stack(segs, axis=0), used


def _signal_quality(
    *,
    filtered: np.ndarray,
    beat_count: int,
) -> Dict[str, Any]:
    """
    Very lightweight heuristic quality estimate (not clinical).
    """
    x = np.asarray(filtered, dtype=np.float64).ravel()
    if x.size == 0:
        return {"label": "bad", "score": 0.0, "reasons": ["empty_signal"]}
    s = float(np.std(x))
    reasons: List[str] = []
    score = 1.0
    if s < 1e-6:
        score *= 0.1
        reasons.append("near_constant")
    if beat_count < 2:
        score *= 0.5
        reasons.append("few_detected_beats")
    if beat_count == 0:
        score *= 0.2
    score = float(max(0.0, min(1.0, score)))
    label = "good" if score >= 0.75 else "ok" if score >= 0.45 else "bad"
    return {"label": label, "score": score, "reasons": reasons}


def analyze_for_studio(
    samples: List[float],
    *,
    fs: float,
    selected_signal_column: str,
    inferred_fs: Optional[float] = None,
) -> Dict[str, Any]:
    """
    End-to-end ECG Studio analysis. Raises ClassifierUnavailableError in strict mode
    when the classifier model is not loaded.
    """
    settings = get_settings()
    window = int(settings.ecg_classifier_input_length)

    if not is_ecg_classifier_loaded() and not settings.enable_mock_inference:
        raise ClassifierUnavailableError(
            "ECG classifier is not loaded. Check /debug/model and server logs. "
            "Install TensorFlow and ensure backend/ml_models/arrhythmia_model.h5 is compatible."
        )

    arr = np.asarray(samples, dtype=np.float64).ravel()
    if arr.size < 10:
        raise ValueError("Signal too short (need at least 10 numeric samples).")

    filtered = bandpass_filter(arr, fs=fs)
    processed = zscore_1d(filtered)
    hr_context = estimate_heart_rate_bpm(filtered, fs)

    segs, centers = _extract_windows_around_peaks(filtered, fs=fs, window=window)
    beat_count = int(segs.shape[0])
    quality = _signal_quality(filtered=filtered, beat_count=beat_count)

    # per-beat inference
    beat_preds: List[Dict[str, Any]] = []
    if beat_count == 0:
        # strict: no fake output; return empty beats + quality
        beat_preds = []
    else:
        for i in range(beat_count):
            x = segs[i].reshape(1, window, 1)
            pred = classify_from_tensor(x, heart_rate_bpm=hr_context)
            beat_preds.append(
                {
                    "beat_index": i,
                    "center_sample_index": int(centers[i]) if i < len(centers) else None,
                    "label": pred.get("label"),
                    "confidence": float(pred.get("confidence") or 0.0),
                    "rhythm_hint": pred.get("rhythm_hint"),
                    "all_probabilities": pred.get("all_probabilities"),
                    "beat_model_label": pred.get("beat_model_label"),
                    "class_probabilities": pred.get("class_probabilities"),
                }
            )

    # aggregate summary (majority vote)
    labels = [p["label"] for p in beat_preds if p.get("label")]
    confs = [float(p.get("confidence") or 0.0) for p in beat_preds]
    dist: Dict[str, int] = {}
    for lb in labels:
        dist[lb] = dist.get(lb, 0) + 1
    top_label = max(dist.items(), key=lambda kv: kv[1])[0] if dist else "unknown"
    mean_conf = float(np.mean(confs)) if confs else 0.0

    clinical_notes = (
        "This is an AI-generated research summary and not a medical diagnosis. "
        "If you have symptoms like chest pain, fainting, severe shortness of breath, or persistent palpitations, "
        "seek urgent medical care."
    )

    return {
        "selected_signal_column": selected_signal_column,
        "sampling_rate_hz_used": float(fs),
        "sampling_rate_hz_inferred": inferred_fs,
        "n_samples": int(arr.size),
        "raw_stats": {
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
        },
        "raw_series": _cap_series(arr),
        "processed_series": _cap_series(processed),
        "window": window,
        "beats_analyzed": beat_count,
        "signal_quality": quality,
        "beat_segments": [segs[i].astype(np.float32).tolist() for i in range(min(beat_count, 12))],
        "beat_predictions": beat_preds[:12],
        "summary": {
            "predicted_class": top_label,
            "confidence_mean": mean_conf,
            "class_distribution": dist,
        },
        "clinical_notes": clinical_notes,
    }

