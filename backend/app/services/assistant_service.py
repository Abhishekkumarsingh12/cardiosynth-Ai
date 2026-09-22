"""
Rule-based AI assistant (no LLM). Context-aware using latest prediction + risk fields.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.chat_assistant_service import (
    CONDITION_EXPLANATIONS,
    DISCLAIMER,
    _faq_answer,
    _recommendation_from_risk,
    _summary_for_abnormal,
    _summary_for_normal,
)


def _lower(s: str) -> str:
    return s.lower().strip()


def build_dashboard_chat_structured(user_message: str, context: Optional[dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Structured chat for Dashboard /api/assistant/chat.
    """
    ctx = context or {}
    pred = ctx.get("last_prediction") or {}
    msg = _lower(user_message)

    label = str(pred.get("predicted_class") or pred.get("label") or "unknown")
    is_normal = label == "Normal"
    conf = float(pred.get("confidence") or 0.0)

    summary = _summary_for_normal(pred) if is_normal else _summary_for_abnormal(pred)
    condition_explanation = CONDITION_EXPLANATIONS.get(
        label,
        "The model produced an automated rhythm-style summary for education — not a diagnosis.",
    )
    risk_level = str(pred.get("risk_level") or "uncertain")
    rec = _recommendation_from_risk(pred)
    risk_explanation = (
        f"Automated risk tier: {risk_level} (confidence {conf:.2f}). Follow-up: {rec}"
    )

    faq = _faq_answer(msg, pred)
    parts: list[str] = []

    if faq:
        parts.append(faq)

    if any(k in msg for k in ("explain", "what does", "meaning", "result", "prediction")):
        parts.append(
            f"Latest analysis summary: **{label}** (confidence {conf:.2f}). "
            f"{condition_explanation[:280]}{'…' if len(condition_explanation) > 280 else ''}"
        )

    if any(k in msg for k in ("exercise", "workout", "run", "cardio")):
        parts.append(
            "General tip: aim for gradual aerobic activity if your clinician says it is safe, "
            "warm up, stay hydrated, and stop if you feel dizzy or chest discomfort."
        )

    if any(k in msg for k in ("sleep", "stress", "anxiety")):
        parts.append(
            "Sleep and stress matter for heart health: consistent sleep schedule, limited late "
            "caffeine, and brief daily relaxation practices can help—discuss persistent symptoms "
            "with a professional."
        )

    if any(k in msg for k in ("diet", "food", "salt", "sodium")):
        parts.append(
            "Diet patterns often discussed with clinicians include more vegetables, fiber, and "
            "moderating sodium—personal needs vary, especially with medications or conditions."
        )

    if any(k in msg for k in ("smoke", "smoking", "tobacco")):
        parts.append(
            "Stopping smoking is one of the strongest steps for cardiovascular risk—your care "
            "team can suggest cessation supports."
        )

    if not parts:
        parts.append(
            "I can explain your latest prediction, common terms (AFib, PVC), or share general wellness tips. "
            "What would you like to know?"
        )

    if re.search(r"\becg\b|\bheart\b|\brhythm\b", msg) and not faq:
        parts.insert(
            0,
            "ECG patterns should be reviewed by qualified clinicians with full clinical context.",
        )

    body = "\n\n".join(parts)
    reply = f"{body}\n\n---\n{DISCLAIMER}"

    return {
        "reply": reply,
        "summary": summary,
        "condition_explanation": condition_explanation,
        "risk_explanation": risk_explanation,
        "recommendation": rec,
    }


def build_assistant_reply(user_message: str, context: Optional[dict[str, Any]] = None) -> str:
    """Backward-compatible plain reply string."""
    return build_dashboard_chat_structured(user_message, context)["reply"]
