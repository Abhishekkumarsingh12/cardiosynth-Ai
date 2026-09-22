"""
Synthetic ECG generation API entry.

1) Try conditional DDPM when weights load (TensorFlow).
2) Else use parametric beat morphology (no neural weights), if enabled.
3) If SYNTHETIC_REQUIRE_DDPM=true and DDPM cannot run, raise SyntheticGenerationError.

UI/API stay stable when swapping backends — check `generation_backend` in metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from app.config import get_settings
from app.core.synthetic_errors import SyntheticGenerationError
from app.services.procedural_synthetic_ecg import generate_procedural_strip, resolve_class_id
from app.services.synthetic_ddpm.inference import resolved_ddpm_model_path, sample_ddpm_waveform
from app.services.synthetic_ddpm.utils import linear_resize_1d, new_synthetic_filename, save_synthetic_csv

_SETUP_HINT = (
    "Add trained DDPM weights at backend/ml_models/synthetic_generator_model.h5 "
    "(run: python training/train_synthetic_ddpm.py from the backend directory), "
    "or leave SYNTHETIC_REQUIRE_DDPM=false (default) to allow the parametric fallback."
)


def run_synthetic_generation(
    *,
    analysis_id: int,
    preprocess_output: Dict[str, Any],
    prediction: Dict[str, Any],
    out_dir: Path,
    target_class: Optional[str] = None,
    num_samples: int = 360,
    noise_scale: float = 0.08,
    diversity_seed: Optional[int] = None,
    num_beats: Optional[int] = None,
) -> Tuple[str, Dict[str, Any], np.ndarray]:
    settings = get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = new_synthetic_filename(analysis_id)
    csv_path = out_dir / fname

    l_out = int(np.clip(int(num_samples), 64, 8000))
    class_id, class_label = resolve_class_id(target_class, prediction)

    meta: Dict[str, Any] = {
        "analysis_id": analysis_id,
        "based_on_stats": preprocess_output.get("stats"),
        "based_on_prediction_label": prediction.get("label"),
        "condition_class_id": int(class_id),
        "condition_label": class_label,
        "output_samples": l_out,
        "disclaimer": "Synthetic ECG for research/education only; not for clinical use.",
        "ddpm_weights_path": str(resolved_ddpm_model_path()),
    }

    w = sample_ddpm_waveform(class_id=class_id, output_length=l_out)
    if w is not None:
        meta["generation_backend"] = "ddpm_conditional"
        meta["ddpm_timesteps"] = int(settings.ecg_ddpm_num_timesteps)
        meta["schedule"] = settings.ecg_ddpm_schedule
    else:
        if settings.synthetic_require_ddpm:
            raise SyntheticGenerationError(
                "DDPM weights are required but missing or failed to load. "
                f"Expected: {resolved_ddpm_model_path()}. {_SETUP_HINT}"
            )
        if not settings.synthetic_procedural_enabled:
            raise SyntheticGenerationError(
                "Synthetic generation unavailable: DDPM did not run and procedural synthesis is disabled. "
                f"{_SETUP_HINT}"
            )
        ns = float(np.clip(noise_scale, 0.0, 1.0))
        w, q_meta = generate_procedural_strip(
            num_samples=l_out,
            class_id=class_id,
            class_label=class_label,
            noise_scale=ns,
            diversity_seed=diversity_seed,
            num_beats=num_beats,
        )
        meta["generation_backend"] = "procedural_parametric"
        meta["procedural_quality"] = q_meta
        meta["noise_scale_applied"] = ns
        if diversity_seed is not None:
            meta["diversity_seed"] = int(diversity_seed)

    save_synthetic_csv(w, csv_path)
    meta["csv_columns"] = ["sample_index", "value"]
    meta["file_size_bytes"] = int(csv_path.stat().st_size)
    meta["stored_filename"] = fname

    return str(csv_path.resolve()), meta, w


def mock_generate_synthetic(
    analysis_id: int,
    preprocess_output: Dict[str, Any],
    prediction: Dict[str, Any],
    out_dir: Path,
    **kwargs: Any,
) -> Tuple[str, Dict[str, Any], np.ndarray]:
    """Backward-compatible entry name used by older route code."""
    return run_synthetic_generation(
        analysis_id=analysis_id,
        preprocess_output=preprocess_output,
        prediction=prediction,
        out_dir=out_dir,
        **kwargs,
    )


def reference_waveform_for_compare(preprocess_output: Dict[str, Any], length: int) -> np.ndarray:
    """Resize stored normalized series to match synthetic length for charts/stats."""
    series = preprocess_output.get("normalized_series") or []
    arr = np.asarray(series, dtype=np.float64).ravel()
    if arr.size == 0:
        return np.zeros(max(length, 0), dtype=np.float64)
    ln = int(np.clip(length, 64, 8000))
    out = linear_resize_1d(arr, ln)
    out -= out.mean()
    std = float(out.std()) or 1.0
    out /= std
    return out.astype(np.float64)


def compare_reference_synthetic(ref_z: np.ndarray, syn_z: np.ndarray) -> Dict[str, float]:
    """Simple z-score-domain comparison (research metrics only)."""
    if ref_z.size != syn_z.size or ref_z.size < 2:
        return {"mse": 0.0, "correlation": 0.0}
    mse = float(np.mean((ref_z - syn_z) ** 2))
    try:
        c = float(np.corrcoef(ref_z, syn_z)[0, 1])
        if np.isnan(c):
            c = 0.0
    except Exception:
        c = 0.0
    return {"mse": mse, "correlation": c}
