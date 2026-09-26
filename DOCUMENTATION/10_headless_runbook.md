# Headless Runbook: Watchdog + Worker

Dieses Runbook beschreibt den stabilen Betrieb ohne GUI.

## Abgrenzung zur Test-App

- Die **neue Test-App** (`test_app_main.py`) nutzt Queue und Arbeitsliste (`jobs/queue/*`) und verarbeitet Jobs ueber dieselbe Worker-Logik wie der Headless-Betrieb (`interfaces/common/queue_worker.py`).
- **Legacy Direktmodus** (`gui_min_ext.py` / `gui_min.py`) umgeht die Queue und ruft `submit` direkt auf.
- Dieses Runbook gilt fuer den **Headless-Dauerbetrieb** mit separaten Watchdog- und Worker-Prozessen.

## 1) Startreihenfolge

1. Watch-Ordner und Backup-Ordner bereitstellen (persistiert in `storage/desktop_settings.json` als `watch_input_path` / `watch_backup_path` wenn `watch_enabled=true`).
2. Watchdog starten:
   - `python watchdog_main.py`
3. Worker starten:
   - `python worker_main.py`

Optionale One-Shot-Checks:

- `$env:ARE_WATCHDOG_ONCE="1"; python watchdog_main.py`
- `$env:ARE_WORKER_ONCE="1"; python worker_main.py`

**ARE_HOME:** Watchdog und Worker loesen den App-Root ueber `src.runtime.api.resolve_app_root()` auf (`ARE_HOME` wenn gesetzt, sonst Source-Tree-Fallback). Settings, Ledger und Queue muessen auf denselben Root zeigen.

## 2) Wichtige Konfiguration

- `ARE_HOME=<writable-root>` (optional; empfohlen fuer isolierte Deployments)
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

### Watch-Einstellungen (DesktopSettings / `storage/desktop_settings.json`)

| Feld | Bedeutung |
|---|---|
| `watch_enabled` | Default `false`. Ohne `true` fuehrt der Watchdog keinen Scan aus (One-Shot: exit 0, keine Writes). |
| `watch_input_path` | Eingangsordner fuer stabile PDFs (Legacy-Alias beim Laden: `watch_dir`). |
| `watch_backup_path` | Zielordner fuer Archivierung nach Queue-`DONE`. Pflicht wenn Watch aktiv ist. |

Watchdog-Verhalten:

- **Dauerbetrieb:** wiederholte `run_watch_cycle()`-Aufrufe mit `ARE_WATCH_STABLE_WINDOW_S` (Stabilitaet ueber Groesse+mtime; erste unveraenderte Beobachtung startet das Fenster).
- **One-Shot (`ARE_WATCHDOG_ONCE=1`):** bei positivem Stabilitaetsfenster zwei getrennte Beobachtungen im selben Prozess (erster Zyklus + `sleep(window)` + zweiter Zyklus), damit halb kopierte Dateien nicht sofort enqueued werden. Bei `watch_enabled=false`: exit 0 ohne Writes. Bei ungueltiger Watch-Konfiguration: stderr + exit code != 0.
- **Worker One-Shot:** verarbeitet maximal einen pending Job pro Aufruf; wiederholte One-Shots drainen die Queue schrittweise.

Legacy `src.watchdog.api` delegiert auf `src.ingestion.api` (Ledger vor Queue-Enqueue; explizites Backup erforderlich).

## 3) Job-Statusmodell

### Queue (`jobs/queue/*.json`)
- `PENDING`: wartend
- `PROCESSING`: von Worker geclaimt
- `DONE`: erfolgreich abgeschlossen
- `FAILED`: Verarbeitung fehlgeschlagen

Queue-Jobs tragen additiv `content_sha256` (voller SHA-256-Hex, Phase-2-Scope).

### Import-Ledger (`storage/ingestion/*.json`)
- `processing_status`: `REGISTERED` | `PENDING` | `PROCESSING` | `DONE` | `FAILED`
- `archive_status`: `NOT_REQUIRED` | `PENDING` | `MOVING` | `ARCHIVED` | `ARCHIVE_FAILED` | `RECOVERY_REQUIRED` (wenn Quelle und Ziel fehlen oder Recovery noetig ist)

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
- Maßnahme: Fehlerursache beheben, dann explizit reaktivieren:
  - Headless/API: `src.jobqueue.api.retry_failed_job(...)`
  - Test-App: **Erneut starten** in der Arbeitsliste
  - Alternativ: Queue-Eintrag manuell loeschen oder `attempts` zuruecksetzen (nur mit Bedacht)

### B) Pipeline-Lock blockiert Job (`reason=locked`)
- Ursache: verwaiste `locks/<job_id>.lock`.
- Mechanismus: stale Locks werden nach `ARE_PIPELINE_LOCK_TTL_S` automatisch ersetzt.
- Maßnahme: TTL prüfen; bei Bedarf manuell Lock löschen und Worker erneut laufen lassen.

### C) SQLite locked
- Mechanismus: `busy_timeout` + retries.
- Maßnahme: Retry-Werte erhöhen oder parallele Workerzahl reduzieren.

### D) Archiv-Fehler nach Queue-`DONE`
- Queue bleibt `DONE`; Ledger `archive_status` wird `ARCHIVE_FAILED` oder `RECOVERY_REQUIRED`.
- Publish: verified partial → exclusive `os.link` into backup target (same volume; fails closed if target exists with different bytes or link unsupported). Orphan verified partials finalize without source; invalid partials are never silently deleted.
- Retry nur ueber `src.ingestion.api.retry_archive` / `ExtractionController.retry_archive` (kein Re-Enqueue).

## 5) Retry- und Fehlerstrategie

- `FAILED` Queue-Jobs werden **nicht** durch erneutes Enqueue (Watchdog-Scan, erneutes Vormerken) automatisch reaktiviert.
- Explizite Reaktivierung nur ueber:
  - `src.jobqueue.api.retry_failed_job(...)` (API)
  - Test-App: **Erneut starten** fuer ausgewaehlte fehlgeschlagene Jobs
- Stale `PROCESSING` wird nach TTL wieder auf `PENDING` gesetzt (Recovery, kein manueller Retry).
- `SKIPPED:locked` wird im Worker als `PENDING` mit `deferred:*` zurueckgestellt.
- `SKIPPED:already_done` wird als `DONE` uebernommen.

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
