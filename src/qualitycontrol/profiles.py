"""Complete immutable profile revisions and explicit measurement grammars."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .model import ConfigurationContext, MutationContext, QCConfigurationError, QCConflictError, canonical_json, content_hash, utc_now
from .store import get_inventory, intent_hash, read_connection, repeated_request, version_record, write_connection

CLASSIC_RULES = ("1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10x")
# Reviewed original exports use a single decimal separator, never grouping.
# Trust exact frozen rule bytes AND the numeric field contract, not an assay
# name, today's mutable rule file, a value's size, or the system locale.
_DECIMAL_EXPORT_RULES = frozenset({
    "6d8a208b8d0bc094a2f773021d77b4c3e017a170a21bd9eab66757608d91f4c6",
    "b4ac927c6a42cf530bd249fd47ce1a00e7e4bfe7121886962453e837314f3582",
    "29712a54603f91555938719ab61dc6c122cb336e065939e4b4b90bd9bf955593",
    "7bcefb846e6adf1bdedb4d336b323ea11f7f564ab0e074c9b0e12094556b2fa7",
    "46dd4579ab241e07fee34ad298eb37195ce38a6844c75f6f0d7b7cd6ed9cb64f",
    "624d69bdcb158c31d3b14c3099982d85772f01a4d994f7db5f8d191f6e02f89e",
    "2a4cfc81a6b795a1a5be6ef5be379c80213ae4e76e3ff753d96d4146d5a3951f",
    "39fd35f36f8b1143e6731bd0282699faecedeb077bbd446aa83726ef6cf1290a",
    "260b37fc3185bbc21422456b611e860b71bf49758a6e7a66d108505a5c2a100f",
    "ad967255c07483b3ff0eeb7951e47ed71d0a32ed6fac9bdc8ec63849c2e02e9a",
})


def interpret_numeric(raw: object, grammar: str, *, field_key: str = "", source: Mapping[str, Any] | None = None) -> dict[str, str]:
    applied, method = grammar, "explicit-profile" if grammar != "auto" else "unambiguous-auto"
    rule_hash = ""
    if grammar == "auto" and source:
        text, rules = source.get("rule_source_text"), source.get("ruleset")
        rule_hash = str(source.get("rule_sha256") or "")
        if isinstance(text, str) and isinstance(rules, dict) and rule_hash in _DECIMAL_EXPORT_RULES and hashlib.sha256(text.encode()).hexdigest() == rule_hash:
            try:
                original = json.loads(text) == rules
            except ValueError:
                original = False
            fields = [field for field in rules.get("extract_rules", {}).get("fields", []) if field.get("key") == field_key]
            numeric_contract = len(fields) == 1 and any(token in str(fields[0].get("regex", "")) for token in (r"\d+(?:[\.,]\d+)?", r"\d+(?:[.,]\d+)?"))
            if original and numeric_contract:
                applied = "decimal_comma" if isinstance(raw, str) and "," in raw else "decimal_dot"
                method = "verified-original-decimal-export-v1"
    value = parse_decimal(raw, applied)
    return {"value": str(value), "grammar": applied, "method": method, "field_key": field_key,
            "rule_sha256": rule_hash if method == "verified-original-decimal-export-v1" else "", "interpretation_version": "qc-number-v2"}


def parse_decimal(raw: object, grammar: str) -> Decimal:
    if grammar == "auto":
        if not isinstance(raw, str):
            raise QCConfigurationError("Messwert fehlt oder ist nicht als Rohtext belegt.")
        text = raw.strip()
        match = re.fullmatch(r"[+-]?(\d+)([.,])(\d+)", text)
        if match and len(match[1]) <= 3 and match[1] != "0" and len(match[3]) == 3:
            raise QCConfigurationError("Zahl ist mehrdeutig; Dezimal- oder Tausendertrennzeichen bitte im Profil ausdrücklich klären.")
        grammar = "decimal_comma" if "," in text else "decimal_dot"
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


def interpret_measurement(payload: Mapping[str, Any], configuration: Mapping[str, Any]) -> dict[str, Any]:
    """One raw-source interpretation shared by charts, chronology and evidence.

    A precision interval expresses what the source actually states. A date is
    never turned into a measured midnight and no import/validation clock is used.
    Historical explicit formats retain their strict parsing contract.
    """
    date_field = configuration.get("measurement_date_field") or ""
    time_field = configuration.get("measurement_time_field") or ""
    date_format = configuration.get("measurement_date_format") or ""
    time_format = configuration.get("measurement_time_format") or ""
    auto = configuration.get("profile_schema_version") == 2
    date_keys = [date_field] if date_field else [key for key in payload if key.casefold() in {"datum", "date", "measurement_date"}]
    time_keys = [time_field] if time_field else ([key for key in payload if key.casefold() in {"zeit", "time", "measurement_time"}] if auto else [])
    result = {"date_raw": payload.get(date_keys[0]) if date_keys else None,
              "time_raw": payload.get(time_keys[0]) if time_keys else None,
              "date_sources": {key: payload.get(key) for key in date_keys}, "time_sources": {key: payload.get(key) for key in time_keys},
              "date": None, "time": None, "precision": "unknown", "interval": None, "reasons": [],
              "interpretation_version": "qc-measurement-v2", "date_format": date_format or "auto", "time_format": time_format or "auto"}
    def precision(fmt):
        value = "day"
        for token, name in (("%H", "hours"), ("%M", "minutes"), ("%S", "seconds")):
            if token not in fmt:
                break
            value = name
        return value
    def automatic_date(raw):
        if not isinstance(raw, str):
            raise ValueError("missing date")
        text = raw.strip()
        match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", text)
        if match:
            return datetime(int(match[3]), int(match[2]), int(match[1])), "day"
        match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?", text)
        if not match:
            raise ValueError("unknown or ambiguous date")
        value = datetime(*(int(match[index]) for index in (1, 2, 3)),
                         *(int(match[index] or 0) for index in (4, 5, 6)))
        return value, "seconds" if match[6] is not None else "minutes" if match[4] is not None else "day"
    dates = []
    for key in date_keys:
        raw = payload.get(key)
        if raw is None or not str(raw).strip():
            continue
        try:
            dates.append((datetime.fromisoformat(parse_measurement_date(raw, date_format)), precision(date_format)) if date_format else automatic_date(raw))
        except (QCConfigurationError, ValueError, TypeError):
            result["reasons"].append("measurement_date_invalid")
    if not dates:
        if not result["reasons"]:
            result["reasons"].append("measurement_date_missing")
        return result
    if result["reasons"] or len({value.date() for value, _ in dates}) != 1:
        result["reasons"].append("measurement_date_conflict" if len(dates) > 1 else "measurement_date_invalid")
        return result
    measured = dates[0][0].replace(hour=0, minute=0, second=0, microsecond=0)
    result["date"] = measured.date().isoformat()
    clocks = [(value.time(), stated) for value, stated in dates if stated != "day"]
    clock_invalid = False
    for key in time_keys:
        raw = payload.get(key)
        if raw is None or not str(raw).strip():
            if time_field:
                result["reasons"].append("measurement_time_missing")
            continue
        try:
            if time_format:
                clocks.append((datetime.fromisoformat(parse_measurement_date(raw, time_format)).time(), precision(time_format)))
            else:
                match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(raw).strip())
                if not match:
                    raise ValueError("unknown clock")
                clock = datetime(2000, 1, 1, int(match[1]), int(match[2]), int(match[3] or 0)).time()
                clocks.append((clock, "seconds" if match[3] is not None else "minutes"))
        except (QCConfigurationError, ValueError, TypeError):
            result["reasons"].append("measurement_time_invalid")
            clock_invalid = True
    ranks = {"day": 0, "hours": 1, "minutes": 2, "seconds": 3}
    chosen = "day"
    if clocks and not clock_invalid:
        ordered = sorted(clocks, key=lambda row: ranks[row[1]], reverse=True)
        best, stated = ordered[0]
        for clock, other in ordered[1:]:
            if clock.isoformat(timespec=other) != best.isoformat(timespec=other):
                result["reasons"].append("measurement_time_conflict")
                clock_invalid = True
        if not clock_invalid:
            chosen = stated
            measured = datetime.combine(measured.date(), best)
            if chosen == "hours":
                measured = measured.replace(minute=0, second=0)
            elif chosen == "minutes":
                measured = measured.replace(second=0)
            result["time"] = measured.time().isoformat(timespec=chosen)
    widths = {"day": 86_400_000_000, "hours": 3_600_000_000, "minutes": 60_000_000, "seconds": 1_000_000}
    lower = ((measured.toordinal() * 86400 + measured.hour * 3600 + measured.minute * 60 + measured.second) * 1_000_000)
    result["precision"] = chosen
    result["interval"] = {"lower": lower, "upper_exclusive": lower + widths[chosen], "precision": chosen,
                          "display": measured.date().isoformat() if chosen == "day" else measured.isoformat(sep=" ", timespec=chosen)}
    return result


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
        invalid = [f"{role}: {key}" for role, key in control["fields"].items() if key and key not in available]
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
    contract = raw.get("profile_schema_version", 1)
    if type(contract) is not int or contract not in (1, 2):
        raise QCConfigurationError("Die Profilfassung wird nicht unterstützt.")
    modern = contract == 2
    required = (
        ("profile_id", "Profilkennung"), ("name", "Profilname"), ("device_id", "Gerät"),
        ("assay_key", "Assay"), ("measurement_date_field", "Messdatumsfeld"),
        ("measurement_date_format", "Messdatumsformat"), ("unit", "Einheit"))
    result = {}
    for key, label in required:
        if modern and key in {"device_id", "measurement_date_field", "measurement_date_format", "unit"}:
            value = raw.get(key, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise QCConfigurationError(f"{label} muss Text sein.")
            result[key] = value.strip()
        else:
            result[key] = _required(raw, key, label)
    if modern:
        result["profile_schema_version"] = 2
        result["dimensionless"] = raw.get("dimensionless", False)
        if not isinstance(result["dimensionless"], bool):
            raise QCConfigurationError("Dimensionslose Größe muss ausdrücklich gewählt sein.")
    date_format = result["measurement_date_format"]
    directives = re.findall(r"%.", date_format)
    if (date_format or not modern) and (not {"%Y", "%m", "%d"}.issubset(directives) or any(value not in {"%Y", "%m", "%d", "%H", "%M", "%S"} for value in directives)):
        raise QCConfigurationError("Datumsformat braucht %Y, %m und %d, optional %H:%M:%S; z. B. %d.%m.%Y.")
    time_field, time_format = raw.get("measurement_time_field"), raw.get("measurement_time_format")
    time_field, time_format = "" if time_field is None else time_field, "" if time_format is None else time_format
    if not isinstance(time_field, str) or not isinstance(time_format, str):
        raise QCConfigurationError("Messzeitfeld und Zeitformat müssen Text sein.")
    time_field, time_format = time_field.strip(), time_format.strip()
    if bool(time_field) != bool(time_format) and not (modern and time_field and not time_format):
        raise QCConfigurationError("Optionales Messzeitfeld und Zeitformat bitte gemeinsam angeben oder beide leer lassen.")
    if time_field:
        time_directives = re.findall(r"%.", time_format)
        if time_format and (time_directives.count("%H") != 1 or time_directives.count("%M") != 1 or time_directives.count("%S") > 1
                or any(value not in {"%H", "%M", "%S"} for value in time_directives)
                or "%" in re.sub(r"%[HMS]", "", time_format)):
            raise QCConfigurationError("Zeitformat braucht einmal %H und %M, optional %S; z. B. %H:%M oder %H:%M:%S, ohne Datum oder Zeitzone.")
        if any(value in directives for value in ("%H", "%M", "%S")):
            raise QCConfigurationError("Ein separates Messzeitfeld braucht ein Datumsformat ohne Uhrzeit.")
        result.update(measurement_time_field=time_field, measurement_time_format=time_format)
    grammar = str(raw.get("numeric_grammar") or ("auto" if modern else ""))
    if grammar not in ({"auto", "decimal_dot", "decimal_comma"} if modern else {"decimal_dot", "decimal_comma"}):
        raise QCConfigurationError("Zahlenschreibweise ausdrücklich wählen: Dezimalpunkt oder Dezimalkomma, ohne Tausendertrennzeichen.")
    if raw.get("qc_profile", "classic-six-v1" if modern else None) != "classic-six-v1":
        raise QCConfigurationError("Das freigegebene QC-Verfahren ist classic-six-v1.")
    enabled = raw.get("enabled_rules", [] if modern else None)
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
        mapping = {}
        for key in ("IST", "SOLL", "MIN", "MAX"):
            if modern and key != "IST" and not fields.get(key):
                mapping[key] = ""
            else:
                mapping[key] = _required(fields, key, f"{name}: Feld für {key}")
        assigned = [value for value in mapping.values() if value]
        if len(set(assigned)) != len(assigned):
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


def list_profile_drafts(store_spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Explicitly retained raw forms; opening a legacy store never migrates it."""
    with read_connection(store_spec) as conn:
        if conn is None or not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='qc_profile_draft_versions'").fetchone():
            return []
        rows = [version_record(row) for row in conn.execute("SELECT * FROM qc_profile_draft_versions ORDER BY version_id")]
    heads = {row["draft_id"]: row for row in rows}
    return [row for row in heads.values() if row["state"] == "retained"]


