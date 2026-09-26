# AP-14B Test-App / Produkt-Shell

## Aktueller Default-Start (Phase 3B)

```powershell
.\.venv\Scripts\python.exe test_app_main.py
```

Startet `AnalyzerDesktopApp` — Sidebar mit fuenf Ansichten:

| Ansicht | Zweck |
|---------|-------|
| **Auswertung** | PDFs verarbeiten, Auto-Import-Status, letzte Vorgänge |
| **Ergebnisse** | Berichte und Occurrences |
| **Regelwerke** | Inventar, Integritaetspruefung, Rule Editor oeffnen |
| **Einstellungen** | Pfade, Geraet, Watch, SQLite |
| **Diagnose** | Fehlerjobs, Duplikat-Klaerfaelle, Draft aus Kandidat |

Orchestrierung ueber `src.application.api`; Hintergrundarbeit via `TkTaskRunner`.

Weitere GUI-Dokumentation (Planungsstand / Inventar):

- Funktionsinventar: `docs/GUI_USER_FUNCTIONS_INVENTORY.md`
- IA-Vorschlag und Journeys: `docs/GUI_IA_PROPOSAL.md`

---

## LegacyTestApp reference — nur mit `ARE_LEGACY_UI`

> **Nicht der Default.** Die folgenden Abschnitte beschreiben ausschliesslich die tabbed
> **LegacyTestApp** (`TestApp`). Normale Nutzer starten ohne `ARE_LEGACY_UI` die
> Produkt-Shell (siehe oben).

### Start (Legacy)

```powershell
$env:ARE_LEGACY_UI = "1"
.\.venv\Scripts\python.exe test_app_main.py
```

Optionaler ADMIN-Tab (**nur Legacy-UI**):

```powershell
$env:ARE_LEGACY_UI = "1"
$env:ARE_SHOW_ADMIN = "1"
.\.venv\Scripts\python.exe test_app_main.py
```

AP-14B.1 ergaenzt die produktionsnahe Basis, ohne `gui_min.py` oder
`gui_min_ext.py` umzubauen.

### Legacy: Tab-Struktur (`SECTION_KEYS`)

| Tab | Zweck |
|-----|-------|
| `EXTRACTOR` | PDFs finden, Arbeitsliste, Extraktion |
| `OPTIONS` | Output, Pfade, Geraet |
| `RULE SUITE` | Nacharbeit fehlgeschlagener Jobs |
| `LOGS` | Chronologisches Protokoll (read-only) |
| `DUPLIKATE` | SQLite-Dubletten pruefen |
| `DATENBANK` | Gespeicherte Ergebnisse ansehen |

Optional (**nur** mit `ARE_SHOW_ADMIN=1` in der Legacy-UI):

| Tab | Zweck |
|-----|-------|
| `ADMIN` | Rohdaten der Job-Queue (Support/Debug) |

### Legacy: EXTRACTOR-Bedienung

Der Legacy-`EXTRACTOR`-Bereich ist fuer kontrollierte Testlaeufe gedacht:

- `Ergebnisse suchen` liest vorhandene PDFs aus dem eingestellten Watch-Ordner.
  Optional `Unterordner einbeziehen` durchsucht Jahres-/Monatsordner rekursiv.
  Der manuelle Scan merkt gefundene PDFs direkt in der Arbeitsliste vor.
- `Dateien hinzufügen` merkt manuell gewaehlte PDFs direkt in der Arbeitsliste vor.
- `Extraktion starten` verarbeitet wartende Arbeitslisten-Jobs ueber dieselbe
  Worker-Logik wie der Headless-Worker.
- `Extraktion stoppen` stoppt kooperativ nach dem aktuell laufenden Ergebnis.
  Bereits gestartete PDF-Verarbeitung wird nicht hart abgebrochen.
- `Fehler erneut verarbeiten` setzt ausgewaehlte fehlgeschlagene Ergebnisse
  kontrolliert wieder auf `Wartet`; fertige oder bereits wartende Ergebnisse
  werden uebersprungen.
- `Aktualisieren` merged den internen Verarbeitungsstatus aus
  `src.jobqueue.api.list_jobs(...)` in die Arbeitsliste.
- `Automatische Suche starten` scannt den Watch-Ordner zyklisch, solange die App offen ist.
  Mit `Unterordner einbeziehen` werden auch Unterordner beruecksichtigt.
- `Automatische Suche stoppen` beendet den geplanten In-App-Scan.

Watch-, Auto-Suche- und manuelle Eintraege teilen dieselbe persistente
Arbeitsliste. Gleiche PDFs werden ueber den Queue-Job-Hash dedupliziert. Der
EXTRACTOR zeigt fachliche Spalten wie `Herkunft`, `Status` und `Verarbeitung`.

Technische Queue-Details sind in der Legacy-UI standardmaessig ausgeblendet und nur im optionalen
`ADMIN`-Tab sichtbar (`ARE_SHOW_ADMIN=1`).

