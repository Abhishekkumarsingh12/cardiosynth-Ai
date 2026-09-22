"""MIT-BIH Arrhythmia Database (PhysioNet `mitdb`) — downloader wrapper."""

from __future__ import annotations

from pathlib import Path

from app.datasets.base import BasePhysioNetDataset


class MitBihArrhythmiaDataset(BasePhysioNetDataset):
    """
    Public MIT-BIH Arrhythmia Database.

    Raw files are usually under backend/datasets/mit_bih/mitdb/ when wfdb uses keep_subdirs=True;
    some wfdb versions place headers flat under mit_bih/ — is_present and prepare_pipeline accept both.
    """

    physionet_db_dir = "mitdb"

    def local_root(self, backend_root: Path) -> Path:
        return backend_root / "datasets" / "mit_bih"

    def is_present(self, backend_root: Path) -> bool:
        sub = self.wfdb_subdir(backend_root)
        root = self.local_root(backend_root)
        for d in (sub, root):
            if d.is_dir() and len(list(d.glob("*.hea"))) >= 5:
                return True
        return False
