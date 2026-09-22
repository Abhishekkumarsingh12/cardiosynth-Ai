from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class WaveformExtractionResult:
    signal: list[float]
    confidence: float
    source: str
    notes: list[str]
    debug: Optional[Dict[str, Any]] = None


def _try_import_cv2():
    try:
        import cv2  # type: ignore

        return cv2
    except Exception:
        return None


def _to_unit_range(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return (x - lo) / (hi - lo)


def _zscore(sig: list[float]) -> list[float]:
    if not sig:
        return []
    m = sum(sig) / len(sig)
    v = sum((x - m) ** 2 for x in sig) / max(1, len(sig) - 1)
    s = math.sqrt(v) if v > 1e-12 else 1.0
    return [(x - m) / s for x in sig]


def extract_waveform_signal_from_image_bytes(image_bytes: bytes, *, target_len: int = 2000) -> WaveformExtractionResult:
    """
    Best-effort waveform trace extraction from an ECG image.

    Safety posture:
    - This is approximate; confidence is conservative.
    - If dependencies are missing or extraction quality is poor, returns empty signal with notes.
    """
    cv2 = _try_import_cv2()
    if cv2 is None:
        return WaveformExtractionResult(
            signal=[],
            confidence=0.0,
            source="image-derived",
            notes=["Waveform extraction unavailable (opencv import failed)."],
        )

    notes: list[str] = []
    try:
        import numpy as np  # type: ignore

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return WaveformExtractionResult(signal=[], confidence=0.0, source="image-derived", notes=["Could not decode image bytes."])

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Denoise / contrast
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        gray = cv2.equalizeHist(gray)

        h, w = gray.shape[:2]
        if h < 80 or w < 160:
            return WaveformExtractionResult(signal=[], confidence=0.0, source="image-derived", notes=["Image too small for waveform extraction."])

        # Remove grid lines: threshold then morphological operations
        thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 5)
        # Horizontal/vertical line removal (grid)
        horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 40), 1))
        vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 40)))
        horiz = cv2.morphologyEx(thr, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
        vert = cv2.morphologyEx(thr, cv2.MORPH_OPEN, vert_kernel, iterations=1)
        grid = cv2.bitwise_or(horiz, vert)
        trace_mask = cv2.bitwise_and(thr, cv2.bitwise_not(grid))

        # Clean small speckles
        trace_mask = cv2.morphologyEx(trace_mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
        trace_mask = cv2.morphologyEx(trace_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)

        # Heuristic graph ROI: take central region (many ECGs have margins/headers).
        y0 = int(h * 0.15)
        y1 = int(h * 0.95)
        x0 = int(w * 0.05)
        x1 = int(w * 0.98)
        roi = trace_mask[y0:y1, x0:x1]
        rh, rw = roi.shape[:2]

        # For each x, pick median y of "on" pixels as trace point.
        ys: list[float] = []
        found = 0
        for x in range(rw):
            col = roi[:, x]
            idx = np.where(col > 0)[0]
            if idx.size == 0:
                ys.append(float("nan"))
                continue
            found += 1
            ys.append(float(np.median(idx)))

        coverage = found / max(1, rw)
        if coverage < 0.25:
            return WaveformExtractionResult(
                signal=[],
                confidence=float(min(0.25, coverage)),
                source="image-derived",
                notes=[f"Trace coverage too low ({coverage:.2f}). Unable to reconstruct waveform reliably."],
                debug={"coverage": float(coverage), "roi": {"x0": x0, "x1": x1, "y0": y0, "y1": y1}},
            )

        # Interpolate NaNs linearly.
        xs = np.arange(rw, dtype=np.float64)
        yv = np.asarray(ys, dtype=np.float64)
        good = np.isfinite(yv)
        if good.sum() < max(10, rw // 10):
            return WaveformExtractionResult(signal=[], confidence=0.0, source="image-derived", notes=["Too few trace points after filtering."])
        yv[~good] = np.interp(xs[~good], xs[good], yv[good])

        # Convert y (downwards) to amplitude (upwards), normalize.
        amp = (rh - 1) - yv
        amp = amp.astype(np.float64)

        # Downsample to target_len for transport + model windowing.
        n = int(target_len)
        if rw > n:
            xi = np.linspace(0, rw - 1, n)
            amp_ds = np.interp(xi, xs, amp)
        else:
            amp_ds = amp

        sig = amp_ds.tolist()
        sig = _zscore(sig)

        # Conservative confidence based on coverage; capped.
        conf = float(min(0.65, 0.15 + 0.6 * coverage))
        notes.append("Waveform extracted from an image; values are approximate and not an exact ECG signal.")
        return WaveformExtractionResult(
            signal=sig,
            confidence=conf,
            source="image-derived",
            notes=notes,
            debug={"coverage": float(coverage)},
        )
    except Exception as e:
        return WaveformExtractionResult(signal=[], confidence=0.0, source="image-derived", notes=[f"Waveform extraction failed: {e}"])

