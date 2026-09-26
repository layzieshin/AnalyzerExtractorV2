# Analyzer Agent Governance

**Stand:** 2026-09-23

**Profil:** `arev2-local-cost-aware`

**Normative Zahlen und Modelle:** [`.cursor/agent-system.json`](../.cursor/agent-system.json)

Dieser Vertrag gilt für **AnalyzerResultExtractorV2**: Windows, lokale Tkinter-Oberfläche, ein Dirty-Baseline-Workspace. PostgreSQL, ein HTTP-Host, GitHub-Review und ein Multi-Worktree-Harness gehören nicht dazu.

QMToolV7 ist eine nicht-bindende Vorlage für Rollengrenzen und Kostenlimits. QMTool-Dateien gelten hier nicht. Workflow-Schritte und Befehle bleiben in [`.cursor/rules/00-agent-workflow.mdc`](../.cursor/rules/00-agent-workflow.mdc). Architektur und Entrypoints bleiben in [`AGENTS.md`](../AGENTS.md), [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) und [`.cursor/rules/01-architecture-boundaries.mdc`](../.cursor/rules/01-architecture-boundaries.mdc).

Wenn diese Datei und `agent-system.json` bei einer Zahl oder einem Modell abweichen, gilt die JSON-Datei.

## 1. Priorität

Konflikte in dieser Reihenfolge auflösen (Addendum V2.3 §0.1):

1. Explizite aktuelle Nutzerentscheidung und freigegebener Scope.
2. Repo-lokale Agenten- und Governance-Dateien dieses Worktrees (`AGENTS.md`, `.cursor/**`, diese Datei).
3. Öffentliche Code-Verträge und grüne Tests (`src/*/api.py`, Architektur-Gates).
4. Aktuelle Analyzer-Dokumentation nach Geltungsbereich.
5. V2.2-Produkt-Roadmap.
6. Historische Phasendokumente.
7. QMToolV7 nur als Migrationsreferenz.

Innerhalb von Stufe 2:

- Zahlen, Modelle, Limits: `.cursor/agent-system.json`
- Ausführungstext: diese Datei
- Befehle: `00-agent-workflow.mdc`
- Grenzen und Entrypoints: `AGENTS.md`

Widerspruch auf gleicher Stufe, der sich nicht mechanisch auflöst: `SCOPE_CORRECTION_REQUIRED` und Stopp.

## 2. Rollen

Nur lokale Cursor-Agenten. Keine Remote- oder Cloud-Agenten. Keine automatische Substitution auf ein anderes oder teureres Modell. `gpt-5.6-sol` und Composer sind in diesem Profil nicht vorgesehen.

| Rolle | Modell | Zugriff | Aufgabe |
|-------|--------|---------|---------|
| `roadmap-architect` | `grok-4.7-high` | readonly | Ein freigegebenes Paket abgrenzen |
| `repo-explorer` | `grok-4.7-high` | readonly | Owner, Pfade, Tests belegen |
| `implementer` | `grok-4.7-high` | einziger Product-Writer | Genau ein freigegebenes Paket oder ein Rework |
| `checkpoint-reviewer` | `gpt-5.6-terra-medium-fast` | readonly | Eine materielle Prüfung |
| `git-steward` | `gpt-5.6-luna-medium-fast` | nur die freigegebene Git-Aktion | Kein Produkt-Writer |
| `escalation-reviewer` | `gpt-5.6-terra-high-fast` | readonly | Eine Prüfung nach ausgeschöpftem Rework-Budget |

Rollen starten keine weiteren Rollen. Der Parent setzt höchstens die eine Rolle ein, die der aktuelle Schritt erlaubt.

## 3. Schlanker Ablauf

1. Nutzer gibt das Paket frei.
2. Vor dem ersten Schreibzugriff bestätigen: Safety-Snapshot außerhalb des Worktrees, Privacy-Preflight, erwarteter HEAD plus absichtlicher Dirty-Baseline, exklusiver Writer.
3. Optional `repo-explorer` oder `roadmap-architect`, beide readonly.
4. Genau ein `implementer`.
5. Review nur nach Abschnitt 4. Sonst lokale Prüfung des Diffs.
6. Bei `FAIL` höchstens das Rework-Budget aus der JSON, derselbe Writer, jeweils nur fokussierte Tests.
7. Danach höchstens eine Eskalationsprüfung. Der nächste Zustand ist `HUMAN_GATE` oder `BLOCKED`.
8. Vollsuite höchstens einmal nach Review-GO. Build- und GUI-Smoke nur, wenn der Scope sie verlangt.
9. Stopp. Die nächste Phase beginnt nur nach neuer Nutzerfreigabe.
10. Git nur als eigener Schritt über `git-steward` (Abschnitt 7).

