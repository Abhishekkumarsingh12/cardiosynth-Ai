"""
Offline data preparation: load WFDB records, segment beats, normalize, save NPZ.

Used by setup_dataset.py and training scripts. Not invoked from the FastAPI app.

Label encoding:
  SYMBOL_TO_CLASS maps MIT-BIH beat annotations (N, L, R, A, V) → integer 0…4.

Imbalance:
  training/train_classifier.py applies inverse-frequency class_weight during fit and light
  Gaussian noise augmentation in full (non-bootstrap) mode. For heavier imbalance, increase
  augmentation or use focal loss in a fork of the training script.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import wfdb

from app.datasets.paths import DEFAULT_PROCESSED_NPZ

log = logging.getLogger(__name__)

# AAMI-style five-class mapping (common in arrhythmia literature) — simplified symbol set
SYMBOL_TO_CLASS = {
    "N": 0,
    "L": 1,
    "R": 2,
    "A": 3,
    "V": 4,
}
CLASS_NAMES = ["N", "L", "R", "A", "V"]

DEFAULT_WINDOW = 187  # ~0.52 s at 360 Hz; standard in many MIT-BIH beat papers
TARGET_FS = 360


def _pick_ml2_channel(record: wfdb.Record) -> int:
    names = [str(s).lower() for s in (record.sig_name or [])]
    for prefer in ("mlii", "ii", "v1"):
        if prefer in names:
            return names.index(prefer)
    return 0


def resolve_mitdb_directory(backend_root: Path) -> Path:
    """
    WFDB may place files under datasets/mit_bih/mitdb/ (keep_subdirs=True) or flat under mit_bih/.
    """
    root = backend_root / "datasets" / "mit_bih"
    nested = root / "mitdb"
    if nested.is_dir() and (list(nested.glob("*.hea")) or (nested / "RECORDS").is_file()):
        return nested
    if root.is_dir() and list(root.glob("*.hea")):
        return root
    raise FileNotFoundError(
        f"No MIT-BIH WFDB headers found under {root} or {nested}. Run setup_dataset.py with network."
    )


def _read_record_ids(mitdb_dir: Path) -> List[str]:
    rec = mitdb_dir / "RECORDS"
    if rec.is_file():
        lines = rec.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        return [ln.strip().split("/")[-1].strip() for ln in lines if ln.strip()]
    stems = sorted({p.stem for p in mitdb_dir.glob("*.hea")})
    return stems


def segment_record_beats(
    record_id: str,
    mitdb_dir: Path,
    window: int = DEFAULT_WINDOW,
    symbols: Optional[Dict[str, int]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load one record, extract fixed-length windows centered on annotated beats.

    Returns X shape (n_beats, window), y shape (n_beats,) int class ids.
    """
    symbols = symbols or SYMBOL_TO_CLASS
    half = window // 2
    data_dir = str(mitdb_dir.resolve())

    try:
        # Local absolute pn_dir can be mis-handled as a remote path in some wfdb versions;
        # chdir keeps reads unambiguously local.
        prev = os.getcwd()
        os.chdir(data_dir)
        try:
            rec = wfdb.rdrecord(record_id)
        finally:
            os.chdir(prev)
    except Exception as e:
        log.warning("Skip record %s: %s", record_id, e)
        return np.zeros((0, window), dtype=np.float32), np.zeros((0,), dtype=np.int32)

    ch = _pick_ml2_channel(rec)
    sig = rec.p_signal[:, ch].astype(np.float64)
    fs = float(rec.fs) if rec.fs else TARGET_FS

    try:
        prev = os.getcwd()
        os.chdir(data_dir)
        try:
            ann = wfdb.rdann(record_id, extension="atr")
        finally:
            os.chdir(prev)
    except Exception as e:
        log.warning("No annotations for %s: %s", record_id, e)
        return np.zeros((0, window), dtype=np.float32), np.zeros((0,), dtype=np.int32)

    xs: List[np.ndarray] = []
    ys: List[int] = []

    for samp, sym in zip(ann.sample, ann.symbol):
        sym_s = sym.decode("ascii", errors="ignore") if isinstance(sym, bytes) else str(sym)
        if sym_s not in symbols:
            continue
        # Resample window length if sampling rate != TARGET_FS (simple linear interp)
        if fs != TARGET_FS:
            # map physical window duration to samples at native fs
            duration_s = window / TARGET_FS
            native_len = max(8, int(duration_s * fs))
            lo = samp - native_len // 2
            hi = lo + native_len
            if lo < 0 or hi > len(sig):
                continue
            seg = sig[lo:hi]
            t_old = np.linspace(0, 1, num=native_len)
            t_new = np.linspace(0, 1, num=window)
            seg = np.interp(t_new, t_old, seg).astype(np.float32)
        else:
            lo = samp - half
            hi = lo + window
            if lo < 0 or hi > len(sig):
                continue
            seg = sig[lo:hi].astype(np.float32)

        # per-beat z-score (training stability)
        m = float(np.mean(seg))
        s = float(np.std(seg)) or 1.0
        seg = ((seg - m) / s).astype(np.float32)

        xs.append(seg)
        ys.append(symbols[sym_s])

    if not xs:
        return np.zeros((0, window), dtype=np.float32), np.zeros((0,), dtype=np.int32)

    return np.stack(xs, axis=0), np.array(ys, dtype=np.int32)


