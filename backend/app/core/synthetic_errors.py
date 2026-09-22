"""Synthetic generation failures surfaced as HTTP 503."""


class SyntheticGenerationError(Exception):
    """DDPM/procedural generation cannot complete (misconfiguration or strict mode)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
