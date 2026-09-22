"""
ECG preprocessing service.

Real implementation would: resample, denoise, baseline correction, R-peak detection, etc.
This module normalizes a 1-D numeric series and returns lightweight stats for the API/UI.
"""

from __future__ import annotations

from typing import Any, List, Optional

import numpy as np


def preprocess_signal(samples: List[float], assumed_fs: Optional[float] = None) -> dict[str, Any]:
    """
    Deterministic preprocessing placeholder suitable for charts and downstream MOCK prediction.

    Replace `preprocess_signal` body with your pipeline; keep the return shape stable for callers.
    """
    arr = np.asarray(samples, dtype=np.float64)
    if arr.size == 0:
        return {
            "normalized_series": [],
            "sampling_rate_hz": assumed_fs,
            "stats": {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "length": 0},
            "notes": "empty_signal",
        }

    # Z-score normalize for display
    mean = float(np.mean(arr))
    std = float(np.std(arr)) or 1.0
    norm = ((arr - mean) / std).tolist()

    stats = {
        "mean": mean,
        "std": std,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "length": int(arr.size),
    }

    return {
        "normalized_series": norm[:5000],  # cap payload for API
        "sampling_rate_hz": assumed_fs,
        "stats": stats,
        "notes": "z_score_normalize_only",
    }
