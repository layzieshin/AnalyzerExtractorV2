# PDF Ergebnis-Extractor (Projekt)

- Projektversion: **2.0.0**; aktueller Prüf-/Freigabestand unter `docs/TESTBASELINE.md`
- Windows 11 Zielumgebung
- `src/` ist Project Root (in PyCharm markieren)
- Public APIs existieren ausschließlich in `src/<module>/api.py`
- `api.py` ist die stabile Public Boundary; Implementierungsdetails bleiben hinter `src/<module>/api.py`
- Root-Entrys delegieren nur noch in `interfaces/cli` oder `interfaces/headless`
- `main.py` und `main02.py` sind Harnesses für den End-to-End Lauf (immer `sample_single.pdf` + `sample_multi.pdf`)
- Tests liegen unter `/tests` (pytest)

## Start

### Feldversuch / Produkt-UI (empfohlen)

```powershell
python test_app_main.py
```

Startet die **Analyzer Result Extractor** Desktop-Oberfläche (Sidebar mit Auswertung, Ergebnisse, Statistik, Validierung, Regelwerke, Einstellungen, Diagnose). Primärer Workflow: PDFs verarbeiten, Auto-Import konfigurieren, Ergebnisse und Klärfälle prüfen, Regelwerke validieren.

In **Ergebnisse** werden alle Assays eines Berichts gemeinsam angezeigt. Einzelne Runs können
mit lokal gespeicherten Operator-Initialen und einem optionalen Kommentar validiert werden.
Eine bestehende Validation wird nie still überschrieben: Die separate Aktion
**Validierung korrigieren** legt nach Bestätigung einen neuen, verknüpften Historieneintrag an.
SQLite ist die verbindliche Ablage für neue Ergebnisse und append-only Validierungen. In **Validierung** stehen das Original-PDF und die Arbeitsliste nebeneinander. Neue Verarbeitung, Erstvalidierung und Korrektur erzeugen oder ändern keine Excel-Dateien. Vorhandene Arbeitsmappen und historische Ausgabepläne bleiben unverändert und lesbar. Historische Excel-Fehler haben in **Diagnose** keine Wiederholungsaktion.

Assay-Tabellen zeigen den vollständigen gespeicherten Namen. Die ausgewählte Ergebnisfassung bestimmt den Namen; eine noch offene Neuanalyse ersetzt ihn nicht. Fehlt ein belegter Name, steht dort **Assayname fehlt**. Auch gleichnamige Assays bleiben getrennt auswählbar. Bei unbekannten Kandidaten ist ein aus der Datei abgeleiteter **Namenshinweis** ausdrücklich als solcher gekennzeichnet.

### Qualitätskontrolle und PDF-Nachweise

Ist die Uhrzeit getrennt extrahiert, können im bestehenden Prüfprofil **Messzeitfeld (optional)** und **Zeitformat** ausdrücklich zugeordnet werden, etwa `ZEIT` mit `%H:%M` oder `%H:%M:%S` (auch `%H%M` ist möglich). Beide Felder bleiben zunächst leer. Ohne Zuordnung gilt der bisherige Datumsweg; bei Zuordnung muss das Datumsformat ohne Uhrzeit sein. Fehlende, unlesbare oder formatwidrige Messzeiten werden mit Grund ausgeschlossen, ohne Ersatz durch Mitternacht oder Importzeit. Gleiche tatsächliche Zeitpunkte bleiben ohne erfundene Reihenfolge. Jede Änderung legt eine neue Profilfassung an; alte Profile und PDF-Nachweise bleiben erhalten.

In **Einstellungen** werden Geräte und benannte Kontrollprofile gepflegt. **Geräte übernehmen** überführt vorhandene Altgeräte ausdrücklich in den ausgewählten SQLite-Speicher; Originaldateien und historische Kennungen bleiben erhalten. Ein verwendbares Gerät braucht einen Namen und mindestens SN, LNR oder EVA. Ein Profil ordnet dem Assay die extrahierten Messdatums- und Kontrollfelder IST/SOLL/MIN/MAX zu und legt Zahlenformat, Einheit, relative QMMA-Grenze und Westgard-Regeln fest. Änderungen erhalten die früheren Fassungen.

