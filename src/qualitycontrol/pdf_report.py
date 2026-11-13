"""Bounded fresh-process MuPDF rendering and exact no-clobber evidence export."""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import os
import tempfile
import threading
import time
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Any

from src.rulesuite.api import LEGACY_HEADER_ALIASES

from .analysis import MAX_MODEL_BYTES, RENDERER_ID
from .model import QCAnalysis, QCPdfReport, QCReportError
from .store import get_report_evidence

RENDER_TIMEOUT_S = 25.0
MAX_PAGES = 200
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 4096
_RENDER_SLOT = threading.Lock()

_REASONS = {
    "sd_origin_unavailable": "Herkunft der SD nicht ausreichend belegt",
    "sd_unit_incompatible": "SD gehört zu einer anderen Einheit",
    "sd_parameter_incompatible": "SD gehört zu einer anderen Messwertdefinition",
    "sd_reference_missing": "Keine SD-Referenz", "baseline_insufficient": "Zu wenige Referenzmessungen",
    "baseline_sd_zero": "Referenz-SD ist null", "sd_nonpositive_or_target_unavailable": "SD oder Zielwert nicht verwendbar",
    "history_insufficient": "Nicht genügend aufeinanderfolgende Messungen", "measurement_order_ambiguous": "Messreihenfolge bei gleichem Zeitpunkt nicht belegt",
    "measurement_order_unavailable": "Messreihenfolge nicht belegbar", "history_value_unavailable": "Messreihe durch nicht verwendbare Werte unterbrochen",
    "eligible_values_missing": "Keine geeigneten validierten Werte", "target_or_unit_conflict": "Zielwerte oder Einheiten widersprechen sich",
    "positive_target_required": "Positiver Zielwert erforderlich", "classic_2sd_trigger_absent": "Aktuelles klassisches 2-SD-Prüfsignal nicht ausgelöst",
    "validation_missing": "Menschliche Validierung fehlt", "validation_ambiguous": "Menschliche Validierung mehrdeutig",
    "validation_binding_mismatch": "Validierung gehört zu einem anderen Ergebnisstand", "validation_unreadable": "Validierungsnachweis unlesbar", "measurement_date_invalid": "Messdatum unlesbar",
    "measurement_time_missing": "Extrahierte Messzeit fehlt", "measurement_time_invalid": "Messzeit passt nicht zum festgelegten Format",
    "target_conflict": "Unterschiedliche Zielwerte", "unit_conflict": "Unterschiedliche Einheiten", "result_choice_pending": "Ergebnisauswahl offen",
    "result_incomplete": "Ergebnis unvollständig", "result_unreadable": "Ergebnis unlesbar", "device_incomplete_or_inactive": "Gerät unvollständig oder inaktiv",
    "sd_or_group_incomplete": "SD oder Kontrollgruppe unvollständig", "within_run_controls_or_sd_unavailable": "Gemeinsamer Analysenlauf oder SD nicht ausreichend belegt",
}
_STATUSES = {"reject": "Ablehnungsbefund", "warning": "Warnung", "unavailable": "Nicht verfügbar", "pass": "Kein Befund",
    "disabled": "Nicht ausgewählt", "not_triggered": "Prüfsignal nicht ausgelöst", "no_rejection": "Kein Ablehnungsbefund",
    "exceeded": "Grenze überschritten", "within_limit": "Innerhalb der Grenze", "not_applicable": "Nicht anwendbar", "not_configured": "Keine Grenze konfiguriert"}


def _reason(value: str) -> str:
    return _REASONS.get(value, "Messwert oder Nachweis klären" if value.endswith("_invalid") else value.replace("_", " "))


