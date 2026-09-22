"""Central paths: raw datasets, processed tensors, exported models."""

from pathlib import Path

# backend/app/datasets/paths.py -> parents[2] == backend/
BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]

DATASETS_DIR: Path = BACKEND_ROOT / "datasets"
MIT_BIH_ROOT: Path = DATASETS_DIR / "mit_bih"
PROCESSED_DIR: Path = DATASETS_DIR / "processed"

ML_MODELS_DIR: Path = BACKEND_ROOT / "ml_models"
CLASSIFIER_MODEL_PATH: Path = ML_MODELS_DIR / "arrhythmia_model.h5"
SYNTHETIC_MODEL_PATH: Path = ML_MODELS_DIR / "synthetic_generator_model.h5"

DEFAULT_PROCESSED_NPZ: Path = PROCESSED_DIR / "mit_bih_beats.npz"
