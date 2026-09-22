"""
Modular 1D DDPM for synthetic ECG (TensorFlow). Training is offline-only.

App orchestration: app.services.synthetic_ecg.run_synthetic_generation
"""

from app.services.synthetic_ddpm.inference import (
    resolved_ddpm_model_path,
    sample_ddpm_waveform,
)

__all__ = ["resolved_ddpm_model_path", "sample_ddpm_waveform"]