class _PDFWriter:
    """Pagination and vector presentation only; all statistics are frozen input."""

    def __init__(self, fitz, document, model_hash: str):
        self.fitz, self.document, self.model_hash = fitz, document, model_hash
        self.font = fitz.Font("helv")
        self.fallback_font = fitz.Font("cjk")
        self._glyph_widths = {}
        self._glyph_fonts = {}
        self.page = None
        self.y = 0.0
        self.section = ""
        self.new_page()

    def new_page(self):
        if self.document.page_count >= MAX_PAGES:
            raise QCReportError("Die Auswertung überschreitet 200 PDF-Seiten. Bitte Quellenumfang klären.")
        self.page = self.document.new_page(width=595, height=842)
        self.page.insert_font(fontname="qcfont", fontbuffer=self.font.buffer)
        self._fallback_added = False
        self.y = 42
        self.line("Validierte Kit-Chargen-Auswertung", size=14, color=(0.10, 0.18, 0.31))
        self.y += 6
        self._body_start = self.y
        if self.section:
            if len(self.wrap(self.section, 490, 10)) > 20:
                raise QCReportError("Die Kontrollbezeichnung ist für einen lesbaren Seitenkopf zu lang.")
            self.paragraph(self.section, size=10)
            self._body_start = self.y

    def line(self, text: str, *, size=9, x=36, color=(0.10, 0.12, 0.16)):
        if self.y + size * 1.5 > 790:
            self.new_page()
        self.draw_text(x, self.y, text, size=size, color=color)
        self.y += size * 1.5

    def glyph(self, char, size):
        if char not in self._glyph_fonts:
            if self.font.has_glyph(ord(char)):
                self._glyph_fonts[char] = "qcfont", self.font
            elif self.fallback_font.has_glyph(ord(char)):
                self._glyph_fonts[char] = "qcfallback", self.fallback_font
            else:
                raise QCReportError(f"Das Zeichen U+{ord(char):04X} kann in der PDF nicht lesbar dargestellt werden.")
        name, font = self._glyph_fonts[char]
        key = char, size
        if key not in self._glyph_widths:
            self._glyph_widths[key] = font.text_length(char, fontsize=size)
        return name, self._glyph_widths[key]

    def draw_text(self, x, y, text, *, size=8, color=(0.10, 0.12, 0.16)):
        runs = []
        for char in text:
            name, advance = self.glyph(char, size)
            if runs and runs[-1][0] == name:
                runs[-1][1] += char
                runs[-1][2] += advance
            else:
                runs.append([name, char, advance])
        for name, value, width in runs:
            if name == "qcfallback" and not self._fallback_added:
                self.page.insert_font(fontname=name, fontbuffer=self.fallback_font.buffer)
                self._fallback_added = True
            self.page.insert_text((x, y), value, fontsize=size, fontname=name, color=color)
            x += width

    def wrap(self, value: object, width: float, size=9) -> list[str]:
        text = str(value if value is not None else "–").replace("\r", "")
        text = "".join(char if ord(char) >= 32 or char == "\n" else f"\\u{ord(char):04X}" for char in text)
        if len(text) > 20_000:
            raise QCReportError("Ein Berichtsfeld ist für die begrenzte PDF-Darstellung zu lang.")
        result = []
        for paragraph in text.split("\n"):
            line = ""
            measured = 0.0
            for char in paragraph:
                _font_name, advance = self.glyph(char, size)
                if line and measured + advance > width:
                    break_at = line.rfind(" ")
                    if break_at > 0:
                        result.append(line[:break_at])
                        line = line[break_at + 1:] + char
                        measured = sum(self.glyph(value, size)[1] for value in line)
                    else:
                        result.append(line)
                        line = char
                        measured = advance
                else:
                    line += char
                    measured += advance
            result.append(line)
        return result or [""]

    def paragraph(self, text: object, *, size=9, width=490):
        for line in self.wrap(text, width, size):
            self.line(line, size=size)
        self.y += 4

    def heading(self, text: str):
        self.y += 8
        if self.y > 730:
            self.new_page()
        self.paragraph(text, size=11)

    def keep_block(self, height: float) -> None:
        if height > 790 - self._body_start:
            raise QCReportError("Ein Kontrollabschnitt ist zu lang für eine vollständig lesbare PDF-Seite. Bitte Bezeichnungen prüfen.")
        if self.y + height > 790:
            self.new_page()

    def table(self, headings, rows, widths):
        def header():
            lines = [self.wrap(text, width - 8, 8) for text, width in zip(headings, widths)]
            count = max(map(len, lines))
            if self.y + count * 12 + 16 > 790:
                self.new_page()
            for index in range(count):
                x = 36
                for column, width in zip(lines, widths):
                    if index < len(column):
                        self.draw_text(x + 3, self.y, column[index], color=(0.12, 0.22, 0.38))
                    x += width
                self.y += 12
            self.page.draw_line((36, self.y - 3), (559, self.y - 3), color=(0.65, 0.70, 0.76), width=0.5)
            self.y += 10
        header()
        header_height = max(len(self.wrap(value, width - 8, 8)) for value, width in zip(headings, widths)) * 12 + 10
        for row in rows:
            columns = [self.wrap(value, width - 8, 8) for value, width in zip(row, widths)]
            line_count = max(map(len, columns))
            row_height = line_count * 12 + 5
            if row_height <= 790 - self._body_start - header_height and self.y + row_height > 790:
                self.new_page()
                header()
            for index in range(line_count):
                if self.y + 14 > 790:
                    self.new_page()
                    header()
                    if index:
                        context = " | ".join(str(value).replace("\n", ", ") for value in row[:2])
                        self.paragraph(f"Fortsetzung dieses Datensatzes: {context}", size=8)
                x = 36
                for column, width in zip(columns, widths):
                    if index < len(column):
                        self.draw_text(x + 3, self.y, column[index])
                    x += width
                self.y += 12
            self.y += 5

    def chart(self, chart, *, show_time=True):
        if self.y + 240 > 790:
            self.new_page()
        left, top, width, height = 78.0, self.y + 10, 450.0, 170.0
        xlo, xhi = map(float, chart["x_range"])
        ylo, yhi = map(float, chart["y_range"])
        if not all(math.isfinite(value) for value in (xlo, xhi, ylo, yhi)) or not (xhi > xlo and yhi > ylo):
            raise QCReportError("Die Diagrammskala ist nicht darstellbar.")
        def xy(x, y):
            return (left + (float(x) - xlo) / (xhi - xlo) * width, top + height - (float(y) - ylo) / (yhi - ylo) * height)
        self.page.draw_rect((left, top, left + width, top + height), color=(0.25, 0.30, 0.36), width=0.6)
        for band in chart["bands"]:
            y = xy(xlo, band["value"])[1]
            self.page.draw_line((left, y), (left + width, y), color=(0.70, 0.76, 0.84), width=0.5)
            self.page.insert_text((left + width + 3, y + 3), f"{band['sd_multiple']:+d} SD", fontname="qcfont", fontsize=7)
        if chart.get("target") is not None:
            y = xy(xlo, chart["target"])[1]
            self.page.draw_line((left, y), (left + width, y), color=(0.18, 0.52, 0.36), width=0.7)
            self.draw_text(left + 4, y - 3, "SOLL", size=7, color=(0.18, 0.52, 0.36))
        points = {point["point_key"]: point for point in chart["points"]}
        for segment in chart["segments"]:
            selected = [points[key] for key in segment if key in points]
            for before, after in zip(selected, selected[1:]):
                self.page.draw_line(xy(before["x"], before["y"]), xy(after["x"], after["y"]), color=(0.18, 0.36, 0.64), width=0.7)
        for point in points.values():
            color = (0.72, 0.18, 0.18) if point["run_status"] == "reject" else ((0.80, 0.48, 0.10) if point["run_status"] == "warning" else (0.18, 0.36, 0.64))
            self.page.draw_circle(xy(point["x"], point["y"]), 2.5, color=color, fill=color)
        self.page.insert_text((36, top + 10), f"{yhi:.4g}", fontsize=7, fontname="qcfont")
        self.page.insert_text((36, top + height), f"{ylo:.4g}", fontsize=7, fontname="qcfont")
        if points:
            for bound, right_aligned in ((xlo, False), (xhi, True)):
                try:
                    ordinal = math.floor(bound)
                    measured = datetime.fromordinal(ordinal) + timedelta(seconds=round((bound - ordinal) * 86400))
                    label = measured.isoformat(sep=" ", timespec="minutes") if show_time else measured.date().isoformat()
                except (ValueError, OverflowError):
                    label = "Datum nicht darstellbar"
                text_width = sum(self.glyph(char, 7)[1] for char in label)
                x = left + width - text_width if right_aligned else left
                self.draw_text(x, top + height + 13, label, size=7)
        self.y = top + height + 30
        self.paragraph(f"{chart['x_label'] if show_time else 'Extrahiertes Messdatum'} · {chart['y_label']}", size=8)


