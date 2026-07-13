# Headless Runbook: Watchdog + Worker

Dieses Runbook beschreibt den stabilen Betrieb ohne GUI.

## Abgrenzung zur Test-UI

- Die Test-UI (`gui_min_ext.py`) nutzt absichtlich den Direktmodus (`submit`, RuleSuite, Rules-Validator).
- Watchdog/Worker/Queue sind dort nicht enthalten.
- Dieses Runbook gilt nur fuer den Headless-Dauerbetrieb mit Watchdog + Worker.

## 1) Startreihenfolge

1. Watch-Ordner bereitstellen (Default `input/watch/`).
2. Watchdog starten:
   - `python watchdog_main.py`
3. Worker starten:
   - `python worker_main.py`

Optionale One-Shot-Checks:
- `$env:ARE_WATCHDOG_ONCE="1"; python watchdog_main.py`
- `$env:ARE_WORKER_ONCE="1"; python worker_main.py`

## 2) Wichtige Konfiguration

- `ARE_OUTPUT_MODE=both|excel|sqlite`
- `ARE_SQLITE_PATH=<pfad>`
- `ARE_DEVICE_ID=<device_id>` (optional; leer = Runtime-Default)
- `ARE_WATCH_STABLE_WINDOW_S=1.0`
- `ARE_QUEUE_PROCESSING_TTL_S=300`
- `ARE_QUEUE_CLAIM_LOCK_TTL_S=120`
- `ARE_QUEUE_MAX_ATTEMPTS=5`
- `ARE_PIPELINE_LOCK_TTL_S=900`
- `ARE_SQLITE_BUSY_TIMEOUT_MS=5000`
- `ARE_SQLITE_RETRY_COUNT=3`
- `ARE_SQLITE_RETRY_SLEEP_S=0.2`
- `ARE_REJECT_INVALID_RUNS=1`

Watchdog-Verhalten:

- `ARE_WATCHDOG_ONCE=1` queued vorhandene PDFs sofort, ohne erste Beobachtungsrunde.
- Dauerbetrieb nutzt `ARE_WATCH_STABLE_WINDOW_S`, um halb kopierte Dateien nicht zu frueh zu queuen.
- Leere oder ungueltige `ARE_WATCH_STABLE_WINDOW_S`-Werte fallen auf `1.0` zurueck.

## 3) Job-Statusmodell

### Queue (`jobs/queue/*.json`)
- `PENDING`: wartend
- `PROCESSING`: von Worker geclaimt
- `DONE`: erfolgreich abgeschlossen
- `FAILED`: Verarbeitung fehlgeschlagen

### Pipeline-State (`jobs/<job_id>.json`)
- `LOCKED`, `PARSED`, `NORMALIZED`, `ASSAYS_DETECTED`, `SPLIT`, `DONE`, `FAILED`
- `SKIPPED` wird als API-Result geliefert (z. B. `already_done`, `locked`)

## 4) Recovery bei Störungen

### A) Queue-Stall (`PROCESSING` bleibt hängen)
- Ursache: Worker-Abbruch während Verarbeitung oder verwaiste Claim-Lock-Datei.
- Mechanismus:
  1. Verwaiste `jobs/queue_locks/<job_id>.claim.lock` werden nach `ARE_QUEUE_CLAIM_LOCK_TTL_S` (Default 120 s) als stale übernommen.
  2. Danach wird stale `PROCESSING` nach `ARE_QUEUE_PROCESSING_TTL_S` auf `PENDING` requeued.
- Maßnahme: `ARE_QUEUE_CLAIM_LOCK_TTL_S` und `ARE_QUEUE_PROCESSING_TTL_S` ggf. temporär kleiner setzen.

### A2) Max-Versuche erreicht (`max_attempts_exceeded`)
- Ursache: Job wurde mehrfach geclaimt und ist wiederholt fehlgeschlagen.
- Mechanismus: Nach `ARE_QUEUE_MAX_ATTEMPTS` (Default 5) bleibt der Queue-Job auf `FAILED`; Watchdog requeued ihn nicht mehr.
- Maßnahme: Fehlerursache beheben, Queue-Eintrag manuell löschen oder `attempts` zurücksetzen.

### B) Pipeline-Lock blockiert Job (`reason=locked`)
- Ursache: verwaiste `locks/<job_id>.lock`.
- Mechanismus: stale Locks werden nach `ARE_PIPELINE_LOCK_TTL_S` automatisch ersetzt.
- Maßnahme: TTL prüfen; bei Bedarf manuell Lock löschen und Worker erneut laufen lassen.

### C) SQLite locked
- Mechanismus: `busy_timeout` + retries.
- Maßnahme: Retry-Werte erhöhen oder parallele Workerzahl reduzieren.

## 5) Retry- und Fehlerstrategie

- `FAILED` Queue-Jobs werden bei erneutem Watchdog-Enqueue auf `PENDING` zurückgesetzt, solange `attempts < ARE_QUEUE_MAX_ATTEMPTS`.
- `SKIPPED:locked` wird im Worker als `PENDING` mit `deferred:*` zurückgestellt.
- `SKIPPED:already_done` wird als `DONE` übernommen.

## 6) Release-Gate (minimal)

Vor Release müssen mindestens folgende Checks grün sein:

1. `pytest -q`
2. `python rules_validate_main.py`
3. Smoke:
   - `python main02.py` (oder definierter Headless-Samplelauf)
4. Manuelle Stichprobe von:
   - Queue-Status
   - `jobs/<job_id>.json`
   - Excel/SQLite Output
