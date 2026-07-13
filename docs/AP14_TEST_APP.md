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
- `Dateien auswaehlen` ergaenzt manuell gewaehlte PDFs.
- `Direkt verarbeiten` ruft `src.jobcontroller.api.submit(...)` fuer die Auswahl auf.
- `In Queue stellen` ruft `src.jobqueue.api.enqueue_pdf_job(...)` fuer die Auswahl auf.
- `Liste aktualisieren` merged den Queue-Status aus `src.jobqueue.api.list_jobs(...)`.

Watch- und manuelle Eintraege teilen dieselbe Arbeitsliste. Gleiche PDFs werden
ueber normalisierte absolute Pfade dedupliziert. Wenn keine Zeile ausgewaehlt
ist, arbeiten `Direkt verarbeiten` und `In Queue stellen` auf allen sichtbaren
Dateizeilen.

## Grenzen

- Keine PyQt-Abhaengigkeit in AREV2.
- Keine dauerhaften Watchdog-/Worker-Prozesse aus der App.
- `In Queue stellen` startet keinen Worker und keinen Watchdog.
- Keine destruktiven Admin-Aktionen.
- Keine Add-/Overwrite-Entscheidungen fuer Duplikate.
- Keine `rules/*.json`-Aenderungen.

Folgepakete koennen Queue-/Worker-Steuerung, vollstaendige Duplicate-Workflows
und spaetere PyQt/QMTool-Adapter auf denselben Presenter-Funktionen aufbauen.