def _point_display(source, point):
    matches = [row for row in source["population"]
        if all(row.get(key) == point.get(key) for key in ("run_id", "revision_id", "selection_id", "selection_token", "source_hash"))]
    original = matches[0] if len(matches) == 1 else {}
    payload = original.get("raw_payload") or {}
    operators = list(dict.fromkeys(str(payload[key]).strip() for key in (LEGACY_HEADER_ALIASES["user"], "user")
                                  if payload.get(key) is not None and str(payload[key]).strip()))
    operator = (operators[0] if len(operators) == 1 else "Mehrdeutig: " + " / ".join(operators)) if operators else "Nicht erfasst"
    record = original.get("validation") or {}
    reasons = [*original.get("reasons", []), *point.get("reasons", [])]
    validation_problem = next((value for value in reasons if value.startswith("validation_")), original.get("validation_error", ""))
    binding = bool(record and not validation_problem and len(matches) == 1
        and all(record.get(key) == point.get(key) for key in ("run_id", "revision_id", "selection_id", "validation_id"))
        and (record.get("selection_token") == point.get("selection_token") or
             (not record.get("selection_token") and point.get("revision_id") == 0 and point.get("selection_id") is None)))
    validator = str(record.get("operator_initials") or "Nicht erfasst") if binding else _reason(validation_problem or "validation_missing")
    validated_at = str(record.get("validated_at_utc") or "Nicht erfasst") if binding else "–"
    if binding:
        try:
            stamp = datetime.fromisoformat(validated_at.replace("Z", "+00:00"))
            if stamp.utcoffset() == timedelta(0):
                validated_at = f"{stamp.date().isoformat()}\n{stamp.time().isoformat()}"
        except ValueError:
            pass
    measured = point.get("measured_at")
    date, clock = "Nicht erfasst", "Nicht erfasst"
    if measured:
        date = measured.split("T")[0]
        if source.get("order_is_explicit") or any(token in source["profile_snapshot"].get("measurement_date_format", "") for token in ("%H", "%M", "%S")):
            clock = measured.split("T", 1)[1] if "T" in measured else "Nicht erfasst"
    else:
        def raw_field(key, invalid_reason):
            raw = original.get(key)
            if raw is None or not str(raw).strip():
                return "Nicht erfasst"
            shown = str(raw)
            return f"{shown}\nUngültig" if invalid_reason in reasons else shown
        date = raw_field("measurement_date_raw", "measurement_date_invalid")
        clock = raw_field("measurement_time_raw", "measurement_time_invalid")
    return date, clock, operator, validator, validated_at