Es gibt keinen direkten Submit-Pfad in der GUI. `Extraktion starten` nutzt
`interfaces.common.queue_worker.process_next_pending(...)`; der Headless-Worker
nutzt dieselbe Funktion.

Die Arbeitsliste wird waehrend der Verarbeitung nach jedem Ergebnis aktualisiert.
Status und Log zeigen den aktuellen Zaehler, die Datei und den neuen Job-Status.
Dadurch bleiben grosse Arbeitslisten sichtbar kontrollierbar.

Fehlgeschlagene Jobs bleiben fehlgeschlagen, bis der Nutzer sie explizit erneut
startet (`Fehler erneut verarbeiten` im EXTRACTOR oder `Nacharbeit wiederholen`
im RULE SUITE). Erneutes Suchen, Hinzufuegen oder die Auto-Suche reaktiviert
FAILED-Jobs nicht automatisch.

Die Auto-Suche ist ein sichtbarer In-App-Watchdog light. Sie erkennt stabile neue
PDFs im Watch-Ordner (optional rekursiv) und merkt sie per
`enqueue_pdf_job(..., source="test-app-auto-watch")` in `jobs/queue/` ein.
Rekursion dient dem Sammeln fuer die persistente Arbeitsliste, nicht der
automatischen Verarbeitung. Der manuelle `Ergebnisse suchen` nutzt
`list_watch_pdf_paths(...)` ohne Scanner-Stabilitaetsbeobachtungen und merkt
gefundene PDFs direkt vor.

Unterordner mit Namen wie `processed`, `failed`, `duplicates`, `duplicate`,
`archive` oder `_archive` werden bei rekursiver Suche case-insensitive
uebersprungen. Symlink-Verzeichnisse werden nicht rekursiv betreten.

Die Auto-Suche startet keinen Worker, ruft kein `submit(...)` auf, schreibt keine
Ergebnisse und bewegt keine Dateien. Bekannte Pfade kommen aus der Arbeitsliste
und einer kleinen Session-Suppress-Liste (nur Anti-Spam innerhalb der laufenden
GUI-Session, Eintrag erst nach erfolgreichem Vormerken).

`Aktualisieren` zeigt vorgemerkte Jobs auch ohne vorherige GUI-Session in der
Extractor-Liste an. Normale Nutzer muessen dort nicht entscheiden, ob etwas in
eine Queue gelegt werden muss.

Das Scan-Intervall kommt aus der Runtime-Konfiguration und wird fuer die GUI gegen
Busy-Loops begrenzt.

### Legacy: OPTIONS

- Output-Modus (`excel` / `sqlite` / `both`), SQLite-Pfad, Watch-Ordner, Geraet
- `Anzeigen` aktualisiert eine read-only Zusammenfassung der aktuellen Werte
- Die fruehere Anzeige `Watch-Modus` wurde entfernt (hatte keine Wirkung auf die
  Auto-Suche; Steuerung erfolgt ueber `Automatische Suche starten/stoppen` im EXTRACTOR)

### Legacy: RULE SUITE (Nacharbeit)

- `Nacharbeit wiederholen` startet ausgewaehlte fehlgeschlagene Jobs erneut
  (gleiche Queue-Logik wie `Fehler erneut verarbeiten`, aber im Nacharbeit-Kontext)
- `Rules validieren` prueft die Integritaet aktiver Regelwerke
- Assay-Kandidaten, Draft-Erstellung und Rule-Editor-Hand-off fuer Reparatur

### Legacy: Grenzen

- Keine PyQt-Abhaengigkeit in AREV2.
- Keine dauerhaften Watchdog-/Worker-Prozesse aus der App.
- `Automatische Suche starten` startet keinen externen Watchdog.
- Keine destruktiven Admin-Aktionen.
- Keine Add-/Overwrite-Entscheidungen fuer Duplikate.
- Keine `rules/*.json`-Aenderungen.

Folgepakete koennen Queue-/Worker-Steuerung, vollstaendige Duplicate-Workflows
und spaetere PyQt/QMTool-Adapter auf denselben Presenter-Funktionen aufbauen.

## Feldversuch-Paket (AP-17A)

Der kanonische portable Build startet die Produkt-Shell ueber `test_app_main.py`:

```powershell
.\.venv\Scripts\python.exe packaging\build_onedir.py
```

Artefakte:

- Onedir: `packaging/dist_output/AnalyzerResultExtractorV2/`
- ZIP: `packaging/dist_output/AnalyzerResultExtractorV2.zip`

Smoke ohne GUI-Blockade:

```powershell
$env:ARE_HOME = "I:\Pfad\zum\entpackten\AnalyzerResultExtractorV2"
$env:ARE_SMOKE_EXIT = "1"
.\AnalyzerResultExtractorV2.exe
```

Das Bundle enthaelt aktive Rules und leere Laufzeitordner (`jobs/`, `output/final/`,
`input/watch/`). `rules/drafts/` wird bewusst nicht mitgeliefert.
