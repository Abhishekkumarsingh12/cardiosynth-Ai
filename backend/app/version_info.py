"""Release metadata (set CARDIOSYNTH_BUILD in deploys to identify logs)."""

import os

# Bump when adding routes like /debug/model or changing startup contract.
APP_VERSION = "0.2.0"
BUILD_ID = os.environ.get("CARDIOSYNTH_BUILD", "local-dev")