def _render_model(fitz, analysis: QCAnalysis, *, include_explanations: bool = False) -> bytes:
    model = analysis.to_dict()
    source, profile = model["source_manifest"], model["source_manifest"]["profile_snapshot"]
    show_time = bool(source.get("order_is_explicit") or any(token in profile.get("measurement_date_format", "") for token in ("%H", "%M", "%S")))
    date_heading = "Messdatum / Messzeit" if show_time else "Messdatum"
    def measurement_labels(run):
        return ", ".join(value if show_time else value.split("T")[0] for value in run["measurement_dates"])
    with fitz.open() as document:
        writer = _PDFWriter(fitz, document, analysis.model_sha256)
        legends = []
        device = next((item for item in source["inventory_snapshot"]["devices"] if item["device_id"] == source["device_id"]), {})
        assay_name = str(model.get("presentation", {}).get("assay_name") or "Assayname fehlt")
        for index, series in enumerate(model["computed_series"]):
            qmma, sd = series["qmma"], series["sd"]
            heading = f"Kontrolle: {series['control_name']} · {series['unit']}"
            writer.section = f"{heading}\nAssay: {assay_name} · Kit-Charge: {source['kit_lot']}"
            if index:
                writer.new_page()
            else:
                writer.paragraph(writer.section, size=10)
            writer.paragraph(f"Gerät: {device.get('display_name') or 'Gerätename fehlt'} · SN: {device.get('serial_number') or '–'} · LNR: {device.get('lnr') or '–'} · EVA: {device.get('eva') or '–'}", size=8)
            writer._body_start = writer.y
            relative = f"{Decimal(qmma['relative_percent']):.6g} %" if qmma['relative_percent'] is not None else _reason(qmma['relative_reason'])
            shown_qmma = format(Decimal(qmma['value']), ".6g") if qmma['available'] else _reason(qmma['reason'])
            summary = f"QMMA: {shown_qmma} {series['unit']} · n = {qmma['n']} · relativ: {relative} · SOLL: {qmma.get('target') or 'nicht verfügbar'}"
            limit = profile.get("relative_limit_percent")
            limit_text = f"QMMA-Grenze (relativ): {str(limit) + ' %' if limit is not None else 'nicht konfiguriert'}; Profilanwendbarkeit: {'ja' if profile.get('rili_applicable') else 'nein'}; relative Auswertung: {'aktiv' if profile.get('relative_enabled') else 'aus'}. QMMA-Bewertung: {_STATUSES.get(qmma['limit_status'], qmma['limit_status'])}."
            reference_kind = "manuell festgelegte SD" if sd.get("kind") == "manual" else (f"bestätigte eingefrorene Referenzserie, n = {sd.get('n')}" if sd.get("kind") == "confirmed_baseline" else "nicht verfügbar")
            shown_sd = format(Decimal(sd['sd']), ".6g") if sd.get("available") else _reason(sd.get('reason', 'sd_reference_missing'))
            shown_center = format(Decimal(sd['center']), ".6g") if sd.get("available") else "nicht verfügbar"
            sd_text = f"SD: {shown_sd} · Mitte: {shown_center} · Referenzart: {reference_kind}"
            legend = (f"Diagrammlegende: Grüne Linie = SOLL {qmma.get('target', 'nicht verfügbar')}; SD-Linien = Referenzmitte {shown_center} mit ±1, ±2 und ±3 SD. Die eingefrorene Referenzmitte kann vom SOLL abweichen." if sd.get("available") else
                "Diagrammlegende: Grüne Linie = SOLL; ohne verwendbare SD-Referenz sind SD-Bänder und Westgard-Auswertung nicht verfügbar.")
            chart_note = f"{series['chart']['x_label'] if show_time else 'Extrahiertes Messdatum'} · {series['chart']['y_label']}"
            legends.append((heading, legend))
            height = sum(len(writer.wrap(value, 490, 9)) * 13.5 + 4 for value in (summary, limit_text, sd_text))
            height += max(240, 210 + len(writer.wrap(chart_note, 490, 8)) * 12 + 4)
            writer.keep_block(height)
            writer.paragraph(summary)
            writer.paragraph(limit_text)
            writer.paragraph(sd_text)
            writer.chart(series["chart"], show_time=show_time)
            points = [point for point in model["points"] if point["control_id"] == series["control_id"]]
            keys = {point["point_key"] for point in points}
            selected_rules = set(profile["enabled_rules"])
            eligible = any(point["eligible"] for point in points)
            evaluated = False
            relevant, unavailable = [], set()
            for run in model["analytical_runs"]:
                if not keys.intersection(run["point_keys"]):
                    continue
                for finding in run["findings"]:
                    if finding["rule"] in selected_rules and finding["status"] in {"pass", "not_triggered"}:
                        evaluated = True
                    if finding["status"] in {"reject", "warning"} and keys.intersection(finding["point_keys"]):
                        relevant.append((measurement_labels(run), finding["rule"], _STATUSES[finding["status"]]))
                    elif finding["status"] == "unavailable":
                        unavailable.add(_reason(finding["reason"]))
            if relevant:
                writer.heading("Warnungen und Ablehnungsbefunde")
                writer.table((date_heading, "Regel", "Befund"), relevant, (240, 80, 203))
            if not selected_rules:
                writer.paragraph("Westgard: keine Regeln ausgewählt.", size=8)
            if not eligible:
                writer.paragraph("Westgard nicht auswertbar: keine geeigneten Kontrollwerte.", size=8)
            elif selected_rules:
                if unavailable:
                    writer.paragraph("Westgard nicht vollständig verfügbar: " + "; ".join(sorted(unavailable)), size=8)
                elif not relevant:
                    writer.paragraph("Westgard: keine Warnung oder Ablehnung in den ausgewählten Regeln." if evaluated else
                        "Westgard nicht verfügbar: keine ausgewählte Regel auswertbar.", size=8)
            writer.heading(f"Einzelwerte · geeignet {series['included_count']}, ausgeschlossen {series['excluded_count']}")
            rows = []
            for point in points:
                date, clock, operator, validator, validated_at = _point_display(source, point)
                value = str(point["raw"].get("IST") if point["raw"].get("IST") is not None else "Nicht erfasst")
                reasons = "; ".join(_reason(reason) for reason in point.get("reasons", []))
                rows.append((value, date, clock, operator, validator, validated_at, reasons or "Geeignet"))
            writer.table(("Messwert", "Datum", "Uhrzeit", "Anwender", "Validiert durch", "Validiert am UTC", "Eignung / Grund"), rows, (66, 66, 53, 76, 80, 88, 94))
        if include_explanations:
            writer.section = "Erläuterungen zur Auswertung"
            writer.new_page()
            writer.paragraph("Gleiche Messzeitpunkte werden nicht künstlich verbunden. Die Diagramme verwenden ausschließlich belegte Messdaten und keine Importreihenfolge.")
            for heading, legend in legends:
                writer.paragraph(f"{heading}\n{legend}", size=8)
            writer.paragraph("Menschliche Extraktionsvalidierung und statistische QC-Befunde sind getrennte Zustände. Berechnete Anzeigewerte werden auf sechs signifikante Stellen gerundet; Rohwerte bleiben vollständig, Grenzentscheidungen verwenden ungerundete Werte.")
            writer.paragraph(f"Analyseverfahren: {model['algorithm_id']} · Ursprüngliches PDF-Verfahren: {model['renderer_id']} · Druckverfahren: {RENDERER_ID} · Inventarfassung: {source['inventory_version_id']} · Profilfassung: {source['profile_version_id']}")
            writer.paragraph(f"Modell SHA-256: {analysis.model_sha256}\nQuellenmanifest: {source['source_token']}")
            writer.paragraph(f"Profilreferenz: {model['profile_reference'] or 'nicht festgelegt'}\nFormelbezug: {model['references']['qmma']['version']} (Definition Seite 2)\nWestgard-Verfahren: classic-six-v1 mit aktuellem 2-SD-Prüfsignal; 1_2s-Auswahl steuert nur die Warnanzeige.")
            writer.paragraph(model["references"]["report_scope"])
            writer.paragraph("Berechnungsbezug: QMMA = sqrt(sum((IST - SOLL)^2) / n); relativ = 100 × QMMA / SOLL bei positivem, konsistentem SOLL. Hersteller-MIN/MAX sind keine SD-Referenz.", size=8)
            for value in model["references"]["qmma"]["url"], model["references"]["westgard"]["url"], model["references"]["westgard"]["r4s_reference"]:
                writer.paragraph(value, size=7, width=470)
            writer.heading("Vollständige Regelbefunde")
            rows = [(measurement_labels(run), finding["rule"], _STATUSES[finding["status"]], _reason(finding["reason"]) if finding["reason"] else "–")
                    for run in model["analytical_runs"] for finding in run["findings"]]
            writer.table((date_heading, "Regel", "Befund", "Grund"), rows, (145, 50, 120, 208))
        for page_index, page in enumerate(document):
            page.insert_text((36, 817), f"Seite {page_index + 1} von {document.page_count} · Modell {analysis.model_sha256[:16]}", fontsize=7, fontname="qcfont", color=(0.35, 0.38, 0.42))
        return document.tobytes(garbage=1, deflate=True)


