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
    "manufacturer_min_conflict": "Unterschiedliche Hersteller-MIN-Werte: Profil klären",
    "manufacturer_max_conflict": "Unterschiedliche Hersteller-MAX-Werte: Profil klären",
    "manufacturer_limits_reversed": "Hersteller-MIN ist größer als MAX",
    "percentage_limits_reversed": "SOLL × (1 ± Prozent / 100) ergibt vertauschte Grenzen",
    "point_ineligible": "Messpunkt nicht für die Auswertung geeignet",
    "not_configured": "Keine Einzelwert-Prozentgrenze konfiguriert",
    "sample_sd_requires_two_values": "Mindestens zwei geeignete Werte für empirische SD und VK erforderlich",
    "positive_mean_required": "Positiver Mittelwert für VK erforderlich",
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
        for band in (() if "reference_lines" in chart else chart["bands"]):
            y = xy(xlo, band["value"])[1]
            self.page.draw_line((left, y), (left + width, y), color=(0.70, 0.76, 0.84), width=0.5)
            self.page.insert_text((left + width + 3, y + 3), f"{band['sd_multiple']:+d} SD", fontname="qcfont", fontsize=7)
        if "reference_lines" not in chart and chart.get("target") is not None:
            y = xy(xlo, chart["target"])[1]
            self.page.draw_line((left, y), (left + width, y), color=(0.18, 0.52, 0.36), width=0.7)
            self.draw_text(left + 4, y - 3, "SOLL", size=7, color=(0.18, 0.52, 0.36))
        line_colors = {"target": (0.18, 0.52, 0.36), "manufacturer": (0.48, 0.32, 0.64),
                       "single_value": (0.90, 0.48, 0.08), "sd": (0.70, 0.76, 0.84)}
        for line in chart.get("reference_lines", []):
            y = xy(xlo, line["value"])[1]
            self.page.draw_line((left, y), (left + width, y), color=line_colors[line["kind"]],
                                width=0.6 if line["kind"] == "sd" else 1,
                                dashes="[4 3] 0" if line["kind"] == "manufacturer" else None)
            if line["kind"] == "sd":
                self.draw_text(left + width + 3, y + 3, line["label"], size=7)
            elif line["kind"] == "target":
                self.draw_text(left + 4, y - 3, line["label"], size=7, color=line_colors["target"])
        points = {point["point_key"]: point for point in chart["points"]}
        for segment in chart["segments"]:
            selected = [points[key] for key in segment if key in points]
            for before, after in zip(selected, selected[1:]):
                self.page.draw_line(xy(before["x"], before["y"]), xy(after["x"], after["y"]), color=(0.18, 0.36, 0.64), width=0.7)
        for point in points.values():
            color = (0.72, 0.18, 0.18) if point["run_status"] == "reject" else ((0.80, 0.48, 0.10) if point["run_status"] == "warning" else (0.18, 0.36, 0.64))
            if any(finding["status"] == "exceeded" for finding in point.get("limit_findings", {}).values()):
                self.page.draw_circle(xy(point["x"], point["y"]), 4.5, color=(0.90, 0.48, 0.08), width=1)
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


