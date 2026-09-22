"""
Extensible PhysioNet / WFDB dataset layout.

Add new datasets by subclassing BasePhysioNetDataset and registering a factory if needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BasePhysioNetDataset(ABC):
    """Shared contract: local root, presence check, download via wfdb."""

    physionet_db_dir: str  # e.g. "mitdb"

    @abstractmethod
    def local_root(self, backend_root: Path) -> Path:
        """Directory under backend/datasets/... for this dataset family."""

    def wfdb_subdir(self, backend_root: Path) -> Path:
        """Where wfdb places the DB when keep_subdirs=True (e.g. .../mit_bih/mitdb)."""
        return self.local_root(backend_root) / self.physionet_db_dir

    def is_present(self, backend_root: Path) -> bool:
        """True if the database looks complete enough to skip re-download."""
        sub = self.wfdb_subdir(backend_root)
        records = sub / "RECORDS"
        if not records.is_file():
            return False
        # At least one record header present (wfdb layout)
        hea = list(sub.glob("*.hea"))
        return len(hea) >= 5

    def download(self, backend_root: Path, *, overwrite: bool = False, annotators: Optional[list] = None) -> None:
        """
        Download from PhysioNet using wfdb. Network required on first run.

        Never call this from HTTP handlers — use setup_dataset.py or admin tooling only.
        """
        import wfdb

        root = self.local_root(backend_root)
        root.mkdir(parents=True, exist_ok=True)
        if self.is_present(backend_root) and not overwrite:
            return
        ann = annotators if annotators is not None else ["atr"]
        wfdb.dl_database(
            self.physionet_db_dir,
            str(root),
            records="all",
            annotators=ann,
            keep_subdirs=True,
            overwrite=overwrite,
        )
