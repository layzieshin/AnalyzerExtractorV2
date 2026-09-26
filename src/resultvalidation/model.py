"""Domain records and failures for append-only run validation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


class ResultValidationError(Exception):
    """Fachlicher Fehler der Run-Validierung."""


class ValidationStoreMissingError(ResultValidationError):
    """Die Ergebnisspeicher-Datei ist nicht vorhanden."""

    def __init__(self) -> None:
        super().__init__("Datenbankdatei nicht gefunden.")


class ValidationStoreUnreadableError(ResultValidationError):
    """Die vorhandene Datenbank kann nicht als Ergebnisspeicher gelesen werden."""

    def __init__(self, message: str = "Datenbank konnte nicht gelesen werden.") -> None:
        super().__init__(message)


class ValidationStoreBusyError(ResultValidationError):
    """Ein paralleler Schreibzugriff hat die Sperre nicht rechtzeitig freigegeben."""

    def __init__(self) -> None:
        super().__init__("Datenbank ist vorübergehend gesperrt.")


class UnsupportedValidationStoreError(ResultValidationError):
    """store_spec verwendet keinen unterstützten Ergebnisspeicher."""

    def __init__(self) -> None:
        super().__init__("Der Ergebnisspeicher wird nicht unterstützt.")


class OperatorInitialsRequiredError(ResultValidationError):
    """Initialen fehlen oder bestehen nur aus Leerzeichen."""

    def __init__(self) -> None:
        super().__init__("Initialen fehlen.")


class RunNotFoundError(ResultValidationError):
    """Der adressierte Run ist im Ergebnisspeicher nicht vorhanden."""

    def __init__(self, run_id: object = None) -> None:
        self.run_id = run_id
        if isinstance(run_id, int) and not isinstance(run_id, bool):
            message = f"Run {run_id} wurde nicht gefunden."
        else:
            message = "Der Run wurde nicht gefunden."
        super().__init__(message)


class ValidationAlreadyExistsError(ResultValidationError):
    """validate_run darf eine vorhandene Validation nicht ersetzen."""

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        super().__init__(f"Run {run_id} ist bereits validiert.")


class ValidationMissingError(ResultValidationError):
    """Eine Korrektur braucht eine bereits wirksame Validation."""

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        super().__init__(f"Run {run_id} hat keine Validation, die korrigiert werden kann.")


class ValidationAmbiguousError(ResultValidationError):
    """Mehr als eine wirksame Validation liegt für denselben Run vor."""

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        super().__init__(f"Die Validation von Run {run_id} ist nicht eindeutig.")


@dataclass(frozen=True)
class RunValidation:
    """Eine append-only Validation ohne Messwerte und ohne Speicherdetails."""

    validation_id: int
    run_id: int
    operator_initials: str
    validated_at_utc: str
    comment: str
    supersedes_validation_id: int | None
    created_at_utc: str | None = None


@dataclass(frozen=True)
class RunValidationList:
    """Historie mehrerer Runs und die jeweils wirksame Validation."""

    records: tuple[RunValidation, ...]
    latest_by_run_id: Mapping[int, RunValidation]

    def __post_init__(self) -> None:
        if not isinstance(self.latest_by_run_id, MappingProxyType):
            object.__setattr__(self, "latest_by_run_id", MappingProxyType(dict(self.latest_by_run_id)))

    def latest(self, run_id: int) -> RunValidation | None:
        return self.latest_by_run_id.get(run_id)
