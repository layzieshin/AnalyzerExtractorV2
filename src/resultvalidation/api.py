"""Public boundary for append-only run validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .model import (
    OperatorInitialsRequiredError,
    ResultValidationError,
    RunNotFoundError,
    RunValidation,
    RunValidationList,
    UnsupportedValidationStoreError,
    ValidationAlreadyExistsError,
    ValidationAmbiguousError,
    ValidationMissingError,
    ValidationStoreBusyError,
    ValidationStoreMissingError,
    ValidationStoreUnreadableError,
)
from .store import correct_validation, get_run_validation, list_run_validations, validate_run

__all__ = [
    "OperatorInitialsRequiredError",
    "ResultValidationError",
    "RunNotFoundError",
    "RunValidation",
    "RunValidationList",
    "UnsupportedValidationStoreError",
    "ValidationAlreadyExistsError",
    "ValidationAmbiguousError",
    "ValidationMissingError",
    "ValidationStoreBusyError",
    "ValidationStoreMissingError",
    "ValidationStoreUnreadableError",
    "correct_validation",
    "get_run_validation",
    "list_run_validations",
    "replace_validation",
    "validate_run",
]


def replace_validation(
    store_spec: Mapping[str, Any],
    run_id: int,
    operator_initials: str,
    comment: str = "",
) -> RunValidation:
    """Append-only correction. Does not update the previous validation."""
    return correct_validation(
        store_spec,
        run_id,
        operator_initials,
        comment=comment,
    )
