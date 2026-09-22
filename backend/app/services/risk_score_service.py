"""
Risk scoring from clinical multi-class prediction (research / education only).

Uses the user-facing clinical label (Normal, AFib, PVC, Tachycardia, Bradycardia) and
top-class confidence. Outputs risk_level, risk_score on [0, 1], recommendation text,
and risk_rationale (aligned with recommendation for backward compatibility).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.clinical_multiclass import CLINICAL_CLASS_NAMES

_UNRELIABLE_LABELS = {
    "unknown",
    "insufficient_data",
    "model_unavailable",
    "classifier_not_trained",
    "inference_error",
}

# Map legacy stored MIT-BIH beat letters to clinical buckets for risk rules (older DB rows).
_LEGACY_BEAT_TO_CLINICAL = {"N": "Normal", "L": "Normal", "R": "Normal", "A": "AFib", "V": "PVC"}


def _effective_clinical_label(pred: Dict[str, Any]) -> str:
    pc = str(pred.get("predicted_class") or "").strip()
    if pc in set(CLINICAL_CLASS_NAMES):
        return pc
    lab = str(pred.get("label") or "").strip()
    if lab in _LEGACY_BEAT_TO_CLINICAL:
        return _LEGACY_BEAT_TO_CLINICAL[lab]
    return lab


def _quality_bad(pred: Dict[str, Any], meta: Optional[Dict[str, Any]]) -> bool:
    sq = pred.get("signal_quality") or ((meta or {}).get("studio") or {}).get("signal_quality") or {}
    return str(sq.get("label") or "") == "bad"


def compute_risk_assessment(
    pred: Dict[str, Any],
    preprocess_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Rules (automated — not diagnostic):
      - Normal + confidence > 0.8 → low
      - Abnormal + confidence in [0.5, 0.8] → medium
      - Abnormal + confidence > 0.8 → high
      - Otherwise → uncertain (low confidence or borderline)

    Returns:
      risk_level: low | medium | high | uncertain
      risk_score: float 0.0–1.0 (higher = more concern in this heuristic)
      recommendation: patient-facing suggestion line
      risk_rationale: same as recommendation (legacy consumers)
    """
    label = _effective_clinical_label(pred)
    conf = float(pred.get("confidence") or 0.0)
    meta = preprocess_metadata or {}
    bad_q = _quality_bad(pred, meta)

    if label in _UNRELIABLE_LABELS or not label or label == "unknown":
        rec = "Automated result is unreliable; consult a clinician with the full ECG recording."
        return {
            "risk_level": "uncertain",
            "risk_score": 0.5,
            "recommendation": rec,
            "risk_rationale": rec,
        }

    is_normal = label == "Normal"
    abnormal = not is_normal and label in set(CLINICAL_CLASS_NAMES)

    if is_normal and conf > 0.8:
        level = "low"
        score = 0.15
        rec = "Normal condition, maintain healthy lifestyle"
    elif abnormal and 0.5 <= conf <= 0.8:
        level = "medium"
        score = 0.55
        rec = "Monitor regularly and consult if symptoms persist"
    elif abnormal and conf > 0.8:
        level = "high"
        score = 0.9
        rec = "Consult a cardiologist immediately"
    elif is_normal and conf <= 0.8:
        level = "medium"
        score = 0.4
        rec = "Monitor regularly and consult if symptoms persist"
    else:
        level = "uncertain"
        score = 0.5
        rec = "Automated confidence is low; seek clinical review of the tracing."

    if bad_q and level == "low":
        level = "medium"
        score = min(1.0, score + 0.15)
        rec = "Monitor regularly and consult if symptoms persist"

    return {
        "risk_level": level,
        "risk_score": round(score, 3),
        "recommendation": rec,
        "risk_rationale": rec,
    }


def enrich_prediction_dict(
    pred: Optional[Dict[str, Any]],
    preprocess_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge risk fields when absent or stale (e.g. missing recommendation or legacy 0–100 scores)."""
    if not pred:
        return {}
    out = dict(pred)
    rs = out.get("risk_score")
    legacy_scale = isinstance(rs, (int, float)) and float(rs) > 1.01
    need_refresh = (
        out.get("risk_level") is None
        or out.get("risk_score") is None
        or out.get("recommendation") is None
        or legacy_scale
    )
    if need_refresh:
        r = compute_risk_assessment(out, preprocess_metadata)
        out.update(r)
    return out
