"""Remove analyses, uploads, and synthetic artifacts from DB and disk."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import ECGAnalysis, ECGUpload, SyntheticECG

log = logging.getLogger(__name__)


def unlink_if_file(path_str: str | None) -> None:
    if not path_str:
        return
    p = Path(path_str)
    try:
        if p.is_file():
            p.unlink()
    except OSError as e:
        log.warning("Could not delete file %s: %s", p, e)


def delete_analysis_bundle(db: Session, analysis: ECGAnalysis, upload: ECGUpload) -> None:
    """Delete synthetic rows/files, analysis row, upload file, upload row."""
    synth_rows = db.query(SyntheticECG).filter(SyntheticECG.analysis_id == analysis.id).all()
    for s in synth_rows:
        unlink_if_file(s.stored_path)

    unlink_if_file(upload.stored_path)

    db.delete(analysis)
    db.delete(upload)
    db.commit()
