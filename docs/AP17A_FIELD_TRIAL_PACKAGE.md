# AP-17A/17B: Feldversuch — portables Paket und Kurzanleitung

## Ziel

Der kanonische Onedir-/ZIP-Build liefert die Test-App (`test_app_main.py`) als
portables Feldversuch-Paket fuer Windows-PCs **ohne Python-Installation**.

Fenstertitel nach Start: **AREV2 Test-App**

## Build (Entwicklungs-PC)

```powershell
cd I:\Projekte\AnalyzerResultExtractorV2
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe rules_validate_main.py
.\.venv\Scripts\python.exe packaging\build_onedir.py
```

## Artefakte

| Artefakt | Pfad |
|----------|------|
| Onedir | `packaging/dist_output/AnalyzerResultExtractorV2/` |
| ZIP | `packaging/dist_output/AnalyzerResultExtractorV2.zip` |

Bundle-Inhalt:

- `AnalyzerResultExtractorV2.exe` (Entry: `test_app_main.py`)
- `_internal/` (PyInstaller-Runtime)
- `rules/` inkl. `index.json` (**ohne** `rules/drafts/`)
- leere Ordner: `jobs/`, `output/final/`, `input/watch/`

Optional mitkopiert, falls vorhanden: `rules/inactive/`, `rules/trash/`.

Smoke ohne GUI (wird im Build automatisch ausgefuehrt):

```powershell
$env:ARE_HOME = "I:\Pfad\zum\AnalyzerResultExtractorV2"
$env:ARE_SMOKE_EXIT = "1"
.\AnalyzerResultExtractorV2.exe
```

## Deployment auf Ziel-PC

1. `AnalyzerResultExtractorV2.zip` kopieren (USB, Netzlaufwerk, RDP)
2. In einen **beschreibbaren** Ordner entpacken, z. B. `D:\Apps\AnalyzerResultExtractorV2\`
3. `AnalyzerResultExtractorV2.exe` starten

Optional festen App-Root setzen:

```powershell
$env:ARE_HOME = "D:\Apps\AnalyzerResultExtractorV2"
.\AnalyzerResultExtractorV2.exe
```

Ohne `ARE_HOME` ist der App-Root das Verzeichnis der EXE.

## Erster Start — Checkliste

### 1. App oeffnen

Doppelklick auf `AnalyzerResultExtractorV2.exe`. Tab **OPTIONS** pruefen.

### 2. Watch-Ordner setzen

Unter **OPTIONS** den Pfad zum PDF-Eingangsordner einstellen (Default:
`input/watch/` relativ zum App-Ordner). Ordner muss existieren und lesbar sein.

### 3. Gerät waehlen

In **OPTIONS** das Geraet aus `config/devices.json` waehlen (falls konfiguriert).
Ohne Konfiguration gilt der Runtime-Default (`DEFAULT_DEVICE`).

### 4. Arbeitsliste fuellen

Tab **EXTRACTOR**:

| Aktion | Zweck |
|--------|-------|
| **Ergebnisse suchen** | PDFs aus Watch-Ordner in Arbeitsliste uebernehmen |
| **Dateien hinzufuegen** | Einzelne PDFs manuell vormerken |
| **Automatische Suche starten** | Zyklischer Scan des Watch-Ordners (In-App) |

Die Arbeitsliste ist Source of Truth. Gleiche PDFs werden dedupliziert.

### 5. Extraktion starten

**Extraktion starten** verarbeitet wartende Jobs. Ergebnisse landen unter
`output/final/` (Excel) und ggf. SQLite (je nach `output_mode` in OPTIONS).

**Aktualisieren** zeigt Queue-Status; technische Details auch im Tab **ADMIN**.

## Fehlgeschlagene Jobs — Nacharbeit

Wenn ein Job **fehlgeschlagen** ist (z. B. unbekannter Assay, fehlende Regeln):

1. Tab **RULE SUITE** (Nacharbeit) oeffnen
2. Fehlgeschlagenen Job in der Nacharbeitsliste waehlen
3. **Assay-Kandidaten** anzeigen lassen (read-only Erkennung aus normalisiertem Dump)
4. **Draft aus Kandidat erstellen** oder Felder aus bestehendem Regelwerk uebernehmen
5. Rule Editor starten (`rule_editor_main.py` — nur auf Entwicklungs-PC mit Python,
   oder Draft-Datei unter `rules/drafts/` auf Entwicklungs-PC bearbeiten und Rules
   ins Paket neu bauen)

### Rule Editor auf Entwicklungs-PC

```powershell
python rule_editor_main.py
```

Im Draft-Tab **Regelwerk-Verwaltung**:

- Inventar filtern: Alle / Aktiv / Drafts / Inaktiv
- Draft bearbeiten, validieren, **aktivieren**
- Aktive Rules: **Inaktivieren** statt loeschen
- Drafts/Inaktive: **Loeschen** archiviert nach `rules/trash/`

Nach Aktivierung neues Regelwerk ins Feldversuch-Paket kopieren (Rebuild) oder
`rules/` manuell auf Ziel-PC aktualisieren (nur mit Bedacht, Index muss passen).

### Job erneut starten

Zurueck in der Test-App, Tab **EXTRACTOR**:

1. Fehlgeschlagenen Job in der Arbeitsliste waehlen
2. **Erneut starten** — setzt den Job explizit auf `Wartet`
3. **Extraktion starten**

Hinweis: Erneutes Suchen/Hinzufuegen reaktiviert **FAILED**-Jobs nicht automatisch.

## Duplikate

Tab **DUPLIKATE** listet SQLite-Duplicate-Kandidaten. Vergleich anzeigen, bei Bedarf
Kandidat **verwerfen**. Overwrite/Add/Excel-Recovery sind noch nicht implementiert.

## Wartung auf dem Ziel-PC

| Ordner | Inhalt |
|--------|--------|
| `jobs/` | Queue- und Pipeline-States |
| `output/final/` | Excel-Ausgaben |
| `rules/` | Aktive Regelwerke (nicht manuell editieren ohne Ruecksprache) |
| `input/watch/` | PDF-Eingang |

Bei Problemen: Tab **LOGS** und **ADMIN** pruefen.

## Abgrenzung

| Enthalten | Nicht enthalten |
|-----------|-----------------|
| Test-App (Arbeitsliste, Queue-Worker-Logik) | Separater Watchdog-/Worker-Prozess |
| Aktive Rules, Runtime-Ordner | Rule Editor als EXE |
| Duplikat-Review (Verwerfen) | `rules/drafts/` aus Entwicklungs-PC |

Legacy Direktmodus (`gui_min.py`) ist nicht Teil des Feldversuch-Pakets.

Weitere Details: `docs/AP14_TEST_APP.md`, `README.md`, `DOCUMENTATION/10_headless_runbook.md`