class _CompactPDFWriter(_PDFWriter):
    """A4 presentation of schema-3 frozen values; no statistical calculations."""

    COLORS = {"target": (0.16, 0.47, 0.31), "mean": (0.43, 0.46, 0.49),
        "manufacturer": (0.48, 0.32, 0.64), "single_value": (0.90, 0.48, 0.08), "sd": (0.64, 0.70, 0.78)}
    DASHES = {"target": None, "mean": "[1 3] 0", "manufacturer": "[5 3] 0", "single_value": "[6 2 1 2] 0", "sd": "[2 3] 0"}

    def __init__(self, fitz, document, analysis):
        self.fitz, self.document, self.model_hash = fitz, document, analysis.model_sha256
        self.model = analysis.to_dict()
        self.source = self.model["source_manifest"]
        self.profile = self.source["profile_snapshot"]
        self.device = next((row for row in self.source["inventory_snapshot"]["devices"] if row["device_id"] == self.source["device_id"]), {})
        self.font, self.fallback_font = fitz.Font("tiro"), fitz.Font("cjk")
        self.heading_font = fitz.Font("tibo")
        self._glyph_widths, self._glyph_fonts = {}, {}
        self.series, self.page, self.record_context = None, None, ""
        self.kind, self.y, self.section = "primary", 0.0, ""

    @staticmethod
    def number(value):
        return format(Decimal(value), ".6g") if value is not None else "–"

    @staticmethod
    def date(value):
        try:
            return datetime.fromisoformat(value).strftime("%d.%m.%Y")
        except (ValueError, TypeError):
            return "ungeklärt"

    @staticmethod
    def short(value, length=28):
        text = str(value if value is not None else "–")
        return text if len(text) <= length else text[:length - 1] + "…"

    def header_lines(self, text, x, y, width, size=8):
        lines = self.wrap(text, width, size)
        if len(lines) > 36:
            raise QCReportError("Die Bezeichnung ist für einen lesbaren Berichtskopf zu lang.")
        for line in lines:
            self.draw_text(x, y, line, size=size)
            y += size + 2
        return y

    def primary_columns(self):
        period = self.series["period"]
        date_span = self.date(period["start_date"]) + " – " + self.date(period["end_date"])
        limits = self.series["limits"]
        def bound(kind):
            value = limits[kind]
            return (self.number(value["lower"]) + " bis " + self.number(value["upper"])) if value["available"] else _reason(value["reason"])
        return [
            ["Gerät: " + str(self.device.get("display_name") or "nicht erfasst"), "Geräte-ID: " + self.source["device_id"],
             "SN: " + str(self.device.get("serial_number") or "–"), "LNR: " + str(self.device.get("lnr") or "–") + " · EVA: " + str(self.device.get("eva") or "–")],
            ["Assay: " + str(self.model.get("presentation", {}).get("assay_name") or "Assayname fehlt"), "Assay-ID: " + self.source["assay_key"],
             "Level: " + self.series["control_name"], "Kit-/Reagenzcharge: " + self.source["kit_lot"]],
            ["Zeitraum: " + date_span, "Einheit: " + self.series["unit"], "SOLL: " + self.number(self.series["qmma"].get("target")),
             "Hersteller: " + bound("manufacturer"), "Einzelwert: " + bound("single_value")]]

    def primary_header_height(self):
        return 17 + max(len(self.wrap("\n".join(values), 166, 8))*10 for values in self.primary_columns()) + 7

    def start_level(self):
        # A new level may share the previous level's last continuation page,
        # provided its complete overview and at least one table row fit.
        required = 5+self.primary_header_height()+242+self.statistics_height()+24+14
        if self.page is None or self.y+required > 790:
            self.new_page("primary")
        else:
            self.kind = "primary"
            self.y += 5
            self.draw_header()

    def draw_header(self):
        self.page.insert_text((36, self.y), "KONTROLLPROBENEINZELMESSUNG", fontname="qchead", fontsize=12, color=(0.12, 0.18, 0.25))
        self.y += 17
        if self.kind == "primary":
            ends = [self.header_lines("\n".join(values), 36+column*178, self.y, 166, 8)
                for column, values in enumerate(self.primary_columns())]
            self.y = max(ends)+7
        else:
            context = (f"Gerät: {self.device.get('display_name') or self.source['device_id']} · Assay: "
                f"{self.model.get('presentation', {}).get('assay_name') or self.source['assay_key']} · Kit-/Reagenzcharge: {self.source['kit_lot']} · Level: {self.series['control_name']}")
            self.y = self.header_lines(context, 36, self.y, 523, 8)+5
            self.page.insert_text((36, self.y), "Messwertnachweise" if self.kind == "evidence" else "Messwerttabelle – Fortsetzung", fontname="qchead", fontsize=10)
            self.y += 16
            if self.record_context:
                self.y = self.header_lines(self.record_context, 36, self.y, 523, 7)+3
        self._body_start = self.y

    def new_page(self, kind=None):
        if self.document.page_count >= MAX_PAGES:
            raise QCReportError("Die Auswertung überschreitet 200 PDF-Seiten. Bitte Quellenumfang klären.")
        if kind is not None:
            self.kind = kind
        self.page = self.document.new_page(width=595, height=842)
        self.page.insert_font(fontname="qcfont", fontbuffer=self.font.buffer)
        self.page.insert_font(fontname="qchead", fontbuffer=self.heading_font.buffer)
        self._fallback_added = False
        self.y = 36
        self.draw_header()

    def paragraph(self, text, *, size=8, width=523):
        return super().paragraph(text, size=size, width=width)

    def metric(self, value):
        return self.number(value["value"]) if value["available"] else "nicht verfügbar"

    def chart(self, chart, *, show_time=True):
        self.keep_block(242)
        left, top, width, height = 46.0, self.y + 5, 390.0, 184.0
        xlo, xhi = map(float, chart["x_range"])
        ylo, yhi = map(float, chart["y_range"])
        if not all(math.isfinite(value) for value in (xlo, xhi, ylo, yhi, xhi-xlo, yhi-ylo)) or not (xhi > xlo and yhi > ylo):
            raise QCReportError("Die Diagrammskala ist nicht darstellbar.")
        def xy(x, y):
            return (left+(float(x)-xlo)/(xhi-xlo)*width, top+height-(float(y)-ylo)/(yhi-ylo)*height)
        self.page.draw_rect((left, top, left+width, top+height), color=(0.65, 0.69, 0.74), width=0.6)
        for line in chart["reference_lines"]:
            y = xy(xlo, line["value"])[1]
            self.page.draw_line((left,y),(left+width,y),color=self.COLORS[line["kind"]],width=0.55 if line["kind"]=="sd" else 1,
                dashes=self.DASHES[line["kind"]])
        points = {point["point_key"]: point for point in chart["points"]}
        for segment in chart["segments"]:
            chosen = [points[key] for key in segment if key in points]
            for first, last in zip(chosen, chosen[1:]):
                self.page.draw_line(xy(first["x"],first["y"]),xy(last["x"],last["y"]),color=(0.18,0.36,0.64),width=0.9)
        for point in points.values():
            x,y = xy(point["x"],point["y"])
            status = point["run_status"]
            color = (0.72,0.18,0.18) if status=="reject" else ((0.80,0.48,0.10) if status=="warning" else (0.18,0.36,0.64))
            if any(finding["status"]=="exceeded" for finding in point["limit_findings"].values()):
                self.page.draw_circle((x,y),4.7,color=(0.90,0.48,0.08),width=1)
            if status=="reject":
                self.page.draw_rect((x-2.5,y-2.5,x+2.5,y+2.5),color=color,fill=color)
            elif status=="warning":
                self.page.draw_polyline([(x,y-3),(x+3,y+2.5),(x-3,y+2.5)],closePath=True,color=color,fill=color)
            else:
                self.page.draw_circle((x,y),2.4,color=color,fill=color)
        for value,y in ((yhi,top+3),(ylo,top+height)):
            text = f"{value:.4g}"
            advance = sum(self.glyph(char,6.8)[1] for char in text)
            self.draw_text(left-5-advance,y,text,size=6.8)
        unique = {}
        for point in sorted(points.values(), key=lambda point: float(point["x"])):
            unique.setdefault(point["x"],point)
        ticks = list(unique.values())
        if len(ticks)>11:
            ticks = [ticks[round(index*(len(ticks)-1)/10)] for index in range(11)]
        same_day = bool(ticks) and len({point["measurement"]["date"] for point in ticks})==1
        # Real time coordinates stay unchanged. Omit close labels rather than
        # printing several measurements a few minutes apart on top of each other.
        spaced_ticks = []
        for point in ticks:
            if not spaced_ticks or xy(point["x"], ylo)[0] - xy(spaced_ticks[-1]["x"], ylo)[0] >= 34:
                spaced_ticks.append(point)
        for point in spaced_ticks:
            measured = point["measurement"]
            label = measured["time"] if same_day and measured["time"] else self.date(measured["date"])
            x = xy(point["x"],ylo)[0]
            origin = self.fitz.Point(x-1,top+height+10)
            self.page.insert_text(origin,label,fontname="qcfont",fontsize=6.4,morph=(origin,self.fitz.Matrix(-45)))
        legend_y = top+5
        def legend(label, detail, kind=None):
            nonlocal legend_y
            if kind:
                self.page.draw_line((448,legend_y-2),(463,legend_y-2),color=self.COLORS[kind],width=1,dashes=self.DASHES[kind])
            else:
                self.page.draw_circle((455,legend_y-2),2,color=(0.18,0.36,0.64),fill=(0.18,0.36,0.64))
            lines = self.wrap(label+"\n"+detail,89,6.8)
            for text in lines:
                self.draw_text(469,legend_y,text,size=6.8)
                legend_y+=8.5
            legend_y+=4
        legend("Messwerte","Punktstatus: Westgard")
        legend("SOLL",self.number(chart.get("target")),"target")
        legend("Mittelwert",self.metric(self.series["descriptive"]["mean"]),"mean")
        for kind,label in (("manufacturer","Herstellergrenzen"),("single_value","Einzelwertgrenzen")):
            value=self.series["limits"][kind]
            detail=(self.number(value["lower"])+" / "+self.number(value["upper"])) if value["available"] else "nicht verfügbar"
            if kind=="single_value" and value.get("percent") is not None:
                detail += " ("+value["percent"]+" %)"
            legend(label,detail,kind)
        sd = self.series["sd"]
        legend("SD-Referenz",("Mitte: "+self.number(sd["center"])+"; SD "+self.number(sd["sd"])+"\n±1 / ±2 / ±3 SD") if sd["available"] else "nicht verfügbar","sd")
        for text in self.wrap("Ring: Grenzbefund; Quadrat: Ablehnung; Dreieck: Warnung", 110, 6.8):
            self.draw_text(448, legend_y, text, size=6.8)
            legend_y += 8.5
        if legend_y > top+232:
            raise QCReportError("Die Diagrammlegende ist für eine lesbare Darstellung zu lang.")
        self.y=top+234

    def statistics_content(self):
        descriptive,qmma = self.series["descriptive"],self.series["qmma"]
        left=["Anzahl: "+str(descriptive["n"]),"Mittelwert: "+self.metric(descriptive["mean"]),
            "Empirische SD (n-1): "+self.metric(descriptive["sample_sd"]),"VK (%): "+self.metric(descriptive["cv_percent"])]
        right=["QMMA: "+(self.number(qmma["value"])+" "+self.series["unit"] if qmma["available"] else "nicht verfügbar"),
            "QMMA relativ: "+(self.number(qmma["relative_percent"])+" %" if qmma["relative_percent"] is not None else "nicht verfügbar"),
            "QMMA-Grenze (relativ): "+(str(self.profile["relative_limit_percent"])+" %" if self.profile.get("relative_limit_percent") is not None else "nicht konfiguriert"),
            "QMMA-Bewertung: "+_STATUSES[qmma["limit_status"]]]
        notes = []
        summary=self.series["findings_summary"]
        sd=self.series["sd"]
        sd_text = "SD-Referenz: "+(_reference_description(sd)+" (getrennt von empirischer SD)" if sd["available"] else _reason(sd["reason"]))
        if not self.series["included_count"]:
            westgard = "Westgard nicht auswertbar: keine geeigneten Kontrollwerte. Westgard: "+_STATUSES[summary["westgard_status"]]
        elif summary["westgard_status"] == "unavailable":
            westgard = "Westgard nicht vollständig verfügbar"
        else:
            westgard = "Westgard: "+_STATUSES[summary["westgard_status"]]
        notes.append(sd_text+"; "+westgard+".")
        if summary["manufacturer_exceeded_count"] or summary["single_value_exceeded_count"]:
            notes.append(f"Einzelwerte: Herstellergrenze {summary['manufacturer_exceeded_count']} × überschritten; Einzelwert-Prozentgrenze {summary['single_value_exceeded_count']} × überschritten.")
        return left, right, notes

    def statistics_height(self):
        left, right, notes = self.statistics_content()
        return max(len(self.wrap("\n".join(values), 251, 8))*10 for values in (left, right))+3+sum(
            len(self.wrap(note, 523, 7))*10.5+4 for note in notes)

    def statistics(self):
        self.keep_block(self.statistics_height())
        left, right, notes = self.statistics_content()
        ends=[self.header_lines("\n".join(values),36+column*266,self.y,251,8) for column,values in enumerate((left,right))]
        self.y=max(ends)+3
        for note in notes:
            self.paragraph(note, size=7)

    def point_findings(self, point):
        return [finding for run_record in self.model["analytical_runs"] if point["point_key"] in run_record["point_keys"]
            for finding in run_record["findings"] if finding["rule"] in self.profile["enabled_rules"]
            and finding["status"] in {"reject", "warning", "unavailable"}]

    def point_notes(self, points):
        groups = {}
        for point in points:
            notes = []
            if not point["eligible"]:
                notes.append("Nicht ausgewertet: "+"; ".join(_reason(reason) for reason in point["reasons"]))
            for kind, label in (("manufacturer", "Herstellergrenze"), ("single_value", "Einzelwert-Prozentgrenze")):
                if point["limit_findings"][kind]["status"] == "exceeded":
                    notes.append(label+": Grenze überschritten")
            notes.extend(dict.fromkeys(f"Westgard {finding['rule']}: {_STATUSES[finding['status']]}"+
                (" · "+_reason(finding["reason"]) if finding["reason"] else "") for finding in self.point_findings(point)
                if finding["status"] in {"reject", "warning"}))
            if _point_display(self.source, point)[2].startswith("Mehrdeutig:"):
                notes.append("Anwenderangabe mehrdeutig")
            if notes:
                groups.setdefault("; ".join(notes), []).append(point["position"])
        return [f"Pos {_positions_label(positions)}: {text}" for text, positions in groups.items()]

    def measurement_table(self, points):
        self.kind="measurement"
        widths=(25,104,40,64,64,64,64,98)
        headings=("Pos","Datum / Zeit","Lauf","Messwert","Zielwert","Abw. abs.","Abw. %","Anwender")
        notes = self.point_notes(points)
        footnote = f"Geeignet {self.series['included_count']}, ausgeschlossen {self.series['excluded_count']}; Datum ungeklärt {self.series['period']['unknown_date_count']}. * Nicht ausgewertet; … gekürzte Angabe."
        trailing_height = 6+sum(len(self.wrap(note, 523, 7))*10.5+4 for note in [footnote, *notes])+60
        def header():
            if self.y+24>790:
                self.new_page("measurement")
            self.page.draw_rect((36,self.y-8,559,self.y+9),color=None,fill=(1.0,0.80,0.36))
            x=36
            for title,width in zip(headings,widths):
                self.page.insert_text((x+3,self.y+3),title,fontname="qchead",fontsize=7.5)
                x+=width
            self.y+=13
        header()
        for index,point in enumerate(points):
            display=point["measurement"]
            date=self.date(display["date"]) if display["date"] else "ungeklärt"
            if display["time"]:
                date += " "+display["time"]
            matches=[row for row in self.source["population"] if _observation_match(row,point)]
            original=matches[0] if len(matches)==1 else {}
            run=original.get("run_group_raw") if self.profile.get("run_grouping_field") else None
            _date,_time,operator,_validator,_at=_point_display(self.source,point)
            deviation=point["deviation"]
            row=(str(point["position"])+( "*" if not point["eligible"] else ""),date,self.short(run,10),
                self.short(point["raw"].get("IST")),self.short(point["raw"].get("SOLL")),
                self.number(deviation["absolute"]["value"]) if deviation["absolute"]["available"] else "–",
                self.number(deviation["relative_percent"]["value"]) if deviation["relative_percent"]["available"] else "–",self.short(operator,28))
            cells=[self.wrap(value,width-6,7.5) for value,width in zip(row,widths)]
            height=max(14,max(map(len,cells))*9+3)
            remaining = (len(points)-index)*height+trailing_height if len(points)-index <= 3 else height
            if self.y+max(height, remaining)>790:
                self.new_page("measurement")
                header()
            self.page.draw_rect((36,self.y-3,559,self.y+height-3),color=(0.80,0.84,0.88),width=0.3,
                fill=(0.99,0.94,0.92) if not point["eligible"] else ((0.94,0.97,1.0) if index%2==0 else (0.91,0.95,0.98)))
            x=36
            for lines,width in zip(cells,widths):
                for line_index,text in enumerate(lines):
                    self.draw_text(x+3,self.y+5+line_index*9,text,size=7.5)
                x+=width
                self.page.draw_line((x,self.y-3),(x,self.y+height-3),color=(0.80,0.84,0.88),width=0.3)
            self.y+=height
        self.y+=6
        self.paragraph(footnote, size=7)
        for note in notes:
            self.paragraph(note, size=7)

    def signatures(self):
        self.keep_block(60)
        self.y+=4
        widths=(75,110,169,169)
        x=36
        for caption,width in zip(("Datum","Bearbeitet von","Unterschrift technische Prüfung","Unterschrift Laborleitung"),widths):
            self.page.draw_rect((x,self.y, x+width,self.y+43),color=(0.77,0.80,0.83),width=0.4)
            self.header_lines(caption,x+3,self.y+10,width-6,6.8)
            x+=width
        self.y+=49

    def evidence_table(self, rows):
        """Keep each compact identity row together and repeat its column labels."""
        widths = (25, 125, 248, 125)
        headings = ("Pos", "Punkt / Ergebnisstand", "Quellhash / Auswahlkennung", "Rohdatum / Rohzeit · Nachweise")

        def header():
            self.page.draw_rect((36, self.y-8, 559, self.y+16), color=None, fill=(0.94, 0.95, 0.97))
            x = 36
            for title, width in zip(headings, widths):
                self.header_lines(title, x+3, self.y, width-6, 7)
                x += width
            self.y += 23

        if self.y + 60 > 790:
            self.new_page("evidence")
        header()
        for index, row in enumerate(rows):
            columns = [self.wrap(value, width-6, 7) for value, width in zip(row, widths)]
            height = max(map(len, columns))*9+5
            if self.y + height > 790:
                self.new_page("evidence")
                header()
            self.page.draw_rect((36, self.y-6, 559, self.y+height-6), color=(0.80, 0.84, 0.88), width=0.3,
                fill=(0.98, 0.99, 1.0) if index % 2 == 0 else (1, 1, 1))
            x = 36
            for lines, width in zip(columns, widths):
                for line_index, text in enumerate(lines):
                    self.draw_text(x+3, self.y+line_index*9, text, size=7)
                x += width
            self.y += height
        self.y += 6

    def mandatory_evidence(self, points):
        """Bind full identities to positions; print identical evidence once by reference."""
        self.new_page("evidence")
        self.paragraph("Validierte Kit-Chargen-Auswertung · Eignung und menschliche Validierung sind getrennte Nachweise.", size=8)
        sd = self.series["sd"]
        self.paragraph("SD-Referenz: "+(_reference_description(sd) if sd["available"] else _reason(sd["reason"]))+
            ("." if sd["available"] else ". SD-Bänder und Westgard-Auswertung nicht verfügbar."), size=7.5)
        for key in ("mean", "sample_sd", "cv_percent"):
            metric = self.series["descriptive"][key]
            if not metric["available"]:
                self.paragraph({"mean":"Mittelwert", "sample_sd":"Empirische SD (n-1)", "cv_percent":"VK"}[key]+": "+_reason(metric["reason"]), size=7.5)
        self.paragraph("Diagrammlinien: "+"; ".join(f"{line['label']} = {line['value']} {self.series['unit']}" for line in self.series["chart"]["reference_lines"]), size=7)
        self.paragraph("Je Pos: Ergebnis-ID (Erg.), Revision (Rev.), Auswahl-ID (Ausw.), Validierungs-ID (V-ID), vollständiger Quellhash und Auswahlkennung. R = Rohwerte; V = Validierung; B = Befund; A = Anwender. Gruppen gelten ausschließlich für die angegebenen Positionen.", size=7)
        if not self.profile.get("run_grouping_field"):
            self.paragraph("Analysenlauf (extrahiert): Nicht erfasst", size=7)

        groups = {kind: {} for kind in ("R", "V", "B", "A")}
        rows, additions = [], []

        def group(kind, text, position):
            if text not in groups[kind]:
                groups[kind][text] = (f"{kind}{len(groups[kind])+1}", [])
            label, positions = groups[kind][text]
            positions.append(position)
            return label

        def raw(value):
            return str(value) if value is not None else "Nicht erfasst"

        def inline(value, width, lines, label, position):
            text = raw(value)
            if len(self.wrap(text, width, 7)) <= lines:
                return text
            additions.append((position, label, text))
            return f"Zusatz Pos {position}"

        for point in points:
            position, measured = point["position"], point["measurement"]
            _date, _time, operator, validator, validated_at = _point_display(self.source, point)
            original = [row for row in self.source["population"] if _observation_match(row, point)]
            original = original[0] if len(original) == 1 else {}
            run = original.get("run_group_raw") if self.profile.get("run_grouping_field") else None
            raw_values = "; ".join(f"Rohwert {key}: {raw(point['raw'].get(key))}" for key in ("IST", "SOLL", "MIN", "MAX"))
            raw_values += f"; Präzision: {measured['precision']}"
            if len(self.wrap(raw_values, 523, 7)) > 3:
                additions.append((position, "Vollständige Rohwerte", raw_values))
                raw_ref = f"R Zusatz Pos {position}"
            else:
                raw_ref = group("R", raw_values, position)
            validation = (f"Validiert durch: {validator}; Validiert am UTC: {validated_at}" if validated_at != "–"
                else f"Validierungsbindung fehlt: {validator}")
            validation_ref = group("V", validation, position)
            assessments = "Eignung: "+("Berücksichtigt" if point["eligible"] else "Ausgeschlossen")
            if point["reasons"]:
                assessments += " · "+"; ".join(_reason(reason) for reason in point["reasons"])
            for kind, label in (("manufacturer", "Hersteller"), ("single_value", "Einzelwert-Prozentgrenze")):
                finding = point["limit_findings"][kind]
                assessments += f"; {label}: {_STATUSES[finding['status']]}"
                if finding["reason"]:
                    assessments += " · "+_reason(finding["reason"])
            findings = self.point_findings(point)
            adverse = dict.fromkeys(f"Westgard {finding['rule']}: {_STATUSES[finding['status']]}"+
                (" · "+_reason(finding["reason"]) if finding["reason"] else "") for finding in findings if finding["status"] != "unavailable")
            if adverse:
                assessments += "; "+"; ".join(adverse)
            unavailable = sorted({finding["reason"] for finding in findings if finding["status"] == "unavailable"})
            if unavailable:
                assessments += "; Westgard nicht vollständig verfügbar: "+"; ".join(_reason(reason) for reason in unavailable)
            assessment_ref = group("B", assessments, position)
            operator_ref = group("A", "Anwender: "+operator, position)
            point_key = inline(point["point_key"], 119, 2, "Punkt", position)
            token = inline(point.get("selection_token"), 242, 2, "Auswahlkennung", position)
            date_time = inline(raw(measured["date_raw"])+" / "+raw(measured["time_raw"]), 119, 2, "Datum/Zeit Rohangabe", position)
            for field, label, reason in (("date_raw", "Datum Rohangabe", "measurement_date_invalid"),
                    ("time_raw", "Zeit Rohangabe", "measurement_time_invalid")):
                if reason in point["reasons"] and measured[field] is not None:
                    additions.append((position, label, raw(measured[field])))
            run_value = inline(run, 100, 1, "Analysenlauf (extrahiert)", position) if run is not None else "–"
            selection = point.get("selection_id") if point.get("selection_id") is not None else "Original"
            validation_id = point.get("validation_id") if point.get("validation_id") is not None else "fehlt"
            rows.append((str(position), f"{point_key}\nErg. {point['run_id']} · Rev. {point['revision_id']}\nAusw. {selection} · V-ID {validation_id}",
                f"{point['source_hash']}\n{token}", f"{date_time}\n{raw_ref} · {validation_ref} · {assessment_ref} · {operator_ref}\nLauf: {run_value}"))
        self.evidence_table(rows)

        self.keep_block(40)
        self.paragraph("Gebündelte Nachweise · Rohangaben und gebundene Validierungen ungekürzt", size=8)
        for records in groups.values():
            for text, (label, positions) in records.items():
                self.record_context = f"Nachweis {label} · Pos {_positions_label(positions)}"
                self.keep_block(25)
                self.paragraph(self.record_context+": "+text, size=7)
        for position, label, text in additions:
            self.record_context = f"Zusatz · Pos {position}"
            self.keep_block(25)
            self.paragraph(f"{self.record_context} · {label}: {text}", size=7)
        self.record_context = ""


