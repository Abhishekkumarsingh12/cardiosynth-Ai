from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class ECGUpload(Base):
    __tablename__ = "ecg_uploads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), default="text/csv")
    original_name: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="uploads")
    analysis: Mapped[Optional["ECGAnalysis"]] = relationship(back_populates="upload", uselist=False)


class ECGAnalysis(Base):
    __tablename__ = "ecg_analysis"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("ecg_uploads.id", ondelete="CASCADE"), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sampling_rate_hz: Mapped[Optional[float]] = mapped_column(nullable=True)
    signal_stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    prediction_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    preprocess_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="analyses")
    upload: Mapped["ECGUpload"] = relationship(back_populates="analysis")
    synthetic_runs: Mapped[list["SyntheticECG"]] = relationship(back_populates="analysis", cascade="all, delete-orphan")


class SyntheticECG(Base):
    __tablename__ = "synthetic_ecg"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("ecg_analysis.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Path to generated CSV (DDPM) + JSON metadata in mock_metadata
    stored_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mock_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    analysis: Mapped["ECGAnalysis"] = relationship(back_populates="synthetic_runs")


from app.models.user import User  # noqa: E402 — register User for relationship resolution
