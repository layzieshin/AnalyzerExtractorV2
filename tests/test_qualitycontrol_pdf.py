"""Real fresh-process PDF, pagination, bounded cleanup and exact export tests."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import copy
import base64
from pathlib import Path
import multiprocessing

import pytest

from src.qualitycontrol.api import (
    MutationContext, QCReportError, analyze_lot, close_lot, export_report_evidence,
    get_lot_sources, get_report_evidence, open_lot, render_analysis_pdf,
)
from src.qualitycontrol.model import content_hash
from test_qualitycontrol_analysis import manifest, manual, analyzed, reference_context
from test_qualitycontrol_profiles_lots import fixture, add_run, payload

def _extract_text_worker(source, destination, geometry_destination=None, structure_destination=None):
    import fitz

    with fitz.open(source) as document:
        text = "\n".join(page.get_text() for page in document)
        if geometry_destination is not None:
            spans = [{"page": number, "text": span["text"], "bbox": span["bbox"]}
                     for number, page in enumerate(document)
                     for block in page.get_text("dict")["blocks"] for line in block.get("lines", []) for span in line["spans"]]
            Path(geometry_destination).write_text(json.dumps(spans, ensure_ascii=False), encoding="utf-8")
        if structure_destination is not None:
            Path(structure_destination).write_text(json.dumps({"attachments": document.embfile_names(),
                "pages": len(document)}), encoding="utf-8")
    Path(destination).write_text(text, encoding="utf-8")


def extract_text(path: Path, *, geometry_destination: Path | None = None, structure_destination: Path | None = None) -> str:
    destination = path.with_suffix(".txt")
    process = multiprocessing.get_context("spawn").Process(target=_extract_text_worker,
        args=(str(path), str(destination), str(geometry_destination) if geometry_destination is not None else None,
            str(structure_destination) if structure_destination is not None else None), daemon=True)
    try:
        process.start()
        process.join(timeout=15)
        assert not process.is_alive() and process.exitcode == 0
        assert destination.stat().st_size < 16 * 1024 * 1024
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.5)
        if process.is_alive():
            process.kill()
            process.join(timeout=0.5)
        process.close()
    return destination.read_text(encoding="utf-8")


def test_real_spawn_multipage_many_controls_long_names_and_large_payload(tmp_path: Path):
    controls = [f"c{index}" for index in range(6)] * 18
    dates = [(datetime(2026, 1, 1) + timedelta(days=index // 6)).isoformat() for index in range(len(controls))]
    groups = [f"analytical-{index // 6}" for index in range(len(controls))]
    source = manifest(["90" if index % 2 else "110" for index in range(len(controls))], targets="100", controls=controls, dates=dates, groups=groups)
    for control in source["profile_snapshot"]["controls"]:
        control["name"] = f"Kontrolle {control['control_id']} – " + "Langer deutscher Kontrollname für die vollständige Qualitätsauswertung " * 3
        control["unit"] = "µg/L"
    for point in source["included"]:
        point["control_name"] = next(control["name"] for control in source["profile_snapshot"]["controls"] if control["control_id"] == point["control_id"])
        point["unit"] = point["unit_raw"] = "µg/L"
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    analysis = analyzed(source, manual(set(controls), value="10"))
    report = render_analysis_pdf(analysis)
    path = tmp_path / "long-report.pdf"
    path.write_bytes(report.pdf_bytes)
    assert report.page_count >= 6 and len(report.pdf_bytes) > 65_536
    assert report.model_sha256 == analysis.model_sha256
    assert report.pdf_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    text = extract_text(path)
    assert "KONTROLLPROBENEINZELMESSUNG" in text and "QMMA: 10" in text
    assert "µg/L" in text and "Messwert" in text
    assert "c0" in text and "c5" in text and "Digitaler Nachweis" in text
    assert "Validiert durch:" not in text and "Validiert am UTC:" not in text
    assert "Vollständige Regelbefunde" not in text and "Modell SHA-256" not in text
    assert "Seite" in text and "18.01.2026" in text
    readable = " ".join(text.split())
    assert "QMMA-Grenze (relativ): 10 %" in readable and "QMMA-Bewertung: Innerhalb der Grenze" in readable
    assert "Referenzart: manuell festgelegte SD" in readable and "Auswahl None" not in readable


def test_real_pdf_no_sd_qmma_and_exact_stored_export_never_clobbers(tmp_path: Path):
    spec, profile = fixture(tmp_path)
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    opened = open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=source["source_token"], context=MutationContext("RR", "open-pdf"))
    analysis = analyze_lot(source, opened["snapshot"]["sd_references"])
    report = render_analysis_pdf(analysis)
    preview = tmp_path / "no-sd-report.pdf"
    preview.write_bytes(report.pdf_bytes)
    text = extract_text(preview)
    assert "QMMA: 2" in text and "Keine SD-Referenz" in text and "nicht verfügbar" in text
    assert "Westgard nicht vollständig verfügbar" in text
    assert "Westgard: keine Warnung oder Ablehnung" not in text
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    witness = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L2")
    closed = close_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], expected_source_token=source["source_token"],
        witness_kit_lot="L2", expected_witness_source_token=witness["source_token"], analysis_model=analysis.to_dict(),
        pdf_bytes=report.pdf_bytes, pdf_sha256=report.pdf_sha256, algorithm_id=analysis.to_dict()["algorithm_id"],
        renderer_id=report.renderer_id, context=MutationContext("RR", "close-pdf"))
    destination = tmp_path / "exported.pdf"
    exported = export_report_evidence(spec, lot_version_id=closed["version_id"], destination=destination)
    assert destination.read_bytes() == get_report_evidence(spec, lot_version_id=closed["version_id"])["pdf_bytes"] == report.pdf_bytes
    assert exported["pdf_sha256"] == report.pdf_sha256
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    with pytest.raises(QCReportError, match="existiert bereits"):
        export_report_evidence(spec, lot_version_id=closed["version_id"], destination=destination)
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before


def test_render_timeout_terminates_then_kills_and_releases_slot(monkeypatch):
    import src.qualitycontrol.pdf_report as renderer

    events = []
    class Process:
        exitcode = None
        alive = True
        def start(self):
            events.append("start")
        def join(self, timeout):
            events.append(("join", timeout))
        def is_alive(self):
            return self.alive
        def terminate(self):
            events.append("terminate")
        def kill(self):
            events.append("kill")
            self.alive = False
        def close(self):
            events.append("close")
    process = Process()
    class Context:
        def Process(self, **kwargs):
            assert kwargs["daemon"] is True and kwargs["target"] is renderer._render_worker
            return process
    monkeypatch.setattr(renderer.multiprocessing, "get_context", lambda value: Context())
    analysis = analyzed(manifest(["1"]), manual())
    with pytest.raises(QCReportError, match="Zeitlimit"):
        render_analysis_pdf(analysis)
    assert events.index("terminate") < events.index("kill") < events.index("close")
    assert renderer._RENDER_SLOT.acquire(blocking=False)
    renderer._RENDER_SLOT.release()


def test_compact_control_pages_keep_own_values_and_bound_people_with_optional_appendix(tmp_path):
    from src.qualitycontrol.api import QCAnalysis
    values = ["110.1234567890123456789"] * 30 + ["98.76543210987654321"] * 30
    source = manifest(values, targets="100", controls=["c1"] * 30 + ["c2"] * 30,
        dates=[(datetime(2026, 1, 1) + timedelta(days=index)).isoformat() for index in range(60)])
    for index, row in enumerate(source["population"]):
        row["raw_payload"] = {"ANWENDER": "EXTRACTED-USER"} if index == 0 else ({"user": "LEGACY-USER"} if index == 1 else {})
        if index == 2:
            row["raw_payload"] = {"ANWENDER": "ONE", "user": "OTHER"}
        row["validation"] = {key: row[key] for key in ("run_id", "revision_id", "selection_id", "selection_token", "validation_id")}
        row["validation"].update(operator_initials="VALIDATOR", validated_at_utc="2026-04-01T05:06:07+00:00")
        if index == 3:
            row["validation"]["revision_id"] = 99
            row["validation"]["operator_initials"] = "WRONG-REVISION"
            row["reasons"] = ["validation_binding_mismatch"]
    invalid = source["included"].pop(3)
    invalid["reasons"] = ["validation_binding_mismatch"]
    source["excluded"].append(invalid)
    source["included_count"], source["excluded_count"] = 59, 1
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    model = analyzed(source, manual(("c1", "c2"), "10")).to_dict()
    model["presentation"] = {"assay_name": "Vollständiger Assayname für beide Kontrollen"}
    analysis = QCAnalysis.freeze(model)
    before = analysis.model_json, analysis.model_sha256
    for extended in (False, True):
        report = render_analysis_pdf(analysis, include_explanations=extended)
        path = tmp_path / ("compact-controls-explained.pdf" if extended else "compact-controls.pdf")
        path.write_bytes(report.pdf_bytes)
        geometry = path.with_suffix(".geometry.json")
        text = extract_text(path, geometry_destination=geometry)
        readable = " ".join(text.split())
        assert ("VALIDATOR" in text) is extended and "WRONG-REVISION" not in text
        assert ("Validiert am UTC" in text) is extended
        assert "anderen Ergebnisstand" in readable and "00:00:00" not in text
        assert "Vollständiger Assayname für beide Kontrollen" in readable and "Assay: A" not in text
        assert ("Erläuterungen zur Auswertung" in text) is extended
        assert ("Vollständige Regelbefunde" in text) is extended
        assert "Herstellergrenzen" in readable and "Mittelwert" in readable
        for phrase in ("nicht künstlich verbunden", "Berechnete Anzeigewerte", "Modell SHA-256"):
            assert (phrase in readable) is extended
        spans = json.loads(geometry.read_text(encoding="utf-8"))
        pages = [" ".join(span["text"] for span in spans if span["page"] == index) for index in range(report.page_count)]
        first = [index for index, page in enumerate(pages) if "Level: c1" in page and "Erläuterungen zur Auswertung" not in page]
        second = [index for index, page in enumerate(pages) if "Level: c2" in page and "Erläuterungen zur Auswertung" not in page]
        assert len(first) >= 2 and len(second) >= 2 and max(first) < min(second)
        assert all("98.76543210987654321" not in "".join(pages[index].split()) for index in first)
        assert all("110.1234567890123456789" not in "".join(pages[index].split()) for index in second)
        assert all("Vollständiger Assayname" in pages[index] and "Kit-/Reagenzcharge: L1" in pages[index] for index in first + second)
        assert ("Messdatum / Messzeit" in readable) is extended
        assert "2025-12-30 13:12" not in readable and "2026-01-31 10:48" not in readable
        column = lambda x: "".join(span["text"] for span in spans if abs(span["bbox"][0] - x) < 0.5)
        assert "EXTRACTED-USER" in column(464) and "LEGACY-USER" in column(464)
        assert "Mehrdeutig:ONE/OTHER" in "".join(readable.split())
        assert "110.1234567890123456789" in column(208) and "98.76543210987654321" in column(208)
    assert (analysis.model_json, analysis.model_sha256) == before


@pytest.mark.parametrize("version", ["current", "genuine_pre_p2", "genuine_pre_p4", "synthetic_v1"])
def test_archived_export_is_exact_and_optional_print_uses_only_stored_model(tmp_path, monkeypatch, version):
    from src.qualitycontrol.api import QCAnalysis
    import src.qualitycontrol.pdf_report as renderer
    fixture = json.loads((Path(__file__).parent / "fixtures" / ("qc_pre_p4_schema2_v3.json" if version == "genuine_pre_p4" else "qc_pre_p2_schema1_v2.json")).read_text(encoding="utf-8"))
    if version == "current":
        model = analyze_lot(manifest(["110"], targets="100"), {}).to_dict()
    else:
        model = json.loads(fixture["model_json"])
        if version == "synthetic_v1":
            # Explicit synthetic compatibility variant of a genuine old model.
            model.update(renderer_id="arev2-qc-pdf-v1", algorithm_id="arev2-qc-analysis-v1")
            model.pop("sd_reference_context")
    analysis = QCAnalysis.freeze(model)
    original = base64.b64decode(fixture["pdf_base64"], validate=True) if version in {"genuine_pre_p2", "genuine_pre_p4"} else render_analysis_pdf(analysis).pdf_bytes
    if version in {"genuine_pre_p2", "genuine_pre_p4"}:
        assert analysis.model_sha256 == fixture["model_sha256"]
        assert hashlib.sha256(original).hexdigest() == fixture["pdf_sha256"]
    evidence = {"model": model, "pdf_bytes": original, "pdf_sha256": hashlib.sha256(original).hexdigest()}
    before = json.dumps(evidence["model"], sort_keys=True), original
    monkeypatch.setattr(renderer, "get_report_evidence", lambda *args, **kwargs: evidence)
    monkeypatch.setattr("src.qualitycontrol.analysis.analyze_lot", lambda *args, **kwargs: pytest.fail("stored evidence must not be recalculated"))
    monkeypatch.setattr("src.qualitycontrol.api.get_lot_sources", lambda *args, **kwargs: pytest.fail("stored print must not read current sources"))
    actual_renderer = renderer.render_analysis_pdf
    monkeypatch.setattr(renderer, "render_analysis_pdf", lambda *args, **kwargs: pytest.fail("ordinary export must use archive bytes"))
    destination = tmp_path / "archive-exact.pdf"
    result = export_report_evidence({}, lot_version_id=1, destination=destination)
    assert result["include_explanations"] is False and destination.read_bytes() == original
    monkeypatch.setattr(renderer, "render_analysis_pdf", actual_renderer)
    printed = tmp_path / "derived-explained.pdf"
    result = export_report_evidence({}, lot_version_id=1, destination=printed, include_explanations=True)
    assert result["include_explanations"] is True and printed.read_bytes() != original
    assert result["pdf_sha256"] == hashlib.sha256(printed.read_bytes()).hexdigest()
    printed_text = extract_text(printed)
    assert "Erläuterungen zur Auswertung" in printed_text
    if version != "current":
        assert "descriptive" not in model["computed_series"][0] and "Empirische SD" not in printed_text
        assert "arev2-qc-pdf-v4" in printed_text
    if version in {"genuine_pre_p2", "synthetic_v1"}:
        assert "Einzelwert-Prozentgrenzen" not in printed_text and "Herstellergrenzen:" not in printed_text
        assert "reference_lines" not in model["computed_series"][0]["chart"]
    for target, mode in ((destination, False), (printed, True)):
        prior = target.read_bytes(), target.stat().st_mtime_ns
        with pytest.raises(QCReportError, match="existiert bereits"):
            export_report_evidence({}, lot_version_id=1, destination=target, include_explanations=mode)
        assert (target.read_bytes(), target.stat().st_mtime_ns) == prior
    assert (json.dumps(evidence["model"], sort_keys=True), evidence["pdf_bytes"]) == before


@pytest.mark.parametrize("bad_mode", [0, 1, "true", None])
def test_print_mode_is_a_strict_boolean_before_any_io(bad_mode, monkeypatch):
    import src.qualitycontrol.pdf_report as renderer
    monkeypatch.setattr(renderer, "get_report_evidence", lambda *args, **kwargs: pytest.fail("bad mode must fail before reading"))
    with pytest.raises(QCReportError, match="Auswahl"):
        render_analysis_pdf(analyze_lot(manifest([]), {}), include_explanations=bad_mode)
    with pytest.raises(QCReportError, match="Auswahl"):
        export_report_evidence({}, lot_version_id=1, destination="unused.pdf", include_explanations=bad_mode)


@pytest.mark.parametrize("metadata_mode", [None, 1, True])
def test_spawn_transport_binds_print_mode_to_verified_metadata(monkeypatch, metadata_mode):
    import src.qualitycontrol.pdf_report as renderer
    analysis = analyze_lot(manifest(["100"], targets="100"), {})
    class Process:
        exitcode = 0
        def __init__(self, **kwargs):
            assert kwargs["args"][2] is False
            self.folder = Path(kwargs["args"][0])
        def start(self):
            raw = b"%PDF-1.7\ntransport-test\n%%EOF"
            (self.folder / "report.pdf").write_bytes(raw)
            data = {"pdf_sha256": hashlib.sha256(raw).hexdigest(), "model_sha256": analysis.model_sha256,
                    "renderer_id": renderer.RENDERER_ID, "page_count": 1, "include_explanations": metadata_mode}
            (self.folder / "result.json").write_text(json.dumps(data), encoding="utf-8")
        def join(self, timeout): pass
        def is_alive(self): return False
        def close(self): pass
    class Context:
        def Process(self, **kwargs):
            return Process(**kwargs)
    monkeypatch.setattr(renderer.multiprocessing, "get_context", lambda _: Context())
    with pytest.raises(QCReportError, match="Metadaten"):
        render_analysis_pdf(analysis)


def test_stored_two_control_report_does_not_call_empty_selection_or_no_values_normal(tmp_path):
    from src.qualitycontrol.api import save_profile
    spec, old = fixture(tmp_path, count=0)
    value = copy.deepcopy(old["snapshot"])
    value["enabled_rules"] = []
    second = copy.deepcopy(value["controls"][0])
    second.update(control_id="c2", name="Kontrolle 2", fields={"IST": "I2", "SOLL": "S2", "MIN": "N2", "MAX": "X2"})
    value["controls"].append(second)
    profile = save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1,
        context=MutationContext("RR", "status-profile"))
    for run_id, lot, date in ((1, "L1", "2026-01-01"), (2, "L2", "2026-02-01")):
        add_run(spec, run_id, lot=lot, data=payload(date, I1="negativ", I2="41", S2="40", N2="30", X2="50"))
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    assert source["included_count"] == source["excluded_count"] == 1
    opened = open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=source["source_token"],
        context=MutationContext("RR", "status-open"))
    analysis = analyze_lot(source, opened["snapshot"]["sd_references"])
    model_before = analysis.model_json, analysis.model_sha256
    assert [row["included_count"] for row in analysis.to_dict()["computed_series"]] == [0, 1]
    report = render_analysis_pdf(analysis)
    witness = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L2")
    closed = close_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], expected_source_token=source["source_token"],
        witness_kit_lot="L2", expected_witness_source_token=witness["source_token"], analysis_model=analysis.to_dict(),
        pdf_bytes=report.pdf_bytes, pdf_sha256=report.pdf_sha256, algorithm_id=analysis.to_dict()["algorithm_id"], renderer_id=report.renderer_id,
        context=MutationContext("RR", "status-close"))
    assert closed["state"] == "closed"
    before = get_report_evidence(spec, lot_version_id=closed["version_id"])
    database_before = Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns
    path, geometry = tmp_path / "stored-control-status.pdf", tmp_path / "stored-control-status.geometry.json"
    export_report_evidence(spec, lot_version_id=closed["version_id"], destination=path)
    text = extract_text(path, geometry_destination=geometry)
    spans = json.loads(geometry.read_text(encoding="utf-8"))
    pages = [" ".join(span["text"] for span in spans if span["page"] == index) for index in range(report.page_count)]
    first = next(page for page in pages if "Level: Kontrolle 1" in page)
    second = next(page for page in pages if "Level: Kontrolle 2" in page)
    assert "Westgard: Nicht ausgewählt" in first and "Westgard: Nicht ausgewählt" in second
    assert "Westgard nicht auswertbar: keine geeigneten Kontrollwerte." in first
    assert "keine geeigneten Kontrollwerte" not in second
    assert "Westgard: keine Warnung oder Ablehnung" not in text
    assert "QMMA: 1 U" in second and "QMMA: 0" not in first
    assert path.read_bytes() == before["pdf_bytes"] == report.pdf_bytes
    assert before["model"] == analysis.to_dict() and get_report_evidence(spec, lot_version_id=closed["version_id"]) == before
    assert (analysis.model_json, analysis.model_sha256) == model_before
    assert (Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns) == database_before


@pytest.mark.parametrize("mode,actual,enabled,expected_status", [
    ("normal", "41", ["1_3s"], "not_triggered"),
    ("warning", "42.1", ["1_2s", "1_3s"], "warning"),
    ("reject", "43.1", ["1_2s", "1_3s"], "reject"),
    ("no-values", "negativ", ["1_3s"], "unavailable"),
])
def test_westgard_summary_uses_existing_performed_findings_independently_of_qmma(tmp_path, mode, actual, enabled, expected_status):
    from src.qualitycontrol.api import get_sd_reference_context, save_profile
    spec, old = fixture(tmp_path, count=0)
    value = copy.deepcopy(old["snapshot"])
    value["enabled_rules"] = enabled
    if mode == "normal":
        value.update(rili_applicable=False, relative_enabled=False)
    profile = save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1,
        context=MutationContext("RR", "performed-profile"))
    add_run(spec, 1, data=payload("2026-01-01", I1=actual))
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    references, origin = {}, {}
    if source["included"]:
        opened = open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=source["source_token"],
            sd_references={"c1": {"kind": "manual", "value": "1"}}, context=MutationContext("RR", "performed-open"))
        references = opened["snapshot"]["sd_references"]
        origin = get_sd_reference_context(spec, lot_key=opened["lot_key"], expected_version_id=opened["version_id"])
    analysis = analyze_lot(source, references, sd_reference_context=origin)
    before = analysis.model_json, analysis.model_sha256, content_hash(source)
    assert any(row["status"] == expected_status for run in analysis.to_dict()["analytical_runs"] for row in run["findings"])
    path = tmp_path / f"westgard-{mode}.pdf"
    path.write_bytes(render_analysis_pdf(analysis).pdf_bytes)
    text = " ".join(extract_text(path).split())
    assert ("Westgard: Kein Ablehnungsbefund" in text) is (mode == "normal")
    if mode == "normal":
        assert "QMMA-Bewertung: Nicht anwendbar" in text
    elif mode == "warning":
        assert "1_2s: Warnung" in text
    elif mode == "reject":
        assert "1_3s: Ablehnungsbefund" in text
    else:
        assert "Westgard nicht auswertbar: keine geeigneten Kontrollwerte." in text
    assert (analysis.model_json, analysis.model_sha256, content_hash(source)) == before


def test_frozen_baseline_center_is_labelled_separately_from_soll(tmp_path: Path):
    baseline = manifest(["90", "91", "92"], targets="100")
    reference = {"c1": {"kind": "confirmed_baseline", "confirmed": True, "reference_id": "baseline-ref",
        "measurements": baseline["included"], "source_token": baseline["source_token"], "profile_version_id": 1,
        "calculation": "sample-sd-and-mean-deferred-to-p5"}}
    analysis = analyzed(manifest(["94"], targets="100"), reference)
    report = render_analysis_pdf(analysis)
    path = tmp_path / "baseline-center-report.pdf"
    path.write_bytes(report.pdf_bytes)
    text = extract_text(path)
    assert "QMMA: 6" in text and "Mitte: 91" in text
    readable = " ".join(text.split())
    assert "SOLL: 100" in readable and "Mitte: 91" in readable and "SD-Referenz" in readable
    assert "bestätigte eingefrorene Referenzserie, n = 3" in readable


def test_configured_qmma_limit_remains_visible_when_values_are_unavailable(tmp_path: Path):
    report = render_analysis_pdf(analyze_lot(manifest([], targets="100"), {}))
    path = tmp_path / "unavailable-report.pdf"
    path.write_bytes(report.pdf_bytes)
    readable = " ".join(extract_text(path).split())
    assert "QMMA-Grenze (relativ): 10 %" in readable
    assert "QMMA-Bewertung: Nicht verfügbar" in readable and "QMMA: 0" not in readable
    assert "Westgard nicht auswertbar: keine geeigneten Kontrollwerte." in readable
    assert "Westgard: keine Warnung oder Ablehnung" not in readable


def test_real_pdf_explains_incompatible_sd_origin_while_qmma_remains_available(tmp_path: Path):
    origin, source = manifest(["90", "91", "92"], targets="100"), manifest(["94"], targets="100")
    source["profile_version_id"] = source["profile_head_version_id"] = 2
    source["profile_snapshot"]["unit"] = source["profile_snapshot"]["controls"][0]["unit"] = "B"
    source["included"][0]["unit"] = source["included"][0]["unit_raw"] = "B"
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    refs = {"c1": {"kind": "confirmed_baseline", "confirmed": True, "profile_version_id": 1, "measurements": origin["included"]}}
    analysis = analyze_lot(source, refs, sd_reference_context=reference_context(source, refs, origin=origin))
    report = render_analysis_pdf(analysis, include_explanations=True)
    path = tmp_path / "incompatible-sd-report.pdf"
    path.write_bytes(report.pdf_bytes)
    readable = " ".join(extract_text(path).split())
    assert "QMMA: 6 B" in readable and "SD gehört zu einer anderen Einheit" in readable
    assert "SD-Bänder und Westgard-Auswertung nicht verfügbar" in readable
    assert "arev2-qc-analysis-v4" in readable and "Mitte: 91" not in readable


def test_real_pdf_axis_labels_only_actual_measurements_and_handles_date_edge_and_empty(tmp_path: Path):
    cases = [
        ("visible", ["2026-01-01T00:00:00", "2026-01-02T00:00:00"], False),
        ("explicit-time", ["2026-01-01T10:15:00", "2026-01-02T11:15:00"], True),
        ("date-edge", ["0001-01-01T00:00:00", "0001-01-02T00:00:00"], False),
        ("empty", [], False),
    ]
    for name, dates, show_time in cases:
        source = manifest(["90", "110"] if dates else [], targets="100", dates=dates)
        source["order_is_explicit"] = show_time
        if show_time:
            source["profile_snapshot"]["measurement_date_format"] = "%Y-%m-%dT%H:%M:%S"
        source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
        analysis = analyze_lot(source, {})
        original = analysis.model_json, analysis.model_sha256
        path, geometry = tmp_path / f"axis-{name}.pdf", tmp_path / f"axis-{name}-geometry.json"
        path.write_bytes(render_analysis_pdf(analysis).pdf_bytes)
        text = extract_text(path, geometry_destination=geometry)
        spans = json.loads(geometry.read_text())
        # Axis labels are actual frozen dates, never padded range boundaries.
        ticks = [span for span in spans if span["page"] == 0 and span["text"] in
            {datetime.fromisoformat(date).strftime("%d.%m.%Y") for date in dates} and span["bbox"][3] - span["bbox"][1] > 15]
        assert len(ticks) == len(dates)
        assert "22:48" not in text and "01:12" not in text and "2025-12-31" not in text
        assert (analysis.model_json, analysis.model_sha256) == original


def test_real_pdf_preserves_frozen_raw_date_time_counterparts_without_interpretation(tmp_path):
    from test_qualitycontrol_profiles_lots import time_profile
    spec, old = fixture(tmp_path, count=0)
    pairs = [("2026-01-01", "24:00"), ("2026-01-02", None), ("2026-01-03", ""),
             ("2026-02-30", "09:15"), (None, "10:45"), ("2026-01-06", "11:30"),
             ("unlesbares Datum", "unlesbare Zeit"), ("", "12:00")]
    for run_id, (date, clock) in enumerate(pairs, 1):
        data = payload(date, I1=str(40 + run_id))
        if clock is not None:
            data["TIME"] = clock
        add_run(spec, run_id, data=data)
    revised = time_profile(spec, old)
    source = get_lot_sources(spec, profile_version_id=revised["version_id"], kit_lot="L1")
    assert source["included_count"] == 1 and source["excluded_count"] == 7
    assert all(row["measured_at"] is None for row in source["population"] if row["run_id"] != 6)
    for name, captured in (("raw-date-time-fields", source), ("raw-date-only-fields",
            get_lot_sources(spec, profile_version_id=old["version_id"], kit_lot="L1"))):
        analysis = analyze_lot(captured, {})
        before = analysis.model_json, analysis.model_sha256, content_hash(captured)
        report = render_analysis_pdf(analysis, include_explanations=True)
        path, geometry = tmp_path / f"{name}.pdf", tmp_path / f"{name}.geometry.json"
        path.write_bytes(report.pdf_bytes)
        extract_text(path, geometry_destination=geometry)
        spans = json.loads(geometry.read_text(encoding="utf-8"))
        text = " ".join(span["text"] for span in spans)
        starts = sorted((span for span in spans if span["page"] == 0 and abs(span["bbox"][0] - 208) < 0.5
                         and span["text"] in {str(40 + number) for number in range(1, 9)}),
                        key=lambda span: span["bbox"][1])
        assert len(starts) == 8
        rows = {}
        for index, start in enumerate(starts):
            end = starts[index + 1]["bbox"][1] if index + 1 < len(starts) else start["bbox"][1] + 22
            rows[int(start["text"]) - 40] = " ".join(span["text"] for span in spans if span["page"] == 0
                and abs(span["bbox"][0] - 64) < 0.5 and start["bbox"][1] - 0.1 <= span["bbox"][1] < end - 0.1)
        assert rows[1] == "01.01.2026"
        assert rows[4] == rows[5] == rows[7] == rows[8] == "ungeklärt"
        assert "Datum Rohangabe: 2026-02-30" in text and "Datum Rohangabe: unlesbares Datum" in text
        assert "Messdatum unlesbar" in text
        if name == "raw-date-time-fields":
            assert rows[6] == "06.01.2026 11:30" and "11:30:00" not in text
            assert "Zeit Rohangabe: 24:00" in text and "Zeit Rohangabe: unlesbare Zeit" in text
            assert "Extrahierte Messzeit fehlt" in text and "Messzeit passt nicht zum festgelegten Format" in text
            assert len(analysis.to_dict()["computed_series"][0]["chart"]["points"]) == 1
        else:
            assert rows[6] == "06.01.2026" and "11:30" not in text
        assert (analysis.model_json, analysis.model_sha256, content_hash(captured)) == before
    assert get_lot_sources(spec, profile_version_id=revised["version_id"], kit_lot="L1") == source


def test_optional_time_pdf_names_errors_and_preserves_old_profile_sd_and_evidence(tmp_path: Path):
    from src.qualitycontrol.api import get_profile, get_sd_reference_context, list_lots
    from test_qualitycontrol_profiles_lots import time_profile
    spec, old = fixture(tmp_path, count=0)
    add_run(spec, 1, data=payload("2026-01-01"))
    add_run(spec, 2, data=payload("2026-01-02", TIME="24:00"))
    add_run(spec, 3, data=payload("2026-01-03", TIME="08:00"))
    add_run(spec, 4, lot="L2", data=payload("2026-02-01", TIME="09:00"))
    source = get_lot_sources(spec, profile_version_id=old["version_id"], kit_lot="L1")
    opened = open_lot(spec, profile_version_id=old["version_id"], kit_lot="L1", expected_source_token=source["source_token"],
        sd_references={"c1": {"kind": "manual", "value": "1"}}, context=MutationContext("RR", "time-pdf-open"))
    refs = opened["snapshot"]["sd_references"]
    origin = get_sd_reference_context(spec, lot_key=opened["lot_key"], expected_version_id=opened["version_id"])
    old_analysis = analyze_lot(source, refs, sd_reference_context=origin)
    old_pdf = render_analysis_pdf(old_analysis)
    witness = get_lot_sources(spec, profile_version_id=old["version_id"], kit_lot="L2")
    closed = close_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], expected_source_token=source["source_token"],
        witness_kit_lot="L2", expected_witness_source_token=witness["source_token"], analysis_model=old_analysis.to_dict(),
        pdf_bytes=old_pdf.pdf_bytes, pdf_sha256=old_pdf.pdf_sha256, algorithm_id=old_analysis.to_dict()["algorithm_id"],
        renderer_id=old_pdf.renderer_id, context=MutationContext("RR", "time-pdf-close"))
    evidence_before = get_report_evidence(spec, lot_version_id=closed["version_id"])
    history_before = list_lots(spec, include_history=True)
    revised = time_profile(spec, old)
    current = get_lot_sources(spec, profile_version_id=revised["version_id"], kit_lot="L1")
    assert current["included_count"] == 1 and current["excluded_count"] == 2
    origin = get_sd_reference_context(spec, lot_key=closed["lot_key"], expected_version_id=closed["version_id"])
    analysis = analyze_lot(current, refs, sd_reference_context=origin)
    assert analysis.to_dict()["computed_series"][0]["sd"]["available"]
    report = render_analysis_pdf(analysis)
    path = tmp_path / "optional-time-errors.pdf"
    path.write_bytes(report.pdf_bytes)
    geometry = path.with_suffix(".geometry.json")
    text = extract_text(path, geometry_destination=geometry)
    spans = json.loads(geometry.read_text(encoding="utf-8"))
    readable = " ".join(text.split())
    assert "Extrahierte Messzeit fehlt" in readable
    assert "Messzeit passt nicht zum" in readable and "festgelegten Format" in readable
    assert "measurement_time_missing" not in readable and "measurement_time_invalid" not in readable
    assert "08:00" in text and "08:00:00" not in text
    assert get_profile(spec, old["version_id"]) == old
    assert list_lots(spec, include_history=True) == history_before
    assert get_report_evidence(spec, lot_version_id=closed["version_id"]) == evidence_before
    assert evidence_before["pdf_bytes"] == old_pdf.pdf_bytes and evidence_before["model"] == old_analysis.to_dict()
    assert old_analysis.to_dict()["sd_references"] == refs and "measurement_time_field" not in old["snapshot"]


def _extract_drawings_worker(source, destination):
    import fitz
    result = []
    with fitz.open(source) as document:
        for page_number, page in enumerate(document):
            for path in page.get_drawings():
                result.append({"page": page_number, "rect": list(path["rect"]), "color": path.get("color"),
                    "width": path.get("width"), "dashes": path.get("dashes"),
                    "lines": [[list(item[1]), list(item[2])] for item in path["items"] if item[0] == "l"],
                    "rectangle": any(item[0] == "re" for item in path["items"])})
    Path(destination).write_text(json.dumps(result), encoding="utf-8")


def test_p2_real_pdf_draws_the_same_frozen_limits_and_reports_independent_findings(tmp_path):
    from test_qualitycontrol_limits import limit_manifest
    source = limit_manifest(["100", "100", "100", "112"], targets="100")
    analysis = analyze_lot(source, {})
    before = analysis.model_json, analysis.model_sha256
    path = tmp_path / "p2-frozen-limits.pdf"
    report = render_analysis_pdf(analysis)
    path.write_bytes(report.pdf_bytes)
    text = " ".join(extract_text(path).split())
    assert "QMMA: 6 U" in text and "Anzahl: 4" in text and "relativ: 6 %" in text
    assert "Hersteller: 80 bis 120" in text and "Einzelwert: 90 bis 110" in text
    assert "90 / 110 (10 %)" in text and "Mittelwert 103" in text and "Keine SD-Referenz" in text
    assert "Grenze überschritten" in text and "Westgard nicht vollständig verfügbar" in text
    destination = tmp_path / "p2-drawings.json"
    process = multiprocessing.get_context("spawn").Process(target=_extract_drawings_worker, args=(str(path), str(destination)), daemon=True)
    try:
        process.start()
        process.join(timeout=15)
        assert not process.is_alive() and process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.5)
        if process.is_alive():
            process.kill()
            process.join(timeout=0.5)
        process.close()
    drawings = json.loads(destination.read_text(encoding="utf-8"))
    box = next(row["rect"] for row in drawings if row["rectangle"] and row["rect"][0] == pytest.approx(46)
        and row["rect"][2] == pytest.approx(436) and row["rect"][3] - row["rect"][1] == pytest.approx(184))
    chart = analysis.to_dict()["computed_series"][0]["chart"]
    ylo, yhi = map(float, chart["y_range"])
    references = [row for row in drawings if len(row["lines"]) == 1 and row["lines"][0][0][0] == pytest.approx(46)
        and row["lines"][0][1][0] == pytest.approx(436) and row["width"] == pytest.approx(1)]
    assert len(references) == len(chart["reference_lines"]) == 6
    for drawn, frozen in zip(references, chart["reference_lines"]):
        y = box[1] + 184 - (float(frozen["value"]) - ylo) / (yhi - ylo) * 184
        assert [coordinate for endpoint in drawn["lines"][0] for coordinate in endpoint] == pytest.approx([46, y, 436, y], abs=0.001)
        if frozen["kind"] == "manufacturer":
            assert "5 3" in drawn["dashes"]
    assert (analysis.model_json, analysis.model_sha256) == before


def test_p2_real_pdf_keeps_manufacturer_conflict_reasons_and_raw_ranges(tmp_path):
    from test_qualitycontrol_limits import limit_manifest
    analysis = analyze_lot(limit_manifest(["40", "40"], targets="40", minimum=["30", "31"], maximum=["50", "49"]), {})
    path = tmp_path / "p2-manufacturer-conflict.pdf"
    path.write_bytes(render_analysis_pdf(analysis, include_explanations=True).pdf_bytes)
    compact = "".join(extract_text(path).split())
    assert "UnterschiedlicheHersteller-MIN-Werte" in compact
    assert "UnterschiedlicheHersteller-MAX-Werte" in compact
    assert "RohwertSOLL:40;RohwertMIN:30;RohwertMAX:50" in compact and "RohwertSOLL:40;RohwertMIN:31;RohwertMAX:49" in compact
    assert "Geeignet0,ausgeschlossen2" in compact


def test_p4_eleven_measurements_have_one_complete_primary_sheet_and_spaced_true_date_ticks(tmp_path):
    from src.qualitycontrol.api import QCAnalysis
    frozen = json.loads((Path(__file__).parent / 'fixtures/qc_pre_p4_schema2_v3.json').read_text())
    old = json.loads(frozen['model_json'])
    source = old['source_manifest']
    dates = ['2026-11-02T10:15:00','2026-11-03T10:15:00','2026-11-04T10:15:00',
        '2026-11-05T10:15:00','2026-11-06T10:15:00','2026-11-06T10:19:00',
        '2026-11-09T10:15:00','2026-11-10T10:15:00','2026-11-10T10:19:00',
        '2026-11-11T10:15:00','2026-11-11T10:19:00']
    for index, (point, original, date) in enumerate(zip(source['included'],source['population'],dates),1):
        point['measured_at'] = original['measured_at'] = date
        point['analytical_run_id'] = original['analytical_run_id'] = f'R{index}'
        original['measurement_date_raw'] = date
        original['run_group_raw'] = f'R{index}'
    source['source_token'] = content_hash({key:value for key,value in source.items() if key != 'source_token'})
    model = analyze_lot(source,old['sd_references'],sd_reference_context=old['sd_reference_context']).to_dict()
    model['presentation'] = old['presentation']
    analysis = QCAnalysis.freeze(model)
    report = render_analysis_pdf(analysis)
    assert report.page_count == 1
    path, geometry = tmp_path/'eleven-primary.pdf', tmp_path/'eleven-primary.geometry.json'
    path.write_bytes(report.pdf_bytes)
    text = extract_text(path,geometry_destination=geometry)
    spans = json.loads(geometry.read_text())
    first = [span for span in spans if span['page'] == 0]
    first_text = ' '.join(span['text'] for span in first)
    for phrase in ('KONTROLLPROBENEINZELMESSUNG','Mittelwert: 61','Empirische SD (n-1): 2.04939',
            'VK (%): 3.35966','QMMA: 2.79610 U','QMMA relativ: 4.43826 %','Datum','Bearbeitet von',
            'Unterschrift technische Prüfung','Unterschrift Laborleitung','Herstellergrenzen','Einzelwertgrenzen'):
        assert phrase in first_text
    positions = [span['text'] for span in first if abs(span['bbox'][0]-39) < .5 and span['text'].isdigit()]
    assert positions == [str(index) for index in range(1,12)]
    assert all(f'R{index}' in first_text for index in range(1,12))
    ticks = [span for span in first if span['text'] in {datetime.fromisoformat(date).strftime('%d.%m.%Y') for date in dates}
        and span['bbox'][3]-span['bbox'][1] > 15]
    assert 5 <= len(ticks) <= 8
    for first_tick, second_tick in zip(ticks,ticks[1:]):
        assert first_tick['bbox'][2] < second_tick['bbox'][0]
    assert all(span['bbox'][2] <= 560.5 and span['bbox'][3] < 800 for span in first if not span['text'].startswith('Seite '))
    assert 'Validiert durch:' not in text and 'Quellhash' not in text
    assert 'Digitaler Nachweis' in ' '.join(text.split())
    assert 'Vollständige Regelbefunde' not in text and 'Modell SHA-256' not in text
    assert all(word not in text for word in ('Labor Muster','Musterstraße','Kalibration','stored-run:'))
    assert report.renderer_id == 'arev2-qc-pdf-v4' and analysis.model_json == QCAnalysis.freeze(model).model_json


def test_p4_no_explicit_run_field_never_labels_internal_identity_as_an_analytical_run(tmp_path):
    source = manifest(['100'],targets='100',groups=['stored-run:987654321'])
    source['population'][0]['run_group_raw'] = 'unchecked-raw-run'
    source['population'][0]['raw_payload'] = {'ANWENDER':'EXTRACTED'}
    source['source_token'] = content_hash({key:value for key,value in source.items() if key != 'source_token'})
    analysis = analyze_lot(source,{})
    path = tmp_path/'no-explicit-run.pdf'
    path.write_bytes(render_analysis_pdf(analysis).pdf_bytes)
    text = ' '.join(extract_text(path).split())
    assert 'Lauf' in text
    assert 'EXTRACTED' in text and 'stored-run:987654321' not in text and 'unchecked-raw-run' not in text


def test_p4_optional_evidence_keeps_full_bindings_and_long_exceptions_for_sixty_rows_per_level(tmp_path):
    from src.qualitycontrol.api import QCAnalysis

    source = manifest(["100"]*120, targets="100", controls=["c1"]*60+["c2"]*60,
        dates=[(datetime(2026, 1, 1)+timedelta(days=index % 60)).isoformat() for index in range(120)])
    source["profile_snapshot"]["run_grouping_field"] = "RUN"
    for control in source["profile_snapshot"]["controls"]:
        control["name"] = control["control_id"]+" – Langer Kontrollname für die lesbare mehrseitige Zuordnung"
    long_token = "selection-"+"abcdef0123456789"*12
    long_raw = "Unlesbarer vollständiger Rohwert "+"vollständige Zusatzangabe "*30
    for index, point in enumerate(source["included"]):
        point["source_hash"] = hashlib.sha256(f"evidence-source-{index}".encode()).hexdigest()
        point["control_name"] = next(control["name"] for control in source["profile_snapshot"]["controls"] if control["control_id"] == point["control_id"])
        point["measurement_date_raw"] = point["measured_at"].split("T")[0]
        point["measurement_time_raw"] = None
        point["run_group_raw"] = f"R{index+1}"
        point["raw_payload"] = {"ANWENDER": "EXTRACTED"}
        if index == 9:
            point.update(revision_id=1, selection_id=200, selection_token=long_token)
        point["validation"] = {key: point[key] for key in ("run_id", "revision_id", "selection_id", "selection_token", "validation_id")}
        point["validation"].update(operator_initials="BOUND-VALIDATOR", validated_at_utc="2026-04-01T05:06:07+00:00")
    source["included"][-1]["raw"]["IST"] = long_raw
    source["included"][-1]["parsed"]["IST"] = None
    source["included"][-1]["reasons"] = ["result_unreadable"]
    source["population"] = copy.deepcopy(source["included"])
    source["excluded"] = [source["included"].pop()]
    source.update(included_count=119, excluded_count=1)
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    model = analyze_lot(source, {}).to_dict()
    model["presentation"] = {"assay_name": "Langer Assayname für die Prüfung des vollständigen Nachweisregisters"}
    analysis = QCAnalysis.freeze(model)
    before = analysis.model_json, analysis.model_sha256
    report = render_analysis_pdf(analysis, include_explanations=True)
    assert report.page_count > 3
    path, geometry = tmp_path/"compact-sixty-per-level.pdf", tmp_path/"compact-sixty-per-level.geometry.json"
    path.write_bytes(report.pdf_bytes)
    text = extract_text(path, geometry_destination=geometry)
    compact = "".join(text.split())
    for point in model["points"]:
        assert point["source_hash"] in compact
        assert "".join(point["selection_token"].split()) in compact
        assert "".join(point["point_key"].split()) in compact
    assert "".join(long_raw.split()) in compact
    assert "BOUND-VALIDATOR" in text and "2026-04-01" in text and "05:06:07" in text
    assert "Zusatz · Pos 10" in text and "Zusatz · Pos 60" in text
    assert "Ergebnis unlesbar" in text and "Eignung: Ausgeschlossen" in text
    assert "Vollständige Regelbefunde" in text and (analysis.model_json, analysis.model_sha256) == before
    spans = json.loads(geometry.read_text())
    assert all(20 <= span["bbox"][0] and span["bbox"][2] <= 560.5 and span["bbox"][3] < 830 for span in spans)
    pages = [" ".join(span["text"] for span in spans if span["page"] == number) for number in range(report.page_count)]
    evidence_pages = [page for page in pages if "Messwertnachweise" in page]
    evidence_numbers = {number for number, page in enumerate(pages) if "Messwertnachweise" in page}
    assert all(span["bbox"][0] >= 35.5 for span in spans if span["page"] in evidence_numbers)
    assert all("Kit-/Reagenzcharge: L1" in page and "Level:" in page for page in evidence_pages)
    assert sum("Quellhash / Auswahlkennung" in page for page in evidence_pages) >= 6


@pytest.mark.parametrize("levels", [1, 2])
def test_p4_standard_sixty_total_rows_fit_three_pages_with_visible_findings_and_no_raw_export(tmp_path, levels):
    from test_qualitycontrol_limits import limit_manifest

    count = 60//levels
    controls = [f"c{level+1}" for level in range(levels) for _ in range(count)]
    source = limit_manifest(["100"]*58+["125", "unlesbar"], targets="100", controls=controls,
        dates=[(datetime(2026, 1, 1, 9, 15)+timedelta(days=index % count)).isoformat() for index in range(60)])
    source["profile_snapshot"].update(measurement_time_field="TIME", measurement_time_format="%H:%M:%S")
    source["inventory_snapshot"]["devices"][0]["display_name"] = "Demo-Gerät mit längerem Anzeigenamen für den lesbaren Umbruch im Seitenkopf"
    source["profile_snapshot"]["controls"][0]["name"] = "Level 1 – langer synthetischer Kontrollname mit mehreren erklärenden Bestandteilen für die Prüfung des automatischen Zeilenumbruchs"
    for point in source["included"]:
        point["control_name"] = next(control["name"] for control in source["profile_snapshot"]["controls"] if control["control_id"] == point["control_id"])
        point["source_hash"] = hashlib.sha256(f"source-{point['run_id']}".encode()).hexdigest()
        point["measurement_date_raw"] = point["measured_at"].split("T")[0]
        point["measurement_time_raw"] = "09:15:00"
    source["included"][-1]["parsed"]["IST"] = None
    source["included"][-1]["reasons"] = ["result_unreadable"]
    source["population"] = copy.deepcopy(source["included"])
    source["population"][0]["raw_payload"] = {"UNRELATED_FIELD": "PRIVATE-RAW-PAYLOAD-SENTINEL"}
    source["excluded"] = [source["included"].pop()]
    source.update(included_count=59, excluded_count=1, order_is_explicit=True)
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    analysis = analyze_lot(source, {})
    before = analysis.model_json, analysis.model_sha256
    report = render_analysis_pdf(analysis)
    path, geometry, structure = (tmp_path/f"standard-{levels}-levels{suffix}" for suffix in (".pdf", ".geometry.json", ".structure.json"))
    path.write_bytes(report.pdf_bytes)
    text = extract_text(path, geometry_destination=geometry, structure_destination=structure)
    readable = " ".join(text.split())
    assert report.page_count <= 3 and json.loads(structure.read_text())["attachments"] == []
    assert "Digitaler Nachweis" in readable and analysis.model_sha256[:16] in text
    assert "Messwertnachweise" not in text and "Quellhash" not in text and "PRIVATE-RAW-PAYLOAD-SENTINEL" not in text
    assert all(point["source_hash"] not in text and point["selection_token"] not in text for point in analysis.to_dict()["points"])
    assert f"Pos {count-1}: Herstellergrenze: Grenze überschritten; Einzelwert-Prozentgrenze: Grenze überschritten" in readable
    assert f"Pos {count}: Nicht ausgewertet: Ergebnis unlesbar" in readable
    assert "Westgard nicht vollständig verfügbar" in readable and "Unterschrift Laborleitung" in readable
    spans = json.loads(geometry.read_text())
    positions = [int(span["text"].rstrip("*")) for span in spans if abs(span["bbox"][0]-39) < .5 and span["text"].rstrip("*").isdigit()]
    assert sorted(positions) == sorted(list(range(1, count+1))*levels)
    assert all(span["bbox"][0] >= 20 and span["bbox"][2] <= 560.5 and span["bbox"][3] < 830 for span in spans)
    assert (analysis.model_json, analysis.model_sha256) == before and "PRIVATE-RAW-PAYLOAD-SENTINEL" in analysis.model_json
