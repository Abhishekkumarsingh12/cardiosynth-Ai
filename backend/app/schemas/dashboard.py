from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_uploads: int
    total_analyses: int
    last_prediction_label: Optional[str]
    last_updated: Optional[datetime]


class RecentAnalysisRow(BaseModel):
    analysis_id: int
    upload_id: int
    filename: str
    created_at: datetime
    label: Optional[str]
    confidence: Optional[float]
    mock: Optional[bool]
