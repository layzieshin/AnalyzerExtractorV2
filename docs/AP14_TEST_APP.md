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

## Extractor-Bedienung

Der `EXTRACTOR`-Bereich ist fuer kontrollierte Testlaeufe gedacht:

- `Ergebnisse suchen` liest vorhandene PDFs aus dem eingestellten Watch-Ordner.
  Optional `Unterordner einbeziehen` durchsucht Jahres-/Monatsordner rekursiv.
  Der manuelle Scan merkt gefundene PDFs direkt in der Arbeitsliste vor.
- `Dateien hinzufügen` merkt manuell gewaehlte PDFs direkt in der Arbeitsliste vor.
- `Extraktion starten` verarbeitet wartende Arbeitslisten-Jobs ueber dieselbe
  Worker-Logik wie der Headless-Worker.
- `Aktualisieren` merged den internen Verarbeitungsstatus aus
  `src.jobqueue.api.list_jobs(...)`.
- `Automatische Suche starten` scannt den Watch-Ordner zyklisch, solange die App offen ist.
  Mit `Unterordner einbeziehen` werden auch Unterordner beruecksichtigt.
- `Automatische Suche stoppen` beendet den geplanten In-App-Scan.

Watch-, Auto-Suche- und manuelle Eintraege teilen dieselbe persistente
Arbeitsliste. Gleiche PDFs werden ueber den Queue-Job-Hash dedupliziert. Der
EXTRACTOR zeigt fachliche Spalten wie `Herkunft`, `Status` und `Verarbeitung`.
Technische Queue-Details bleiben im `ADMIN`-Bereich sichtbar.

Es gibt keinen direkten Submit-Pfad in der GUI. `Extraktion starten` nutzt
`interfaces.common.queue_worker.process_next_pending(...)`; der Headless-Worker
nutzt dieselbe Funktion.

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

## Grenzen

- Keine PyQt-Abhaengigkeit in AREV2.
- Keine dauerhaften Watchdog-/Worker-Prozesse aus der App.
- `Automatische Suche starten` startet keinen externen Watchdog.
- Keine destruktiven Admin-Aktionen.
- Keine Add-/Overwrite-Entscheidungen fuer Duplikate.
- Keine `rules/*.json`-Aenderungen.

Folgepakete koennen Queue-/Worker-Steuerung, vollstaendige Duplicate-Workflows
und spaetere PyQt/QMTool-Adapter auf denselben Presenter-Funktionen aufbauen.
