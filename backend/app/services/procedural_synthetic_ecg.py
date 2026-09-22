"""
Parametric single-lead ECG-like synthesis (no neural weights).

Use when DDPM weights are absent or as a deterministic fallback if DDPM sampling fails
and procedural fallback is allowed. Metadata must label `generation_backend` accordingly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from app.services.synthetic_ddpm.utils import BEAT_CLASS_TO_ID, UNCOND_CLASS_ID, linear_resize_1d

ID_TO_LABEL = {v: k for k, v in BEAT_CLASS_TO_ID.items()}
ID_TO_LABEL[UNCOND_CLASS_ID] = "U"


def resolve_class_id(target_class: Optional[str], prediction: Dict[str, Any]) -> Tuple[int, str]:
    """Return (class_id, label human) for conditioning."""
    if target_class and isinstance(target_class, str):
        t = target_class.strip().upper()
        if t in BEAT_CLASS_TO_ID:
            return BEAT_CLASS_TO_ID[t], t
    label = prediction.get("predicted_class") or prediction.get("label") or ""
    if isinstance(label, str) and label in BEAT_CLASS_TO_ID:
        return BEAT_CLASS_TO_ID[label], label
    return UNCOND_CLASS_ID, ID_TO_LABEL[UNCOND_CLASS_ID]


def _single_beat_morphology(length: int, class_id: int, rng: np.random.Generator, noise_scale: float) -> np.ndarray:
    if length < 16:
        length = 16
    t = np.linspace(-1.0, 1.0, length, dtype=np.float64)
    qrs_sigma = 0.055 + (0.05 if class_id == 4 else 0.0)
    qrs = np.exp(-((t / qrs_sigma) ** 2))
    if class_id == 4:
        qrs *= 1.25
    if class_id == 1:
        qrs *= np.where(t > 0, 1.35, 1.0)
    elif class_id == 2:
        qrs *= np.where(t < 0, 1.35, 1.0)
    p_wave = 0.22 * np.exp(-(((t - 0.48) / 0.07) ** 2))
    tw = 0.11 if class_id != 3 else 0.14
    t_wave = 0.32 * np.exp(-(((t + 0.32) / tw) ** 2))
    baseline = 0.015 * np.sin(np.pi * t * 2.5)
    sig = p_wave + qrs + t_wave + baseline
    sig -= sig.mean()
    std = float(sig.std()) or 1.0
    sig /= std
    noise = rng.standard_normal(length) * max(noise_scale, 0.0)
    sig = sig + noise
    sig -= sig.mean()
    std2 = float(sig.std()) or 1.0
    sig /= std2
    return sig


def generate_procedural_strip(
    *,
    num_samples: int,
    class_id: int,
    class_label: str,
    noise_scale: float,
    diversity_seed: Optional[int],
    num_beats: Optional[int],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Build a synthetic strip by stitching beat-shaped segments with optional gaps.

    Returns z-scored waveform and quality metadata.
    """
    rng = np.random.default_rng(diversity_seed if diversity_seed is not None else 42)
    L = int(np.clip(num_samples, 64, 8000))
    if num_beats is None:
        n_beats = max(1, min(48, L // 90))
    else:
        n_beats = int(np.clip(num_beats, 1, 48))
    beat_len = max(48, L // n_beats)
    pieces: list[np.ndarray] = []
    for b in range(n_beats):
        sub_seed = (diversity_seed + 10007 * b) if diversity_seed is not None else None
        br = np.random.default_rng(sub_seed) if sub_seed is not None else rng
        piece = _single_beat_morphology(beat_len, class_id, br, noise_scale)
        pieces.append(piece)
        if b < n_beats - 1:
            gap = max(3, beat_len // 10)
            if class_id == 3:
                gap += int(rng.integers(0, max(2, beat_len // 15)))
            pieces.append(np.zeros(gap, dtype=np.float64))
    concat = np.concatenate(pieces) if pieces else np.zeros(L, dtype=np.float64)
    out = linear_resize_1d(concat, L)
    out = out.astype(np.float64)
    out -= out.mean()
    std = float(out.std()) or 1.0
    out /= std

    quality = {
        "peak_to_peak": float(out.max() - out.min()),
        "std": float(out.std()),
        "n_beats_synthesized": n_beats,
        "target_class_label": class_label,
        "noise_effective": float(noise_scale),
    }
    return out, quality