def _render_worker(folder_name: str, model_hash: str, include_explanations: bool = False) -> None:
    folder = Path(folder_name)
    try:
        if type(include_explanations) is not bool:
            raise QCReportError("Die Auswahl der Erläuterungen ist ungültig.")
        model_path = folder / "model.json"
        if model_path.stat().st_size > MAX_MODEL_BYTES:
            raise QCReportError("Das Analysemodell überschreitet die PDF-Grenze.")
        analysis = QCAnalysis(model_path.read_text(encoding="utf-8"), model_hash)
        import fitz  # MuPDF only on the main thread of this fresh spawn process.

        raw = _render_model(fitz, analysis, include_explanations=include_explanations)
        if not raw or len(raw) > MAX_PDF_BYTES:
            raise QCReportError("Die erzeugte PDF überschreitet 64 MB.")
        with fitz.open(stream=raw, filetype="pdf") as check:
            if not check.is_pdf or check.needs_pass or check.is_repaired or not 0 < check.page_count <= MAX_PAGES:
                raise QCReportError("Die erzeugte PDF konnte nicht verifiziert werden.")
            if not all(page.get_text().strip() for page in check):
                raise QCReportError("Eine erzeugte PDF-Seite ist leer.")
            count = check.page_count
        (folder / "report.pdf").write_bytes(raw)
        result = {"pdf_sha256": hashlib.sha256(raw).hexdigest(), "model_sha256": model_hash,
                  "renderer_id": RENDERER_ID, "page_count": count, "include_explanations": include_explanations}
    except Exception as exc:
        result = {"error": str(exc) if isinstance(exc, QCReportError) else "Die PDF-Auswertung konnte nicht erzeugt oder verifiziert werden."}
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")


