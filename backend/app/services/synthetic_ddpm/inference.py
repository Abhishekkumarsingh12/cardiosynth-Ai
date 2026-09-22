"""
Runtime DDPM generation: load ε_θ weights and sample x_0.

Training is offline-only (training/train_synthetic_ddpm.py). No training here.

This module only attempts neural sampling. Orchestration (procedural fallback, IO) lives
in app.services.synthetic_ecg.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np

from app.config import get_settings
from app.datasets.paths import SYNTHETIC_MODEL_PATH
from app.services.synthetic_ddpm.sampling import sample_ddpm
from app.services.synthetic_ddpm.utils import linear_resize_1d

log = logging.getLogger(__name__)

_MODEL: Optional[Any] = None


def _model_signal_length(model: Any) -> int:
    return int(model.input_shape[0][1])


def resolved_ddpm_model_path() -> Path:
    p = get_settings().ecg_ddpm_model_path.strip()
    return Path(p) if p else SYNTHETIC_MODEL_PATH


def reset_ddpm_model_cache() -> None:
    global _MODEL
    _MODEL = None


def _get_eps_model() -> Optional[Any]:
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    path = resolved_ddpm_model_path()
    if not path.is_file():
        log.warning("DDPM weights not found at %s", path)
        return None

    import tensorflow as tf

    from app.services.synthetic_ddpm.unet1d import build_conditional_eps_model

    L_cfg = int(get_settings().ecg_ddpm_signal_length)
    try:
        tf.keras.utils.disable_interactive_logging()
        try:
            m = tf.keras.models.load_model(path, compile=False)
            log.info("Loaded DDPM ε-model (full H5) from %s", path)
        except Exception:
            m = build_conditional_eps_model(L_cfg)
            m.load_weights(str(path))
            log.info("Loaded DDPM ε-weights into built U-Net (%s samples) from %s", L_cfg, path)
        _MODEL = m
        return _MODEL
    except Exception as e:
        log.exception("DDPM load failed: %s", e)
        return None


def ddpm_weights_exist() -> bool:
    return resolved_ddpm_model_path().is_file()


def sample_ddpm_waveform(*, class_id: int, output_length: int) -> Optional[np.ndarray]:
    """
    If weights load and sampling succeeds, return 1-D float64 waveform of length output_length.
    Otherwise return None (caller decides procedural fallback or error).
    """
    settings = get_settings()
    model = _get_eps_model()
    if model is None:
        return None

    T = int(settings.ecg_ddpm_num_timesteps)
    sched = settings.ecg_ddpm_schedule.strip() or "linear"
    L = _model_signal_length(model)
    y = np.array([int(class_id)], dtype=np.int32)
    try:
        x = sample_ddpm(
            model,
            batch_size=1,
            signal_length=L,
            class_ids=y,
            num_timesteps=T,
            schedule_kind=sched,
        )
        w = x[0, :, 0].astype(np.float64)
        if L != output_length:
            w = linear_resize_1d(w, output_length)
        w -= w.mean()
        std = float(w.std()) or 1.0
        w /= std
        return w
    except Exception as e:
        log.exception("DDPM sampling failed: %s", e)
        return None
