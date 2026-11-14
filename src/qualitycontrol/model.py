"""Small immutable contracts shared by the quality-control owner."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

CURRENT_ANALYSIS_ID = "arev2-qc-analysis-v5"
SUPPORTED_MODEL_VERSIONS = frozenset({
    (1, algorithm, renderer)
    for algorithm in ("arev2-qc-analysis-v1", "arev2-qc-analysis-v2")
    for renderer in ("arev2-qc-pdf-v1", "arev2-qc-pdf-v2")
} | {(2, "arev2-qc-analysis-v3", "arev2-qc-pdf-v3"),
     (3, "arev2-qc-analysis-v4", "arev2-qc-pdf-v4"), (4, CURRENT_ANALYSIS_ID, "arev2-qc-pdf-v5")})


def sd_parameter_definition(profile: object, control_id: str, *, device_id: str | None = None) -> dict[str, str] | None:
    """Only the identity, value interpretation and unit of the SD's variable.

    Names, dates, grouping, SOLL and manufacturer limits do not define SD.
    Control IDs are scoped by their stable profile, device and assay identities.
    """
    if not isinstance(profile, Mapping) or not isinstance(profile.get("controls"), list):
        return None
    controls = [row for row in profile["controls"] if isinstance(row, Mapping) and row.get("control_id") == control_id]
    if len(controls) != 1:
        return None
    control = controls[0]
    fields = control.get("fields")
    if not isinstance(fields, Mapping):
        return None
    result = {key: profile.get(key) for key in ("profile_id", "device_id", "assay_key", "numeric_grammar")}
    if not result["device_id"] and profile.get("profile_schema_version") == 2:
        result["device_id"] = device_id
    result.update(control_id=control_id, ist_field=fields.get("IST"), unit=control.get("unit") or profile.get("unit"),
                  unit_field=control.get("unit_field", ""))
    if profile.get("dimensionless") is True:
        result.update(unit="1", unit_field="")
    if (any(not isinstance(value, str) or not value.strip() for key, value in result.items() if key != "unit_field")
            or not isinstance(result["unit_field"], str) or result["numeric_grammar"] not in {"auto", "decimal_dot", "decimal_comma"}):
        return None
    return result


class QualityControlError(Exception):
    """A visible, controlled QC failure."""


class QCStoreError(QualityControlError):
    """The explicitly selected store cannot safely be used."""


class QCConflictError(QualityControlError):
    """An inspected configuration or source population has changed."""


class QCConfigurationError(QualityControlError):
    """Configuration needs clarification; values must not be guessed."""


class QCReportError(QualityControlError):
    """A supplied analysis cannot be rendered or exported safely."""


@dataclass(frozen=True)
class QCAnalysis:
    """Immutable canonical bytes shared by statistical presentation and PDF.

    Reading a model returns a fresh value. No mutable Python dictionary remains
    attached to the frozen analysis or can alter its declared hash afterwards.
    """

    model_json: str
    model_sha256: str

    def __post_init__(self) -> None:
        try:
            model = json.loads(self.model_json)
        except (ValueError, TypeError) as exc:
            raise QCConfigurationError("Das Analysemodell ist unlesbar.") from exc
        if not isinstance(model, dict) or canonical_json(model) != self.model_json or content_hash(model) != self.model_sha256:
            raise QCConfigurationError("Das Analysemodell oder seine Prüfsumme ist ungültig.")

    @classmethod
    def freeze(cls, model: dict[str, Any]) -> "QCAnalysis":
        return cls(canonical_json(model), content_hash(model))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.model_json)

    @property
    def is_supported(self) -> bool:
        model = self.to_dict()
        version, algorithm, renderer = (model.get(key) for key in ("analysis_model_version", "algorithm_id", "renderer_id"))
        return (type(version) is int and isinstance(algorithm, str) and isinstance(renderer, str)
                and (version, algorithm, renderer) in SUPPORTED_MODEL_VERSIONS)


@dataclass(frozen=True)
class QCUsageSnapshot:
    """Canonical read-only usage evidence, independent of statistical eligibility."""

    snapshot_json: str
    snapshot_sha256: str

    def __post_init__(self):
        try:
            value = json.loads(self.snapshot_json)
        except (TypeError, ValueError) as exc:
            raise QCConfigurationError("Der Nutzungsnachweis ist unlesbar.") from exc
        if not isinstance(value, dict) or canonical_json(value) != self.snapshot_json or content_hash(value) != self.snapshot_sha256:
            raise QCConfigurationError("Der Nutzungsnachweis oder seine Prüfsumme ist ungültig.")

    @classmethod
    def freeze(cls, value):
        return cls(canonical_json(value), content_hash(value))

    def to_dict(self):
        return json.loads(self.snapshot_json)


@dataclass(frozen=True)
class QCPdfReport:
    pdf_bytes: bytes
    pdf_sha256: str
    model_sha256: str
    renderer_id: str
    page_count: int


@dataclass(frozen=True)
class ConfigurationContext:
    """Configuration edits have technical provenance without requiring a person.

    This context is deliberately separate from the mandatory actor carried by
    result validation and clinical lot decisions. Empty means not provided.
    """

    request_id: str
    operator_initials: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise QCConfigurationError("Anfragekennung fehlt.")
        for key in ("request_id", "operator_initials", "reason"):
            value = getattr(self, key)
            if not isinstance(value, str):
                raise QCConfigurationError("Konfigurationskontext muss Text enthalten.")
            object.__setattr__(self, key, value.strip())


@dataclass(frozen=True)
class MutationContext:
    operator_initials: str
    request_id: str
    reason: str = ""

    def __post_init__(self) -> None:
        for field, label in (("operator_initials", "Initialen"), ("request_id", "Anfragekennung")):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise QCConfigurationError(f"{label} fehlen.")
            object.__setattr__(self, field, value.strip())
        if not isinstance(self.reason, str):
            raise QCConfigurationError("Die Begründung muss Text sein.")
        object.__setattr__(self, "reason", self.reason.strip())


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise QCConfigurationError("Die Konfiguration enthält nicht speicherbare Werte.") from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