def save_profile_draft(store_spec: Mapping[str, Any], *, draft_id: str, profile_id: str, base_version_id: int,
                       snapshot: Mapping[str, Any], expected_version_id: int, context: ConfigurationContext,
                       discard: bool = False) -> dict[str, Any]:
    """Keep incomplete raw text separately; this never publishes a live profile."""
    if not draft_id.strip() or not profile_id.strip() or not isinstance(snapshot, Mapping):
        raise QCConfigurationError("Entwurfskennung und Formularinhalt fehlen.")
    serialized = canonical_json(dict(snapshot))
    if len(serialized.encode("utf-8")) > 1024 * 1024:
        raise QCConfigurationError("Der Profilentwurf ist zu groß.")
    intent = content_hash({"draft": draft_id, "profile": profile_id, "base": base_version_id, "snapshot": dict(snapshot),
                           "expected": expected_version_id, "discard": discard})
    with write_connection(store_spec, initialize=True) as conn:
        repeated = conn.execute("SELECT * FROM qc_profile_draft_versions WHERE request_id=?", (context.request_id,)).fetchone()
        if repeated:
            if repeated["intent_hash"] != intent:
                raise QCConflictError("Die Anfragekennung gehört zu einem anderen Entwurf.")
            return version_record(repeated)
        previous = conn.execute("SELECT * FROM qc_profile_draft_versions WHERE draft_id=? ORDER BY version_id DESC LIMIT 1", (draft_id,)).fetchone()
        if (previous["version_id"] if previous else 0) != expected_version_id:
            raise QCConflictError("Der behaltene Entwurf wurde geändert. Ihre Eingaben bleiben erhalten.")
        cursor = conn.execute("""INSERT INTO qc_profile_draft_versions
            (draft_id,predecessor_id,profile_id,base_version_id,snapshot_json,state,created_at_utc,request_id,intent_hash)
            VALUES (?,?,?,?,?,?,?,?,?)""", (draft_id, expected_version_id, profile_id, base_version_id, serialized,
            "discarded" if discard else "retained", utc_now(), context.request_id, intent))
        return version_record(conn.execute("SELECT * FROM qc_profile_draft_versions WHERE version_id=?", (cursor.lastrowid,)).fetchone())