def _stop_process(process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(timeout=0.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.5)


def render_analysis_pdf(analysis: QCAnalysis, *, include_explanations: bool = False) -> QCPdfReport:
    if type(include_explanations) is not bool:
        raise QCReportError("Die Auswahl der Erläuterungen ist ungültig.")
    if not isinstance(analysis, QCAnalysis) or len(analysis.model_json.encode("utf-8")) > MAX_MODEL_BYTES:
        raise QCReportError("Ein gültiges eingefrorenes Analysemodell ist erforderlich.")
    if not analysis.is_supported:
        raise QCReportError("Die PDF-Verfahrensfassung wird nicht unterstützt.")
    deadline = time.monotonic() + RENDER_TIMEOUT_S
    if not _RENDER_SLOT.acquire(timeout=RENDER_TIMEOUT_S):
        raise QCReportError("Die PDF-Erzeugung hat das Zeitlimit überschritten.")
    process, started = None, False
    try:
        with tempfile.TemporaryDirectory(prefix="arev2-qc-report-") as temporary:
            folder = Path(temporary)
            (folder / "model.json").write_text(analysis.model_json, encoding="utf-8")
            try:
                process = multiprocessing.get_context("spawn").Process(target=_render_worker, args=(temporary, analysis.model_sha256, include_explanations), daemon=True)
                process.start()
                started = True
                process.join(timeout=max(0.0, deadline - time.monotonic()))
                if process.is_alive():
                    raise QCReportError("Die PDF-Erzeugung hat das Zeitlimit überschritten.")
                if process.exitcode != 0:
                    raise QCReportError("Die PDF-Erzeugung wurde unerwartet beendet.")
                metadata_path = folder / "result.json"
                if metadata_path.stat().st_size > MAX_METADATA_BYTES:
                    raise QCReportError("Die PDF-Prüfdaten überschreiten die Grenze.")
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("error"):
                    raise QCReportError(str(metadata["error"]))
                pdf_path = folder / "report.pdf"
                if not 0 < pdf_path.stat().st_size <= MAX_PDF_BYTES:
                    raise QCReportError("Die erzeugte PDF-Größe ist ungültig.")
                raw = pdf_path.read_bytes()
                if (hashlib.sha256(raw).hexdigest() != metadata["pdf_sha256"] or metadata["model_sha256"] != analysis.model_sha256
                        or metadata["renderer_id"] != RENDERER_ID or type(metadata["page_count"]) is not int
                         or type(metadata.get("include_explanations")) is not bool or metadata["include_explanations"] != include_explanations
                        or not 0 < metadata["page_count"] <= MAX_PAGES or not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]):
                    raise QCReportError("Die erzeugte PDF-Prüfsumme oder Metadaten stimmen nicht.")
                return QCPdfReport(raw, metadata["pdf_sha256"], analysis.model_sha256, RENDERER_ID, metadata["page_count"])
            finally:
                if process is not None:
                    if started:
                        _stop_process(process)
                    if not started or not process.is_alive():
                        process.close()
    except QCReportError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise QCReportError("Die PDF-Auswertung konnte nicht vollständig erstellt werden.") from exc
    finally:
        _RENDER_SLOT.release()


