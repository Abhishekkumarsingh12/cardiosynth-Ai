"""
Medical caution: pre-check user messages, post-process model output, block overconfident diagnosis tone.
"""

from __future__ import annotations

import re
from typing import Any, Dict

# Patterns suggesting urgent clinical evaluation (not diagnosis — triage language only)
_RED_FLAG = re.compile(
    r"\b(chest\s*pain|crushing|heart\s*attack|mi\b|myocardial|faint|fainting|syncope|"
    r"unconscious|stroke|can't\s*breathe|cannot\s*breathe|severe\s*shortness|sob\b|"
    r"call\s*911|emergency)\b",
    re.I,
)


def user_message_has_red_flags(text: str) -> bool:
    return bool(_RED_FLAG.search(text or ""))


def build_safety_system_instructions() -> str:
    return (
        "Safety and scope (must follow):\n"
        "- You are an educational assistant for ECG-related questions. You are NOT a doctor.\n"
        "- Never state or imply a definitive diagnosis (avoid phrases like 'you definitely have', 'you have X for sure').\n"
        "- Use cautious language: 'may suggest', 'could be consistent with', 'worth discussing with a clinician'.\n"
        "- If confidence is low or signal/report quality is uncertain, say so clearly.\n"
        "- If the data source is image-derived waveform, call it approximate and less reliable than raw signal.\n"
        "- If the user mentions chest pain, fainting, severe breathlessness, or similar, advise urgent in-person/emergency care calmly.\n"
        "- Include a brief disclaimer that this is AI-assisted information, not a substitute for professional care.\n"
        "- Do not prescribe medications or give dosing. Do not tell the user to stop prescribed drugs.\n"
    )


def post_process_reply(text: str, *, grounding: Dict[str, Any]) -> str:
    """Light touch: ensure disclaimer line if missing; trim excess."""
    t = (text or "").strip()
    if not t:
        return t
    low = t.lower()
    if (
        "not a medical diagnosis" not in low
        and "not a substitute" not in low
        and "ai-assisted" not in low
        and "ai-generated" not in low
    ):
        t += (
            "\n\nThis is AI-assisted guidance based on the information shown in CardioSynth and "
            "should not replace evaluation by a qualified clinician."
        )
    return t


def infer_tone(grounding: Dict[str, Any], user_message: str) -> str:
    risk = str(grounding.get("risk_level") or "").lower()
    conf = float(grounding.get("confidence") or 0.0)
    if user_message_has_red_flags(user_message):
        return "serious_calm"
    if risk == "high" or conf < 0.45:
        return "cautious"
    if str(grounding.get("prediction") or "").lower() in {"normal", "report_interpretation"} and conf >= 0.6:
        return "reassuring"
    return "neutral_helpful"


def merge_sources_used(
    *,
    used_prediction: bool,
    used_report_values: bool,
    used_history: bool,
    used_patient_history: bool,
) -> Dict[str, bool]:
    return {
        "prediction": used_prediction,
        "report_values": used_report_values,
        "history": used_history,
        "patient_history": used_patient_history,
    }
