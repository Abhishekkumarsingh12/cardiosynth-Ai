"""Generate professional PDF summaries for ECG analysis reports (reportlab + matplotlib)."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

DISCLAIMER_PDF = "This is AI-generated analysis and not a medical diagnosis."


def _plot_figures(
    chart_series: List[float],
    window_waveform: Optional[List[float]],
    importance_normalized: Optional[List[float]],
) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(2, 1, figsize=(7.5, 4.2), dpi=110)
    ax0, ax1 = axes
    if chart_series:
        y = np.asarray(chart_series, dtype=np.float64)
        n = min(len(y), 4000)
        if len(y) > n:
            idx = np.linspace(0, len(y) - 1, n, dtype=int)
            y = y[idx]
            xs = np.arange(n)
        else:
            xs = np.arange(len(y))
        ax0.plot(xs, y, color="#0e7490", lw=0.9)
        ax0.set_title("Stored trace (normalized, preview)")
        ax0.set_xlabel("index")
        ax0.grid(True, alpha=0.25)

    if (
        window_waveform
        and importance_normalized
        and len(window_waveform) == len(importance_normalized)
        and len(window_waveform) > 0
    ):
        w = np.asarray(window_waveform, dtype=np.float64)
        im = np.clip(np.asarray(importance_normalized, dtype=np.float64), 0.0, 1.0)
        xw = np.arange(len(w))
        ax1.plot(xw, w, color="#0e7490", lw=1.0, label="Classifier window")
        ax1.fill_between(xw, np.min(w), w + im * (np.max(w) - np.min(w) + 1e-6) * 0.35, color="#ea580c", alpha=0.25)
        ax1.set_title("Classifier input window + saliency (normalized overlay)")
        ax1.set_xlabel("timestep")
        ax1.grid(True, alpha=0.25)
    else:
        ax1.text(0.5, 0.5, "Saliency plot unavailable", ha="center", va="center")
        ax1.axis("off")

    fig.tight_layout()
    png_buf = BytesIO()
    fig.savefig(png_buf, format="png", bbox_inches="tight")
    plt.close(fig)
    png_buf.seek(0)
    return png_buf.read()


def build_analysis_pdf_bytes(
    *,
    analysis_id: int,
    created_at_str: str,
    filename: str,
    signal_column: str,
    chart_series: List[float],
    prediction: Dict[str, Any],
    risk_level: str,
    risk_score: Any,
    risk_rationale: str,
    guidance_summary: str,
    explanation_summary: str,
    explanation_text: str = "",
    important_regions: Optional[List[Dict[str, Any]]] = None,
    window_waveform: Optional[List[float]],
    importance_normalized: Optional[List[float]],
) -> bytes:
    """Build a single PDF in memory."""
    png = _plot_figures(chart_series, window_waveform, importance_normalized)

    buf_pdf = BytesIO()
    doc = SimpleDocTemplate(buf_pdf, pagesize=letter, topMargin=0.65 * inch, bottomMargin=0.65 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="TitleCS",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=12,
    )
    h2 = ParagraphStyle(name="H2CS", parent=styles["Heading2"], fontSize=12, spaceAfter=8)
    body = ParagraphStyle(name="BodyCS", parent=styles["Normal"], fontSize=10, leading=14)

    story: list[Any] = []
    story.append(Paragraph("CardioSynth AI", title_style))
    story.append(Paragraph("ECG analysis report", styles["Heading2"]))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph(f"<b>Report ID:</b> {analysis_id}", body))
    story.append(Paragraph(f"<b>Upload:</b> {filename}", body))
    story.append(Paragraph(f"<b>Date (UTC):</b> {created_at_str}", body))
    story.append(Paragraph(f"<b>Signal column:</b> {signal_column}", body))
    story.append(Spacer(1, 0.12 * inch))

    label = prediction.get("label") or prediction.get("predicted_class") or "—"
    conf = prediction.get("confidence")
    conf_s = f"{float(conf) * 100:.1f}%" if isinstance(conf, (int, float)) else "—"
    story.append(Paragraph("<b>Prediction</b>", h2))
    story.append(Paragraph(f"Class: {label}", body))
    story.append(Paragraph(f"Confidence: {conf_s}", body))
    probs = prediction.get("all_probabilities")
    if isinstance(probs, list) and probs:
        story.append(
            Paragraph(
                "<b>Class probabilities (clinical view):</b> "
                + ", ".join(f"{float(p) * 100:.1f}%" for p in probs),
                body,
            )
        )
    rs = risk_score
    if isinstance(rs, (int, float)) and float(rs) <= 1.0:
        rs_display = f"{float(rs):.2f}"
    else:
        rs_display = str(rs)
    story.append(Paragraph(f"<b>Risk level:</b> {risk_level.upper()} (score: {rs_display})", body))
    story.append(Paragraph(risk_rationale, body))
    rec_pdf = str(prediction.get("recommendation") or "").strip()
    if rec_pdf:
        story.append(Paragraph(f"<b>Recommendation:</b> {rec_pdf}", body))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("<b>Explainability summary</b>", h2))
    story.append(Paragraph(explanation_summary or "Not available.", body))
    if explanation_text:
        story.append(Spacer(1, 0.06 * inch))
        story.append(Paragraph("<b>Interpretation</b>", h2))
        story.append(Paragraph(explanation_text, body))
    if important_regions:
        top = important_regions[:3]
        reg_s = ", ".join(f"{int(r.get('start', 0))}–{int(r.get('end', 0))}" for r in top if isinstance(r, dict))
        if reg_s:
            story.append(Paragraph(f"<b>Top salient regions (sample indices):</b> {reg_s}", body))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("<b>Guidance summary</b>", h2))
    story.append(Paragraph(guidance_summary.replace("\n", "<br/>"), body))
    story.append(Spacer(1, 0.15 * inch))

    story.append(RLImage(BytesIO(png), width=6.5 * inch, height=3.4 * inch))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph(f"<i>{DISCLAIMER_PDF}</i>", body))

    doc.build(story)
    buf_pdf.seek(0)
    return buf_pdf.read()