## 4. Review

**Erforderlich** (genau ein `checkpoint-reviewer`) bei materieller Logik, öffentlicher API, Persistenz, Datenintegrität oder Packaging.

**Optional:** triviale Doku. Diff und `git diff --check` lokal prüfen. Keinen Agenten-Review erfinden.

Beispiele:

- Ein Satz in `docs/TESTBASELINE.md`: lokale Prüfung.
- Änderung an `src/*/api.py`, SQLite-Semantik oder `packaging/build_onedir.py`: ein Checkpoint-Review.

Ein Reviewer korrigiert nicht selbst und startet keine zweite Review-Runde auf eigene Faust. Nach `FAIL` schreibt derselbe Implementer den einen Rework-Auftrag.

## 5. Kostenbudget

Quelle: `.cursor/agent-system.json` → `defaults`.

| Limit | Wert |
|-------|------|
| `max_parallel_writers` | 1 |
| `max_writer_agents` | 1 |
| `max_normal_reviewers` | 1 |
| `max_rework_rounds` | 2 |
| `max_escalation_reviews` | 1 |
| `max_full_regression_runs_after_review_go` | 1 |

Eskalation auf Sol ist aus. Ist das konfigurierte Review-Modell nicht verfügbar, den Lauf als Orchestrator-Review oder `HUMAN_GATE` dokumentieren. Kein stiller Wechsel auf ein teureres Modell.

## 6. Modellattestation

Konfigurierte und angeforderte Modelle sind keine Laufzeit-Attestation. `observed model` und `observed effort` nur nennen, wenn echte Telemetrie vorliegt. Sonst `UNAVAILABLE`.

## 7. Git und destruktive Grenzen

Kein Git-Schreibzugriff ohne separate, explizite Nutzerfreigabe der exakten Aktion. Diese Freigabe ist nicht im Implementierungs-Scope enthalten. Ausgeführt wird sie nur durch `git-steward`.

Reset, Clean, Stash, Commit, Push, Merge, Branch- und Worktree-Aktionen sind ohne diese Freigabe verboten. Der Dirty-Baseline-Worktree bleibt stehen.

Explizite Scope-Freigabe brauchen zusätzlich:

- `rules/*.json`, `rules/index.json`, `rules/template.json`
- Produkt- und Runtime-Daten (`jobs/`, `input/`, `storage/`, SQLite, Excel, Logs)
- destruktive Build-Ziele

## 8. Stop-Status

Sofort stoppen, bevor irgendetwas geschrieben wird:

- `SCOPE_CORRECTION_REQUIRED`
- `BASELINE_SELECTION_REQUIRED`
- `WORKTREE_CHANGED_EXTERNALLY`
- `EXCLUSIVE_WRITER_NOT_CONFIRMED`
- `GOVERNANCE_CONFLICT`
- `PRIVACY_OR_SECRET_REVIEW_REQUIRED`

Keine Best-Effort-Korrektur und kein Phasenwechsel aus diesen Zuständen.

## 9. Gate-Bericht

Nach jedem Paket stoppen. Nächste Phase nur nennen.

1. Phase / Gate
2. Preflight: HEAD vor/nachher, exklusiver Writer, fremde Worktree-Änderungen
3. Scope: geplant, tatsächlich, Abweichung
4. Verträge/Owner und phasengleiche Doku
5. Tests: Befehl, pass/fail/skip, Baseline-Differenz
6. Manuelle Checks
7. Offene Risiken
8. Genau ein Status: `GATE_PASSED`, `GATE_FAILED`, ein Stop-Status aus Abschnitt 8, oder nach Eskalation `HUMAN_GATE` / `BLOCKED`
9. Nächste Phase: nur nennen

Phasenfortschritt nur nach Nutzerfreigabe.

## 10. Außerhalb dieses Profils

Bewusst nicht angelegt und nicht in Kraft:

- `.cursor/hooks`, `.cursor/runtime`, `.cursor/worktrees.json`
- GitHub- oder External-Review-Werkzeuge
- Rollen `plan-challenger` und `external-review-triager`
- kopierte QMTool-Skills und Python-Runner
- eine allgemeine Workflow-Engine
- Root-`GOVERNANCE.md`
