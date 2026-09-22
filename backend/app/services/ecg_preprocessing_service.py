"""
ECG preprocessing for TensorFlow classifier inference (distinct from chart-oriented ecg_preprocessing.py).

Pipeline: Butterworth bandpass → optional full-trace operations → fixed-length window → per-window z-score
→ model input tensor (1, L, 1).

Training alignment: MIT-BIH beat classifier used window=187 and per-beat z-score. For arbitrary CSV strips
we take a center crop of the filtered signal, then z-score that window (same as a single-beat normalization).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

log = logging.getLogger(__name__)


def _bandpass_filter(signal: np.ndarray, fs: float, low_hz: float = 0.5, high_hz: float = 40.0) -> np.ndarray:
    nyq = 0.5 * fs
    hi = min(high_hz, 0.45 * nyq)
    lo = max(low_hz, 0.5 / max(fs, 1.0))
    if lo >= hi:
        return signal.astype(np.float64)
    b, a = butter(N=4, Wn=[lo, hi], btype="band", fs=fs)
    pad = 3 * max(len(a), len(b))
    if signal.size <= pad:
        return signal.astype(np.float64)
    try:
        return filtfilt(b, a, signal.astype(np.float64), method="pad").astype(np.float64)
    except ValueError as e:
        log.warning("Bandpass skipped: %s", e)
        return signal.astype(np.float64)


def bandpass_filter(signal: np.ndarray, fs: float, low_hz: float = 0.5, high_hz: float = 40.0) -> np.ndarray:
    """Public wrapper used by ECG Studio (returns full-length filtered trace)."""
    return _bandpass_filter(np.asarray(signal, dtype=np.float64).ravel(), fs=fs, low_hz=low_hz, high_hz=high_hz)


def zscore_1d(x: np.ndarray) -> np.ndarray:
    """Z-score normalize a 1-D array (float64 in, float64 out)."""
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size == 0:
        return arr
    m = float(np.mean(arr))
    s = float(np.std(arr)) or 1.0
    return (arr - m) / s


def estimate_heart_rate_bpm(filtered: np.ndarray, fs: float) -> Optional[float]:
    """Simple R-peak–style estimate from filtered 1-D ECG (not clinical-grade)."""
    if filtered.size < int(fs * 1.5):
        return None
    x = filtered - np.mean(filtered)
    s = float(np.std(x)) or 1.0
    x = x / s
    min_dist = int(0.25 * fs)
    peaks, _ = find_peaks(x, distance=min_dist, prominence=0.25)
    if peaks.size < 2:
        return None
    rr_sec = np.diff(peaks).astype(np.float64) / fs
    rr_sec = rr_sec[(rr_sec > 0.30) & (rr_sec < 2.0)]
    if rr_sec.size == 0:
        return None
    return float(60.0 / np.median(rr_sec))


def prepare_for_classifier(
    samples: np.ndarray,
    fs: float,
    window: int = 187,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Returns:
        model_input: float32 array shape (1, window, 1)
        meta: includes filtered trace (1d) and fs for HR / debugging
    """
    arr = np.asarray(samples, dtype=np.float64).ravel()
    meta: Dict[str, Any] = {"fs": fs, "window": window}

    if arr.size == 0:
        z = np.zeros((1, window, 1), dtype=np.float32)
        meta["filtered"] = np.array([], dtype=np.float64)
        return z, meta

    filtered = _bandpass_filter(arr, fs)
    meta["filtered"] = filtered

    if filtered.size >= window:
        start = (filtered.size - window) // 2
        seg = filtered[start : start + window]
    else:
        seg = np.zeros(window, dtype=np.float64)
        seg[: filtered.size] = filtered

    m = float(np.mean(seg))
    s = float(np.std(seg)) or 1.0
    seg_z = ((seg - m) / s).astype(np.float32)
    model_input = seg_z.reshape(1, window, 1)
    return model_input, meta