def get_profile(store_spec: Mapping[str, Any], version_id: int) -> dict[str, Any]:
    with read_connection(store_spec) as conn:
        row = conn.execute("SELECT * FROM qc_profile_versions WHERE version_id=?", (int(version_id),)).fetchone() if conn is not None else None
        result = version_record(row)
    if result is None:
        raise QCConfigurationError("Das Prüfprofil wurde nicht gefunden.")
    return result


def save_profile(store_spec: Mapping[str, Any], snapshot: Mapping[str, Any], *, expected_version_id: int,
                 expected_inventory_version_id: int, context: ConfigurationContext | MutationContext,
                 available_field_keys: Collection[str] | None = None, draft_id: str = "") -> dict[str, Any]:
    """Save a revision; application writes supply the current assay's field catalog.

    Independent QC clients may omit catalog context. Historical reads never
    revalidate frozen mappings against a newer rule catalog.
    """
    value = normalize_profile(snapshot)
    if available_field_keys is not None:
        _validate_current_fields(value, available_field_keys)
    intent = intent_hash("save_profile", {"snapshot": value, "expected": expected_version_id,
                                         "inventory": expected_inventory_version_id, **({"draft_id": draft_id} if draft_id else {})}, context)
    with write_connection(store_spec, initialize=value.get("profile_schema_version") == 2 and expected_version_id == 0) as conn:
        repeated = repeated_request(conn, "qc_profile_versions", context, intent)
        if repeated:
            return repeated
        inventory = get_inventory(store_spec)
        if inventory["version_id"] != expected_inventory_version_id:
            raise QCConflictError("Die Geräteliste wurde geändert. Bitte neu laden.")
        if value["device_id"]:
            device = next((row for row in inventory["snapshot"]["devices"] if row["device_id"] == value["device_id"]), None)
            if not device or not device.get("display_name") or not device["active"]:
                raise QCConfigurationError("Die gewählte Gerätebindung braucht ein aktives benanntes Gerät.")
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
        result = version_record(conn.execute("SELECT * FROM qc_profile_versions WHERE version_id=?", (cursor.lastrowid,)).fetchone())
        if draft_id:
            retained = conn.execute("SELECT * FROM qc_profile_draft_versions WHERE draft_id=? ORDER BY version_id DESC LIMIT 1", (draft_id,)).fetchone()
            if retained and retained["state"] == "retained":
                if retained["profile_id"] != value["profile_id"] or retained["base_version_id"] != expected_version_id:
                    raise QCConflictError("Der Entwurf gehört zu einer anderen Profilfassung. Ihre Eingaben bleiben erhalten.")
                conn.execute("""INSERT INTO qc_profile_draft_versions
                    (draft_id,predecessor_id,profile_id,base_version_id,snapshot_json,state,created_at_utc,request_id,intent_hash)
                    VALUES (?,?,?,?,?,'discarded',?,?,?)""", (draft_id, retained["version_id"], value["profile_id"], expected_version_id,
                    retained["snapshot_json"], utc_now(), context.request_id + ":draft", content_hash({"published_profile_version_id": result["version_id"]})))
        return result
