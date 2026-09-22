from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ECGUploadOut(BaseModel):
    id: int
    original_name: str
    file_size: int
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryItem(BaseModel):
    analysis_id: int
    upload_id: int
    original_name: str
    created_at: datetime
    prediction_label: Optional[str]
    confidence: Optional[float]


class SyntheticOut(BaseModel):
    id: int
    stored_path: Optional[str]
    mock_metadata: Optional[dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class SyntheticGenerateIn(BaseModel):
    """Optional body for POST /ecg/generate-synthetic/{analysis_id}."""

    target_class: Optional[str] = Field(
        default=None,
        description="Beat class N, L, R, A, or V (optional; defaults to stored prediction).",
    )
    num_samples: int = Field(default=360, ge=64, le=8000)
    noise_scale: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
        description="Procedural backend only: Gaussian noise mix (0–1).",
    )
    diversity_seed: Optional[int] = Field(default=None, description="RNG seed for procedural diversity.")
    num_beats: Optional[int] = Field(
        default=None,
        ge=1,
        le=48,
        description="Procedural backend: approximate beat segments (optional).",
    )


class AnalysisDetail(BaseModel):
    analysis_id: int
    upload: ECGUploadOut
    sampling_rate_hz: Optional[float]
    signal_stats: Optional[dict[str, Any]]
    prediction_result: Optional[dict[str, Any]]
    preprocess_metadata: Optional[dict[str, Any]]
    chart_series: List[float]
    created_at: datetime
    synthetic_runs: List[SyntheticOut]


class SyntheticPlaygroundIn(BaseModel):
    condition: str = Field(description="Condition label (e.g. Normal, AFib, PVC or beat labels N/A/V).")
    num_samples: int = Field(default=720, ge=64, le=8000)
    noise_scale: float = Field(default=0.08, ge=0.0, le=1.0)
    diversity_seed: Optional[int] = Field(default=None)


class SyntheticPlaygroundOut(BaseModel):
    condition: str
    num_samples: int
    sampling_rate_hz: float
    waveform: List[float]
    prediction: dict[str, Any]
    explanation: Optional[dict[str, Any]] = None
    csv_text: str