def _observation_match(row,point):
    return all(row.get(key)==point.get(key) for key in ("run_id","revision_id","selection_id","selection_token","source_hash"))


def _positions_label(positions):
    spans, start, end = [], None, None
    for position in positions:
        if end is not None and position == end+1:
            end = position
        else:
            if start is not None:
                spans.append(str(start) if start == end else f"{start}–{end}")
            start = end = position
    if start is not None:
        spans.append(str(start) if start == end else f"{start}–{end}")
    return ", ".join(spans)


def _reference_description(sd):
    kind = "manuell festgelegte SD" if sd.get("kind") == "manual" else f"bestätigte eingefrorene Referenzserie, n = {sd.get('n')}"
    return f"Referenzart: {kind}; Mitte: {_CompactPDFWriter.number(sd['center'])}; SD: {_CompactPDFWriter.number(sd['sd'])}"


def _render_compact_model(fitz, analysis, *, include_explanations=False):
    model=analysis.to_dict()
    source,profile=model["source_manifest"],model["source_manifest"]["profile_snapshot"]
    with fitz.open() as document:
        writer=_CompactPDFWriter(fitz,document,analysis)
        for series in model["computed_series"]:
            writer.series=series
            writer.record_context=""
            if include_explanations:
                writer.new_page("primary")
            else:
                writer.start_level()
            writer.chart(series["chart"])
            writer.statistics()
            points=sorted((point for point in model["points"] if point["control_id"]==series["control_id"]),key=lambda point:point["position"])
            writer.measurement_table(points)
            writer.signatures()
            if include_explanations:
                writer.mandatory_evidence(points)
        if include_explanations:
            writer.new_page("evidence")
            writer.heading("Erläuterungen zur Auswertung")
            writer.paragraph("QMMA = sqrt(sum((IST - SOLL)^2) / n). Empirische SD verwendet n-1 und ist keine freigegebene SD-Referenz. VK = 100 × empirische SD / Mittelwert nur bei positivem Mittelwert. Abw. abs. = abs(IST-SOLL), Abw. % nur bei positivem SOLL.")
            writer.paragraph("Gleiche Messzeitpunkte werden nicht künstlich verbunden. Darstellungsnummern sind keine analytischen Laufnummern. Berechnete Anzeigewerte werden auf sechs signifikante Stellen gerundet; Rohwerte und Grenzentscheidungen bleiben ungerundet.")
            writer.paragraph(f"Analyseverfahren: {model['algorithm_id']} · Ursprüngliches PDF-Verfahren: {model['renderer_id']} · Druckverfahren: {RENDERER_ID}\nModell SHA-256: {analysis.model_sha256}\nQuellenmanifest: {source['source_token']}")
            writer.paragraph(model["references"]["report_scope"])
            writer.heading("Vollständige Regelbefunde")
            by_key = {point["point_key"]: point for point in model["points"]}
            def run_labels(run):
                labels = []
                for key in run["point_keys"]:
                    measured = by_key[key]["measurement"]
                    label = measured["date"] or "Datum ungeklärt"
                    if measured["time"]:
                        label += " " + measured["time"]
                    if label not in labels:
                        labels.append(label)
                return ", ".join(labels)
            rows=[(run_labels(run),finding["rule"],_STATUSES[finding["status"]],_reason(finding["reason"]) if finding["reason"] else "–")
                for run in model["analytical_runs"] for finding in run["findings"]]
            writer.table(("Messdatum / Messzeit","Regel","Befund","Grund"),rows,(145,50,120,208))
        for index,page in enumerate(document):
            page.insert_text((36,817),f"Seite {index+1} von {document.page_count} · Digitaler Nachweis: Modell {analysis.model_sha256[:16]}",fontname="qcfont",fontsize=7,color=(0.35,0.38,0.42))
        return document.tobytes(garbage=1,deflate=True)


