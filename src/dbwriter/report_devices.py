"""DbWriter transaction for report-device evidence and qualified identities."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.resultstore.api import get_report_device_context, get_result_run, list_result_runs
from src.jobcontroller.api import get_job_evidence
from src.ingestion.api import resolve_current_path

from .model import ResultRevisionConflictError, ResultRevisionError


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def ensure_report_device_schema(conn):
    expected = {
        "report_device_assignments": {"assignment_id", "report_id", "predecessor_id", "pdf_sha256", "device_id", "snapshot_json", "actor", "reason", "request_id", "intent_hash", "created_at_utc"},
        "run_device_claims": {"claim_id", "assay_key", "identity_hash", "device_id", "run_id", "assignment_id", "revision_id", "created_at_utc"},
        "candidate_materializations": {"candidate_id", "run_id", "source_snapshot_json", "created_at_utc"},
    }
    versions = [int(row[0]) for row in conn.execute("SELECT version FROM dbwriter_schema_migrations ORDER BY version")]
    present = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} & expected.keys()
    if 2 in versions or present:
        if present != expected.keys() or any({str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")} != columns for table, columns in expected.items()):
            raise ResultRevisionError("Unvollständiges Bericht-Geräteschema; bitte Datenbestand klären.")
    conn.execute("""CREATE TABLE IF NOT EXISTS report_device_assignments (
        assignment_id INTEGER PRIMARY KEY, report_id TEXT NOT NULL, predecessor_id INTEGER NOT NULL,
        pdf_sha256 TEXT NOT NULL, device_id TEXT NOT NULL, snapshot_json TEXT NOT NULL,
        actor TEXT NOT NULL, reason TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE,
        intent_hash TEXT NOT NULL, created_at_utc TEXT NOT NULL, UNIQUE(report_id,predecessor_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS run_device_claims (
        claim_id INTEGER PRIMARY KEY, assay_key TEXT NOT NULL, identity_hash TEXT NOT NULL,
        device_id TEXT NOT NULL, run_id INTEGER NOT NULL, assignment_id INTEGER NOT NULL,
        revision_id INTEGER NOT NULL, created_at_utc TEXT NOT NULL,
        UNIQUE(assay_key,identity_hash,device_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS candidate_materializations (
        candidate_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL UNIQUE,
        source_snapshot_json TEXT NOT NULL, created_at_utc TEXT NOT NULL)""")
    conn.execute("INSERT OR IGNORE INTO dbwriter_schema_migrations VALUES (2,?)", (_stamp(),))
    for table in ("report_device_assignments", "run_device_claims", "candidate_materializations"):
        for verb in ("UPDATE", "DELETE"):
            conn.execute(f"""CREATE TRIGGER IF NOT EXISTS immutable_{table}_{verb.lower()}
                BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_device_evidence'); END""")


def semantic_identity(result):
    """Original assay identity without an import default/device namespace."""
    basis = result.get("dedupe_basis")
    version = result.get("dedupe_version")
    if not isinstance(basis, dict) or not basis:
        raise ResultRevisionError("Die ursprünglichen Identitätsbestandteile fehlen. Bitte diesen Fall gezielt klären.")
    if version == "v2":
        keys = ("PLATTE", "DATUM", "ZEIT", "TEST")
        if any(not isinstance(basis.get(key), str) or not basis[key].strip() for key in keys):
            raise ResultRevisionError("Die ursprüngliche v2-Messidentität ist unvollständig.")
        identity = {key: basis[key] for key in keys}
    elif version == "explicit_legacy":
        identity = {key: value for key, value in basis.items() if key != "device_id"}
        if not identity or any(value is None or not str(value).strip() for value in identity.values()):
            raise ResultRevisionError("Die explizite Altidentität ist unvollständig.")
    else:
        raise ResultRevisionError("Die ursprüngliche Deduplizierungsfassung ist nicht belegt.")
    return _hash([result["assay_key"], version, identity])


def _claim(conn, result, device_id, run_id, assignment_id, revision_id=0):
    identity = semantic_identity(result)
    owner = conn.execute("SELECT run_id FROM run_device_claims WHERE assay_key=? AND identity_hash=? AND device_id=?",
                         (result["assay_key"], identity, device_id)).fetchone()
    if owner and int(owner[0]) != run_id:
        raise ResultRevisionConflictError("Diese Messidentität gehört auf dem bestätigten Gerät bereits zu einer anderen Messung. Bitte den Duplikatfall klären.")
    if not owner:
        conn.execute("INSERT INTO run_device_claims(assay_key,identity_hash,device_id,run_id,assignment_id,revision_id,created_at_utc) VALUES(?,?,?,?,?,?,?)",
                     (result["assay_key"], identity, device_id, run_id, assignment_id, revision_id, _stamp()))


def _verified_candidate(candidate, project_root, *, run_id=None, sqlite_path=None):
    meta = candidate["meta"]
    provenance = meta.get("source_provenance") or {}
    root = str(project_root or provenance.get("project_root") or "")
    job_id = str(meta.get("job_id") or "")
    evidence = get_job_evidence(root, job_id) if root else None
    if not evidence or not evidence.state_available or evidence.status != "DONE":
        raise ResultRevisionError("Der abgeschlossene ursprüngliche Verarbeitungsnachweis des Kandidaten fehlt.")
    state = json.loads(Path(evidence.state_path).read_text(encoding="utf-8"))
    if state.get("job_id") != job_id or state.get("pdf_sha256") != candidate["pdf_sha256"] or job_id != candidate["pdf_sha256"][:16]:
        raise ResultRevisionError("Quellbericht und vollständiger PDF-Hash widersprechen sich.")
    if sqlite_path and Path(state.get("output_plan", {}).get("sqlite_path", "")).resolve() != Path(sqlite_path).resolve():
        raise ResultRevisionError("Der eingefrorene Verarbeitungsplan gehört zu einem anderen Ergebnisspeicher.")
    entries = state.get("output_plan", {}).get("assays", [])
    matches = [entry for entry in entries if (entry.get("write_item", {}).get("duplicate_candidate_id") == candidate["candidate_id"]
        if candidate.get("candidate_id") is not None else entry.get("sqlite_run_id") == run_id)]
    if len(matches) != 1:
        raise ResultRevisionError("Die ursprüngliche Kandidaten-/Assayzuordnung ist nicht eindeutig.")
    entry = matches[0]
    record, write = entry["assay_record"], entry["write_item"]
    if any(record.get(key) != candidate.get(key) for key in ("assay_key", "dedupe_key", "dedupe_version", "dedupe_basis")) or record.get("data") != candidate["payload"]:
        raise ResultRevisionError("Die eingefrorenen Nutzlast- oder Identitätsdaten des Kandidaten wurden verändert.")
    if write.get("assay_block_hash") != candidate["assay_block_hash"] or write.get("pdf_sha256") != candidate["pdf_sha256"] or (candidate.get("candidate_id") is not None and write.get("existing_run_id") != candidate["existing_run_id"]):
        raise ResultRevisionError("Die eingefrorene Quell- oder Vergleichszuordnung wurde verändert.")
    frozen = write.get("source_provenance")
    if not isinstance(frozen, dict) or (provenance and frozen != provenance):
        raise ResultRevisionError("Der ursprüngliche eingefrorene Regel-/Quellstand fehlt oder widerspricht sich.")
    text = frozen.get("rule_source_text")
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != frozen.get("rule_sha256") or json.loads(text) != frozen.get("ruleset"):
        raise ResultRevisionError("Der ursprüngliche vollständige Regelstand ist nicht nachgewiesen.")
    normalized = Path(evidence.normalized_dump_path).read_text(encoding="utf-8")
    start, end = frozen.get("block_start"), frozen.get("block_end")
    if (hashlib.sha256(normalized.encode()).hexdigest() != frozen.get("normalized_sha256") or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(normalized) or hashlib.sha256(normalized[start:end].encode()).hexdigest() != candidate["assay_block_hash"]):
        raise ResultRevisionError("Der ursprüngliche normalisierte Assayblock ist nicht nachgewiesen.")
    resolution = resolve_current_path(root, job_id, evidence.pdf_path)
    pdf = Path(resolution.current_pdf_path)
    if resolution.path_status == "ambiguous" or not pdf.is_file() or hashlib.sha256(pdf.read_bytes()).hexdigest() != candidate["pdf_sha256"]:
        raise ResultRevisionError("Die unveränderte ursprüngliche PDF ist nicht eindeutig verfügbar.")
    return record, frozen


def _verify_report_runs(conn, context, project_root, sqlite_path):
    for row in context["runs"]:
        original = row.get("original_result") or row
        provenance = row.get("source_provenance") or {}
        materialized = provenance.get("device_materialization")
        if materialized:
            cursor = conn.execute("SELECT * FROM duplicate_candidates WHERE id=?", (materialized["candidate_id"],))
            raw = cursor.fetchone()
            if raw is None:
                raise ResultRevisionError("Der ursprüngliche Kandidatenbeleg fehlt.")
            value = dict(zip([column[0] for column in cursor.description], raw))
            candidate = {**value, "candidate_id": value["id"], "meta": json.loads(value["candidate_meta_json"]),
                         "payload": json.loads(value["candidate_payload_json"]), "dedupe_basis": json.loads(value["dedupe_basis_json"])}
        else:
            candidate = {**original, "candidate_id": None, "meta": {"job_id": row["job_id"], "source_provenance": provenance}}
        _verified_candidate(candidate, project_root, run_id=row["id"], sqlite_path=sqlite_path)


def _device_identity_owners(conn, sqlite_path, result, device_id):
    """All retained qualified claims, including readable historical owners."""
    identity = semantic_identity(result)
    claimed = conn.execute("SELECT run_id FROM run_device_claims WHERE assay_key=? AND identity_hash=? AND device_id=?",
                           (result["assay_key"], identity, device_id)).fetchone()
    owners = {int(claimed[0])} if claimed else set()
    spec = {"driver": "sqlite", "path": str(Path(sqlite_path).resolve())}
    for other in list_result_runs(spec, assay_key=result["assay_key"], limit=None)["runs"]:
        if other.get("effective_device_id") != device_id:
            continue
        selected = {selection["revision_id"] for selection in other.get("result_selections", [])}
        states = [other.get("original_result") or other, other]
        states += [revision["result"] for revision in other.get("result_revisions", []) if revision["revision_id"] in selected]
        for state in states:
            try:
                same = semantic_identity(state) == identity
            except ResultRevisionError:
                same = state.get("dedupe_key") == result.get("dedupe_key")
            if same:
                owners.add(int(other["id"]))
    return owners


def assert_device_identity_available(conn, sqlite_path, result, device_id, run_id):
    if _device_identity_owners(conn, sqlite_path, result, device_id) - {run_id}:
        raise ResultRevisionConflictError("Die fachliche Messidentität ist auf diesem Gerät bereits belegt. Bitte den Duplikatfall klären.")


def confirm_report_device(sqlite_path, report_id, device_id, *, expected_context_token, request_id, actor, reason="", project_root=None):
    """First owner step: evidence and optional materialization, never validation."""
    from .revisions import _write_connection
    if not isinstance(actor, str) or not actor.strip() or not isinstance(request_id, str) or not request_id.strip():
        raise ResultRevisionError("Für die Berichtbestätigung bitte Initialen und Anfragekennung angeben.")
    intent = _hash([report_id, device_id, expected_context_token, actor.strip(), reason])
    spec = {"driver": "sqlite", "path": str(Path(sqlite_path).resolve())}
    with _write_connection(sqlite_path) as conn:
        prior = conn.execute("SELECT assignment_id,intent_hash FROM report_device_assignments WHERE request_id=?", (request_id,)).fetchone()
        context = get_report_device_context(spec, report_id)
        if not context:
            raise ResultRevisionConflictError("Der Quellbericht wurde nicht gefunden. Bitte aktualisieren.")
        if prior:
            if prior[1] != intent or context["assignment_id"] != prior[0]:
                raise ResultRevisionConflictError("Die Anfrage wurde schon für einen anderen oder inzwischen überholten Berichtstand verwendet.")
            return context
        if context["context_token"] != expected_context_token:
            raise ResultRevisionConflictError("Bericht, Gerätebestand, Vergleichsmessung oder Ergebnisauswahl wurde geändert. Bitte erneut prüfen.")
        if not context["source_identity_verified"]:
            raise ResultRevisionError("Dieser Altbericht hat keinen eindeutigen vollständigen Quellbeleg. Bitte die Geräteherkunft gezielt klären.")
        if device_id not in {row["device_id"] for row in context["devices"]}:
            raise ResultRevisionError("Bitte ein aktives benanntes Gerät auswählen.")
        if context["assignment_id"] and context["device_id"] != device_id and not str(reason).strip():
            raise ResultRevisionError("Für eine Gerätekorrektur bitte den Grund angeben.")
        _verify_report_runs(conn, context, project_root, sqlite_path)
        materialize = []
        unresolved = []
        for candidate, comparison in zip(context["candidates"], context["comparisons"]):
            record, frozen = _verified_candidate(candidate, project_root, sqlite_path=sqlite_path)
            target_owners = _device_identity_owners(conn, sqlite_path, record, device_id)
            if target_owners:
                # A third PDF may still name raw owner A while B already owns
                # this qualified identity. Keep its own report/device evidence
                # and clarification case; do not duplicate B or block another
                # independently eligible assay in this same report.
                unresolved.append({"candidate_id": candidate["candidate_id"], "reason": "same_device_duplicate",
                    "target_run_ids": sorted(target_owners)})
                continue
            other = comparison["device_id"]
            if not other or other == device_id:
                unresolved.append({"candidate_id": candidate["candidate_id"], "reason": "comparison_device_unconfirmed" if not other else "same_device_duplicate"})
                continue
            if candidate["pdf_sha256"] == (get_result_run(spec, candidate["existing_run_id"]) or {}).get("pdf_sha256"):
                raise ResultRevisionError("Eine byteidentische Quelle ist kein unabhängiger zweiter Bericht.")
            materialize.append((candidate, record, frozen))
        if context["assignment_id"] and context["device_id"] == device_id and not materialize:
            return context
        snapshot = {"run_ids": [int(row["id"]) for row in context["runs"]], "candidate_decisions": unresolved,
            "source_context_token": expected_context_token, "inventory_version_id": context["inventory_version_id"]}
        # BEGIN IMMEDIATE serializes this allocation with every writer. The
        # immutable evidence row is inserted once, with its final membership.
        assignment_id = int(conn.execute("SELECT COALESCE(MAX(assignment_id),0)+1 FROM report_device_assignments").fetchone()[0])
        for row in context["runs"]:
            # Claims retain every previously selected correction identity.
            original = row.get("original_result") or row
            assert_device_identity_available(conn, sqlite_path, original, device_id, int(row["id"]))
            assert_device_identity_available(conn, sqlite_path, row, device_id, int(row["id"]))
            _claim(conn, original, device_id, int(row["id"]), assignment_id)
            _claim(conn, row, device_id, int(row["id"]), assignment_id, int(row.get("revision_id") or 0))
        for candidate, record, frozen in materialize:
            identity = semantic_identity(record)
            assert_device_identity_available(conn, sqlite_path, record, device_id, 0)
            owners = conn.execute("SELECT run_id FROM run_device_claims WHERE assay_key=? AND identity_hash=? AND device_id=?", (record["assay_key"], identity, device_id)).fetchall()
            if owners:
                raise ResultRevisionConflictError("Die Kandidatenmessung ist auf diesem Gerät bereits vorhanden; keine zweite Messung angelegt.")
            storage_key = "device-v1:" + _hash([device_id, record["assay_key"], identity])
            inserted = conn.execute("""INSERT INTO runs(job_id,pdf_path,assay_key,lot_id,dedupe_key,device_id,dedupe_version,dedupe_basis_json,pdf_sha256,assay_block_hash,ruleset_file,payload_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (report_id, candidate["meta"]["pdf_path"], record["assay_key"], record["lot_id"], storage_key,
                record["device_id"], record["dedupe_version"], _json(record["dedupe_basis"]), candidate["pdf_sha256"], candidate["assay_block_hash"], frozen["ruleset_file"], _json(record["data"]), _stamp()))
            run_id = int(inserted.lastrowid)
            provenance = {**frozen, "device_materialization": {"candidate_id": candidate["candidate_id"], "original_dedupe_key": record["dedupe_key"], "identity_hash": identity}}
            conn.execute("INSERT INTO run_source_provenance VALUES(?,?)", (run_id, _json(provenance)))
            _claim(conn, {**record, "payload": record["data"]}, device_id, run_id, assignment_id)
            conn.execute("INSERT INTO candidate_materializations VALUES(?,?,?,?)", (candidate["candidate_id"], run_id, _json({"record": record, "source_provenance": frozen}), _stamp()))
            conn.execute("UPDATE duplicate_candidates SET status='resolved',decision_at=?,decision_by=?,decision_note=? WHERE id=? AND status='pending'", (_stamp(), actor.strip(), "Eigener bestätigter Gerätebezug", candidate["candidate_id"]))
            conn.execute("INSERT INTO duplicate_decision_log(candidate_id,action,decided_at,decided_by,note) VALUES(?,?,?,?,?)", (candidate["candidate_id"], "separate_device", _stamp(), actor.strip(), "Quelle und getrennte Geräteidentität bestätigt"))
            snapshot["run_ids"].append(run_id)
        conn.execute("""INSERT INTO report_device_assignments
            (assignment_id,report_id,predecessor_id,pdf_sha256,device_id,snapshot_json,actor,reason,request_id,intent_hash,created_at_utc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (assignment_id, report_id, context["assignment_id"], context["pdf_sha256"], device_id,
            _json(snapshot), actor.strip(), str(reason).strip(), request_id, intent, _stamp()))
    return get_report_device_context(spec, report_id)
