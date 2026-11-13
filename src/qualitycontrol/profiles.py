"""Complete immutable profile revisions and explicit measurement grammars."""
from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .model import MutationContext, QCConfigurationError, QCConflictError, canonical_json, utc_now
from .store import get_inventory, intent_hash, read_connection, repeated_request, version_record, write_connection

CLASSIC_RULES = ("1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10x")


def parse_decimal(raw: object, grammar: str) -> Decimal:
    if not isinstance(raw, str) or grammar not in {"decimal_dot", "decimal_comma"}:
        raise QCConfigurationError("Messwert oder Zahlenschreibweise fehlt.")
    text = raw.strip()
    separator = r"\." if grammar == "decimal_dot" else ","
    if not re.fullmatch(rf"[+-]?(?:[0-9]+(?:{separator}[0-9]+)?|{separator}[0-9]+)", text):
        raise QCConfigurationError("Zahl ist leer, qualifiziert, mehrdeutig oder entspricht nicht der gewählten Schreibweise.")
    try:
        value = Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise QCConfigurationError("Zahl konnte nicht gelesen werden.") from exc
    if not value.is_finite():
        raise QCConfigurationError("Zahlen müssen endlich sein.")
    return value


def parse_measurement_date(raw: object, date_format: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise QCConfigurationError("Extrahiertes Messdatum fehlt.")
    try:
        value = datetime.strptime(raw.strip(), date_format)
        if value.strftime(date_format) != raw.strip():
            raise ValueError("format mismatch")
        return value.isoformat()
    except (ValueError, TypeError) as exc:
        raise QCConfigurationError("Messdatum entspricht nicht dem festgelegten Format.") from exc


def _single_value_limit(raw: Mapping[str, Any]) -> tuple[bool, str | None]:
    enabled = raw.get("single_value_limits_enabled", False)
    if not isinstance(enabled, bool):
        raise QCConfigurationError("RiliBÄK-Grenzen vorhanden muss eindeutig gewählt sein.")
    if not enabled:
        return False, None
    value = raw.get("single_value_limit_percent")
    text = str(value).strip() if value is not None and not isinstance(value, bool) else ""
    if not re.fullmatch(r"[+]?(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)", text):
        raise QCConfigurationError("Für die Einzelwertgrenzen ist eine endliche, nicht negative Abweichung in % erforderlich (Punkt oder Komma, ohne Tausendertrennzeichen).")
    number = Decimal(text.replace(",", "."))
    if not number.is_finite() or number < 0:
        raise QCConfigurationError("Die erlaubte Einzelwertabweichung muss endlich und nicht negativ sein.")
    return True, str(number)


def _validate_current_fields(value: Mapping[str, Any], available_field_keys: Collection[str]) -> None:
    available = set(available_field_keys)
    for control in value["controls"]:
        invalid = [f"{role}: {key}" for role, key in control["fields"].items() if key not in available]
        if invalid:
            raise QCConfigurationError(
                f"{control['name']}: Feldzuordnung prüfen. Diese Felder gehören nicht zum aktuellen Assay {value['assay_key']}: {', '.join(invalid)}."
            )


def _required(value: Mapping[str, Any], key: str, label: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text.strip():
        raise QCConfigurationError(f"{label} fehlt.")
    return text.strip()


def normalize_sd_reference(raw: object, *, declaration: bool = False) -> dict[str, Any] | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, Mapping):
        raise QCConfigurationError("Die SD-Referenz ist ungültig.")
    kind = raw.get("kind")
    if kind == "manual":
        value = parse_decimal(raw.get("value"), "decimal_dot")
        if value <= 0:
            raise QCConfigurationError("Die manuelle SD muss positiv sein.")
        return {"kind": "manual", "value": str(value), "reference": str(raw.get("reference") or "").strip()}
    if kind == "confirmed_baseline" and (declaration or raw.get("confirmed") is True):
        return {"kind": "confirmed_baseline", "confirmed": raw.get("confirmed") is True}
    raise QCConfigurationError("Eine Referenzserie muss ausdrücklich bestätigt werden.")


def normalize_profile(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise QCConfigurationError("Ein vollständiges Prüfprofil ist erforderlich.")
    result = {key: _required(raw, key, label) for key, label in (
        ("profile_id", "Profilkennung"), ("name", "Profilname"), ("device_id", "Gerät"),
        ("assay_key", "Assay"), ("measurement_date_field", "Messdatumsfeld"),
        ("measurement_date_format", "Messdatumsformat"), ("unit", "Einheit"))}
    date_format = result["measurement_date_format"]
    directives = re.findall(r"%.", date_format)
    if not {"%Y", "%m", "%d"}.issubset(directives) or any(value not in {"%Y", "%m", "%d", "%H", "%M", "%S"} for value in directives):
        raise QCConfigurationError("Datumsformat braucht %Y, %m und %d, optional %H:%M:%S; z. B. %d.%m.%Y.")
    time_field, time_format = raw.get("measurement_time_field"), raw.get("measurement_time_format")
    time_field, time_format = "" if time_field is None else time_field, "" if time_format is None else time_format
    if not isinstance(time_field, str) or not isinstance(time_format, str):
        raise QCConfigurationError("Messzeitfeld und Zeitformat müssen Text sein.")
    time_field, time_format = time_field.strip(), time_format.strip()
    if bool(time_field) != bool(time_format):
        raise QCConfigurationError("Optionales Messzeitfeld und Zeitformat bitte gemeinsam angeben oder beide leer lassen.")
    if time_field:
        time_directives = re.findall(r"%.", time_format)
        if (time_directives.count("%H") != 1 or time_directives.count("%M") != 1 or time_directives.count("%S") > 1
                or any(value not in {"%H", "%M", "%S"} for value in time_directives)
                or "%" in re.sub(r"%[HMS]", "", time_format)):
            raise QCConfigurationError("Zeitformat braucht einmal %H und %M, optional %S; z. B. %H:%M oder %H:%M:%S, ohne Datum oder Zeitzone.")
        if any(value in directives for value in ("%H", "%M", "%S")):
            raise QCConfigurationError("Ein separates Messzeitfeld braucht ein Datumsformat ohne Uhrzeit.")
        result.update(measurement_time_field=time_field, measurement_time_format=time_format)
    grammar = str(raw.get("numeric_grammar") or "")
    if grammar not in {"decimal_dot", "decimal_comma"}:
        raise QCConfigurationError("Zahlenschreibweise ausdrücklich wählen: Dezimalpunkt oder Dezimalkomma, ohne Tausendertrennzeichen.")
    if raw.get("qc_profile") != "classic-six-v1":
        raise QCConfigurationError("Das freigegebene QC-Verfahren ist classic-six-v1.")
    enabled = raw.get("enabled_rules")
    if not isinstance(enabled, list) or len(set(enabled)) != len(enabled) or any(rule not in CLASSIC_RULES for rule in enabled):
        raise QCConfigurationError("Die Westgard-Regelauswahl ist ungültig.")
    controls = raw.get("controls")
    if not isinstance(controls, list) or not controls:
        raise QCConfigurationError("Mindestens eine benannte Kontrolle ist erforderlich.")
    prepared, ids, names = [], set(), set()
    for control in controls:
        if not isinstance(control, Mapping):
            raise QCConfigurationError("Eine Kontrolle ist ungültig.")
        identifier = _required(control, "control_id", "Kontrollkennung")
        name = _required(control, "name", "Kontrollname")
        if identifier in ids or name.casefold() in names:
            raise QCConfigurationError("Kontrollkennungen und Kontrollnamen müssen eindeutig sein.")
        ids.add(identifier)
        names.add(name.casefold())
        fields = control.get("fields")
        if not isinstance(fields, Mapping):
            raise QCConfigurationError("IST/SOLL/MIN/MAX-Feldzuordnung fehlt.")
        mapping = {key: _required(fields, key, f"{name}: Feld für {key}") for key in ("IST", "SOLL", "MIN", "MAX")}
        if len(set(mapping.values())) != 4:
            raise QCConfigurationError("IST/SOLL/MIN/MAX brauchen unterschiedliche exakte Feldschlüssel.")
        prepared.append({"control_id": identifier, "name": name, "fields": mapping,
                         "unit": str(control.get("unit") or result["unit"]).strip(),
                         "unit_field": str(control.get("unit_field") or "").strip(),
                         "sd_reference": normalize_sd_reference(control.get("sd_reference"), declaration=True)})
    relative = raw.get("relative_limit_percent")
    if relative is not None and str(relative).strip():
        number = parse_decimal(str(relative), "decimal_dot")
        if number < 0:
            raise QCConfigurationError("Die relative Grenze darf nicht negativ sein.")
        relative = str(number)
    else:
        relative = None
    for flag in ("rili_applicable", "relative_enabled"):
        if not isinstance(raw.get(flag, False), bool):
            raise QCConfigurationError("Anwendbarkeit und relative Auswertung müssen eindeutig gewählt sein.")
    single_enabled, single_percent = _single_value_limit(raw)
    result.update(numeric_grammar=grammar, qc_profile="classic-six-v1", enabled_rules=list(enabled), controls=prepared,
                  rili_applicable=raw.get("rili_applicable", False), relative_enabled=raw.get("relative_enabled", False),
                  relative_limit_percent=relative, run_grouping_field=str(raw.get("run_grouping_field") or "").strip(),
                  guideline_reference=str(raw.get("guideline_reference") or "").strip(),
                  single_value_limits_enabled=single_enabled, single_value_limit_percent=single_percent)
    return result


def list_profiles(store_spec: Mapping[str, Any], *, include_history: bool = False) -> list[dict[str, Any]]:
    with read_connection(store_spec) as conn:
        if conn is None:
            return []
        rows = [version_record(row) for row in conn.execute("SELECT * FROM qc_profile_versions ORDER BY version_id")]
    if include_history:
        return rows
    heads = {row["profile_id"]: row for row in rows}
    return list(heads.values())


def get_profile(store_spec: Mapping[str, Any], version_id: int) -> dict[str, Any]:
    with read_connection(store_spec) as conn:
        row = conn.execute("SELECT * FROM qc_profile_versions WHERE version_id=?", (int(version_id),)).fetchone() if conn is not None else None
        result = version_record(row)
    if result is None:
        raise QCConfigurationError("Das Prüfprofil wurde nicht gefunden.")
    return result


def save_profile(store_spec: Mapping[str, Any], snapshot: Mapping[str, Any], *, expected_version_id: int,
                 expected_inventory_version_id: int, context: MutationContext,
                 available_field_keys: Collection[str] | None = None) -> dict[str, Any]:
    """Save a revision; application writes supply the current assay's field catalog.

    Independent QC clients may omit catalog context. Historical reads never
    revalidate frozen mappings against a newer rule catalog.
    """
    value = normalize_profile(snapshot)
    if available_field_keys is not None:
        _validate_current_fields(value, available_field_keys)
    intent = intent_hash("save_profile", {"snapshot": value, "expected": expected_version_id,
                                         "inventory": expected_inventory_version_id}, context)
    with write_connection(store_spec) as conn:
        repeated = repeated_request(conn, "qc_profile_versions", context, intent)
        if repeated:
            return repeated
        inventory = get_inventory(store_spec)
        if inventory["version_id"] != expected_inventory_version_id:
            raise QCConflictError("Die Geräteliste wurde geändert. Bitte neu laden.")
        device = next((row for row in inventory["snapshot"]["devices"] if row["device_id"] == value["device_id"]), None)
        if not device or device["incomplete"] or not device["active"]:
            raise QCConfigurationError("Das Prüfprofil braucht ein aktives Gerät mit Namen und SN, LNR oder EVA.")
        previous = version_record(conn.execute("SELECT * FROM qc_profile_versions WHERE profile_id=? ORDER BY version_id DESC LIMIT 1",
                                               (value["profile_id"],)).fetchone())
        if (previous["version_id"] if previous else 0) != expected_version_id:
            raise QCConflictError("Das Prüfprofil wurde geändert. Bitte neu laden.")
        if previous and any(previous["snapshot"][key] != value[key] for key in ("device_id", "assay_key")):
            raise QCConfigurationError("Gerät und Assay einer Profilidentität bleiben erhalten; bitte ein neues Profil anlegen.")
        cursor = conn.execute("""INSERT INTO qc_profile_versions
            (profile_id, predecessor_id, snapshot_json, actor, created_at_utc, reason, request_id, intent_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (value["profile_id"], expected_version_id, canonical_json(value),
                context.operator_initials, utc_now(), context.reason or "Prüfprofil geändert", context.request_id, intent))
        return version_record(conn.execute("SELECT * FROM qc_profile_versions WHERE version_id=?", (cursor.lastrowid,)).fetchone())