def _render_model(fitz, analysis: QCAnalysis, *, include_explanations=False):
    if analysis.to_dict()["analysis_model_version"] == 3:
        return _render_compact_model(fitz,analysis,include_explanations=include_explanations)
    return _render_legacy_model(fitz,analysis,include_explanations=include_explanations)


def _render_legacy_model(fitz, analysis: QCAnalysis, *, include_explanations: bool = False) -> bytes:
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
            limit_lines = []
            if model["analysis_model_version"] == 2:
                for kind, label in (("manufacturer", "Herstellergrenzen"), ("single_value", "Einzelwert-Prozentgrenzen")):
                    limit_value = series["limits"][kind]
                    detail = f"{limit_value['lower']} bis {limit_value['upper']} {series['unit']}" if limit_value["available"] else _reason(limit_value["reason"])
                    percent = f" · {limit_value['percent']} % vom SOLL" if kind == "single_value" and limit_value["percent"] is not None else ""
                    limit_lines.append(f"{label}: {detail}{percent}.")
                limit_lines.append("Diagrammlegende: grün = SOLL; violett gestrichelt = Hersteller-MIN/MAX; orange = Einzelwert-Prozentgrenzen; graublau = SD. Orange Ringe markieren Grenzüberschreitungen; die Punktfarbe zeigt unabhängig den Westgard-Befund.")
            height = sum(len(writer.wrap(value, 490, 9)) * 13.5 + 4 for value in (summary, limit_text, sd_text))
            height += sum(len(writer.wrap(value, 490, 8)) * 12 + 4 for value in limit_lines)
            height += max(240, 210 + len(writer.wrap(chart_note, 490, 8)) * 12 + 4)
            writer.keep_block(height)
            writer.paragraph(summary)
            writer.paragraph(limit_text)
            writer.paragraph(sd_text)
            for value in limit_lines:
                writer.paragraph(value, size=8)
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
                if model["analysis_model_version"] == 2:
                    assessments = "; ".join(f"{label}: {_STATUSES.get(point['limit_findings'][kind]['status'], point['limit_findings'][kind]['status'])}"
                        for kind, label in (("manufacturer", "Hersteller"), ("single_value", "Einzelwert")))
                    if not point["eligible"]:
                        assessments += f"; Rohwerte SOLL {point['raw'].get('SOLL', '–')}, MIN {point['raw'].get('MIN', '–')}, MAX {point['raw'].get('MAX', '–')}"
                    reasons = (reasons + "; " if reasons else "") + assessments
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
