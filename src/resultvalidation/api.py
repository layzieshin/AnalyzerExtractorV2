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
    ValidationStateConflictError,
)
from .store import correct_validation, get_run_validation, list_run_validations, list_run_validations_readonly, validate_run

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
    "ValidationStateConflictError",
    "correct_validation",
    "get_run_validation",
    "list_run_validations",
    "list_run_validations_readonly",
    "replace_validation",
    "validate_run",
]


def replace_validation(
    store_spec: Mapping[str, Any],
    run_id: int,
    operator_initials: str,
    comment: str = "",
    *,
    expected_selection_token: str | None = None,
    request_id: str | None = None,
    project_root: str | None = None,
) -> RunValidation:
    """Append-only correction. Does not update the previous validation."""
    return correct_validation(
        store_spec,
        run_id,
        operator_initials,
        comment=comment,
        expected_selection_token=expected_selection_token,
        request_id=request_id,
        project_root=project_root,
    )
