#!/usr/bin/env python3
"""
Offline evaluation for the MIT-BIH beat classifier: confusion matrix + per-class metrics.

Usage (from backend/):
  .venv/bin/python training/evaluate_classifier.py

Requires: TensorFlow, scikit-learn, processed NPZ (datasets/processed/mit_bih_beats.npz).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def main() -> None:
    try:
        import tensorflow as tf
        from sklearn.metrics import classification_report, confusion_matrix
        from sklearn.model_selection import train_test_split
    except ImportError as e:
        print("Missing dependency:", e)
        sys.exit(1)

    from app.config import get_settings
    from app.datasets.paths import CLASSIFIER_MODEL_PATH, DEFAULT_PROCESSED_NPZ
    from app.datasets.prepare_pipeline import load_processed_npz

    cfg = get_settings()
    model_path = (
        Path(cfg.ecg_classifier_model_path.strip()).expanduser().resolve()
        if cfg.ecg_classifier_model_path.strip()
        else CLASSIFIER_MODEL_PATH
    )
    if not model_path.is_file():
        print("Model not found:", model_path)
        sys.exit(2)

    if not DEFAULT_PROCESSED_NPZ.is_file():
        print("Processed NPZ missing:", DEFAULT_PROCESSED_NPZ)
        sys.exit(3)

    X, y, class_names = load_processed_npz()
    X = X[..., np.newaxis].astype(np.float32)
    strat = y if np.min(np.bincount(y, minlength=len(class_names))) >= 2 else None
    _, X_te, _, y_te = train_test_split(X, y, test_size=0.15, random_state=42, stratify=strat)

    model = tf.keras.models.load_model(str(model_path), compile=False)
    proba = model.predict(X_te, verbose=0)
    y_hat = np.argmax(proba, axis=1)

    print("Classes:", class_names)
    print("\nConfusion matrix (rows=true, cols=pred):\n")
    cm = confusion_matrix(y_te, y_hat, labels=list(range(len(class_names))))
    print(cm)
    print("\nPer-class precision / recall / F1:\n")
    print(
        classification_report(
            y_te,
            y_hat,
            labels=list(range(len(class_names))),
            target_names=class_names,
            digits=4,
            zero_division=0,
        )
    )


if __name__ == "__main__":
    main()