def export_report_evidence(store_spec, *, lot_version_id: int, destination: str | Path, include_explanations: bool = False) -> dict[str, Any]:
    if type(include_explanations) is not bool:
        raise QCReportError("Die Auswahl der Erläuterungen ist ungültig.")
    evidence = get_report_evidence(store_spec, lot_version_id=lot_version_id)
    if evidence is None:
        raise QCReportError("Der gespeicherte PDF-Nachweis wurde nicht gefunden.")
    raw, checksum = evidence["pdf_bytes"], evidence["pdf_sha256"]
    if include_explanations:
        report = render_analysis_pdf(QCAnalysis.freeze(evidence["model"]), include_explanations=True)
        raw, checksum = report.pdf_bytes, report.pdf_sha256
    path = Path(destination)
    created_identity = None
    try:
        with path.open("xb") as stream:
            stat = os.fstat(stream.fileno())
            created_identity = (stat.st_dev, stat.st_ino)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return {"path": str(path.resolve()), "pdf_sha256": checksum, "bytes_written": len(raw), "include_explanations": include_explanations}
    except FileExistsError as exc:
        raise QCReportError("Die Zieldatei existiert bereits. Bitte einen neuen Dateinamen wählen.") from exc
    except OSError as exc:
        if created_identity is not None:
            try:
                stat = path.stat()
                if (stat.st_dev, stat.st_ino) == created_identity:
                    path.unlink()
            except OSError:
                pass
        raise QCReportError("Der PDF-Nachweis konnte nicht vollständig gespeichert werden.") from exc
