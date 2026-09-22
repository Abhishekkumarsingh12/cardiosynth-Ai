"""
1D conditional U-Net epsilon predictor ε_θ(x_t, t, class) for DDPM on ECG-shaped series.

Designed for signal_length divisible by 8 (default 128). Resize upstream waveforms to match.

--- REPLACE ---
Deeper blocks, attention, or extra context channels without changing the model I/O contract.
"""

from __future__ import annotations

from typing import Tuple

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

from app.services.synthetic_ddpm.utils import sinusoidal_time_embedding


def _film_vector(ch: int, t_emb: tf.Tensor, cls_emb: tf.Tensor) -> tf.Tensor:
    h = layers.Concatenate()([t_emb, cls_emb])
    h = layers.Dense(ch, activation="swish")(h)
    return h[:, None, :]


def _res_block(x: tf.Tensor, ch: int, t_emb: tf.Tensor, cls_emb: tf.Tensor) -> tf.Tensor:
    h = layers.Conv1D(ch, 3, padding="same", use_bias=False)(x)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = h + _film_vector(ch, t_emb, cls_emb)
    h = layers.Activation("swish")(h)
    h = layers.Conv1D(ch, 3, padding="same", use_bias=False)(h)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = h + _film_vector(ch, t_emb, cls_emb)
    h = layers.Activation("swish")(h)
    if x.shape[-1] != ch:
        x = layers.Conv1D(ch, 1, padding="same", use_bias=False)(x)
    return x + h


def build_conditional_eps_model(
    signal_length: int,
    *,
    base_channels: int = 48,
    num_classes: int = 6,
    time_embed_dim: int = 128,
    name: str = "ddpm_eps_1d",
) -> keras.Model:
    """
    Predicts noise ε with shape (B, signal_length, 1).
    Use signal_length=128 (or 256) for clean stride-2 U-Net symmetry.
    """
    if signal_length % 8 != 0:
        raise ValueError("signal_length should be divisible by 8 for this U-Net (e.g. 128).")

    x_in = layers.Input(shape=(signal_length, 1), name="x_noisy")
    t_in = layers.Input(shape=(), dtype=tf.int32, name="timestep")
    y_in = layers.Input(shape=(), dtype=tf.int32, name="class_id")

    t_emb = sinusoidal_time_embedding(t_in, time_embed_dim)
    t_emb = layers.Dense(time_embed_dim, activation="swish")(t_emb)
    t_emb = layers.Dense(time_embed_dim, activation="swish")(t_emb)
    cls_emb = layers.Embedding(num_classes, time_embed_dim)(y_in)

    ch = base_channels
    h = layers.Conv1D(ch, 3, padding="same", use_bias=False)(x_in)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = h + _film_vector(ch, t_emb, cls_emb)
    h = layers.Activation("swish")(h)

    skips = []
    h = _res_block(h, ch, t_emb, cls_emb)
    skips.append(h)
    h = layers.Conv1D(ch, 4, strides=2, padding="same", use_bias=False)(h)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = layers.Activation("swish")(h)

    ch *= 2
    h = _res_block(h, ch, t_emb, cls_emb)
    skips.append(h)
    h = layers.Conv1D(ch, 4, strides=2, padding="same", use_bias=False)(h)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = layers.Activation("swish")(h)

    ch *= 2
    h = _res_block(h, ch, t_emb, cls_emb)
    skips.append(h)
    h = layers.Conv1D(ch, 4, strides=2, padding="same", use_bias=False)(h)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = layers.Activation("swish")(h)

    h = _res_block(h, ch, t_emb, cls_emb)

    ch //= 2
    h = layers.Conv1DTranspose(ch, 4, strides=2, padding="same", use_bias=False)(h)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = layers.Activation("swish")(h)
    h = layers.Concatenate(axis=-1)([h, skips.pop()])
    h = layers.Conv1D(ch, 1, padding="same", use_bias=False)(h)
    h = _res_block(h, ch, t_emb, cls_emb)

    ch //= 2
    h = layers.Conv1DTranspose(ch, 4, strides=2, padding="same", use_bias=False)(h)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = layers.Activation("swish")(h)
    h = layers.Concatenate(axis=-1)([h, skips.pop()])
    h = layers.Conv1D(ch, 1, padding="same", use_bias=False)(h)
    h = _res_block(h, ch, t_emb, cls_emb)

    ch //= 2
    h = layers.Conv1DTranspose(ch, 4, strides=2, padding="same", use_bias=False)(h)
    h = layers.LayerNormalization(epsilon=1e-5)(h)
    h = layers.Activation("swish")(h)
    h = layers.Concatenate(axis=-1)([h, skips.pop()])
    h = layers.Conv1D(ch, 1, padding="same", use_bias=False)(h)
    h = _res_block(h, ch, t_emb, cls_emb)

    out = layers.Conv1D(1, 3, padding="same", name="eps_out")(h)
    return keras.Model(inputs=[x_in, t_in, y_in], outputs=out, name=name)


def model_signal_length(model: keras.Model) -> int:
    shape = model.input_shape[0]
    return int(shape[1])
