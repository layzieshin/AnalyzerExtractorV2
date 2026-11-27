"""Real fresh-process PDF, pagination, bounded cleanup and exact export tests."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import copy
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

def _extract_text_worker(source, destination, geometry_destination=None):
    import fitz

    with fitz.open(source) as document:
        text = "\n".join(page.get_text() for page in document)
        if geometry_destination is not None:
            spans = [{"page": number, "text": span["text"], "bbox": span["bbox"]}
                     for number, page in enumerate(document)
                     for block in page.get_text("dict")["blocks"] for line in block.get("lines", []) for span in line["spans"]]
            Path(geometry_destination).write_text(json.dumps(spans, ensure_ascii=False), encoding="utf-8")
    Path(destination).write_text(text, encoding="utf-8")


def extract_text(path: Path, *, geometry_destination: Path | None = None) -> str:
    destination = path.with_suffix(".txt")
    process = multiprocessing.get_context("spawn").Process(target=_extract_text_worker,
        args=(str(path), str(destination), str(geometry_destination) if geometry_destination is not None else None), daemon=True)
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
    assert "Validierte Kit-Chargen-Auswertung" in text and "QMMA: 10" in text
    assert "µg/L" in text and "Einzelwerte" in text
    assert "c0" in text and "c5" in text and "Validiert am UTC" in text
    assert "Vollständige Regelbefunde" not in text and "Modell SHA-256" not in text
    assert "Seite" in text and "2026-01-18" in text
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
        assert "VALIDATOR" in text and "WRONG-REVISION" not in text and "Validiert am UTC" in text
        assert "anderen Ergebnisstand" in readable and "00:00:00" not in text
        assert "Vollständiger Assayname für beide Kontrollen" in readable and "Assay: A" not in text
        assert ("Erläuterungen zur Auswertung" in text) is extended
        assert ("Vollständige Regelbefunde" in text) is extended
        for phrase in ("Diagrammlegende", "kann vom SOLL abweichen", "nicht künstlich verbunden", "Berechnungsbezug:", "Modell SHA-256"):
            assert (phrase in readable) is extended
        spans = json.loads(geometry.read_text(encoding="utf-8"))
        pages = [" ".join(span["text"] for span in spans if span["page"] == index) for index in range(report.page_count)]
        first = [index for index, page in enumerate(pages) if "Kontrolle: c1" in page and "Erläuterungen zur Auswertung" not in page]
        second = [index for index, page in enumerate(pages) if "Kontrolle: c2" in page and "Erläuterungen zur Auswertung" not in page]
        assert len(first) >= 2 and len(second) >= 2 and max(first) < min(second)
        assert all("98.76543210987654321" not in "".join(pages[index].split()) for index in first)
        assert all("110.1234567890123456789" not in "".join(pages[index].split()) for index in second)
        assert all("Vollständiger Assayname" in pages[index] and "Kit-Charge: L1" in pages[index] for index in first + second)
        assert "Messdatum / Messzeit" not in readable and "2025-12-30 13:12" not in readable and "2026-01-31 10:48" not in readable
        column = lambda x: "".join(span["text"] for span in spans if abs(span["bbox"][0] - x) < 0.5)
        assert "EXTRACTED-USER" in column(224) and "LEGACY-USER" in column(224)
        assert "Mehrdeutig: ONE/ OTHER" in column(224)
        assert "110.1234567890123456789" in column(39) and "98.76543210987654321" in column(39)
    assert (analysis.model_json, analysis.model_sha256) == before


@pytest.mark.parametrize("legacy", [False, True])
def test_archived_export_is_exact_and_optional_print_uses_only_stored_model(tmp_path, monkeypatch, legacy):
    from src.qualitycontrol.api import QCAnalysis
    import src.qualitycontrol.pdf_report as renderer
    model = analyze_lot(manifest(["110"], targets="100"), {}).to_dict()
    if legacy:
        model["renderer_id"] = "arev2-qc-pdf-v1"
        model["algorithm_id"] = "arev2-qc-analysis-v1"
        model.pop("sd_reference_context")
    analysis = QCAnalysis.freeze(model)
    original = render_analysis_pdf(analysis).pdf_bytes
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
    assert "Erläuterungen zur Auswertung" in extract_text(printed)
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
    first = next(page for page in pages if "Kontrolle: Kontrolle 1" in page)
    second = next(page for page in pages if "Kontrolle: Kontrolle 2" in page)
    assert "Westgard: keine Regeln ausgewählt." in first and "Westgard: keine Regeln ausgewählt." in second
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
    assert ("Westgard: keine Warnung oder Ablehnung" in text) is (mode == "normal")
    if mode == "normal":
        assert "QMMA-Bewertung: Nicht anwendbar" in text
    elif mode == "warning":
        assert "1_2s Warnung" in text
    elif mode == "reject":
        assert "1_3s Ablehnungsbefund" in text
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
    assert "SOLL: 100" in readable and "Mitte: 91" in readable and "Diagrammlegende" not in readable
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
    assert "arev2-qc-analysis-v2" in readable and "Mitte: 91" not in readable


def test_real_pdf_axis_uses_visible_bounds_right_alignment_and_handles_date_edge_and_empty(tmp_path: Path):
    cases = [
        ("visible", ["2026-01-01T00:00:00", "2026-01-02T00:00:00"],
         ("2025-12-31", "2026-01-02"), False),
        ("explicit-time", ["2026-01-01T00:00:00", "2026-01-02T00:00:00"],
         ("2025-12-31 22:48", "2026-01-02 01:12"), True),
        ("date-edge", ["0001-01-01T00:00:00", "0001-01-02T00:00:00"],
         ("Datum nicht darstellbar", "0001-01-02"), False),
        ("empty", [], (), False),
    ]
    for name, dates, labels, show_time in cases:
        source = manifest(["90", "110"] if dates else [], targets="100", dates=dates)
        source["order_is_explicit"] = show_time
        if show_time:
            source["profile_snapshot"]["measurement_date_format"] = "%Y-%m-%dT%H:%M:%S"
        source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
        analysis = analyze_lot(source, {})
        original_json, original_hash = analysis.model_json, analysis.model_sha256
        report = render_analysis_pdf(analysis)
        path, geometry = tmp_path / f"axis-{name}.pdf", tmp_path / f"axis-{name}-geometry.json"
        path.write_bytes(report.pdf_bytes)
        text = extract_text(path, geometry_destination=geometry)
        spans = json.loads(geometry.read_text(encoding="utf-8"))
        if labels:
            left = [span for span in spans if span["text"] == labels[0] and abs(span["bbox"][0] - 78) < 0.75]
            right = [span for span in spans if span["text"] == labels[1] and abs(span["bbox"][2] - 528) < 0.75]
            assert len(left) == len(right) == 1
            assert abs(left[0]["bbox"][0] - 78) < 0.75
            assert abs(right[0]["bbox"][2] - 528) < 0.75
            assert abs(left[0]["bbox"][1] - right[0]["bbox"][1]) < 0.75
        else:
            assert "Datum nicht darstellbar" not in text and not any(span["text"].startswith("0001-") for span in spans)
        assert analysis.model_json == original_json and analysis.model_sha256 == original_hash


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
        report = render_analysis_pdf(analysis)
        path, geometry = tmp_path / f"{name}.pdf", tmp_path / f"{name}.geometry.json"
        path.write_bytes(report.pdf_bytes)
        extract_text(path, geometry_destination=geometry)
        spans = json.loads(geometry.read_text(encoding="utf-8"))
        starts = sorted((span for span in spans if abs(span["bbox"][0] - 39) < 0.5
                         and span["text"] in {str(40 + number) for number in range(1, 9)}),
                        key=lambda span: (span["page"], span["bbox"][1]))
        assert len(starts) == 8
        rows = {}
        for index, start in enumerate(starts):
            end = starts[index + 1]["bbox"][1] if index + 1 < len(starts) and starts[index + 1]["page"] == start["page"] else 790
            def cell(x):
                return " ".join(span["text"] for span in spans if span["page"] == start["page"]
                    and abs(span["bbox"][0] - x) < 0.5 and start["bbox"][1] - 0.1 <= span["bbox"][1] < end - 0.1)
            rows[int(start["text"]) - 40] = cell(105), cell(171), cell(468)
        assert rows[1][0] == "2026-01-01"
        assert rows[4][0] == "2026-02-30 Ungültig"
        assert rows[5][0] == rows[8][0] == "Nicht erfasst"
        if name == "raw-date-time-fields":
            assert rows[1][1] == "24:00 Ungültig"
            assert rows[2][0] == "2026-01-02" and rows[2][1] == rows[3][1] == "Nicht erfasst"
            assert rows[4][1] == "09:15" and rows[5][1] == "10:45" and rows[8][1] == "12:00"
            assert rows[6][1] == "11:30:00"
            assert rows[7][0] == "unlesbares Datum Ungültig" and rows[7][1] == "unlesbare Zeit Ungültig"
            assert "Messzeit" in rows[1][2] and "Messdatum" in rows[4][2]
            assert len(analysis.to_dict()["computed_series"][0]["chart"]["points"]) == 1
        else:
            assert all(row[1] == "Nicht erfasst" for row in rows.values())
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
    readable = " ".join(" ".join(span["text"] for span in spans if abs(span["bbox"][0] - 468) < 0.5).split())
    assert "Extrahierte Messzeit fehlt" in readable
    assert "Messzeit passt nicht zum" in readable and "festgelegten Format" in readable
    assert "measurement_time_missing" not in readable and "measurement_time_invalid" not in readable
    assert "08:00:00" in text
    assert get_profile(spec, old["version_id"]) == old
    assert list_lots(spec, include_history=True) == history_before
    assert get_report_evidence(spec, lot_version_id=closed["version_id"]) == evidence_before
    assert evidence_before["pdf_bytes"] == old_pdf.pdf_bytes and evidence_before["model"] == old_analysis.to_dict()
    assert old_analysis.to_dict()["sd_references"] == refs and "measurement_time_field" not in old["snapshot"]
