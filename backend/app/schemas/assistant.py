from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: Optional[dict[str, Any]] = None
    analysis_id: Optional[int] = Field(default=None, description="Optional analysis to ground the reply.")
    session_id: Optional[str] = Field(default=None, description="Client session id for multi-turn memory.")
    include_history: bool = Field(default=True, description="Include recent chat turns in LLM context.")


class ChatOut(BaseModel):
    reply: str
    disclaimer: str
    summary: Optional[str] = None
    condition_explanation: Optional[str] = None
    risk_explanation: Optional[str] = None
    recommendation: Optional[str] = None
    answer: Optional[str] = Field(default=None, description="Same as reply; for newer API clients.")
    sources_used: Optional[dict[str, bool]] = None
    meta: Optional[dict[str, Any]] = None


class ReportGuidanceIn(BaseModel):
    message: str = Field(min_length=0, max_length=4000, default="")
    prediction_result: dict[str, Any]
    preprocess_metadata: Optional[dict[str, Any]] = None
    analysis_id: Optional[int] = None
    session_id: Optional[str] = None
    include_history: bool = True


class ReportGuidanceOut(BaseModel):
    reply: str
    urgency: str
    disclaimer: str
    summary: Optional[str] = None
    condition_explanation: Optional[str] = None
    risk_explanation: Optional[str] = None
    recommendation: Optional[str] = None
    answer: Optional[str] = None
    sources_used: Optional[dict[str, bool]] = None
    meta: Optional[dict[str, Any]] = None
