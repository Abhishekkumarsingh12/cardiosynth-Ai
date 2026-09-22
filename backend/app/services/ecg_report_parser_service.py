from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


_NUM = r"(?P<val>\d+(?:\.\d+)?)"


@dataclass(frozen=True)
class ReportParseResult:
    extracted_text: str
    fields: Dict[str, Any]
    patient_friendly_explanation: str
    confidence: float
    notes: list[str]


def _try_import_pytesseract():
    try:
        import pytesseract  # type: ignore

        return pytesseract
    except Exception:
        return None


def _normalize_ws(s: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\s+", " ", s or "")).strip()


def _find_first(patterns: list[str], text: str) -> Optional[Tuple[float, str]]:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            v = float(m.group("val"))
        except Exception:
            continue
        return v, m.group(0)
    return None


def _extract_fields(text: str) -> tuple[dict[str, Any], float, list[str]]:
    """
    Extract common ECG report values from OCR / PDF text.
    Returns (fields, confidence, notes).
    """
    t = _normalize_ws(text)
    notes: list[str] = []
    fields: dict[str, Any] = {
        "heart_rate": None,
        "pr_interval": None,
        "qrs_duration": None,
        "qt": None,
        "qtc": None,
        "interpretation": None,
    }

    hr = _find_first(
        [
            rf"(?:heart\s*rate|hr)\s*[:=]?\s*{_NUM}\s*(?:bpm)?",
            rf"{_NUM}\s*(?:bpm)\b",
        ],
        t,
    )
    if hr:
        fields["heart_rate"] = hr[0]
    pr = _find_first([rf"\bpr\s*(?:interval)?\s*[:=]?\s*{_NUM}\s*ms\b"], t)
    if pr:
        fields["pr_interval"] = pr[0]
    qrs = _find_first([rf"\bqrs\s*(?:duration)?\s*[:=]?\s*{_NUM}\s*ms\b"], t)
    if qrs:
        fields["qrs_duration"] = qrs[0]
    qt = _find_first([rf"\bqt\s*(?:interval)?\s*[:=]?\s*{_NUM}\s*ms\b"], t)
    if qt:
        fields["qt"] = qt[0]
    qtc = _find_first([rf"\bqtc\b\s*[:=]?\s*{_NUM}\s*ms\b", rf"\bqt\s*/\s*qtc\s*[:=]?\s*\d+(?:\.\d+)?\s*/\s*{_NUM}\s*ms\b"], t)
    if qtc:
        fields["qtc"] = qtc[0]

    # Interpretation / impression lines (best-effort).
    interp = None
    for pat in [
        r"(?:interpretation|impression|conclusion)\s*[:=]\s*(.+)$",
        r"(?:summary)\s*[:=]\s*(.+)$",
    ]:
        m = re.search(pat, text or "", flags=re.IGNORECASE | re.MULTILINE)
        if m:
            interp = _normalize_ws(m.group(1))[:600]
            break
    if interp:
        fields["interpretation"] = interp

    present = sum(1 for k in ("heart_rate", "pr_interval", "qrs_duration", "qtc", "interpretation") if fields.get(k) not in (None, "", "—"))
    # Conservative confidence: 0.2 base + 0.15 per key field, capped.
    conf = min(0.9, 0.2 + 0.15 * float(present))
    if present == 0:
        notes.append("No structured ECG values detected in extracted text.")
    return fields, conf, notes


def _patient_explanation(fields: dict[str, Any]) -> str:
    hr = fields.get("heart_rate")
    pr = fields.get("pr_interval")
    qrs = fields.get("qrs_duration")
    qtc = fields.get("qtc")
    interp = fields.get("interpretation")

    bits: list[str] = []
    if hr is not None:
        bits.append(f"Heart rate appears to be about {hr:g} bpm.")
    if pr is not None:
        bits.append(f"PR interval is listed as {pr:g} ms.")
    if qrs is not None:
        bits.append(f"QRS duration is listed as {qrs:g} ms.")
    if qtc is not None:
        bits.append(f"QTc is listed as {qtc:g} ms.")
    if interp:
        bits.append(f"Report impression: {interp}")

    if not bits:
        return (
            "I couldn’t reliably read key ECG measurements from this file. "
            "If you have them available, you can enter heart rate, PR, QRS, QT/QTc manually for a better summary."
        )
    return " ".join(bits) + " This is an AI-assisted summary and not a medical diagnosis."


def extract_text_from_pdf_bytes(pdf_bytes: bytes, *, max_pages: int = 3) -> tuple[str, list[str]]:
    notes: list[str] = []
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as e:
        return "", [f"PDF text extraction unavailable (pypdf import failed: {e})."]

    try:
        reader = PdfReader(io_bytes := __import__("io").BytesIO(pdf_bytes))
        pages = reader.pages[: max(1, int(max_pages))]
        texts: list[str] = []
        for i, p in enumerate(pages):
            try:
                txt = p.extract_text() or ""
                if txt.strip():
                    texts.append(txt)
            except Exception:
                notes.append(f"Failed extracting text from page {i+1}.")
        return "\n".join(texts).strip(), notes
    except Exception as e:
        return "", [f"PDF parsing failed: {e}"]


def extract_text_from_image_bytes(image_bytes: bytes) -> tuple[str, list[str]]:
    notes: list[str] = []
    pytesseract = _try_import_pytesseract()
    if pytesseract is None:
        return "", ["OCR unavailable (pytesseract not importable)."]

    try:
        from PIL import Image  # type: ignore
        import io

        img = Image.open(io.BytesIO(image_bytes))
        # Light preprocessing to help OCR, without over-committing.
        img = img.convert("L")
        text = pytesseract.image_to_string(img) or ""
        return text.strip(), notes
    except Exception as e:
        return "", [f"OCR failed: {e}"]


def parse_ecg_report_text(text: str) -> ReportParseResult:
    fields, conf, notes = _extract_fields(text)
    expl = _patient_explanation(fields)
    return ReportParseResult(
        extracted_text=text or "",
        fields=fields,
        patient_friendly_explanation=expl,
        confidence=float(conf),
        notes=notes,
    )


def parse_ecg_report_from_bytes(*, file_type: str, data: bytes) -> ReportParseResult:
    """
    file_type: 'pdf' | 'image'
    """
    extracted = ""
    notes: list[str] = []
    if file_type == "pdf":
        extracted, notes = extract_text_from_pdf_bytes(data)
    elif file_type == "image":
        extracted, notes = extract_text_from_image_bytes(data)
    else:
        return ReportParseResult(extracted_text="", fields={}, patient_friendly_explanation="", confidence=0.0, notes=["Unsupported file_type"])

    res = parse_ecg_report_text(extracted)
    # Merge notes; keep confidence conservative if extraction produced tiny text.
    merged_notes = list(notes) + list(res.notes)
    conf = float(res.confidence)
    if len(_normalize_ws(extracted)) < 40:
        conf = min(conf, 0.35)
        merged_notes.append("Extracted text is very short; report parsing confidence reduced.")

    return ReportParseResult(
        extracted_text=extracted,
        fields=res.fields,
        patient_friendly_explanation=res.patient_friendly_explanation,
        confidence=conf,
        notes=merged_notes,
    )

