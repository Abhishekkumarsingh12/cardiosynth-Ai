"""Errors raised when the ECG classifier is required but unavailable."""


class ClassifierUnavailableError(Exception):
    """Strict inference mode: model missing, TensorFlow missing, or load/inference failed."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
