from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from fastapi import UploadFile

from app.config import get_settings
from app.core.classifier_errors import ClassifierUnavailableError
from app.services import ecg_prediction, ecg_preprocessing
from app.services.ecg_report_parser_service import parse_ecg_report_from_bytes
from app.services.risk_score_service import compute_risk_assessment, enrich_prediction_dict
from app.services.waveform_extraction_service import extract_waveform_signal_from_image_bytes
from app.utils.csv_ecg import CSVValidationError, parse_ecg_csv, validate_csv_file


@dataclass(frozen=True)
class IngestionDecision:
    file_type: str  # csv | image | pdf | unknown
    content_type: str  # text | waveform | hybrid
    mime_type: str
    notes: list[str]


DISCLAIMER = "This is AI-assisted analysis and not a medical diagnosis."


def _uploads_base() -> Path:
    base = Path(__file__).resolve().parent.parent.parent.parent / get_settings().uploads_dir
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sniff_file_type(raw: bytes, *, filename: str, content_type: str) -> str:
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if name.endswith(".csv") or ct in {"text/csv", "application/csv"}:
        return "csv"
    if name.endswith(".pdf") or ct == "application/pdf" or raw[:4] == b"%PDF":
        return "pdf"
    if any(name.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")) or ct.startswith("image/"):
        return "image"
    # Magic bytes
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if raw[:2] == b"\xff\xd8":
        return "image"
    return "unknown"


def _detect_content_type_for_visual(*, file_type: str, raw: bytes) -> tuple[str, dict[str, Any]]:
    """
    Prefer text extraction over waveform extraction for reliability.
    Returns (content_type, evidence dict).
    """
    evidence: dict[str, Any] = {}
    report = parse_ecg_report_from_bytes(file_type=file_type, data=raw)
    text_len = len((report.extracted_text or "").strip())
    evidence["report_parse_confidence"] = report.confidence
    evidence["report_fields_present"] = sum(1 for v in (report.fields or {}).values() if v not in (None, "", "—"))
    evidence["extracted_text_len"] = text_len

    # Heuristic: meaningful text implies text-based report. Hybrid if we also can extract a waveform with some confidence.
    looks_text = text_len >= 80 or evidence["report_fields_present"] >= 2
    if file_type == "image":
        wf = extract_waveform_signal_from_image_bytes(raw, target_len=2000)
        evidence["waveform_confidence"] = wf.confidence
        if looks_text and wf.confidence >= 0.35:
            return "hybrid", evidence
        if looks_text:
            return "text", evidence
        if wf.confidence >= 0.25:
            return "waveform", evidence
        return "text", evidence  # default to text-first, even if weak

    # PDF: without rasterization, waveform extraction is not attempted here. Text-first only.
    return ("text" if looks_text else "waveform"), evidence


def decide_ingestion(*, raw: bytes, filename: str, mime_type: str) -> IngestionDecision:
    ft = _sniff_file_type(raw, filename=filename, content_type=mime_type)
    notes: list[str] = []
    ct = (mime_type or "").strip() or "application/octet-stream"

    if ft == "csv":
        return IngestionDecision(file_type="csv", content_type="waveform", mime_type=ct, notes=notes)
    if ft in {"image", "pdf"}:
        content_type, evidence = _detect_content_type_for_visual(file_type=ft, raw=raw)
        if evidence.get("report_parse_confidence", 0.0) < 0.35:
            notes.append("Report text extraction confidence is low; results may be incomplete.")
        if content_type == "waveform":
            notes.append("Waveform-derived extraction is approximate and should not be treated as an exact ECG signal.")
        return IngestionDecision(file_type=ft, content_type=content_type, mime_type=ct, notes=notes)
    notes.append("Unrecognized file format. Supported: CSV, PNG/JPG, PDF.")
    return IngestionDecision(file_type="unknown", content_type="text", mime_type=ct, notes=notes)


def persist_upload_bytes(*, user_id: int, original_name: str, mime_type: str, raw: bytes) -> tuple[str, str, int]:
    uid = str(uuid.uuid4())
    ext = ""
    low = (original_name or "").lower()
    for e in (".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp"):
        if low.endswith(e):
            ext = e
            break
    safe_name = f"{user_id}_{uid}{ext or ''}"
    dest = _uploads_base() / safe_name
    dest.write_bytes(raw)
    return safe_name, str(dest.resolve()), len(raw)


def run_csv_raw_signal_pipeline(*, raw: bytes) -> tuple[np.ndarray, str, dict[str, Any]]:
    validate_csv_file(raw)
    try:
        samples, col_name, parse_meta = parse_ecg_csv(io.BytesIO(raw))
    except CSVValidationError as e:
        raise ValueError(str(e)) from e
    arr = np.asarray(samples, dtype=np.float64).ravel()
    return arr, col_name, parse_meta


def build_universal_analysis_payload(
    *,
    decision: IngestionDecision,
    raw: bytes,
    assumed_fs: float,
) -> tuple[Optional[np.ndarray], dict[str, Any], Optional[dict[str, Any]]]:
    """
    Returns (signal_or_none, preprocess_metadata, prediction_or_none)
    """
    meta: dict[str, Any] = {
        "ingestion": {
            "file_type": decision.file_type,
            "content_type": decision.content_type,
            "mime_type": decision.mime_type,
            "notes": decision.notes,
        }
    }

    if decision.file_type == "csv":
        sig, col, parse_meta = run_csv_raw_signal_pipeline(raw=raw)
        pre = ecg_preprocessing.preprocess_signal(sig, assumed_fs=assumed_fs)
        pred = ecg_prediction.predict_ecg(sig, assumed_fs)
        pred = enrich_prediction_dict(pred, meta)
        pred.update(compute_risk_assessment(pred, meta))
        meta["source_column"] = col
        meta.update(
            {
                "signal_stats": pre.get("stats"),
                "selected_signal_column": parse_meta.get("selected_signal_column"),
                "time_column": parse_meta.get("time_column"),
                "sampling_rate_hz_inferred": parse_meta.get("sampling_rate_hz_inferred"),
                "series_length_original": parse_meta.get("n_samples") or int(sig.size),
                "available_numeric_columns": parse_meta.get("available_numeric_columns"),
                "signal_stats_raw": parse_meta.get("signal_stats"),
                "preprocess_notes": pre.get("notes"),
                "reliability": {
                    "data_source": "raw_signal",
                    "reliability_label": "High",
                    "analysis_label": "High reliability (raw signal analysis)",
                    "disclaimer": DISCLAIMER,
                },
            }
        )
        return sig, meta, pred

    if decision.file_type in {"image", "pdf"}:
        # 1) Text-first report parsing.
        report = parse_ecg_report_from_bytes(file_type=decision.file_type, data=raw)
        meta["report_text"] = {
            "fields": report.fields,
            "confidence": report.confidence,
            "notes": report.notes,
        }
        meta["patient_friendly_explanation"] = report.patient_friendly_explanation

        # 2) Waveform extraction only for images (advanced, approximate).
        wf_pred: Optional[dict[str, Any]] = None
        wf_signal: Optional[np.ndarray] = None
        if decision.content_type in {"waveform", "hybrid"} and decision.file_type == "image":
            wf = extract_waveform_signal_from_image_bytes(raw, target_len=2000)
            meta["waveform_extraction"] = {
                "confidence": wf.confidence,
                "source": wf.source,
                "notes": wf.notes,
            }
            if wf.signal:
                wf_signal = np.asarray(wf.signal, dtype=np.float64).ravel()
                pre = ecg_preprocessing.preprocess_signal(wf_signal, assumed_fs=assumed_fs)
                meta["signal_stats"] = pre.get("stats")
                try:
                    wf_pred = ecg_prediction.predict_ecg(wf_signal, assumed_fs)
                    wf_pred = enrich_prediction_dict(wf_pred, meta)
                    wf_pred.update(compute_risk_assessment(wf_pred, meta))
                except ClassifierUnavailableError:
                    wf_pred = None

        # 3) Choose best "prediction_result" for storage:
        # - If waveform prediction exists, store it but clearly label approximate.
        # - Else store a report-only payload with no model label.
        if wf_pred:
            wf_pred["reliability_label"] = "Approximate"
            wf_pred["analysis_label"] = "Approximate waveform-derived analysis"
            wf_pred["data_source"] = "image_waveform"
            wf_pred["disclaimer"] = DISCLAIMER
            meta["reliability"] = {
                "data_source": "image_waveform",
                "reliability_label": "Approximate",
                "analysis_label": "Approximate waveform-derived analysis",
                "disclaimer": DISCLAIMER,
            }
            return wf_signal, meta, wf_pred

        meta["reliability"] = {
            "data_source": "report_text",
            "reliability_label": "Medium",
            "analysis_label": "Report-based interpretation (moderate to high reliability)",
            "disclaimer": DISCLAIMER,
        }
        pred_report = {
            "label": "report_interpretation",
            "predicted_class": "report_interpretation",
            "confidence": float(report.confidence),
            "status": "partial" if report.confidence < 0.45 else "success",
            "explanation_stub": report.patient_friendly_explanation,
            "mock": True,
            "data_source": "report_text",
            "reliability_label": "Medium",
            "analysis_label": "Report-based interpretation (moderate to high reliability)",
            "disclaimer": DISCLAIMER,
            "manual_input_required": bool(report.confidence < 0.35),
            "manual_input_fields": ["heart_rate", "pr_interval", "qrs_duration", "qtc", "symptoms"],
        }
        return None, meta, pred_report

    # Unknown type: return manual fallback request
    meta["reliability"] = {
        "data_source": "unknown",
        "reliability_label": "Approximate",
        "analysis_label": "Unsupported file type — manual input recommended",
        "disclaimer": DISCLAIMER,
    }
    pred_fallback = {
        "label": "unsupported_file",
        "predicted_class": "unknown",
        "confidence": 0.0,
        "status": "failed",
        "explanation_stub": "Unsupported file type. Please upload CSV, image, or PDF, or enter values manually. " + DISCLAIMER,
        "mock": True,
        "data_source": "unknown",
        "reliability_label": "Approximate",
        "analysis_label": "Unsupported file type — manual input recommended",
        "disclaimer": DISCLAIMER,
        "manual_input_required": True,
        "manual_input_fields": ["heart_rate", "pr_interval", "qrs_duration", "qtc", "symptoms"],
    }
    return None, meta, pred_fallback

