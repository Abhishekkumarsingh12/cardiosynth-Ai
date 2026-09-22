"""
Build structured grounding payloads for the assistant from ECG analysis data.

All values are for AI context only — not clinical truth.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import ECGAnalysis


def _ingestion_report_type(meta: Dict[str, Any]) -> str:
    ing = meta.get("ingestion") or {}
    ft = str(ing.get("file_type") or "").lower()
    ct = str(ing.get("content_type") or "").lower()
    if ft == "csv":
        return "csv"
    if ft == "pdf":
        return "hybrid" if ct == "hybrid" else "pdf"
    if ft == "image":
        if ct == "hybrid":
            return "hybrid"
        if ct == "waveform":
            return "image"
        return "image"
    return "unknown"


def _reliability_note(meta: Dict[str, Any], pred: Dict[str, Any]) -> str:
    rel = meta.get("reliability") or {}
    ds = str(rel.get("data_source") or pred.get("data_source") or "")
    label = str(rel.get("analysis_label") or pred.get("analysis_label") or "")
    if ds == "raw_signal":
        return "Higher reliability: analysis used raw digitized ECG samples (CSV)."
    if ds == "report_text":
        return "Moderate reliability: answers lean on extracted report text (OCR/PDF); verify against the original report."
    if ds == "image_waveform":
        return "Lower reliability: waveform was approximated from an image — not equivalent to raw signal."
    if label:
        return label
    return "Reliability depends on upload type and extraction quality."


def build_grounding_bundle(
    *,
    prediction_result: Optional[Dict[str, Any]],
    preprocess_metadata: Optional[Dict[str, Any]],
    manual_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    pred = dict(prediction_result or {})
    meta = dict(preprocess_metadata or {})
    studio = meta.get("studio") or {}
    report_text = meta.get("report_text") or {}
    fields = report_text.get("fields") if isinstance(report_text, dict) else None
    if not isinstance(fields, dict):
        fields = {}

    report_values = {
        "heart_rate": fields.get("heart_rate"),
        "pr_interval": fields.get("pr_interval"),
        "qrs_duration": fields.get("qrs_duration"),
        "qt": fields.get("qt"),
        "qtc": fields.get("qtc"),
        "interpretation": fields.get("interpretation"),
    }

    sq = pred.get("signal_quality") or studio.get("signal_quality") or {}
    signal_quality = str(sq.get("label") or sq.get("quality") or pred.get("signal_quality_label") or "unknown")

    bundle: Dict[str, Any] = {
        "prediction": str(pred.get("predicted_class") or pred.get("label") or "unknown"),
        "confidence": float(pred.get("confidence") or 0.0),
        "risk_level": str(pred.get("risk_level") or "uncertain"),
        "signal_quality": signal_quality,
        "report_type": _ingestion_report_type(meta),
        "report_values": report_values,
        "explanation_summary": str(pred.get("explanation_stub") or pred.get("studio_summary") or "")[:2000],
        "reliability_note": _reliability_note(meta, pred),
        "data_source": str((meta.get("reliability") or {}).get("data_source") or pred.get("data_source") or ""),
        "beats_analyzed": pred.get("beats_analyzed") or studio.get("beats_analyzed"),
        "patient_friendly_explanation": str(meta.get("patient_friendly_explanation") or "")[:2000],
    }
    mi = manual_input or meta.get("manual_input")
    if isinstance(mi, dict) and mi:
        bundle["manual_input"] = {k: mi.get(k) for k in ("heart_rate", "pr_interval", "qrs_duration", "qtc", "symptoms") if mi.get(k) not in (None, "")}
    return bundle


def fetch_recent_analysis_labels(db: Session, *, user_id: int, limit: int = 3) -> List[Dict[str, Any]]:
    rows = (
        db.query(ECGAnalysis)
        .filter(ECGAnalysis.user_id == user_id)
        .order_by(ECGAnalysis.created_at.desc())
        .limit(limit)
        .all()
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        pr = r.prediction_result or {}
        out.append(
            {
                "analysis_id": r.id,
                "label": str(pr.get("predicted_class") or pr.get("label")),
                "confidence": pr.get("confidence"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return out


def load_analysis_for_user(
    db: Session, *, analysis_id: int, user_id: int
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    row = db.get(ECGAnalysis, analysis_id)
    if not row or row.user_id != user_id:
        return None
    return (dict(row.prediction_result or {}), dict(row.preprocess_metadata or {}))
