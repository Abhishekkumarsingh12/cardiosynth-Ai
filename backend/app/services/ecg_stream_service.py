from __future__ import annotations

import asyncio
from dataclasses import dataclass
import io
from pathlib import Path
from typing import AsyncIterator, Optional

import numpy as np

from app.config import get_settings
from app.services.procedural_synthetic_ecg import resolve_class_id, generate_procedural_strip
from app.utils.csv_ecg import CSVValidationError, parse_ecg_csv


@dataclass(frozen=True)
class StreamMeta:
    sampling_rate_hz: float
    source: str
    signal_length: int


def _load_signal_from_csv(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    samples, _, _ = parse_ecg_csv(io.BytesIO(raw))
    return np.asarray(samples, dtype=np.float64).ravel()


def build_stream_source(
    *,
    stored_csv_path: Optional[str],
    sampling_rate_hz: Optional[float],
    mode: str,
    condition: Optional[str],
) -> tuple[np.ndarray, StreamMeta]:
    """
    Build a 1-D waveform source for streaming.

    - mode=analysis: stream from stored CSV.
    - mode=synthetic_demo: stream a procedural synthetic strip (no DB required).
    """
    settings = get_settings()
    fs = float(sampling_rate_hz) if sampling_rate_hz else float(settings.ecg_default_sampling_rate_hz)
    m = (mode or "analysis").strip().lower()

    if m == "analysis":
        if not stored_csv_path:
            raise ValueError("stored_csv_path required for mode=analysis")
        p = Path(stored_csv_path)
        if not p.is_file():
            raise ValueError("Stored CSV missing on disk")
        try:
            sig = _load_signal_from_csv(p)
        except CSVValidationError as e:
            raise ValueError(str(e)) from e
        meta = StreamMeta(sampling_rate_hz=fs, source="analysis_csv", signal_length=int(sig.size))
        return sig, meta

    if m == "synthetic_demo":
        pred = {"label": (condition or "N").strip().upper()}
        class_id, class_label = resolve_class_id(pred.get("label"), pred)
        sig, quality = generate_procedural_strip(
            num_samples=4000,
            class_id=class_id,
            class_label=class_label,
            noise_scale=0.06,
            diversity_seed=None,
            num_beats=None,
        )
        # Keep quality in the future if we extend metadata; for now just stream.
        _ = quality
        meta = StreamMeta(sampling_rate_hz=fs, source="procedural_demo", signal_length=int(sig.size))
        return sig, meta

    raise ValueError(f"Unknown mode: {mode!r}")


async def stream_signal_chunks(
    signal: np.ndarray,
    *,
    chunk_size: int = 24,
    tick_ms: int = 40,
    loop: bool = True,
) -> AsyncIterator[list[float]]:
    """
    Async generator that yields small chunks of samples at a steady cadence.
    """
    sig = np.asarray(signal, dtype=np.float64).ravel()
    if sig.size == 0:
        return

    i = 0
    n = int(sig.size)
    cs = int(max(1, chunk_size))
    delay = max(0.0, float(tick_ms) / 1000.0)

    while True:
        j = i + cs
        if j <= n:
            out = sig[i:j].tolist()
            i = j
        else:
            # wrap or finish
            if loop:
                out = np.concatenate([sig[i:n], sig[0 : (j - n)]]).tolist()
                i = (j - n) % n
            else:
                out = sig[i:n].tolist()
                i = n
        # Avoid emitting empty final chunks (common when loop=False and i == n).
        if not out:
            if not loop and i >= n:
                return
            continue
        yield out
        if not loop and i >= n:
            return
        if delay:
            await asyncio.sleep(delay)

