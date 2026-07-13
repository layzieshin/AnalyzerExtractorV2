# AP-14B Test-App

AP-14B.1 ergaenzt eine produktionsnahe Test-App-Basis, ohne `gui_min.py` oder
`gui_min_ext.py` umzubauen.

## Start

```powershell
.\.venv\Scripts\python.exe test_app_main.py
```

## Struktur

Die App ist ein Tkinter-Adapter unter `interfaces/tk/`. Sie nutzt nur Public APIs
aus `src.*.api` und UI-neutrale Presenter aus `src.testui.api`.

Hauptbereiche:

- `EXTRACTOR`
- `OPTIONS`
- `RULE SUITE`
- `LOGS`
- `DUPLIKATE`
- `ADMIN`

## Extractor-/Queue-Bedienung

Der `EXTRACTOR`-Bereich ist fuer kontrollierte Testlaeufe gedacht:

- `Watch-Ordner scannen` liest vorhandene PDFs aus dem eingestellten Watch-Ordner.
  Optional `Unterordner einbeziehen` durchsucht Jahres-/Monatsordner rekursiv.
  Der manuelle Scan ist nur Sichtprüfung: Er fuellt die Extractor-Liste und queued
  nie automatisch, auch nicht bei vielen rekursiven Funden.
- `Dateien auswaehlen` ergaenzt manuell gewaehlte PDFs.
- `Direkt verarbeiten` ruft `src.jobcontroller.api.submit(...)` fuer die Auswahl auf.
- `In Queue stellen` ruft `src.jobqueue.api.enqueue_pdf_job(...)` fuer die Auswahl auf.
- `Liste aktualisieren` merged den Queue-Status aus `src.jobqueue.api.list_jobs(...)`.
- `Auto-Suche starten` scannt den Watch-Ordner zyklisch, solange die App offen ist.
  Mit `Unterordner einbeziehen` werden auch Unterordner beruecksichtigt.
- `Auto-Suche stoppen` beendet den geplanten In-App-Scan.

Watch- und manuelle Eintraege teilen dieselbe Arbeitsliste. Gleiche PDFs werden
ueber normalisierte absolute Pfade dedupliziert. Wenn keine Zeile ausgewaehlt
ist, arbeiten `Direkt verarbeiten` und `In Queue stellen` auf allen sichtbaren
Dateizeilen.

Die Auto-Suche ist ein sichtbarer In-App-Watchdog light. Sie erkennt stabile neue
PDFs im Watch-Ordner (optional rekursiv) und stellt sie per
`enqueue_pdf_job(..., source="test-app-auto-watch")` in `jobs/queue/` ein.
Rekursion dient dem Sammeln fuer die persistente Queue-Aufnahme, nicht der
automatischen Verarbeitung. Der manuelle `Watch-Ordner scannen` nutzt
`list_watch_pdf_paths(...)` nur zur Anzeige und veraendert keine Scanner-
Stabilitaetsbeobachtungen.

Unterordner mit Namen wie `processed`, `failed`, `duplicates`, `duplicate`,
`archive` oder `_archive` werden bei rekursiver Suche case-insensitive
uebersprungen. Symlink-Verzeichnisse werden nicht rekursiv betreten.

Sie startet keinen Worker, ruft kein `submit(...)` auf, schreibt keine Ergebnisse
und bewegt keine Dateien. Bekannte Pfade kommen aus der Extractor-Liste,
bestehenden Queue-Jobs und einer kleinen Session-Suppress-Liste (nur Anti-Spam
innerhalb der laufenden GUI-Session, Eintrag erst nach erfolgreichem Enqueue).

`Liste aktualisieren` und der Queue-Merge zeigen Queue-Jobs auch ohne vorherige
GUI-Session in der Extractor-Liste an. `Direkt verarbeiten` ist fuer Queue-Zeilen
blockiert, damit keine Verarbeitung am Ledger vorbei laeuft.

Das Scan-Intervall kommt aus der Runtime-Konfiguration und wird fuer die GUI gegen
Busy-Loops begrenzt.

## Grenzen

- Keine PyQt-Abhaengigkeit in AREV2.
- Keine dauerhaften Watchdog-/Worker-Prozesse aus der App.
- `In Queue stellen` startet keinen Worker und keinen Watchdog.
- `Auto-Suche starten` startet keinen externen Watchdog.
- Keine destruktiven Admin-Aktionen.
- Keine Add-/Overwrite-Entscheidungen fuer Duplikate.
- Keine `rules/*.json`-Aenderungen.

Folgepakete koennen Queue-/Worker-Steuerung, vollstaendige Duplicate-Workflows
und spaetere PyQt/QMTool-Adapter auf denselben Presenter-Funktionen aufbauen.
