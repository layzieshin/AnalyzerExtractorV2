# AP-17A/17B: Feldversuch — portables Paket und Kurzanleitung

## Ziel

Der kanonische Onedir-/ZIP-Build liefert die Produkt-Shell (`test_app_main.py` →
`AnalyzerDesktopApp`) als portables Feldversuch-Paket fuer Windows-PCs **ohne
Python-Installation**.

Fenstertitel nach Start: **Analyzer Result Extractor** (Sidebar-Ansichten). Legacy-Tab-UI
nur mit `ARE_LEGACY_UI=1` (Titel **AREV2 Test-App**).

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

## Erster Start — Checkliste (Produkt-Shell)

### 1. App oeffnen

Doppelklick auf `AnalyzerResultExtractorV2.exe`. Ansicht **Einstellungen** pruefen.

### 2. Watch-Ordner setzen

Unter **Einstellungen** Eingabe- und Archivordner fuer Auto-Import setzen (Default:
`input/watch/` relativ zum App-Ordner). Ordner muessen existieren und lesbar sein.
Auto-Import aktivieren und Einstellungen speichern.

### 3. Gerät waehlen

In **Einstellungen** das Geraet waehlen (falls konfiguriert). Ohne Konfiguration gilt
der Runtime-Default (`DEFAULT_DEVICE`).

### 4. PDFs verarbeiten

Ansicht **Auswertung**:

| Aktion | Zweck |
|--------|-------|
| **PDFs auswählen** | Manuelle PDFs einreihen; die Verarbeitung startet automatisch |
| Auto-Import | Zyklischer Watch (nach Speichern der Einstellungen) |

Ergebnisse unter **Ergebnisse** (Berichte, Occurrences, PDF/Ausgabeordner oeffnen).
Klaerfaelle und Duplikat-Kandidaten unter **Diagnose**.

### 5. Regelwerke

Ansicht **Regelwerke**: Inventar, Integritaetspruefung, Rule Editor oeffnen.

Im **portablen Paket** startet der Rule Editor dieselbe `AnalyzerResultExtractorV2.exe`
neu mit `ARE_START_RULE_EDITOR=1` (intern gesetzt). Es gibt **keine** separate
Rule-Editor-EXE und auf dem Ziel-PC ist **kein Python** erforderlich.

Auf dem Entwicklungs-PC alternativ: `python rule_editor_main.py`.

## Fehlgeschlagene Jobs — Nacharbeit (Default-Produkt-Shell)

Wenn eine Verarbeitung fehlschlaegt (z. B. unbekannter Assay, fehlende Regeln):

1. Ansicht **Diagnose** oeffnen
2. Fehlgeschlagenen Vorgang in der Liste waehlen
3. **Details** — technische Diagnose und Assay-Kandidaten anzeigen
4. Kandidat waehlen, **Draft aus Kandidat** bestaetigen — legt bei Bedarf einen Draft an
5. Rule Editor oeffnen (aus **Regelwerke** oder nach Draft-Handoff; im Paket dieselbe EXE)
6. Draft bearbeiten, validieren, aktivieren (Entwicklungs-PC oder nach Rules-Update im Paket)
7. Zurueck in **Diagnose**: **Erneut verarbeiten** fuer den betroffenen Job

Hinweis: Erneutes Einreihen oder Auto-Import reaktiviert **FAILED**-Jobs nicht automatisch.

### Rule Editor — Lifecycle (Kurz)

Im Rule Editor (Inventar-Startseite **Regelwerke**):

- Inventar filtern: Alle / Aktiv / Drafts / Inaktiv
- Draft bearbeiten, validieren, **aktivieren**
- Aktive Rules: **Inaktivieren** statt loeschen
- Drafts/Inaktive: **Loeschen** archiviert nach `rules/trash/`

Nach Aktivierung neues Regelwerk ins Feldversuch-Paket kopieren (Rebuild) oder
`rules/` auf Ziel-PC aktualisieren (nur mit Bedacht, Index muss passen).

## Excel-Ausgabe nach gespeichertem Ergebnis