Unter **Statistik** werden Kit-Chargen und ihre menschlich validierten Quellen geprüft. Die Kontrollauswahl zeigt QMMA, optionale SD, Befunde und ein Diagramm mit anklickbaren Messpunkten, Vergrößern und Verschieben. QMMA braucht keine SD. Ohne verwendbare SD sind SD-Bänder und Westgard ausdrücklich nicht verfügbar. Eine manuelle SD oder eine bestätigte validierte Referenzserie wird beim Einrichten der Charge eingefroren; Referenzserien liefern Mittelwert und Stichproben-SD. Gleichdatierte Werte ohne belegte zeitliche Reihenfolge werden nicht künstlich zu einer Messfolge verbunden. Das klassische 2-SD-Prüfsignal bleibt aktiv; die Auswahl **1₂s** steuert die Warnanzeige.

Eine SD-Referenz muss zur belegten Messwertdefinition und Einheit gehören. Bei einer anderen Einheit, IST-Feldzuordnung oder Zahlenschreibweise wird die alte SD mit sichtbarem Grund gesperrt; QMMA bleibt unabhängig verfügbar. Eine bewusst neu eingegebene manuelle SD erhält den Bezug zum aktuellen Profil. Reine Namensänderungen sowie Datums-, Regel-, SOLL- oder MIN/MAX-Anpassungen sperren eine ansonsten passende SD nicht. Nicht belegbare Alt-Referenzen werden nicht umgedeutet; frühere PDF-Nachweise bleiben unverändert.

**Mit PDF abschließen** verlangt eine bewusst gewählte neuere validierte Nachfolgecharge. Analyse und PDF werden gemeinsam als unveränderlicher Nachweis gespeichert. Jede Kontrolle beginnt auf einer eigenen Seite mit Diagramm, kompakten Kennzahlen und ausschließlich ihren Einzelwerten: Messwert, Datum, tatsächlich erfasste Uhrzeit, Anwender und menschlicher Validierer samt Validierungszeit in UTC. Lange Tabellen werden für dieselbe Kontrolle fortgesetzt. Ohne erfasste Uhrzeit steht **Nicht erfasst**; fehlende oder widersprüchliche Anwender-/Validierungsnachweise werden sichtbar benannt. Anwender und Validierer werden nicht aus den Initialen des Chargenabschlusses abgeleitet.

**Nachweisfassungen** zeigt frühere Auswertungen. **PDF speichern** exportiert standardmäßig deren ursprüngliche Bytes an einen neuen Dateinamen. Die zunächst ausgeschaltete Option **Erläuterungen zur Diagrammauswertung mitdrucken** erstellt zusätzlich eine erweiterte Druckfassung aus dem gespeicherten Analysemodell. Legenden, Interpretation und Verfahrensdetails stehen nur in deren Anhang; gespeicherte Nachweise und Berechnungen bleiben unverändert. Bestehende Dateien werden nicht überschrieben. Späte Messwerte benötigen eine begründete Wiederöffnung; alte Nachweise bleiben lesbar. Der Bericht heißt **Validierte Kit-Chargen-Auswertung** und ist kein Nachweis vollständiger Rili-BÄK-Konformität. Die statistischen Befunde verändern keine menschliche Ergebnisvalidierung.

Alltagstauglicher Ablauf: `DOCUMENTATION/13_ui_v21_user_workflow.md`.

