# PDF Ergebnis-Extractor (Projekt)

- Projektversion: **2.2.0**; Änderungen unter `docs/RELEASE_NOTES_2_2_0.md`, Prüfstand unter `docs/TESTBASELINE.md`
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

In **Ergebnisse** werden alle Assays eines Berichts gemeinsam angezeigt. **In Validierung prüfen** bzw. **Validierung / Berichtgerät korrigieren** öffnen denselben Arbeitsbereich mit Original-PDF und Messwerten. Dort das konkrete Gerät einmal für den ganzen Quellbericht bestätigen und anschließend jeden Assay mit Initialen und optionalem Kommentar einzeln freigeben. Ein fehlendes Gerät kann direkt hier mit einem unterscheidbaren Namen angelegt werden. Eine Importvoreinstellung ist noch keine Gerätebestätigung.

Ein Gerätewechsel zeigt den bisherigen und neuen Stand sowie den Umfang des gesamten Berichts. Ein Grund ist erforderlich; danach braucht jeder betroffene Assay eine erneute Freigabe. Bereits gespeicherte Validierungen, Ergebnisfassungen und QK-Berichte bleiben erhalten. SQLite ist die verbindliche Ablage. Neue Verarbeitung und Validierung erzeugen keine Excel-Dateien; vorhandene Arbeitsmappen und historische Ausgabepläne bleiben lesbar.

Assay-Tabellen zeigen den vollständigen gespeicherten Namen. Die ausgewählte Ergebnisfassung bestimmt den Namen; eine noch offene Neuanalyse ersetzt ihn nicht. Fehlt ein belegter Name, steht dort **Assayname fehlt**. Auch gleichnamige Assays bleiben getrennt auswählbar. Bei unbekannten Kandidaten ist ein aus der Datei abgeleiteter **Namenshinweis** ausdrücklich als solcher gekennzeichnet.

### Qualitätskontrolle und PDF-Nachweise

Unter **Einstellungen → Assays & QK** auch vor dem ersten Import den Assay wählen und ein Profil mit einem benannten Level und dessen **IST-Feld** speichern. Gerät, SOLL, MIN/MAX, Datum-/Zeitformat und Westgard sind optionale Ergänzungen. Konfigurationsänderungen brauchen keine Operatorinitialen. Für eine gemeinsame statistische Skala eine Einheit bestätigen oder die Größe unter **Erweitert** ausdrücklich als dimensionslos kennzeichnen. Eine fehlende Einheit kann beim Bearbeiten desselben Profils ergänzt werden.

Ein Profil gilt standardmäßig für den Assay auf allen Geräten. Die Messwerte bleiben trotzdem je physischem Gerät getrennt. Bei Bedarf kann ein neues Profil gerätespezifisch sein; die Bindung eines bestehenden Profils bleibt fest. **Weiteres Profil** übernimmt vorhandene Zuordnungen als bearbeitbare Kopie. Gerätename genügt; SN, LNR und EVA sind optional. Alte Kennungen werden nicht zusammengelegt.

Der Entwurf bleibt während der Sitzung beim Wechsel zwischen Profilen, beim Inline-Anlegen eines Geräts und nach Eingabefehlern erhalten. Beim Schließen kann er ausdrücklich **behalten** oder verworfen werden. Behaltene Entwürfe erscheinen mit Namen in derselben Assayübersicht und werden über **Entwurf fortsetzen** wieder geöffnet. Speichern veröffentlicht eine neue vollständige Profilfassung; frühere Fassungen bleiben unverändert.

Bekannte Datums-/Zeitangaben wie `14.11.2026`, `2026-11-14`, `8:05` und `08:05:00` werden ohne Formatcode erkannt. Leere optionale Formatfelder bedeuten Automatik; vorhandene bewusste Overrides bleiben erhalten. Ein Tag erhält keine erfundene Uhrzeit und Minuten keine ergänzten Sekunden. Unbekannte oder widersprüchliche Zeiten beeinflussen die zeitabhängigen Funktionen; ein gültiger IST-Wert kann weiterhin in Mittelwert und empirische SD eingehen. Unklare Zahlenschreibweisen aus unbekannter Herkunft brauchen eine bewusste Komma-/Punkteinstellung; belegte unveränderte Originalexportfelder haben einen eingefrorenen Dezimalnachweis.

Herstellergrenzen aus MIN/MAX und aktivierbare Einzelwert-Prozentgrenzen sind getrennte Grenzarten. Die Prozentgrenzen verwenden je Level dessen SOLL: `SOLL × (1 ± p / 100)`. Sie sind unabhängig von der bisherigen relativen QMMA-Schwelle, SD und Westgard. Eine Grenzüberschreitung allein entfernt den Messwert nicht aus der Statistik. Bestehende QMMA-Grenzen werden nicht automatisch in die neue Prozentkonfiguration übernommen; die Konfiguration bestätigt keine vollständige Rili-BÄK-Konformität.

