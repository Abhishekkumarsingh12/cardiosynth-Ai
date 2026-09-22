"""
Offline dataset management for CardioSynth AI.

This package is intended for admin/setup and training scripts only.
Do NOT import from FastAPI request handlers — keep uploads fast and side-effect free.
"""

from app.datasets.paths import (
    BACKEND_ROOT,
    CLASSIFIER_MODEL_PATH,
    DATASETS_DIR,
    ML_MODELS_DIR,
    MIT_BIH_ROOT,
    PROCESSED_DIR,
    SYNTHETIC_MODEL_PATH,
)
from app.datasets.mit_bih import MitBihArrhythmiaDataset
from app.datasets.registry import get_dataset, list_registered_datasets

__all__ = [
    "BACKEND_ROOT",
    "CLASSIFIER_MODEL_PATH",
    "DATASETS_DIR",
    "MIT_BIH_ROOT",
    "PROCESSED_DIR",
    "ML_MODELS_DIR",
    "SYNTHETIC_MODEL_PATH",
    "MitBihArrhythmiaDataset",
    "get_dataset",
    "list_registered_datasets",
]
