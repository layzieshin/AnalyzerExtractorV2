"""Bounded, read-only PDF header/assay identity for monthly archive evidence."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import multiprocessing
from pathlib import Path
import re
import tempfile

from .reanalysis import MAX_PDF_BYTES, MAX_RESULT_BYTES, _PROCESS_LOCK


def _worker(source, known_keys, folder):
    from src.parser.api import parse
    from src.normalizer.api import normalize_lines
    from src.contentsplitter.api import split_assay_sections
    plates, dates = {}, set()
    try:
        document = parse(source)
        if not 0 < len(document.pages) <= 1000:
            raise ValueError("PDF-Seitenzahl ist nicht zulässig.")
        text = "\n".join(normalize_lines([line for page in document.pages for line in page.lines]))
        plates = {value.strip().casefold(): value.strip() for value in re.findall(r"Plattenname:[ \t]*([^\n]*?)[ \t]+Zeit:", text)}
        dates = {datetime.strptime(value, "%d.%m.%Y").date().isoformat()
                 for value in re.findall(r"Datum:[ \t]*(\d{2}\.\d{2}\.\d{4})", text)}
        sections = split_assay_sections(text, known_keys=known_keys)
        if len(plates) > 1 or len(dates) > 1 or not sections:
            raise ValueError("Platte, Messdatum oder erwartete Assays sind in der PDF nicht eindeutig belegt.")
        result = {"plate": next(iter(plates.values()), ""), "date": next(iter(dates), ""),
                  "assay_keys": [row.assay_key for row in sections], "error": ""}
    except Exception as exc:
        result = {"plate": next(iter(plates.values())) if len(plates) == 1 else "",
                  "date": next(iter(dates)) if len(dates) == 1 else "",
                  "assay_keys": [], "error": str(exc)}
    result["plate_candidates"] = sorted(plates.values(), key=str.casefold)
    (Path(folder) / "identity.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def inspect_pdf_archive_identity(pdf_path, *, expected_sha256, known_assay_keys=(), project_root=None):
    """Parse exactly the selected SHA snapshot in a bounded fresh child."""
    with Path(pdf_path).open("rb") as handle:
        payload = handle.read(MAX_PDF_BYTES + 1)
    if len(payload) > MAX_PDF_BYTES or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("PDF wurde geändert oder überschreitet 128 MB.")
    known_keys = set(known_assay_keys)
    if project_root is not None:
        from src.assaycandidate.api import load_known_assay_keys
        configured = load_known_assay_keys(str(Path(project_root) / "rules/index.json"))
        if configured is None:
            raise ValueError("Konfigurierte Assayabschnitte sind nicht sicher lesbar.")
        known_keys.update(configured)
    if not _PROCESS_LOCK.acquire(timeout=20):
        raise ValueError("PDF-Prüfung ist beschäftigt.")
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="arev2-archive-identity-") as temporary:
            source = Path(temporary) / "source.pdf"
            source.write_bytes(payload)
            process = multiprocessing.get_context("spawn").Process(target=_worker,
                args=(str(source), tuple(sorted(known_keys)), temporary), daemon=True)
            process.start()
            process.join(timeout=20)
            if process.is_alive() or process.exitcode != 0:
                raise ValueError("PDF-Prüfung ist fehlgeschlagen oder hat das Zeitlimit überschritten.")
            result = Path(temporary) / "identity.json"
            if result.stat().st_size > MAX_RESULT_BYTES:
                raise ValueError("PDF-Prüfdaten sind zu groß.")
            return {**json.loads(result.read_text(encoding="utf-8")), "sha256": expected_sha256}
    finally:
        if process is not None:
            if process.is_alive():
                process.terminate()
                process.join(timeout=.5)
            if process.is_alive():
                process.kill()
                process.join(timeout=.5)
            process.close()
        _PROCESS_LOCK.release()
