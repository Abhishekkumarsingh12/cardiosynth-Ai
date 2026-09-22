"""
Gradient-based saliency for the 1-D ECG beat classifier (Keras).

Uses ∂(logit of predicted class)/∂input on the (1, L, 1) window actually fed to the model.
Not a clinical explanation — a standard XAI approximation.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from app.core.classifier_errors import ClassifierUnavailableError
from app.services.prediction_service import DEFAULT_CLASS_NAMES, _load_keras_model


def _normalize_importance(raw: np.ndarray) -> np.ndarray:
    x = np.asarray(raw, dtype=np.float64).ravel()
    if x.size == 0:
        return x
    x = x - float(np.min(x))
    mx = float(np.max(x))
    if mx <= 1e-12:
        return np.ones_like(x) / max(1, x.size)
    return x / mx


def _important_regions_from_importance(
    importance_normalized: np.ndarray,
    *,
    quantile: float = 0.85,
    min_len: int = 6,
) -> List[Dict[str, Any]]:
    """
    Convert a 1-D importance array into contiguous important regions.

    Returns list of {start, end, score_mean, score_max}.
    Indices are inclusive.
    """
    x = np.asarray(importance_normalized, dtype=np.float64).ravel()
    L = int(x.size)
    if L <= 0:
        return []

    q = float(np.clip(quantile, 0.0, 1.0))
    thr = float(np.quantile(x, q))
    mask = x >= thr

    regions: list[dict[str, Any]] = []
    i = 0
    while i < L:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < L and mask[j + 1]:
            j += 1
        if (j - i + 1) >= int(max(1, min_len)):
            seg = x[i : j + 1]
            regions.append(
                {
                    "start": int(i),
                    "end": int(j),
                    "score_mean": float(np.mean(seg)),
                    "score_max": float(np.max(seg)),
                }
            )
        i = j + 1

    regions.sort(key=lambda r: (-float(r.get("score_mean") or 0.0), -(r["end"] - r["start"])))
    return regions[:8]


def compute_input_gradient_saliency(
    model_input: np.ndarray,
    *,
    predicted_class_index: int,
) -> np.ndarray:
    """
    model_input: float32 (1, L, 1)

    Returns 1-D importance (L,) nonnegative, before normalization.
    """
    model = _load_keras_model(log_load_exception=False)
    if model is None:
        raise ClassifierUnavailableError(
            "Cannot compute explainability: ECG classifier is not loaded."
        )

    import tensorflow as tf

    x = tf.Variable(model_input.astype(np.float32), trainable=True)
    ci = int(predicted_class_index)
    with tf.GradientTape(watch_accessed_variables=False) as tape:
        tape.watch(x)
        y = model(x, training=False)
        y = tf.convert_to_tensor(y)
        if len(y.shape) < 2 or y.shape[1] is None or int(y.shape[1]) <= 0:
            raise ClassifierUnavailableError("Classifier output shape unexpected for saliency.")
        nc = int(y.shape[1])
        if ci < 0 or ci >= nc:
            ci = int(tf.argmax(y[0]))
        target = y[0, ci]
    grads = tape.gradient(target, x)
    if grads is None:
        raise ClassifierUnavailableError("Model gradients are unavailable (saliency not supported for this graph).")
    imp = tf.reduce_mean(tf.abs(grads), axis=-1)[0]
    return imp.numpy().astype(np.float64)


def class_name_to_index(label: str) -> int:
    s = str(label or "").strip()
    if s in DEFAULT_CLASS_NAMES:
        return DEFAULT_CLASS_NAMES.index(s)
    return 0


def build_explanation_payload(
    *,
    model_input: np.ndarray,
    pred: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Full JSON-safe explainability payload for API.
    """
    idx = int(pred.get("class_index") if pred.get("class_index") is not None else 0)
    probs = pred.get("class_probabilities") or {}
    if probs and str(pred.get("label")) in probs:
        # already have label; idx matches argmax from predict path
        pass
    raw = compute_input_gradient_saliency(model_input, predicted_class_index=idx)
    norm = _normalize_importance(raw)
    L = int(norm.shape[0])
    top_thr = float(np.quantile(norm, 0.85)) if L else 0.0
    highlighted = [i for i in range(L) if norm[i] >= top_thr]
    lo, hi = (min(highlighted), max(highlighted)) if highlighted else (0, max(0, L - 1))
    regions = _important_regions_from_importance(norm, quantile=0.85, min_len=6)

    wave = model_input[0, :, 0].astype(np.float64).tolist()
    beat_lbl = pred.get("beat_model_label") or pred.get("label")
    clin = pred.get("predicted_class") or pred.get("label")
    explanation_text = (
        f"Irregularities that influenced the model are concentrated around samples {lo}–{hi} "
        f"of the {L}-sample classifier window (predicted «{clin}»). "
        "Highlighted regions indicate where small input changes would most affect the prediction; "
        "this is model sensitivity, not anatomical localization."
    )
    summary = (
        f"Gradient saliency is strongest around samples {lo}–{hi} in the {L}-sample window "
        f"(beat-classifier logit «{beat_lbl}», index {idx}). Clinical summary: «{clin}». "
        "This reflects model sensitivity, not clinical localization."
    )

    return {
        "window_length": L,
        "importance": raw.astype(float).tolist(),
        "importance_normalized": norm.astype(float).tolist(),
        "window_waveform": wave,
        "explanation_summary": summary,
        "explanation_text": explanation_text,
        "important_regions": regions,
        "highlight_range": [lo, hi],
        "method": "input_gradient_saliency",
    }


def merge_class_index_into_prediction(pred: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure class_index targets the Keras model logit (MIT-BIH beat classes), not clinical index.
    """
    out = dict(pred)
    bmi = out.get("beat_model_class_index")
    if bmi is not None:
        out["class_index"] = int(bmi)
    elif out.get("class_index") is None:
        out["class_index"] = class_name_to_index(str(out.get("beat_model_label") or out.get("label") or ""))
    return out