Details: `docs/AP14_TEST_APP.md`, Feldversuch-Paket: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`

Legacy-Tab-UI (EXTRACTOR/OPTIONS/…) nur bei Bedarf:

```powershell
$env:ARE_LEGACY_UI = "1"
python test_app_main.py
```

`ARE_SHOW_ADMIN=1` gilt nur für die Legacy-UI (optionaler ADMIN-Tab). Rule Editor: Regelwerke-Ansicht oder `rule_editor_main.py`.

### Rule Editor

```powershell
python rule_editor_main.py
```

Visueller Regelwerk-Editor inkl. Inventar, Drafts, Nacharbeit und Lifecycle (Aktiv / Draft / Inaktiv).

### Headless Dauerbetrieb

```powershell
python watchdog_main.py
python worker_main.py
```

Optional nur ein Durchlauf:

```powershell
$env:ARE_WATCHDOG_ONCE="1"; python watchdog_main.py
$env:ARE_WORKER_ONCE="1"; python worker_main.py
```

Runbook: `DOCUMENTATION/10_headless_runbook.md`

### Headless Phase 2 (Watchfolder + Archiv)

- Watch ist **standardmaessig deaktiviert** (`watch_enabled=false` in `storage/desktop_settings.json`).
- Vor dem Watchdog: `watch_enabled=true` sowie gueltige `watch_input_path` und `watch_backup_path` setzen.
- Isolierter Laufzeit-Root: `$env:ARE_HOME = "I:\pfad\zum\isolierten-home"` (leere `jobs/`, `input/`, `output/`, `storage/` werden bei Bedarf angelegt).
- **Produktion:** `watchdog_main.py` und `worker_main.py` dauerhaft parallel (kontinuierlicher Scan + Queue-Verarbeitung).
- **One-Shot Watchdog** (`ARE_WATCHDOG_ONCE=1`): fuehrt Stabilitaetsbeobachtungen aus; enqueued erst nach konfiguriertem Stabilitaetsfenster.
- **One-Shot Worker** (`ARE_WORKER_ONCE=1`): verarbeitet **einen** wartenden Job; zum Leeren der Queue wiederholt starten.
- Erfolgreiche Queue-Jobs (`DONE`) werden archiviert; `FAILED` wird **nicht** archiviert.
- Manuell hinzugefuegte PDFs werden **nie** automatisch verschoben (nur Watchfolder-Importe).

### Legacy Direktmodus (Alt-/Smoke-UI)

```powershell
python gui_min_ext.py
python gui_min.py
```

Direkter `submit`-Pfad ohne Queue/Arbeitsliste. Nicht mehr der Packaging-Entry; nur noch für Entwicklung und Smoke.

### Entwicklung / CLI-Harness

1. Lege PDFs ab:
   - `input/sample_single.pdf`
   - `input/sample_multi.pdf`
2. Pflege `rules/index.json` und die referenzierten RuleSet JSONs unter `rules/`
3. Install:
   - `pip install -r requirements.txt`
   - optional für Embedding-Entwicklung: `pip install -e .`
4. Run:
   - `python main02.py` (empfohlen für bessere CLI-Übersicht)

## Headless Betrieb

- Watchdog dauerhaft starten:
  - `python watchdog_main.py`
- Worker dauerhaft starten:
  - `python worker_main.py`
- Optional nur ein Durchlauf:
  - `$env:ARE_WATCHDOG_ONCE="1"; python watchdog_main.py`
  - `$env:ARE_WORKER_ONCE="1"; python worker_main.py`

## Ausgabe (SQLite)

- Effektiver Modus für alle neuen Wege ist `sqlite`: Desktop, Watch/Worker, CLI-Harness und direktes `submit`.
- `ARE_OUTPUT_MODE=both|excel` und alte gleichnamige Caller-/Settings-Werte bleiben als Kompatibilitätseingaben akzeptiert; sie aktivieren ausschließlich SQLite. Unbekannte Environment-/Worker-Werte fallen sicher auf SQLite zurück; unbekannte direkte `submit`- und Desktop-Settings-Werte werden abgewiesen.
- Das Laden alter Einstellungen schreibt die Datei nicht um. Erst normales **Speichern** persistiert `output_mode=sqlite` und erhält die übrigen Einstellungen.
- Historische Exportpläne werden weder migriert noch fortgesetzt oder automatisch abgeschlossen. Die alten Release-/Excel-Retry-APIs liefern ohne Schreibzugriff `SKIPPED: excel_export_retired`.
- SQLite-Zielpfad:
  - `ARE_SQLITE_PATH=I:/path/to/results.sqlite3`
- Queue/Pipeline Recovery:
  - `ARE_QUEUE_PROCESSING_TTL_S=300`
  - `ARE_QUEUE_CLAIM_LOCK_TTL_S=120`
  - `ARE_QUEUE_MAX_ATTEMPTS=5`
  - `ARE_PIPELINE_LOCK_TTL_S=900`
- SQLite Robustheit:
  - `ARE_SQLITE_BUSY_TIMEOUT_MS=5000`
  - `ARE_SQLITE_RETRY_COUNT=3`
  - `ARE_SQLITE_RETRY_SLEEP_S=0.2`
- Das lokale Operator-Kürzel für die Ergebnisvalidation wird in der Produkt-UI unter
  **Einstellungen** gepflegt (`operator_initials` in `storage/desktop_settings.json`).
- Invalide Läufe blockieren:
  - `ARE_REJECT_INVALID_RUNS=1` (Default)

## LegacyTestApp / Support-Fallback (nur mit ARE_LEGACY_UI)

Die tabbed **LegacyTestApp** (`TestApp`) ist kein Default mehr. Sie bleibt für Support, Vergleich und historische Bedienpfade verfügbar:

```powershell
$env:ARE_LEGACY_UI = "1"
python test_app_main.py
```

Fenstertitel: **AREV2 Test-App**. Optionaler Support-Tab **ADMIN** (technische Queue-Rohdaten) — **nur in der Legacy-UI**:

```powershell
$env:ARE_LEGACY_UI = "1"
$env:ARE_SHOW_ADMIN = "1"
python test_app_main.py
```

Legacy-Standard-Tabs: **EXTRACTOR**, **OPTIONS**, **RULE SUITE**, **LOGS**, **DUPLIKATE**, **DATENBANK**.

In der Legacy-UI ist die **Arbeitsliste** Source of Truth. PDFs werden als Queue-Jobs vorgemerkt und über dieselbe Worker-Logik wie der Headless-Betrieb verarbeitet.

GUI-Inventar und IA-Vorschlag (Legacy-Kontext): `docs/GUI_USER_FUNCTIONS_INVENTORY.md`, `docs/GUI_IA_PROPOSAL.md`.

Details: `docs/AP14_TEST_APP.md` (Abschnitt LegacyTestApp).

### Legacy: EXTRACTOR

- **Ergebnisse suchen** — PDFs aus dem Watch-Ordner in die Arbeitsliste übernehmen (optional rekursiv)
- **Dateien hinzufügen** — manuell gewählte PDFs vormerken
- **Automatische Suche** — zyklischer In-App-Scan des Watch-Ordners (Watchdog light, ohne separaten Prozess)
- **Extraktion starten** — wartende Jobs verarbeiten
- **Fehler erneut verarbeiten** — ausgewählte fehlgeschlagene Jobs explizit auf `Wartet` setzen (`retry_failed_job`)

Fehlgeschlagene Jobs werden durch erneutes Suchen/Hinzufügen **nicht** automatisch reaktiviert.

### Legacy: Nacharbeit (RULE SUITE)

Für fehlgeschlagene Läufe mit normalisiertem Dump (nur Legacy-UI):

- **Nacharbeit wiederholen** — ausgewählte fehlgeschlagene Jobs erneut in die Queue stellen
- Assay-Kandidaten anzeigen (read-only Erkennung)
- Draft aus Kandidat erstellen
- Felder aus bestehendem Regelwerk übernehmen
- Rule Editor öffnen, Draft bearbeiten, aktivieren, Job erneut starten

### Legacy: Duplikate

Tab **DUPLIKATE** (nur Legacy-UI) listet SQLite-Duplicate-Kandidaten, zeigt Vergleich und unterstützt manuelles Verwerfen.

## Rule Suite

### Rule Editor (empfohlen)

```powershell
python rule_editor_main.py
```

Editor-Funktionen (Auszug):

- Inventar als Startseite und dreispaltiger Arbeitsbereich: Feldliste, Beispielbericht, Feldeinstellungen
- Geführter Anlage-Wizard, Regex-Bibliothek, Markierungs-Ansicht, Undo/Redo und Auto-Save; seltene Funktionen unter `Erweiterte Optionen`
- Draft-vs-Active-Diff vor Aktivierung

### Inventar und Lifecycle (AP-16C / AP-16D)

Auf der Inventar-Startseite **Regelwerke**:

| Typ | Bedeutung |
|-----|-----------|
| **Aktiv** | produktiv in `rules/index.json` referenziert |
| **Draft** | Arbeitsstand unter `rules/drafts/` |
| **Inaktiv** | deaktiviert unter `rules/inactive/` |

Wichtige Aktionen:

- **Inaktivieren** — aktives Regelwerk aus dem Index entfernen, Datei nach `rules/inactive/` verschieben (kein direktes Löschen aktiver Rules)
- **Löschen** — nur für Drafts und Inaktive nach `rules/trash/`
- **Als Basis für Draft verwenden / klonen** — sicheres Ableiten ohne Überschreiben
- **Draft aus Kandidat** — Nacharbeit aus normalisiertem Dump
- **Format übernehmen** — Felder aus bestehendem Regelwerk in Draft übernehmen

Inaktive Regelwerke werden nicht direkt bearbeitet; stattdessen Kopie nach `rules/drafts/`.

### CLI (optional)

- Draft erstellen: `python rule_suite_main.py create-draft --assay-key "(6bd7)"`
- Felder anzeigen: `python rule_suite_main.py list-fields --assay-key "(6bd7)"`
- Preview: `python rule_suite_main.py preview --pdf input/sample_single.pdf --assay-key "(6bd7)" --draft-path <path>`

## Rules-Integrität prüfen

- `python rules_validate_main.py`

## Rule-/Pipeline-Matrix (Testbetrieb)

- Funktionaler Preview-Check gegen aktive Rulesets und Sample-PDFs:
  - `python rules_matrix_main.py --mode preview`
- Voller E2E-Modus inkl. Write-Pfad:
  - `python rules_matrix_main.py --mode e2e`
- Ergebnisdateien liegen unter `output/verification/`.
- Aktueller Testbetrieb:
  - Baseline: `docs/TESTBASELINE.md`
  - Dedupe-Policy: `docs/DEDUPE_POLICY.md`
  - Known Issues: `docs/KNOWN_ISSUES.md`

## Tests

- `pytest -q`

## Architektur / Embedding

- Architekturüberblick: `docs/ARCHITECTURE.md`
- Embedding/Public API: `docs/EMBEDDING.md`
- Root-Wrapper delegieren auf:
  - `interfaces/cli/`
  - `interfaces/headless/`
  - `interfaces/tk/` (Produkt-Shell `AnalyzerDesktopApp`; Legacy `LegacyTestApp`)

## Build (Feldversuch-Paket)

Kanonischer portabler Build für Windows ohne Python auf dem Ziel-PC:

```powershell
python packaging/build_onedir.py
```

Ausgabe:

| Artefakt | Pfad |
|----------|------|
| Onedir | `packaging/dist_output/AnalyzerResultExtractorV2/` |
| ZIP | `packaging/dist_output/AnalyzerResultExtractorV2.zip` |

Entry der gebündelten EXE: `test_app_main.py` (Produkt-Shell, nicht mehr `gui_min.py`).

Der Builder prüft zuerst die vollständige Testsuite und beendet sich bei Fehlern vor Bereinigung oder Build. Die Produktversion stammt aus `pyproject.toml`; `build-info.json` neben der EXE dokumentiert Version, tatsächlichen Ausgangscommit/Arbeitsbaumzustand, Eingabe-Fingerabdruck und Abhängigkeiten. Der Fenstertitel zeigt die geladene Version. `ARE_HOME` beeinflusst den Datenordner, nicht die Produktversion. Ein alter Build ist kein Beleg für den aktuellen Prüfstand.

Auf dem Ziel-PC: ZIP entpacken, `AnalyzerResultExtractorV2.exe` starten.
Optional `$env:ARE_HOME` auf den entpackten Ordner setzen.

Anleitung: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`

Legacy: `AnalyzerResultExtractorV2.spec` ist nur noch Altbestand und **nicht** der bevorzugte Build-Weg.
