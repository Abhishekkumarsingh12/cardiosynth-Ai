"""
Report-based ECG guidance assistant (rule-based, no external API).

Context-aware: uses clinical predicted_class, confidence, risk_level, and optional HR.
Returns structured fields plus a plain reply for backward compatibility.

LLM orchestration (memory, grounding, OpenAI-compatible API) lives in
``assistant_llm_orchestrator.py``; those flows call ``build_report_guidance`` and
``assistant_service.build_dashboard_chat_structured`` when the LLM is disabled or unavailable.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.clinical_multiclass import CLINICAL_CLASS_NAMES

DISCLAIMER = "This is AI-generated guidance and not a medical diagnosis."


CONDITION_EXPLANATIONS = {
    "Normal": (
        "Normal sinus-style appearance on this automated view means the model’s summary aligns "
        "with a typical rhythm pattern — this does not rule out all disease without a full clinical ECG."
    ),
    "AFib": (
        "Atrial fibrillation (AFib) is an irregular and often rapid heart rhythm where the upper chambers "
        "of the heart (atria) beat chaotically instead of in sync with the ventricles. Only a clinician "
        "can diagnose AFib from a full tracing and history."
    ),
    "PVC": (
        "A premature ventricular contraction (PVC) is an extra heartbeat that starts in the ventricles, "
        "often felt as a skipped beat. Occasional PVCs can be benign, but frequency and symptoms matter — "
        "a clinician should interpret this in context."
    ),
    "Tachycardia": (
        "Tachycardia means a faster-than-normal heart rate. Many causes exist (stress, fever, arrhythmia, etc.); "
        "persistent or symptomatic fast rates warrant medical evaluation."
    ),
    "Bradycardia": (
        "Bradycardia means a slower-than-normal heart rate. It can be normal in athletes or medication-related, "
        "but symptomatic slow rates (fatigue, dizziness, fainting) need clinical review."
    ),
}


def _label_human(pred: Dict[str, Any]) -> str:
    c = str(pred.get("predicted_class") or pred.get("label") or "unknown")
    if c in CONDITION_EXPLANATIONS:
        return c
    m = {
        "N": "Normal beat morphology (model N)",
        "L": "Left bundle branch block pattern (model L)",
        "R": "Right bundle branch block pattern (model R)",
        "A": "Atrial / supraventricular pattern (model A)",
        "V": "Ventricular pattern (model V)",
    }
    return m.get(c, c)


def _condition_explanation(pred: Dict[str, Any]) -> str:
    label = str(pred.get("predicted_class") or pred.get("label") or "unknown")
    if label in CONDITION_EXPLANATIONS:
        return CONDITION_EXPLANATIONS[label]
    return (
        "This automated summary maps a beat-level model to broad clinical-style buckets for education only. "
        "Interpretation requires a qualified clinician."
    )


def _risk_explanation(pred: Dict[str, Any]) -> str:
    level = str(pred.get("risk_level") or "uncertain")
    conf = float(pred.get("confidence") or 0.0)
    rec = str(pred.get("recommendation") or pred.get("risk_rationale") or "")
    return (
        f"Automated risk tier: **{level}** (model confidence {conf:.2f}). "
        f"Suggested follow-up: {rec or 'see clinician with full ECG and symptoms.'}"
    )


def _summary_for_normal(pred: Dict[str, Any]) -> str:
    conf = float(pred.get("confidence") or 0.0)
    return (
        f"The automated summary is closest to **Normal** (confidence {conf:.2f}). "
        "This is reassuring from a screening-style tool only — it is not a definitive diagnosis."
    )


def _summary_for_abnormal(pred: Dict[str, Any]) -> str:
    label = str(pred.get("predicted_class") or pred.get("label") or "unknown")
    conf = float(pred.get("confidence") or 0.0)
    return (
        f"The summary suggests **{label}** (confidence {conf:.2f}). "
        "This pattern can have many causes; correlation with symptoms, medications, and a full ECG is essential."
    )


def _recommendation_from_risk(pred: Dict[str, Any]) -> str:
    r = str(pred.get("recommendation") or "").strip()
    if r:
        return r
    level = str(pred.get("risk_level") or "").lower()
    if level == "low":
        return "Maintain a healthy lifestyle with regular exercise, sleep, and balanced diet as appropriate."
    if level == "medium":
        return "Monitor symptoms and consider scheduling a clinical review if palpitations, chest pain, or fainting occur."
    if level == "high":
        return "Seek prompt medical evaluation — especially if you have chest pain, severe shortness of breath, or fainting."
    return "Discuss this tracing with a clinician; automated tools cannot confirm or exclude disease."


def _urgency_from_context(*, label: str, confidence: float, quality_label: str, risk_level: str) -> str:
    if quality_label == "bad" or confidence < 0.5:
        return "soon"
    if risk_level == "high" and confidence >= 0.6:
        return "urgent"
    if label not in {"Normal", "unknown"} and label in set(CLINICAL_CLASS_NAMES) and confidence >= 0.75:
        return "soon"
    return "routine"


def _danger_symptoms_text() -> str:
    return (
        "Seek urgent medical care now (emergency) if you have: chest pain/pressure, fainting, "
        "severe shortness of breath, new confusion, weakness on one side, or a very fast/irregular heartbeat "
        "with dizziness. If symptoms are severe, call local emergency services."
    )


def _faq_answer(msg: str, pred: Dict[str, Any]) -> Optional[str]:
    if "what is afib" in msg or "what's afib" in msg:
        return CONDITION_EXPLANATIONS["AFib"]
    if "pvc" in msg and ("what" in msg or "explain" in msg):
        return CONDITION_EXPLANATIONS["PVC"]
    if "tachycardia" in msg and "what" in msg:
        return CONDITION_EXPLANATIONS["Tachycardia"]
    if "bradycardia" in msg and "what" in msg:
        return CONDITION_EXPLANATIONS["Bradycardia"]
    if "dangerous" in msg or "how bad" in msg or "serious" in msg:
        level = str(pred.get("risk_level") or "")
        if level == "high":
            return (
                "The automated tier is **high** — this is a signal to involve a clinician promptly, "
                "especially with symptoms. It is not a standalone diagnosis."
            )
        if level == "medium":
            return (
                "The automated tier is **medium**. Many people need clinician context to know significance; "
                "symptoms and full ECG matter."
            )
        if str(pred.get("predicted_class")) == "Normal" and float(pred.get("confidence") or 0) > 0.75:
            return "The automated summary leans **Normal**, but any concerning symptoms still deserve clinical attention."
        return "Severity depends on symptoms, history, and full ECG — use this output only as educational context."
    return None


def build_report_guidance(
    user_message: str,
    *,
    prediction_result: Dict[str, Any],
    preprocess_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns:
      reply: str (markdown-ish, includes disclaimer)
      urgency: routine | soon | urgent | emergency_red_flag
      summary, condition_explanation, risk_explanation, recommendation: structured strings
    """
    pred = prediction_result or {}
    meta = preprocess_metadata or {}

    label = str(pred.get("label") or pred.get("predicted_class") or "unknown")
    conf = float(pred.get("confidence") or 0.0)
    quality = pred.get("signal_quality") or (meta.get("studio") or {}).get("signal_quality") or {}
    quality_label = str(quality.get("label") or "unknown")
    beats = pred.get("beats_analyzed") or (meta.get("studio") or {}).get("beats_analyzed")
    col = meta.get("selected_signal_column") or meta.get("source_column")
    risk_level = str(pred.get("risk_level") or "uncertain")

    msg = (user_message or "").strip().lower()
    uncertainty = quality_label in {"bad", "unknown"} or conf < 0.55

    urgency = _urgency_from_context(
        label=label, confidence=conf, quality_label=quality_label, risk_level=risk_level
    )
    if any(k in msg for k in ("danger", "red flag", "emergency", "911", "symptom")):
        urgency = "emergency_red_flag"

    is_normal = label == "Normal"

    condition_explanation = _condition_explanation(pred)
    risk_explanation = _risk_explanation(pred)
    recommendation = _recommendation_from_risk(pred)
    summary = _summary_for_normal(pred) if is_normal else _summary_for_abnormal(pred)

    faq = _faq_answer(msg, pred)

    parts: list[str] = []

    if faq:
        parts.append(faq)

    if any(k in msg for k in ("explain", "result", "what", "meaning")) or not msg:
        parts.append(
            f"Your report’s automated class is **{_label_human(pred)}** with confidence **{conf:.2f}**."
        )
        if beats is not None:
            parts.append(f"Beats analyzed: **{beats}**.")
        if col:
            parts.append(f"Signal column used: **{col}**.")
        if uncertainty:
            parts.append(
                "Signal quality and/or confidence limit how much we should read into this automated summary."
            )

    if any(k in msg for k in ("serious", "worried", "how bad")) and not faq:
        if uncertainty:
            parts.append(
                "The result is **uncertain** because confidence and/or signal quality are low. "
                "A clinician should review the full ECG and your symptoms."
            )
        else:
            parts.append(
                "This result may merit clinician review depending on your symptoms and history. "
                "It does **not** confirm a diagnosis by itself."
            )

    if any(k in msg for k in ("doctor", "see", "when should", "appointment")):
        if urgency == "routine":
            parts.append("Suggested timing: **routine** follow-up (next scheduled visit or within a few weeks).")
        elif urgency == "soon":
            parts.append("Suggested timing: **soon** (consider contacting a clinician within days).")
        elif urgency == "urgent":
            parts.append("Suggested timing: **urgent** (same-day/next-day clinical advice).")
        else:
            parts.append(_danger_symptoms_text())

    if any(k in msg for k in ("danger", "symptom", "red flag", "emergency")):
        parts.append(_danger_symptoms_text())

    if not parts:
        parts.append(
            "Ask about: the predicted class, what AFib or PVC means, risk level, when to see a doctor, or red-flag symptoms."
        )

    parts.append(f"\n---\n{DISCLAIMER}")

    reply = "\n\n".join(parts)

    return {
        "reply": reply,
        "urgency": urgency,
        "summary": summary,
        "condition_explanation": condition_explanation,
        "risk_explanation": re.sub(r"\*\*([^*]+)\*\*", r"\1", risk_explanation),
        "recommendation": recommendation,
    }


def guidance_summary_plain_for_pdf(
    *,
    prediction_result: Dict[str, Any],
    preprocess_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Compact plain text for PDF embedding."""
    g = build_report_guidance(
        "explain",
        prediction_result=prediction_result or {},
        preprocess_metadata=preprocess_metadata,
    )
    lines = [
        str(g.get("summary") or ""),
        str(g.get("condition_explanation") or ""),
        str(g.get("risk_explanation") or ""),
        str(g.get("recommendation") or ""),
        DISCLAIMER,
    ]
    return "\n\n".join(line for line in lines if line).strip()
