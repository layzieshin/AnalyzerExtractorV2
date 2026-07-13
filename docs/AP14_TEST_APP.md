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

## Grenzen

- Keine PyQt-Abhaengigkeit in AREV2.
- Keine dauerhaften Watchdog-/Worker-Prozesse aus der App.
- Keine destruktiven Admin-Aktionen.
- Keine Add-/Overwrite-Entscheidungen fuer Duplikate.
- Keine `rules/*.json`-Aenderungen.

Folgepakete koennen Queue-/Worker-Steuerung, vollstaendige Duplicate-Workflows
und spaetere PyQt/QMTool-Adapter auf denselben Presenter-Funktionen aufbauen.
