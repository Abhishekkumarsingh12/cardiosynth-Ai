"""
Clinical 5-class view derived from MIT-BIH beat-classifier probabilities + heart rate.

The deployed Keras model remains a 5-way softmax on beat morphologies (N, L, R, A, V).
This module maps those probabilities into user-facing clinical buckets:

  Normal, AFib, PVC, Tachycardia, Bradycardia

Mapping is heuristic (research / education — not a standalone diagnostic standard).
For true rhythm labels (e.g. AFib from continuous rhythm strips), retrain with rhythm-level labels.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple

import numpy as np

# Order matches API contract: index i ↔ all_probabilities[i]
CLINICAL_CLASS_NAMES: List[str] = ["Normal", "AFib", "PVC", "Tachycardia", "Bradycardia"]

# HR gates (BPM) for rate-related classes — tunable constants
TACHYCARDIA_BPM = 100.0
BRADYCARDIA_BPM = 60.0


def clinical_probabilities_from_beat_model(
    beat_probabilities: Mapping[str, float],
    *,
    heart_rate_bpm: Optional[float],
) -> np.ndarray:
    """
    Build a normalized 5-vector over CLINICAL_CLASS_NAMES from beat-level softmax + optional HR.

    beat_probabilities: class name → probability (sums ~1 over N,L,R,A,V)
    """
    p = np.zeros(len(CLINICAL_CLASS_NAMES), dtype=np.float64)
    pm = {k: float(v) for k, v in beat_probabilities.items()}

    p[0] = pm.get("N", 0.0) + 0.35 * (pm.get("L", 0.0) + pm.get("R", 0.0))
    p[1] = pm.get("A", 0.0) + 0.2 * (pm.get("L", 0.0) + pm.get("R", 0.0))
    p[2] = pm.get("V", 0.0)

    hr = heart_rate_bpm
    if hr is not None and np.isfinite(hr):
        h = float(hr)
        if h >= TACHYCARDIA_BPM:
            excess = min(1.0, (h - TACHYCARDIA_BPM) / max(TACHYCARDIA_BPM, 1.0))
            p[3] += 0.12 + 0.38 * excess
        elif h <= BRADYCARDIA_BPM:
            deficit = min(1.0, (BRADYCARDIA_BPM - h) / max(BRADYCARDIA_BPM, 1.0))
            p[4] += 0.12 + 0.38 * deficit

    p = np.maximum(p, 1e-9)
    p /= p.sum()
    return p


def clinical_prediction_from_beat_output(
    *,
    beat_probabilities: Dict[str, float],
    heart_rate_bpm: Optional[float],
) -> Tuple[str, int, float, List[float], np.ndarray]:
    """
    Returns:
      predicted_class, class_index, confidence, all_probabilities (5 floats), clinical_probs array
    """
    cprobs = clinical_probabilities_from_beat_model(beat_probabilities, heart_rate_bpm=heart_rate_bpm)
    idx = int(np.argmax(cprobs))
    conf = float(cprobs[idx])
    name = CLINICAL_CLASS_NAMES[idx]
    return name, idx, conf, cprobs.astype(float).tolist(), cprobs


def rhythm_hint_clinical(clinical_name: str) -> str:
    return {
        "Normal": "sinus_normal",
        "AFib": "atrial_fibrillation_hint",
        "PVC": "premature_ventricular",
        "Tachycardia": "tachycardia_rate",
        "Bradycardia": "bradycardia_rate",
    }.get(clinical_name, "unknown")
