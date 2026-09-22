"""
DDPM reverse sampling loop (1D).

--- REPLACE ---
DDIM / faster samplers: implement parallel `sample_ddim` and switch in inference.py.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.services.synthetic_ddpm.noise_schedule import make_schedule


def _posterior_mean_from_x0(
    x0_hat: Any,
    xt: Any,
    t: int,
    alphas_cumprod: np.ndarray,
    alphas_cumprod_prev: np.ndarray,
    betas: np.ndarray,
    alphas: np.ndarray,
) -> Any:
    import tensorflow as tf

    coef1 = float(np.sqrt(alphas_cumprod_prev[t]) * betas[t] / (1.0 - alphas_cumprod[t] + 1e-20))
    coef2 = float(np.sqrt(alphas[t]) * (1.0 - alphas_cumprod_prev[t]) / (1.0 - alphas_cumprod[t] + 1e-20))
    return tf.cast(coef1, tf.float32) * x0_hat + tf.cast(coef2, tf.float32) * xt


def _posterior_variance(t: int, betas: np.ndarray, alphas_cumprod: np.ndarray, alphas_cumprod_prev: np.ndarray) -> float:
    return float(betas[t] * (1.0 - alphas_cumprod_prev[t]) / (1.0 - alphas_cumprod[t] + 1e-20))


def sample_ddpm(
    model: Any,
    *,
    batch_size: int,
    signal_length: int,
    class_ids: np.ndarray,
    num_timesteps: int,
    schedule_kind: str = "linear",
) -> np.ndarray:
    """
    Generate x_0 ~ p_θ(x) starting from Gaussian noise.

    Returns float32 array (B, L, 1).
    """
    import tensorflow as tf

    betas, alphas, alphas_cumprod, alphas_cumprod_prev, _ = make_schedule(
        num_timesteps, kind=schedule_kind
    )

    x = tf.random.normal(shape=(batch_size, signal_length, 1), dtype=tf.float32)
    y = tf.constant(class_ids, dtype=tf.int32)

    for t in reversed(range(num_timesteps)):
        t_batch = tf.fill([batch_size], t)
        pred_noise = model([x, t_batch, y], training=False)

        alpha_bar = float(alphas_cumprod[t])
        pred_x0 = (x - np.sqrt(1.0 - alpha_bar) * pred_noise) / (np.sqrt(alpha_bar) + 1e-8)
        pred_x0 = tf.clip_by_value(pred_x0, -5.0, 5.0)

        mean = _posterior_mean_from_x0(
            pred_x0, x, t, alphas_cumprod, alphas_cumprod_prev, betas, alphas
        )
        var = _posterior_variance(t, betas, alphas_cumprod, alphas_cumprod_prev)

        if t > 0:
            noise = tf.random.normal(shape=tf.shape(x), dtype=tf.float32)
            x = mean + tf.sqrt(var) * noise
        else:
            x = mean

    return x.numpy().astype(np.float32)
