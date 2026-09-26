# Working Agreement – Phase 0: Architektur & Setup

## Zweck
Verbindliche Architektur- und Projektgrundlage für alle weiteren Phasen.
Alles Nicht-Geschriebene gilt als nicht garantiert.

## Verbindliche Entscheidungen
- Serielle, crash-sichere Verarbeitung
- Job-ID = Hash des PDF-Dateiinhalts
- DONE + gleiche Job-ID => Skip
- Multi-Assay PDFs werden unterstützt und getrennt verarbeitet
- Pro Assay eine Excel-Datei
- Pro Lot ein Sheet
- Pro Analysenlauf eine Zeile
- Append-only + Dedupe
- Dedupe-Key: test|YYYY-MM-DD|HH:MM:SS
- Assay-Erkennung: contains(assay_name) (MVP)
- Ziel-OS: Windows 11

## Projektstruktur (bindend)

src/
  jobcontroller/
  parser/
  normalizer/
  assaychooser/
  ruleresolver/
  extractor/
  writer/

tests/
rules/
input/
output/
locks/
jobs/

## Nicht-Ziele
- Keine Implementierung
- Keine UI/CLI
- Keine Optimierungen
