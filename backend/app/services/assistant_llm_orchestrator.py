"""
Orchestrates LLM + grounding + memory + safety for /assistant/chat and /assistant/report-guidance.

Falls back to existing rule-based assistants when LLM is unavailable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.assistant_service import build_dashboard_chat_structured
from app.services.chat_assistant_service import build_report_guidance
from app.services.chat_grounding_service import (
    build_grounding_bundle,
    fetch_recent_analysis_labels,
    load_analysis_for_user,
)
from app.services.chat_memory_service import get_chat_memory
from app.services.chat_safety_service import (
    infer_tone,
    merge_sources_used,
    post_process_reply,
    user_message_has_red_flags,
)
from app.services.llm_chat_service import is_llm_available, run_llm_turn


def _resolve_dashboard_prediction(
    db: Optional[Session],
    *,
    user_id: int,
    context: Optional[Dict[str, Any]],
    analysis_id: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    pred: Dict[str, Any] = {}
    meta: Dict[str, Any] = {}
    ctx = dict(context or {})

    if analysis_id is not None and db is not None:
        loaded = load_analysis_for_user(db, analysis_id=analysis_id, user_id=user_id)
        if loaded:
            pred, meta = loaded

    if not pred and ctx.get("last_prediction"):
        pred = dict(ctx["last_prediction"])
    if not meta and ctx.get("preprocess_metadata"):
        meta = dict(ctx["preprocess_metadata"])

    if not pred and db is not None:
        from app.models import ECGAnalysis

        last = (
            db.query(ECGAnalysis)
            .filter(ECGAnalysis.user_id == user_id)
            .order_by(ECGAnalysis.created_at.desc())
            .first()
        )
        if last and last.prediction_result:
            pred = dict(last.prediction_result or {})
            meta = dict(last.preprocess_metadata or {})

    return pred, meta


def run_dashboard_assistant(
    *,
    db: Session,
    user_id: int,
    message: str,
    context: Optional[Dict[str, Any]],
    analysis_id: Optional[int],
    session_id: Optional[str],
    include_history: bool,
) -> Dict[str, Any]:
    pred, meta = _resolve_dashboard_prediction(db, user_id=user_id, context=context, analysis_id=analysis_id)
    manual = None
    if isinstance(meta.get("manual_input"), dict):
        manual = meta.get("manual_input")

    grounding = build_grounding_bundle(prediction_result=pred, preprocess_metadata=meta, manual_input=manual)
    patient_hist: List[Dict[str, Any]] = []
    try:
        patient_hist = fetch_recent_analysis_labels(db, user_id=user_id, limit=3)
    except Exception:
        patient_hist = []
    if patient_hist:
        grounding["history"] = patient_hist

    mem = get_chat_memory()
    prior: List[dict] = []
    if include_history:
        prior = mem.get_recent(user_id, session_id=session_id, analysis_id=analysis_id)

    used_report = any(v not in (None, "", "—") for v in (grounding.get("report_values") or {}).values())
    used_pred = bool(pred)
    used_hist = bool(prior)
    used_ph = bool(patient_hist)

    reply_text: str
    summary: Optional[str]
    cond_ex: Optional[str]
    risk_ex: Optional[str]
    rec: Optional[str]
    tone: str
    follow: Optional[str]

    llm_out = None
    if is_llm_available():
        llm_out = run_llm_turn(
            user_message=message,
            grounding_json=grounding,
            history=prior if include_history else [],
            mode="dashboard",
        )

    if llm_out and llm_out.get("reply"):
        reply_text = post_process_reply(str(llm_out["reply"]), grounding=grounding)
        summary = llm_out.get("summary")
        cond_ex = llm_out.get("condition_explanation")
        risk_ex = llm_out.get("risk_explanation")
        rec = llm_out.get("recommendation")
        tone = str(llm_out.get("tone") or infer_tone(grounding, message))
        follow = llm_out.get("follow_up_suggestion")
        if user_message_has_red_flags(message) and "urgent" not in reply_text.lower() and "emergency" not in reply_text.lower():
            reply_text += (
                "\n\nIf you have chest pain, fainting, severe shortness of breath, or similar severe symptoms, "
                "seek urgent in-person care or emergency services."
            )
    else:
        rb = build_dashboard_chat_structured(message, {**dict(context or {}), "last_prediction": pred})
        reply_text = post_process_reply(rb["reply"], grounding=grounding)
        summary = rb.get("summary")
        cond_ex = rb.get("condition_explanation")
        risk_ex = rb.get("risk_explanation")
        rec = rb.get("recommendation")
        tone = infer_tone(grounding, message)
        follow = None

    mem.append(user_id, session_id=session_id, analysis_id=analysis_id, role="user", content=message)
    mem.append(user_id, session_id=session_id, analysis_id=analysis_id, role="assistant", content=reply_text)

    sources = merge_sources_used(
        used_prediction=used_pred,
        used_report_values=used_report,
        used_history=used_hist and include_history,
        used_patient_history=used_ph,
    )

    return {
        "reply": reply_text,
        "answer": reply_text,
        "summary": summary,
        "condition_explanation": cond_ex,
        "risk_explanation": risk_ex,
        "recommendation": rec,
        "sources_used": sources,
        "meta": {
            "tone": tone,
            "reliability_note": grounding.get("reliability_note"),
            "follow_up_suggested": follow,
            "llm_used": bool(llm_out),
        },
    }


def run_report_assistant(
    *,
    db: Session,
    user_id: int,
    message: str,
    prediction_result: Dict[str, Any],
    preprocess_metadata: Optional[Dict[str, Any]],
    analysis_id: Optional[int],
    session_id: Optional[str],
    include_history: bool,
) -> Dict[str, Any]:
    pred = dict(prediction_result or {})
    meta = dict(preprocess_metadata or {})
    if analysis_id is not None:
        loaded = load_analysis_for_user(db, analysis_id=analysis_id, user_id=user_id)
        if loaded:
            pred = {**loaded[0], **pred}
            meta = {**loaded[1], **meta}

    grounding = build_grounding_bundle(prediction_result=pred, preprocess_metadata=meta)
    patient_hist = fetch_recent_analysis_labels(db, user_id=user_id, limit=3)
    grounding["history"] = patient_hist

    mem = get_chat_memory()
    prior: List[dict] = []
    if include_history:
        prior = mem.get_recent(user_id, session_id=session_id or str(analysis_id), analysis_id=analysis_id)

    used_report = any(v not in (None, "", "—") for v in (grounding.get("report_values") or {}).values())
    used_pred = bool(pred)
    used_hist = bool(prior)

    llm_out = None
    if is_llm_available():
        llm_out = run_llm_turn(
            user_message=message,
            grounding_json=grounding,
            history=prior if include_history else [],
            mode="report",
        )

    if llm_out and llm_out.get("reply"):
        reply_text = post_process_reply(str(llm_out["reply"]), grounding=grounding)
        summary = llm_out.get("summary")
        cond_ex = llm_out.get("condition_explanation")
        risk_ex = llm_out.get("risk_explanation")
        rec = llm_out.get("recommendation")
        urgency = "routine"
        if user_message_has_red_flags(message):
            urgency = "emergency_red_flag"
        elif str(grounding.get("risk_level") or "").lower() == "high":
            urgency = "urgent"
        elif float(grounding.get("confidence") or 0) < 0.5:
            urgency = "soon"
        follow = llm_out.get("follow_up_suggestion")
    else:
        rb = build_report_guidance(message, prediction_result=pred, preprocess_metadata=meta)
        reply_text = post_process_reply(rb["reply"], grounding=grounding)
        summary = rb.get("summary")
        cond_ex = rb.get("condition_explanation")
        risk_ex = rb.get("risk_explanation")
        rec = rb.get("recommendation")
        urgency = str(rb.get("urgency") or "routine")
        follow = None

    mem.append(user_id, session_id=session_id or (str(analysis_id) if analysis_id else None), analysis_id=analysis_id, role="user", content=message)
    mem.append(user_id, session_id=session_id or (str(analysis_id) if analysis_id else None), analysis_id=analysis_id, role="assistant", content=reply_text)

    sources = merge_sources_used(
        used_prediction=used_pred,
        used_report_values=used_report,
        used_history=used_hist and include_history,
        used_patient_history=bool(patient_hist),
    )

    return {
        "reply": reply_text,
        "answer": reply_text,
        "urgency": urgency,
        "summary": summary,
        "condition_explanation": cond_ex,
        "risk_explanation": risk_ex,
        "recommendation": rec,
        "sources_used": sources,
        "meta": {
            "tone": str((llm_out or {}).get("tone") or infer_tone(grounding, message)),
            "reliability_note": grounding.get("reliability_note"),
            "follow_up_suggested": follow,
            "llm_used": bool(llm_out),
        },
    }
