"""
DDPM beta / alpha schedule (numpy). Used by sampling and offline training.

--- REPLACE / TUNE ---
Swap `linear_beta_schedule` for `cosine_beta_schedule` etc. without changing `make_schedule` return shape.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def linear_beta_schedule(timesteps: int, beta_start: float = 1e-4, beta_end: float = 0.02) -> np.ndarray:
    return np.linspace(beta_start, beta_end, timesteps, dtype=np.float64)


def cosine_beta_schedule(timesteps: int, s: float = 0.008) -> np.ndarray:
    """Nichol & Dhariwal style cosine schedule (betas derived from alpha_bar)."""
    steps = timesteps + 1
    x = np.linspace(0, timesteps, steps, dtype=np.float64)
    alphas_cumprod = np.cos(((x / timesteps) + s) / (1 + s) * np.pi * 0.5) ** 2
    alphas_cumprod = alphas_cumprod / alphas_cumprod[0]
    betas = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
    return np.clip(betas, 1e-8, 0.999).astype(np.float64)


def make_schedule(
    timesteps: int,
    *,
    kind: str = "linear",
    beta_start: float = 1e-4,
    beta_end: float = 0.02,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns betas, alphas, alphas_cumprod, alphas_cumprod_prev, sqrt_one_minus_alphas_cumprod
    (all length `timesteps`).
    """
    if kind == "cosine":
        betas = cosine_beta_schedule(timesteps)
    else:
        betas = linear_beta_schedule(timesteps, beta_start, beta_end)

    alphas = 1.0 - betas
    alphas_cumprod = np.cumprod(alphas, axis=0)
    alphas_cumprod_prev = np.append(1.0, alphas_cumprod[:-1])
    sqrt_one_minus_alphas_cumprod = np.sqrt(1.0 - alphas_cumprod)
    return betas, alphas, alphas_cumprod, alphas_cumprod_prev, sqrt_one_minus_alphas_cumprod