def build_mit_bih_processed_npz(
    backend_root: Path,
    out_path: Optional[Path] = None,
    window: int = DEFAULT_WINDOW,
    max_records: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Walk MIT-BIH records under backend/datasets/mit_bih/mitdb/, segment beats, save NPZ.

    Returns summary dict with counts and output path.
    """
    out_path = out_path or DEFAULT_PROCESSED_NPZ
    mitdb_dir = resolve_mitdb_directory(backend_root)

    ids = _read_record_ids(mitdb_dir)
    if max_records:
        ids = ids[:max_records]

    all_x: List[np.ndarray] = []
    all_y: List[np.ndarray] = []

    for rid in ids:
        X, y = segment_record_beats(rid, mitdb_dir, window=window)
        if len(X):
            all_x.append(X)
            all_y.append(y)
        log.info("Record %s: %d beats", rid, len(X))

    if not all_x:
        raise RuntimeError("No beats extracted — check dataset download and annotations.")

    Xf = np.concatenate(all_x, axis=0)
    yf = np.concatenate(all_y, axis=0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        X=Xf,
        y=yf,
        class_names=np.array(CLASS_NAMES),
        window=np.array([window]),
        source=np.array(["mitdb"]),
    )

    log.info("Saved %s — samples=%d window=%d", out_path, len(Xf), window)
    return {
        "out_path": str(out_path),
        "n_samples": int(len(Xf)),
        "window": window,
        "classes": CLASS_NAMES,
        "per_class_counts": {CLASS_NAMES[i]: int(np.sum(yf == i)) for i in range(len(CLASS_NAMES))},
    }


def load_processed_npz(path: Optional[Path] = None) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Load training-ready arrays from NPZ (for training scripts)."""
    path = path or DEFAULT_PROCESSED_NPZ
    if not path.is_file():
        raise FileNotFoundError(f"Processed file missing: {path}. Run setup_dataset.py.")
    z = np.load(path, allow_pickle=True)
    X = z["X"].astype(np.float32)
    y = z["y"].astype(np.int32)
    if "class_names" in z.files:
        raw = z["class_names"]
        names = []
        for item in np.atleast_1d(raw):
            if isinstance(item, bytes):
                names.append(item.decode("utf-8", errors="ignore"))
            else:
                names.append(str(item))
    else:
        names = list(CLASS_NAMES)
    return X, y, names
