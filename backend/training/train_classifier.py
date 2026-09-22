#!/usr/bin/env python3
"""
Offline ECG beat classifier training (MIT-BIH processed NPZ).

Saves: backend/ml_models/arrhythmia_model.h5 (or path from env / same as app.datasets.paths).

If datasets/processed/mit_bih_beats.npz is missing but local MIT-BIH WFDB data exists
(flat datasets/mit_bih/*.hea or nested mit_bih/mitdb/), the NPZ is rebuilt automatically
via prepare_pipeline.build_mit_bih_processed_npz. Otherwise run: python setup_dataset.py

Requires: TensorFlow + scikit-learn.

Do NOT invoke from HTTP handlers; may be called by classifier_bootstrap at process startup.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("train_classifier")

# Exit codes: 1 = dependencies, 2 = no local raw data / user must run setup, 3 = rebuild failed
EXIT_MISSING_DEPS = 1
EXIT_NO_RAW_DATA = 2
EXIT_REBUILD_FAILED = 3


def _path_relative_to_backend(path: Path) -> str:
    """e.g. datasets/processed/mit_bih_beats.npz"""
    return path.resolve().relative_to(BACKEND_ROOT.resolve()).as_posix()


def _model_save_display_path(out_path: Path) -> str:
    """Default layout: backend/ml_models/arrhythmia_model.h5 (from project root)."""
    p = out_path.resolve()
    br = BACKEND_ROOT.resolve()
    try:
        rel = p.relative_to(br)
        return f"backend/{rel.as_posix()}"
    except ValueError:
        return p.as_posix()


def ensure_processed_npz(npz_path: Path) -> None:
    """
    Use existing NPZ or rebuild from local MIT-BIH via prepare_pipeline (no duplicate logic).
    """
    if npz_path.is_file():
        return

    log.info("Processed dataset missing, attempting automatic rebuild...")
    from app.datasets.prepare_pipeline import build_mit_bih_processed_npz, resolve_mitdb_directory

    try:
        mitdb_dir = resolve_mitdb_directory(BACKEND_ROOT)
    except FileNotFoundError:
        log.error(
            "No local MIT-BIH WFDB data found. Run from the backend directory:\n"
            "  python setup_dataset.py\n"
            "Network access may be required on first run to download MIT-BIH from PhysioNet."
        )
        sys.exit(EXIT_NO_RAW_DATA)

    log.info("Found local MIT-BIH data at %s", mitdb_dir.resolve().as_posix())

    try:
        build_mit_bih_processed_npz(BACKEND_ROOT, out_path=npz_path)
    except RuntimeError as e:
        log.error("Automatic NPZ rebuild failed: %s", e)
        sys.exit(EXIT_REBUILD_FAILED)
    except Exception as e:
        log.error("Automatic NPZ rebuild failed: %s", e)
        sys.exit(EXIT_REBUILD_FAILED)

    if not npz_path.is_file():
        log.error("NPZ was not created at %s", npz_path.resolve().as_posix())
        sys.exit(EXIT_REBUILD_FAILED)

    log.info("Rebuilt %s successfully", _path_relative_to_backend(npz_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train MIT-BIH beat classifier")
    parser.add_argument(
        "--bootstrap-quick",
        action="store_true",
        help="Fewer epochs / samples for faster auto-bootstrap (not for publication quality)",
    )
    args = parser.parse_args()

    try:
        import tensorflow as tf
        from sklearn.model_selection import train_test_split
    except ImportError as e:
        log.error("Missing dependency: %s", e)
        sys.exit(EXIT_MISSING_DEPS)

    from app.config import get_settings
    from app.datasets.paths import CLASSIFIER_MODEL_PATH, DEFAULT_PROCESSED_NPZ
    from app.datasets.prepare_pipeline import load_processed_npz

    cfg = get_settings()
    out_path = (
        Path(cfg.ecg_classifier_model_path.strip()).expanduser().resolve()
        if cfg.ecg_classifier_model_path.strip()
        else CLASSIFIER_MODEL_PATH
    )

    ensure_processed_npz(DEFAULT_PROCESSED_NPZ)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    X, y, class_names = load_processed_npz()
    n_classes = len(class_names)
    X = X[..., np.newaxis]

    if args.bootstrap_quick:
        max_n = min(len(X), 8000)
        X, y = X[:max_n], y[:max_n]
        epochs = 2
        log.info("Bootstrap-quick mode: samples=%s epochs=%s", max_n, epochs)
    else:
        epochs = 8
        rng = np.random.default_rng(42)
        n_aug = min(len(X) // 4, 5000)
        pick = rng.choice(len(X), size=n_aug, replace=False)
        noise = rng.normal(0, 0.02, size=X[pick].shape).astype(np.float32)
        X_aug = X[pick] + noise
        y_aug = y[pick]
        X = np.concatenate([X, X_aug], axis=0)
        y = np.concatenate([y, y_aug], axis=0)
        perm = rng.permutation(len(X))
        X, y = X[perm], y[perm]
        log.info("Full training mode: samples=%s epochs=%s", len(X), epochs)

    strat = y if np.min(np.bincount(y, minlength=n_classes)) >= 2 else None
    X_tr, X_va, y_tr, y_va = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=strat
    )

    counts = np.bincount(y_tr, minlength=n_classes).astype(np.float64)
    counts[counts == 0] = 1.0
    class_weight = {i: float(len(y_tr) / (n_classes * counts[i])) for i in range(n_classes)}

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(X.shape[1], 1)),
            tf.keras.layers.Conv1D(32, 5, activation="relu", padding="same"),
            tf.keras.layers.MaxPooling1D(2),
            tf.keras.layers.Conv1D(64, 5, activation="relu", padding="same"),
            tf.keras.layers.MaxPooling1D(2),
            tf.keras.layers.GlobalAveragePooling1D(),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dropout(0.35),
            tf.keras.layers.Dense(n_classes, activation="softmax"),
        ]
    )
    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    log.info("Starting classifier training...")
    model.fit(
        X_tr,
        y_tr,
        validation_data=(X_va, y_va),
        epochs=epochs,
        batch_size=64,
        class_weight=class_weight,
        verbose=1,
    )

    model.save(str(out_path))
    done_msg = f"Training complete. Model saved to {_model_save_display_path(out_path)}"
    log.info(done_msg)
    print(done_msg)


if __name__ == "__main__":
    main()
