from __future__ import annotations


class ApplicationError(Exception):
    """Controlled application-layer failure."""


class SettingsLoadError(ApplicationError):
    """Desktop settings could not be loaded safely."""


class SettingsValidationError(ApplicationError):
    """Desktop settings failed validation."""


class SettingsSaveError(ApplicationError):
    """Desktop settings could not be persisted."""


class ApplicationWatchError(ApplicationError):
    """Watch-folder settings or cycle failed validation."""


class PathOpenError(ApplicationError):
    """A controlled desktop path could not be opened."""


class ReportNotFoundError(ApplicationError):
    """Requested report summary/detail is not available."""


class ValidationInputError(ApplicationError):
    """Validation input or the addressed run cannot be accepted."""


class ValidationConflictError(ApplicationError):
    """An existing validation must not be overwritten or guessed."""
