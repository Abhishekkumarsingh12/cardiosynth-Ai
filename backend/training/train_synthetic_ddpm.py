#!/usr/bin/env python3
"""
Offline DDPM ε_θ training skeleton for 1-D synthetic ECG (conditional on beat class).

Saves:
  - backend/ml_models/synthetic_generator_model.h5  (full Keras model via model.save)

Before training:
  - python setup_dataset.py   # MIT-BIH NPZ
  - Match inference hyperparameters in app.config.Settings (timesteps, schedule, signal_length).

--- EXTENSION POINTS ---
- Increase `epochs`, `T`, batch size, dataset size.
- Swap `linear` schedule for `cosine` in both this script and server `ecg_ddpm_schedule`.
- Add EMA weights, mixed precision, or context channels in unet1d.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf


def linear_resize_batch(X: np.ndarray, new_len: int) -> np.ndarray:
    """X: (N, L0) -> (N, new_len)."""
    out = np.zeros((X.shape[0], new_len), dtype=np.float32)
    for i in range(X.shape[0]):
        old = np.linspace(0, 1, num=X.shape[1])
        new = np.linspace(0, 1, num=new_len)
        out[i] = np.interp(new, old, X[i])
    return out


def main() -> None:
    from app.datasets.paths import DEFAULT_PROCESSED_NPZ, SYNTHETIC_MODEL_PATH
    from app.datasets.prepare_pipeline import load_processed_npz
    from app.services.synthetic_ddpm.noise_schedule import make_schedule
    from app.services.synthetic_ddpm.unet1d import build_conditional_eps_model

    # --- Hyperparameters (keep aligned with production Settings defaults) ---
    T = 200
    L = 128
    schedule_kind = "linear"
    epochs = 1  # increase for real training
    batch_size = 32
    lr = 2e-4

    if not DEFAULT_PROCESSED_NPZ.is_file():
        raise SystemExit(f"Missing {DEFAULT_PROCESSED_NPZ} — run python setup_dataset.py first.")

    X_raw, y_raw, _ = load_processed_npz(DEFAULT_PROCESSED_NPZ)
    X = linear_resize_batch(X_raw.astype(np.float32), L)[..., np.newaxis]
    y_cond = np.clip(y_raw.astype(np.int32), 0, 4)

    betas, _, alphas_cumprod, _, _ = make_schedule(T, kind=schedule_kind)
    alphas_cumprod = alphas_cumprod.astype(np.float32)
    alphas_cumprod_tf = tf.constant(alphas_cumprod, dtype=tf.float32)

    model = build_conditional_eps_model(L)
    opt = tf.keras.optimizers.Adam(learning_rate=lr)
    mse = tf.keras.losses.MeanSquaredError()

    n = X.shape[0]
    rng = np.random.default_rng(42)

    @tf.function
    def train_step(x0, t, noise, ycls):
        ab = tf.gather(alphas_cumprod_tf, t)[:, None, None]
        xt = tf.sqrt(ab) * x0 + tf.sqrt(1.0 - ab) * noise
        with tf.GradientTape() as tape:
            pred = model([xt, t, ycls], training=True)
            loss = mse(noise, pred)
        grads = tape.gradient(loss, model.trainable_variables)
        opt.apply_gradients(zip(grads, model.trainable_variables))
        return loss

    steps_per_epoch = max(1, n // batch_size)
    for ep in range(epochs):
        losses = []
        for _ in range(steps_per_epoch):
            idx = rng.integers(0, n, size=batch_size)
            x0 = tf.constant(X[idx])
            t = tf.constant(rng.integers(0, T, size=batch_size), dtype=tf.int32)
            noise = tf.random.normal(shape=x0.shape, dtype=tf.float32)
            ycls = tf.constant(y_cond[idx], dtype=tf.int32)
            losses.append(float(train_step(x0, t, noise, ycls)))
        print(f"epoch {ep+1}/{epochs} train_mse~={np.mean(losses):.5f}")

    SYNTHETIC_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(SYNTHETIC_MODEL_PATH))
    print(f"Saved DDPM ε-model to {SYNTHETIC_MODEL_PATH}")


if __name__ == "__main__":
    main()
