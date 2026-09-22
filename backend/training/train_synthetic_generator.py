#!/usr/bin/env python3
"""
Legacy entrypoint: synthetic generation is now a conditional DDPM.

Train offline with:
    python training/train_synthetic_ddpm.py
"""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    script = Path(__file__).resolve().with_name("train_synthetic_ddpm.py")
    raise SystemExit(subprocess.call([sys.executable, str(script)]))
