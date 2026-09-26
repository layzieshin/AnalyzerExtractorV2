# KI-Handoff-Protokoll

> **Zweck:** Übergabe eines Entwicklungsstandes an **menschliche Entwickler und KI-Agenten**.  
> Dieses Dokument ist **normativ**: Alles Nicht-Geschriebene gilt als **nicht garantiert**.

---

## 0. Meta

- **Handoff-ID:** PHASE-0-PDF-EXTRACTOR
- **Projekt:** PDF Ergebnis-Extractor
- **Komponente / System:** Gesamtarchitektur & Projekt-Setup
- **Phase / Scope:** Phase 0 – Setup, Architektur, Verträge
- **Stand:** ACCEPTED
- **Gültig ab:** 2026-01-28
- **Gültig bis:** unbegrenzt (bis explizite Revision)
- **Referenz-Regelwerk / Dev Guide:** Contract-First, Phase-Isolation, SRP, MVC (verbindlich)
- **Erstellt von:** Software-Planungs-Coach
- **Letzte Änderung:** 2026-01-28

---

## 1. Ziel & Nicht-Ziel (verbindlich)

### Ziel

- Festlegung einer **vollständigen, stabilen Architektur- und Projektbasis**
- Definition aller **globalen Designentscheidungen**, die für alle Folgephasen bindend sind
- Sicherstellung von deterministischem Verhalten, Crash-Sicherheit und klarer Verantwortlichkeit
- Übergabe eines Zustands, auf dem **implementiert werden darf**

### Nicht-Ziele

- Keine Implementierung von Fachlogik
- Keine UI/CLI-Definition
- Keine Optimierungen (Performance, Parallelität)
- Keine Assay-spezifischen Regelwerke

---

## 2. Übergabe-Garantie

Mit diesem Handoff wird garantiert:

- ☑ Der beschriebene Stand ist **architektonisch konsistent**
- ☑ Der Stand ist **deterministisch reproduzierbar**
- ☑ Die beschriebenen Artefakte und Regeln sind **prüfbar**
- ☑ Darauf aufbauende Phasen **dürfen implementiert werden**

Nicht garantiert wird alles, was hier **nicht explizit aufgeführt** ist.

---

## 3. Aktueller Ist-Zustand

### 3.1 Implementierte Komponenten

| Komponente | Verantwortlichkeit | Pfad / Modul | Status |
|-----------|-------------------|--------------|--------|
| Architektur | Gesamtstruktur & Verträge | Dokumentation | STABLE |
| Projektstruktur | Ordner- & Modulkonvention | Repo / src | STABLE |
| Sample Inputs | Testgrundlage | input/ | STABLE |

> Hinweis: Es existiert **keine fachliche Implementierung**.

---

### 3.2 Öffentliche Contracts / Datenobjekte

| Contract | Typ | Stabilität | Quelle |
|--------|-----|------------|--------|
| ParsedDocument | Datenobjekt | STABLE | Architektur |
| AssayMatch | Datenobjekt | STABLE | Architektur |
| RuleSet | Datenobjekt | STABLE | Architektur |
| RunRow | Datenobjekt | STABLE | Architektur |
| JobState | Datenobjekt | STABLE | Architektur |

---

## 4. Explizite Designentscheidungen

Diese Entscheidungen gelten ab Übergabe als **bindend**:

- Verarbeitung ist **seriell**, aber **crash-sicher**
- **Job-ID = Hash des PDF-Dateiinhalts**
- Existiert `job_state = DONE` → Job wird **übersprungen**
- PDFs dürfen **mehrere Assays** enthalten → getrennte Verarbeitung
- Excel-Modell:
  - pro Assay **eine Excel-Datei**
  - pro Lot **ein Sheet**
  - pro Analysenlauf **eine Zeile**
- Schreiben ist **append-only**
- Deduplikation über `(test, date, time)`
- Assay-Erkennung: `contains(assay_name)` (MVP, änderbar)
- Parser arbeitet **positional / line-basiert**
- Normalizer entfernt nur **Whitespace innerhalb von Zeilen**
- Ziel-OS: **Windows 11**

---

## 5. Abweichungen vom Regelwerk

| Regel | Abweichung | Begründung | Rückbaubar |
|------|-----------|-----------|------------|
| – | keine | – | – |

---

## 6. Stabil vs. Änderbar

### 6.1 Stabil (nicht ohne Analyse ändern)

- Job-ID-Strategie
- Excel-Zielstruktur (Assay-Datei / Lot-Sheet / 1 Zeile pro Run)
- Append-only + Dedupe-Prinzip
- Modul- & API-Regeln (`src/<modul>/api.py`)
- Sample-PDFs als Referenzbasis

### 6.2 Änderbar / offen

- Assay-Matching-Strategie (`contains` → präziser)
- Assay-spezifische Regelwerksinhalte
- Segment-basierte Extraktion
- UI / CLI

---

## 7. Tests & Reproduzierbarkeit

### 7.1 Tests

| Test | Typ | Pfad | Status |
|-----|----|------|--------|
| Parser Smoke | manuell / später auto | tests/ | PENDING |
| Single-Assay | funktional | sample_single.pdf | PENDING |
| Multi-Assay | funktional | sample_multi.pdf | PENDING |

### 7.2 Reproduktion

```text
Input:
- input/sample_single.pdf
- input/sample_multi.pdf

Erwartung:
- stabile Parser-Ausgabe
- korrekte Assay-Erkennung
```

---

## 8. Artefakte & Outputs

| Artefakt | Pfad | Zweck | Persistenz |
|--------|-----|------|------------|
| sample_single.pdf | input/ | Testbasis | dauerhaft |
| sample_multi.pdf | input/ | Testbasis | dauerhaft |
| rules/index.json | rules/ | Assay-Mapping | dauerhaft |
| jobs/*.json | jobs/ | Job-State | laufzeitabhängig |
| output/final/*.xlsx | output/ | Ergebnisse | dauerhaft |

---

## 9. Failure Modes & bekannte Risiken

### 9.1 Definierte Failure States

- PDF nicht lesbar → FAILED
- Kein Assay erkannt → FAILED
- Regelwerk ungültig → FAILED
- Pflichtfelder fehlen → FAILED

### 9.2 Bekannte Risiken

- `contains(assay_name)` kann False-Positives erzeugen
- Excel-Dedupe hängt von Datenqualität (Datum/Zeit/Test) ab

---

## 10. Nächster empfohlener Schritt

**Phase 1 – Parser**

- Implementierung des positional Parsers gemäß Vertrag
- Tests gegen sample_single.pdf und sample_multi.pdf
- Keine Normalisierung, keine Fachlogik

---

## 11. Integrations-Check (KI-tauglich)

1. ☑ Ziel & Nicht-Ziel explizit
2. ☑ Klare Orchestrierungsstelle
3. ☑ Strikte Verantwortlichkeitstrennung
4. ☑ Öffentliche Contracts definiert
5. ☑ Keine stillen Contract-Änderungen
6. ☑ Deterministisches Verhalten
7. ☑ Explizite Failure-States
8. ☑ Reproduzierbare Artefakte
9. ☑ Phase isoliert prüfbar
10. ☑ Übergabe an nächste Phase möglich

---

## 12. Abnahme / Sign-off

- **Übergeben von:** Software-Planungs-Coach
- **Übernommen von (Mensch / KI):** —
- **Datum:** 2026-01-28
- **Status:** ACCEPTED

---

> **Leitregel:** Alles, was nicht eindeutig aus diesem Dokument ableitbar ist, gilt als **nicht Teil der Übergabe**.

