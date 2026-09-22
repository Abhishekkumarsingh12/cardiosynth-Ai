#!/usr/bin/env python3
"""
Offline dataset setup: download MIT-BIH (if missing) and build processed training NPZ.

Usage (from backend/):
    python setup_dataset.py
    python setup_dataset.py --dataset mit_bih --max-records 10   # quick smoke test

This script must NOT be called from FastAPI request handlers.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("setup_dataset")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare ECG datasets (offline).")
    parser.add_argument(
        "--dataset",
        default="mit_bih",
        help="Registered dataset key (default: mit_bih)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download even if dataset appears present",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Limit number of RECORDS entries for faster dev runs",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Only run preparation (expects raw files already on disk)",
    )
    args = parser.parse_args()

    from app.datasets.paths import BACKEND_ROOT
    from app.datasets.registry import get_dataset
    from app.datasets.prepare_pipeline import build_mit_bih_processed_npz

    ds = get_dataset(args.dataset)
    root = ds.local_root(BACKEND_ROOT)

    if not args.skip_download:
        log.info("Dataset root: %s", root)
        if ds.is_present(BACKEND_ROOT) and not args.overwrite:
            log.info("Dataset already present — skipping download (use --overwrite to force).")
        else:
            log.info("Downloading %s from PhysioNet (requires network)…", ds.physionet_db_dir)
            ds.download(BACKEND_ROOT, overwrite=args.overwrite)
            log.info("Download step finished.")
    else:
        log.info("Skipping download (--skip-download).")

    if args.dataset == "mit_bih":
        log.info("Building segmented / normalized NPZ…")
        summary = build_mit_bih_processed_npz(BACKEND_ROOT, max_records=args.max_records)
        log.info("Done. Summary: %s", summary)
    else:
        log.warning("No preparation pipeline wired for %s yet — extend prepare_pipeline.py.", args.dataset)


if __name__ == "__main__":
    main()
