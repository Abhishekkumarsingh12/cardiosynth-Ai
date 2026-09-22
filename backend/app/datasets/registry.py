"""Register PhysioNet datasets for future expansion (add entries + downloader class)."""

from __future__ import annotations

from typing import Dict, Type

from app.datasets.base import BasePhysioNetDataset
from app.datasets.mit_bih import MitBihArrhythmiaDataset

REGISTRY: Dict[str, Type[BasePhysioNetDataset]] = {
    "mit_bih": MitBihArrhythmiaDataset,
}


def get_dataset(key: str) -> BasePhysioNetDataset:
    key = key.lower().strip()
    if key not in REGISTRY:
        raise KeyError(f"Unknown dataset {key!r}. Available: {list(REGISTRY)}")
    return REGISTRY[key]()


def list_registered_datasets() -> list[str]:
    return sorted(REGISTRY.keys())