SQLite ist die strukturierte Ablage. Excel ist der nachgelagerte Export. Sind die Ergebnisdaten gespeichert und scheitert nur die Excel-Datei, zeigt Auswertung und Diagnose genau:

`Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen`

Die Fehlerart in **Diagnose** ist `Excel-Ausgabe`.

1. Ansicht **Diagnose** oeffnen und den Eintrag waehlen.
2. **Erneut verarbeiten** — das ist die vorhandene Diagnose-Aktion, kein zweiter Button.
3. Wiederholt wird nur die fehlgeschlagene Excel-Ausgabe aus dem eingefrorenen Plan. Die PDF und die aktuellen Regelwerke werden nicht neu gelesen. Das bereits gespeicherte SQLite-Ergebnis wird nicht erneut geschrieben.
4. Bleibt die Excel-Datei gesperrt, bleibt der Vorgang fehlgeschlagen und erneut ausfuehrbar. Nach erfolgreichem Export wird der Lauf `Fertig`. Watch-Importe werden erst dann archiviert.

`Excel-Ausgabe fehlgeschlagen` ohne den Zusatz „Ergebnis gespeichert“ bedeutet, dass keine strukturierte SQLite-Ablage fuer diesen Lauf vorliegt (reiner Excel-Modus oder SQLite war nicht erfolgreich). Auch dann ist **Erneut verarbeiten** die vorhandene Aktion; ohne versionierten Plan laeuft die Verarbeitung vollstaendig erneut.

## Duplikate und Ergebnisreview (Default)

- **Ergebnisse** — gespeicherte Berichte, Detailansicht, Occurrences
- **Diagnose** — ausstehende Duplikat-Kandidaten unter **Klärfälle (Duplikate)**: **Details**, Vergleich, bei Bedarf **Verwerfen**

Overwrite und Add fuer Duplikate sind nicht implementiert. Es gibt keine Aktion, die ein bestehendes Ergebnis ueberschreibt oder als zusaetzliche Messung anlegt.

## Wartung auf dem Ziel-PC

| Ordner | Inhalt |
|--------|--------|
| `jobs/` | Queue- und Pipeline-States |
| `output/final/` | Excel-Ausgaben |
| `rules/` | Aktive Regelwerke (nicht manuell editieren ohne Ruecksprache) |
| `input/watch/` | PDF-Eingang |

Bei Problemen: Ansicht **Diagnose** (Fehlerjobs, Klärfälle) und **Auswertung** (letzte Laeufe).
Technische Queue-Rohdaten nur in der Legacy-UI (`ARE_LEGACY_UI=1`, optional `ARE_SHOW_ADMIN=1`).

## LegacyTestApp — Support-Fallback

Nur bei Bedarf (Support/Vergleich):

```powershell
$env:ARE_LEGACY_UI = "1"
.\AnalyzerResultExtractorV2.exe
```

Tab-Workflow (**EXTRACTOR**, **OPTIONS**, **RULE SUITE**, **DUPLIKATE**, **DATENBANK**):
siehe `docs/AP14_TEST_APP.md` (Abschnitt LegacyTestApp).

## Abgrenzung

| Enthalten | Nicht enthalten |
|-----------|-----------------|
| Produkt-Shell (Auswertung, Ergebnisse, Regelwerke, Einstellungen, Diagnose) | Separater Watchdog-/Worker-Prozess aus der GUI |
| Rule Editor ueber dieselbe EXE (`ARE_START_RULE_EDITOR=1`) | Separate Rule-Editor-EXE |
| Aktive Rules, Runtime-Ordner | `rules/drafts/` aus Entwicklungs-PC im Bundle |
| Duplikat-Review (Anzeigen, Verwerfen) in Diagnose | Overwrite/Add fuer Duplikate |

Legacy Direktmodus (`gui_min.py`) ist nicht Teil des Feldversuch-Pakets.

Weitere Details: `docs/AP14_TEST_APP.md`, `README.md`, `DOCUMENTATION/10_headless_runbook.md`
