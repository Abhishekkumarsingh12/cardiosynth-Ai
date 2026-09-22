"""
Ensure `arrhythmia_model.h5` exists before serving traffic.

- Path: `ECG_CLASSIFIER_MODEL_PATH` or `ml_models/arrhythmia_model.h5`.
- Missing file + TensorFlow installed → subprocess `training/train_classifier.py` (optionally `--bootstrap-quick`).
- Optional: `ECG_AUTO_PREPARE_DATASET=true` runs `setup_dataset.py` when NPZ is missing (downloads data).
- Training failure → dummy Keras model only if ENABLE_MOCK_INFERENCE=true (dev convenience).
- No TensorFlow + no weights → `RuntimeError` at startup (unless skip bootstrap).

`SKIP_CLASSIFIER_AUTO_BOOTSTRAP=true` disables this entire step.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolved_classifier_path() -> Path:
    """OS-independent absolute path to the classifier H5."""
    from app.config import get_settings
    from app.datasets.paths import CLASSIFIER_MODEL_PATH

    raw = get_settings().ecg_classifier_model_path.strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return CLASSIFIER_MODEL_PATH.resolve()


def _try_import_tensorflow() -> bool:
    try:
        import tensorflow  # noqa: F401

        return True
    except ImportError:
        return False


def save_dummy_classifier(path: Path, *, seq_len: int = 187, n_classes: int = 5) -> None:
    """
    Minimal Keras model: input (seq_len, 1), 5-class softmax. Not clinically valid.
    """
    import tensorflow as tf

    path.parent.mkdir(parents=True, exist_ok=True)
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(seq_len, 1)),
            tf.keras.layers.GlobalAveragePooling1D(),
            tf.keras.layers.Dense(n_classes, activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy")
    x = tf.random.normal((16, seq_len, 1))
    y = tf.constant([0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0], dtype=tf.int32)
    model.fit(x, y, epochs=1, verbose=0)
    model.save(str(path))
    log.warning("Saved dummy ECG classifier to %s (not for clinical use)", path)


def _run_training_subprocess(*, bootstrap_quick: bool) -> int:
    root = backend_root()
    script = root / "training" / "train_classifier.py"
    if not script.is_file():
        log.error("Training script missing: %s", script)
        return 127
    cmd = [sys.executable, str(script)]
    if bootstrap_quick:
        cmd.append("--bootstrap-quick")
    log.info("Classifier training subprocess: %s (cwd=%s)", " ".join(cmd), root)
    proc = subprocess.run(cmd, cwd=str(root), env=os.environ.copy(), text=True)
    return int(proc.returncode)


def _maybe_prepare_dataset() -> None:
    from app.config import get_settings
    from app.datasets.paths import DEFAULT_PROCESSED_NPZ

    if not get_settings().ecg_auto_prepare_dataset:
        return
    if DEFAULT_PROCESSED_NPZ.is_file():
        return
    root = backend_root()
    setup = root / "setup_dataset.py"
    if not setup.is_file():
        log.error("setup_dataset.py not found at %s", setup)
        return
    max_rec = os.environ.get("ECG_BOOTSTRAP_MAX_RECORDS", "5").strip() or "5"
    cmd = [sys.executable, str(setup), "--max-records", max_rec]
    log.warning("Processed NPZ missing — running %s (may download PhysioNet data)…", " ".join(cmd))
    subprocess.run(cmd, cwd=str(root), env=os.environ.copy(), text=True)


def ensure_classifier_model() -> None:
    from app.config import get_settings

    settings = get_settings()
    if settings.skip_classifier_auto_bootstrap:
        log.info("skip_classifier_auto_bootstrap — skipping classifier ensure step")
        return

    path = resolved_classifier_path()
    seq_len = int(settings.ecg_classifier_input_length)

    if path.is_file():
        log.info("ECG classifier weights found at %s", path)
        return

    if not _try_import_tensorflow():
        msg = (
            f"No classifier weights at {path} and TensorFlow is not installed. "
            "Install TensorFlow (see backend/requirements-tensorflow.txt), then train or place arrhythmia_model.h5."
        )
        log.error("%s ECG classification will return HTTP 503 until resolved.", msg)
        return

    _maybe_prepare_dataset()

    quick = os.environ.get("ECG_CLASSIFIER_BOOTSTRAP_QUICK", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    log.warning("Model not found at %s — training started (bootstrap_quick=%s)…", path, quick)
    code = _run_training_subprocess(bootstrap_quick=quick)

    if path.is_file():
        log.info("Training completed, model saved at %s", path)
        return

    log.error("Classifier training failed (exit code %s) or output file still missing", code)

    if settings.enable_mock_inference:
        try:
            save_dummy_classifier(path, seq_len=seq_len)
            log.warning("Training failed; dummy classifier saved to %s (ENABLE_MOCK_INFERENCE=true)", path)
        except Exception as e:
            msg = (
                f"No classifier at {path} after training (exit {code}) and dummy save failed: {e}. "
                "Run: python setup_dataset.py && python training/train_classifier.py"
            )
            log.exception("%s", msg)
            if os.environ.get("ECG_CLASSIFIER_STRICT", "").strip().lower() in ("1", "true", "yes"):
                raise RuntimeError(msg) from e
        return

    log.error(
        "No classifier weights at %s after bootstrap training (exit %s). "
        "Train manually: cd backend && .venv/bin/python training/train_classifier.py",
        path,
        code,
    )


def preload_classifier_for_logging() -> bool:
    """Deprecated: lifespan calls startup_load_ecg_classifier() instead."""
    from app.services.prediction_service import load_classifier_eager

    ok = load_classifier_eager()
    if ok:
        log.info("Model loaded successfully")
    else:
        log.warning("Model not loaded — see prediction_service / startup logs")
    return ok
