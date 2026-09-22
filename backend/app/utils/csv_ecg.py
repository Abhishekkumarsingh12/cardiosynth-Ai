"""
Validate and parse ECG CSV.

Signal column selection priority:
1) ecg
2) signal
3) lead_ii
4) first non-time numeric column
5) fallback to first numeric column (only if it's the only numeric column)
"""

from __future__ import annotations

from typing import Any, BinaryIO, Optional, Tuple

import pandas as pd


class CSVValidationError(ValueError):
    pass


MAX_ROWS = 500_000
MAX_FILE_BYTES = 50 * 1024 * 1024


def validate_csv_file(content: bytes) -> None:
    if len(content) > MAX_FILE_BYTES:
        raise CSVValidationError("File too large (max 50MB).")
    if len(content) == 0:
        raise CSVValidationError("Empty file.")


def _normalize_colname(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def _is_time_like_col(name_norm: str) -> bool:
    if name_norm in {"time", "timestamp", "t", "sec", "secs", "second", "seconds", "ms", "millis", "milliseconds"}:
        return True
    return "time" in name_norm or "timestamp" in name_norm


def _infer_sampling_rate_hz(time_values: list[float], *, name_norm: str) -> Optional[float]:
    """
    Best-effort inference from a time column. Returns None if unreliable.
    - seconds: dt ~ 0.0028 for 360 Hz
    - milliseconds: dt ~ 2.8 for 360 Hz
    """
    if len(time_values) < 20:
        return None
    # use median diff robustly
    diffs = []
    prev = time_values[0]
    for v in time_values[1:]:
        dv = float(v) - float(prev)
        prev = v
        if dv > 0:
            diffs.append(dv)
    if len(diffs) < 10:
        return None
    diffs.sort()
    dt = float(diffs[len(diffs) // 2])
    if dt <= 0:
        return None

    # explicit unit hints
    if "ms" in name_norm or "milli" in name_norm:
        hz = 1000.0 / dt
        return float(hz) if 0.1 <= hz <= 5000 else None

    # heuristic: dt > 1 looks like milliseconds; dt <= 1 looks like seconds
    if dt > 1.0 and dt < 10_000:
        hz = 1000.0 / dt
    else:
        hz = 1.0 / dt
    return float(hz) if 0.1 <= hz <= 5000 else None


def parse_ecg_csv(file_like: BinaryIO) -> Tuple[list[float], str, dict[str, Any]]:
    """
    Read CSV and choose an ECG signal column (avoid selecting time when possible).

    Returns:
        samples: list[float]
        signal_column: str
        meta: dict with selected column info + basic stats + inferred fs (if possible)
    """
    try:
        df = pd.read_csv(file_like, nrows=MAX_ROWS)
    except Exception as e:
        raise CSVValidationError(f"Could not parse CSV: {e}") from e

    if df.empty or len(df.columns) == 0:
        raise CSVValidationError("CSV has no columns.")

    # Collect numeric candidates (>=10 numeric samples)
    numeric: list[tuple[str, str, list[float]]] = []  # (orig_name, norm_name, values)
    for col in list(df.columns):
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) >= 10:
            numeric.append((str(col), _normalize_colname(str(col)), s.astype(float).tolist()))

    if not numeric:
        raise CSVValidationError("No numeric column with at least 10 samples found.")

    # Identify a time-like column (first match)
    time_col: Optional[tuple[str, str, list[float]]] = None
    for item in numeric:
        if _is_time_like_col(item[1]):
            time_col = item
            break

    # Choose signal column by priority
    preferred = ["ecg", "signal", "lead_ii"]
    chosen: Optional[tuple[str, str, list[float]]] = None
    for key in preferred:
        for item in numeric:
            if item[1] == key:
                chosen = item
                break
        if chosen is not None:
            break

    # Else choose first numeric that isn't time-like (if available)
    if chosen is None:
        for item in numeric:
            if time_col is not None and item[0] == time_col[0]:
                continue
            if not _is_time_like_col(item[1]):
                chosen = item
                break

    # If still none, only numeric column is time — fall back to it
    if chosen is None:
        chosen = numeric[0]

    signal_values = chosen[2]
    sig_min = float(min(signal_values)) if signal_values else 0.0
    sig_max = float(max(signal_values)) if signal_values else 0.0
    sig_mean = float(sum(signal_values) / max(1, len(signal_values))) if signal_values else 0.0

    inferred_fs = None
    time_column_name = None
    if time_col is not None:
        time_column_name = time_col[0]
        inferred_fs = _infer_sampling_rate_hz(time_col[2], name_norm=time_col[1])

    meta: dict[str, Any] = {
        "selected_signal_column": chosen[0],
        "time_column": time_column_name,
        "n_samples": int(len(signal_values)),
        "sampling_rate_hz_inferred": inferred_fs,
        "signal_stats": {"min": sig_min, "max": sig_max, "mean": sig_mean},
        "available_numeric_columns": [c[0] for c in numeric],
    }
    return signal_values, chosen[0], meta

def parse_first_numeric_column(file_like: BinaryIO) -> tuple[list[float], str]:
    """Backward-compat shim (prefer parse_ecg_csv)."""
    samples, col, _ = parse_ecg_csv(file_like)
    return samples, col
