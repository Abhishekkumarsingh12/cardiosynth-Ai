"""Shared helpers: timestep embedding, class id from prediction dict, CSV IO."""

from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np


BEAT_CLASS_TO_ID: Dict[str, int] = {"N": 0, "L": 1, "R": 2, "A": 3, "V": 4}
UNCOND_CLASS_ID = 5  # embedding slot for unknown / unconditional


def prediction_to_class_id(prediction: Dict[str, Any]) -> int:
    """Map classifier `label` / `predicted_class` to conditioning index."""
    label = prediction.get("predicted_class") or prediction.get("label") or ""
    if isinstance(label, str) and label in BEAT_CLASS_TO_ID:
        return BEAT_CLASS_TO_ID[label]
    return UNCOND_CLASS_ID


def sinusoidal_time_embedding(timesteps: Any, dim: int) -> Any:
    """timesteps: (batch,) int32 -> (batch, dim) float32."""
    import tensorflow as tf

    half = dim // 2
    freqs = tf.exp(-tf.range(half, dtype=tf.float32) * (tf.math.log(10000.0) / tf.maximum(float(half - 1), 1.0)))
    t = tf.cast(timesteps, tf.float32)[:, None] * freqs[None, :]
    emb = tf.concat([tf.sin(t), tf.cos(t)], axis=-1)
    if dim % 2 == 1:
        emb = tf.pad(emb, [[0, 0], [0, 1]])
    return emb


def save_synthetic_csv(waveform: np.ndarray, path: Path) -> int:
    """Write single-column CSV; returns bytes written (approx)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    w = np.asarray(waveform, dtype=np.float64).ravel()
    with path.open("w", newline="", encoding="utf-8") as f:
        w_csv = csv.writer(f)
        w_csv.writerow(["sample_index", "value"])
        for i, v in enumerate(w):
            w_csv.writerow([i, float(v)])
    return path.stat().st_size


def new_synthetic_filename(analysis_id: int, suffix: str = "csv") -> str:
    return f"synthetic_ddpm_{analysis_id}_{uuid.uuid4().hex[:10]}.{suffix}"


def linear_resize_1d(x: np.ndarray, new_len: int) -> np.ndarray:
    """Resample 1-D series to new length (linear interpolation)."""
    x = np.asarray(x, dtype=np.float64).ravel()
    if new_len <= 1 or x.size <= 1:
        return np.resize(x, (new_len,))
    old_idx = np.linspace(0.0, 1.0, num=x.size)
    new_idx = np.linspace(0.0, 1.0, num=new_len)
    return np.interp(new_idx, old_idx, x).astype(np.float64)