Unter **Statistik** zeigen die Kontrollserien je Gerät Anzahl, Mittelwert, empirische Stichproben-SD (n−1), VK und die jeweils verfügbaren unabhängigen Bewertungen. SOLL wird erst für QMMA, MIN/MAX erst für Herstellergrenzen benötigt. Westgard ist bei neuen Profilen ausgeschaltet; inaktive Regelblöcke erscheinen im Standardbericht und Diagramm nicht. QMMA und empirische Kennzahlen brauchen keine freigegebene SD-Referenz. Für Westgard muss eine manuelle SD oder bestätigte Referenzserie mit passender Messwertdefinition, Zahlenschreibweise und Einheit belegt sein. Eine unpassende oder nicht belegbare Referenz bleibt mit Grund gesperrt. Die empirische SD erzeugt keine neue Westgard-Referenz. Das Diagramm verwendet die eingefrorenen Werte und Grenzen; Messpunkte können angeklickt, vergrößert und verschoben werden.

**Abschluss prüfen** bereitet aus dem vollständigen Nutzungsverlauf eine unverbindliche Modell-/PDF-Vorschau vor. Ein zeitlich sicher späterer Nutzungszeuge einer anderen Kit-Charge kann auch unvalidiert oder statistisch ungeeignet sein; eine globale Chargenreihenfolge wird daraus nicht abgeleitet. Vorschau und **Später** schreiben nichts. Erst die abschließende Bestätigung speichert exakt das vorbereitete Modell und PDF gemeinsam. Geänderte Quellen, Profilfassungen oder Auswahlkontexte blockieren eine veraltete Vorschau.

Der Standardausdruck **KONTROLLPROBENEINZELMESSUNG** ist kompakt: A4 mit Stammdaten, Diagramm und rechter Legende, Kennzahlen, Messwerttabelle sowie leeren Unterschriftsfeldern. Datum und tatsächliche Uhrzeit stehen in einer Zeile. Fortsetzungen wiederholen die Zuordnung und Tabellenköpfe; ein weiteres Level kann mit vollständigem eigenem Kopf, Diagramm und Kennzahlen auf derselben Seite beginnen. Ausschlüsse, Grenzüberschreitungen und Westgard-Warnungen bleiben positionsbezogen sichtbar. Technische Hash-/Tokenlisten und wiederholte Einzelprobenbelege werden standardmäßig nicht mitgedruckt; vollständige Rohwerte, Identitäten und gebundene Validierungen bleiben im digitalen Analysemodell erhalten. Der PDF-Fuß nennt dessen Modellkennung. Anwender stammt aus der Extraktion; Validierer und Abschlussinitialen werden davon getrennt behandelt und ersetzen keinen Anwender.

**Nachweisfassungen → PDF speichern** exportiert die archivierten Originalbytes an einen neuen Dateinamen. **Erläuterungen und zusätzliche Nachweise mitdrucken** ist standardmäßig aus und gilt bewusst für den einzelnen Export. Bei Auswahl kommen vollständige punktbezogene Rohwert-/Quell-/Validierungsnachweise, Methoden und Regelbefunde hinzu; diese Druckfassung darf mehr Seiten benötigen. Nach erfolgreichem Export wird die Option wieder ausgeschaltet, bei einem Fehler bleibt sie für einen erneuten Versuch erhalten. Alte Modelle erhalten dabei keine nachberechneten neuen Kennzahlen, gespeicherte Modelle und Original-PDFs bleiben unverändert. Vorhandene Zieldateien werden nicht überschrieben. Späte Messwerte erfordern eine begründete Wiederöffnung; frühere Nachweise bleiben lesbar.

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

Der geladene Entwurf wird zunächst mit **Mit PDFs prüfen** geprüft. **Prüfung erfolgreich – noch nicht aktiviert** ist ein Nachweis für genau diesen Entwurf und diese PDF-Auswahl. Updates brauchen zusätzlich eine eigenständige passende Referenz. Änderungen an Entwurf, PDF-Auswahl oder aktiver Bindung entwerten den Nachweis. Erst eine abschließende Aktivierungsbestätigung veröffentlicht den geprüften Stand; Proof-only und **Nein** ändern keine aktive Regel. Ein Update archiviert die exakten bisherigen Regelbytes.

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

Das Windows-Release enthält das geprüfte portable ZIP samt Prüfsummen und Buildnachweis. Für einen eigenen Windows-Build ohne Python auf dem Ziel-PC gilt:

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

Auf dem Ziel-PC: ZIP vollständig entpacken, `AnalyzerResultExtractorV2.exe` starten. `_internal` und `rules` gehören zum Paket.

**Bestehende portable Installation aktualisieren:** Anwendung schließen und den bisherigen Ordner sichern. EXE, `_internal` und `build-info.json` durch die neue Fassung ersetzen. Vorhandene `rules`, `storage`, `jobs`, `input` und `output` einschließlich SQLite und eingefrorener Jobbelege behalten; diese enthalten Konfiguration, eigene Regeln und Quellnachweise. Ein neues leeres Projekt ist kein Ersatz für diese Daten.
Optional `$env:ARE_HOME` auf den entpackten Ordner setzen.

Anleitung: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`

Legacy: `AnalyzerResultExtractorV2.spec` ist nur noch Altbestand und **nicht** der bevorzugte Build-Weg.
