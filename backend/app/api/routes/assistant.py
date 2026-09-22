from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import AssistantLog, ECGAnalysis, User
from app.schemas.assistant import ChatIn, ChatOut, ReportGuidanceIn, ReportGuidanceOut
from app.services.assistant_llm_orchestrator import run_dashboard_assistant, run_report_assistant
from app.services.assistant_service import DISCLAIMER

router = APIRouter()


@router.post("/chat", response_model=ChatOut)
def chat(
    body: ChatIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ctx = dict(body.context or {})
    # Enrich with latest analysis prediction if client did not send it
    if "last_prediction" not in ctx:
        last = (
            db.query(ECGAnalysis)
            .filter(ECGAnalysis.user_id == current.id)
            .order_by(ECGAnalysis.created_at.desc())
            .first()
        )
        if last and last.prediction_result:
            ctx["last_prediction"] = last.prediction_result

    out = run_dashboard_assistant(
        db=db,
        user_id=current.id,
        message=body.message,
        context=ctx,
        analysis_id=body.analysis_id,
        session_id=body.session_id,
        include_history=body.include_history,
    )
    log = AssistantLog(
        user_id=current.id,
        message=body.message,
        response=out.get("reply"),
        context={
            **ctx,
            "structured": {k: out.get(k) for k in ("summary", "condition_explanation", "risk_explanation", "recommendation")},
            "sources_used": out.get("sources_used"),
            "meta": out.get("meta"),
        },
    )
    db.add(log)
    db.commit()

    return ChatOut(
        reply=out["reply"],
        disclaimer=DISCLAIMER,
        summary=out.get("summary"),
        condition_explanation=out.get("condition_explanation"),
        risk_explanation=out.get("risk_explanation"),
        recommendation=out.get("recommendation"),
        answer=out.get("answer"),
        sources_used=out.get("sources_used"),
        meta=out.get("meta"),
    )


@router.post("/report-guidance", response_model=ReportGuidanceOut)
def report_guidance(
    body: ReportGuidanceIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Rule-based report guidance assistant.

    Strict safety: not a diagnosis, no medication advice, always includes disclaimer.
    """
    result = run_report_assistant(
        db=db,
        user_id=current.id,
        message=body.message,
        prediction_result=body.prediction_result,
        preprocess_metadata=body.preprocess_metadata,
        analysis_id=body.analysis_id,
        session_id=body.session_id,
        include_history=body.include_history,
    )
    log = AssistantLog(
        user_id=current.id,
        message=body.message,
        response=result.get("reply"),
        context={
            "prediction_result": body.prediction_result,
            "preprocess_metadata": body.preprocess_metadata,
            "urgency": result.get("urgency"),
            "sources_used": result.get("sources_used"),
            "meta": result.get("meta"),
        },
    )
    db.add(log)
    db.commit()
    return ReportGuidanceOut(
        reply=result["reply"],
        urgency=str(result["urgency"]),
        disclaimer="This is AI-generated guidance and not a medical diagnosis.",
        summary=result.get("summary"),
        condition_explanation=result.get("condition_explanation"),
        risk_explanation=result.get("risk_explanation"),
        recommendation=result.get("recommendation"),
        answer=result.get("answer"),
        sources_used=result.get("sources_used"),
        meta=result.get("meta"),
    )
