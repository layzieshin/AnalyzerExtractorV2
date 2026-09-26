# QMToolV7 Strukturvergleich — AnalyzerResultExtractorV2

| Feld | Wert |
|------|------|
| **Projekt** | AnalyzerResultExtractorV2 (AREV2) |
| **Benchmark** | QMToolV7 Kanon-Architektur (P0-Docs) |
| **Erstellt** | 2026-07-01 |
| **Zielgruppe** | Dev, Architect, Cursor-Agents |
| **Status** | Analyse abgeschlossen — keine Implementierung enthalten |
| **Begleitdokument** | [`RESTRUCTURE_PLAN_EXTERNAL.md`](RESTRUCTURE_PLAN_EXTERNAL.md) |

## Zweck

Diese Matrix dokumentiert **Abweichungen** zwischen dem Ist-Zustand von AREV2 und den architektonischen Vorgaben von QMToolV7. Sie ist für Menschen und Cursor-Agents gleichermaßen lesbar: jede Zeile hat eine stabile `id`, konkrete Evidenzpfade und Regeln, was beim Umbau erlaubt bzw. verboten ist.

**Wichtig:** QMToolV7 ist Benchmark, kein 1:1-Ziel. Zeilen mit Status `N/A` sind bewusst nicht umzubauen, sofern der Supervisor nichts anderes entscheidet.

## Legende

| Spalte | Bedeutung |
|--------|-----------|
| `status` | `konform` · `teilweise` · `abweichend` · `N/A` |
| `priority` | `must_fix` · `should_fix` · `could_fix` · `ignore` |
| `qm_relevant` | `ja` · `nein` · `optional` — ob QMToolV7-Muster für AREV2 sinnvoll ist |
| `cursor_allowed` | Was Agents in diesem Bereich dürfen |
| `cursor_forbidden` | Was Agents hier nicht tun dürfen |
| `gate_needed` | Ob ein automatisierter Architecture-Gate-Test fehlt (`ja`/`nein`) |

---

## 1. Dokumentation & Governance

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| DOC-01 | P0/P1/P2-Dokumenthierarchie mit kanonischem Index | `docs/` nur mit Matrix+Plan; kein `AGENTS.md`, kein `CONTRIBUTING.md`, kein P0-Index | abweichend | should_fix | ja | `docs/QMTOOLV7_STRUCTURE_COMPARISON_MATRIX.md` | `docs/DOCS_CANONICAL_INDEX.md` | `AGENTS.md` und minimale Architektur-Doku anlegen | P0-Docs aus QMToolV7 kopieren ohne Anpassung | nein | Phase 3: `AGENTS.md` + `docs/ARCHITECTURE.md` |
| DOC-02 | Onboarding-Map und klare Regelquellen | Nur `README.md` mit `api.py`-Regel, ohne Enforcement | teilweise | should_fix | ja | `README.md` | `CONTRIBUTING.md`, `AGENTS.md` | README um Verweis auf Matrix/Plan ergänzen | README-Regeln als erfüllt behandeln ohne Gate | nein | README als P2 behandeln; Gates in Phase 3 |

---

## 2. Verzeichnislayout

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| LAYOUT-01 | Fachmodule unter `modules/`, Plattform unter `qm_platform/` | Fachmodule unter `src/` (14 Ordner), kein `qm_platform/` | abweichend | could_fix | optional | `src/parser/`, `src/jobcontroller/` | `modules/documents/`, `qm_platform/` | Bei `src/` bleiben: Konvention dokumentieren | Umbenennung `src/`→`modules/` ohne Supervisor-Entscheid | nein | Default: `src/` belassen |
| LAYOUT-02 | Adapter in `interfaces/cli`, `interfaces/pyqt`, `src/backend` | Adapter als Root-`main*.py`, `gui_min_ext.py`, `rule_editor/` | abweichend | should_fix | ja | `main02.py`, `worker_main.py`, `watchdog_main.py`, `rule_editor_main.py`, `gui_min_ext.py` | `interfaces/cli/`, `interfaces/pyqt/` | Schrittweise `interfaces/` einführen | Business-Logik in Adapter verschieben | ja | Phase 2 optional |
| LAYOUT-03 | Backend-Transport-Host `src/backend/` | Kein HTTP-Backend | N/A | ignore | nein | — | `src/backend/api.py` | — | Backend ohne Anforderung einführen | nein | Nicht umsetzen |
| LAYOUT-04 | Runtime-Daten außerhalb Repo oder neben EXE | `jobs/`, `output/`, `locks/`, `rules/` im Projektbaum; `ARE_HOME` für portable Roots | teilweise | could_fix | optional | `src/runtime/paths.py`, `jobs/`, `output/final/` | `qm_platform/runtime/paths.py`, `storage/` | `ARE_HOME`-Semantik beibehalten | Harte Pfade ohne `resolve_app_root` | nein | Bereits tragfähig für Desktop-Tool |

---

## 3. Public API (`api.py`)

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| API-01 | Jedes Modul: öffentliche Grenze nur über `api.py` | 12 von 14 `src/`-Modulen haben `api.py` | teilweise | must_fix | ja | `src/parser/api.py` … `src/rulesuite/api.py` | `modules/documents/api.py` | Fehlende `api.py` ergänzen (`runtime`, `testui`) | Neue interne Importpfade ohne `api.py` | ja | Phase 1: `runtime/api.py` |
| API-02 | `runtime/` und Hilfsmodule ohne Public API | `src/runtime/` und `src/testui/` ohne `api.py`, direkt importiert | abweichend | must_fix | ja | `src/runtime/config.py`, `src/testui/helpers.py` | `qm_platform/runtime/` (intern, via Container) | `runtime/api.py` als dünne Facade | Direktimport `runtime.file_lock` aus Adaptern nach Phase 1 | ja | Phase 1 |
| API-03 | README: `api.py` = eine Delegationszeile | `rulesuite/api.py` ~25 Funktionen; `jobqueue/api.py` mit Factory `_queue()` | abweichend | could_fix | optional | `src/rulesuite/api.py`, `src/jobqueue/api.py` | `modules/documents/api.py` (größere Facade) | Große Facade dokumentiert akzeptieren | README-Regel wörtlich erzwingen ohne Nutzen | nein | Supervisor-Entscheidung |
| API-04 | `contracts.py` für DTOs, Re-Export über `api.py` | DTOs in `model.py`, teils direkt importiert über Modulgrenzen | abweichend | should_fix | ja | `src/contentsplitter/model.py`, `src/jobqueue/model.py` | `modules/documents/contracts.py` | `AssayDescriptor`, `QueueJob` über `api`/`contracts` exportieren | `*.model` aus fremden Modulen importieren | ja | Phase 1 |
| API-05 | Deprecated API entfernen oder klar markieren | `contentsplitter/api.py` behält Legacy-Funktionen | teilweise | could_fix | optional | `src/contentsplitter/api.py` | — | Legacy mit Deprecation-Hinweis belassen | Legacy still entfernen ohne Tests | nein | Nach Gate-Phase |

---

## 4. Boundary-Verstöße

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| BOUND-01 | Kein Cross-Module-Import von Interna/Models | `jobcontroller.py` importiert `contentsplitter.model.AssayDescriptor` | abweichend | must_fix | ja | `src/jobcontroller/jobcontroller.py:73` | `tests/interfaces/test_architecture_gates.py` | Re-Export in `contentsplitter/api.py` oder `contracts.py` | Model-Import in Orchestrator belassen | ja | Phase 1 |
| BOUND-02 | Kein Cross-Module-Import von Interna/Models | `rulesuite/rulesuite.py` importiert `contentsplitter.model.AssayDescriptor` | abweichend | must_fix | ja | `src/rulesuite/rulesuite.py:18` | `tests/interfaces/test_architecture_gates.py` | Wie BOUND-01 | — | ja | Phase 1 |
| BOUND-03 | Kein Cross-Module-Import von Interna/Models | `watchdog/service.py` und `watchdog/api.py` importieren `jobqueue.model.QueueJob` | abweichend | must_fix | ja | `src/watchdog/service.py:8`, `src/watchdog/api.py:5` | `tests/interfaces/test_architecture_gates.py` | `QueueJob` über `jobqueue.api` re-exportieren | — | ja | Phase 1 |
| BOUND-04 | Adapter importieren nur Public APIs | `watchdog_main.py` importiert `watchdog.service.WatchdogService` direkt | abweichend | must_fix | ja | `watchdog_main.py:7` | `interfaces/cli/commands/*.py` (nur `api.py`) | Auf `watchdog.api` umstellen | Service-Klasse in Main importieren | ja | Phase 1 |
| BOUND-05 | Tests: Adapter-Gates strikt; Modultests dürfen Interna | Tests importieren `jobqueue.queue`, `ruleresolver.ruleresolver`, diverse `*.model` | teilweise | should_fix | ja | `tests/test_jobqueue.py`, `tests/test_rulesuite.py`, `tests/test_watchdog.py` | `tests/modules/` (Interna in Modultests ok) | Architecture-Gate nur für Root-Adapter + `rule_editor/` | Alle Test-Interna-Imports verbieten | ja | Phase 3: Gate für Adapter; Modultests Interna ok |
| BOUND-06 | Cross-Module nur über `api.py` für Typen/Services | `extractor`, `writer`, `dbwriter` importieren Peer-Typen via `*.api` | teilweise | could_fix | optional | `src/writer/writer.py`, `src/dbwriter/dbwriter.py` | `modules/documents/api.py` Re-Exports | Peer-`api`-Imports beibehalten | Direktimport fremder `model.py` in Services | nein | Akzeptables Muster |
| BOUND-07 | Runtime nur über Public Facade | `jobcontroller`, `jobqueue` importieren `runtime.file_lock` direkt | abweichend | should_fix | ja | `src/jobcontroller/jobcontroller.py:9`, `src/jobqueue/queue.py:11` | `qm_platform/runtime/` intern | Nach `runtime/api.py` umstellen | — | ja | Phase 1 mit API-02 |

---

## 5. Service-Schicht

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| SVC-01 | Business-Logik in Services, nicht in Adaptern | Pipeline in `src/*`; GUIs rufen `api` auf; `gui_min_ext` orchestriert mehrere APIs | teilweise | should_fix | ja | `src/jobcontroller/jobcontroller.py`, `gui_min_ext.py` | `modules/documents/service.py` | Orchestrator-Logik in `jobcontroller` belassen | PDF-Pipeline in Tkinter-Code | nein | GUI nur delegieren |
| SVC-02 | Facade (`service.py`) + Ops-Split (`*_ops.py`) | Ein Service-Klasse pro Modul-Datei (`Parser`, `JobController`, `RuleSuite`) | abweichend | ignore | nein | `src/parser/parser.py`, `src/jobcontroller/jobcontroller.py` | `modules/documents/service.py`, `artifact_ops.py` | Kleine Module nicht künstlich splitten | — | nein | Nur bei Wachstum splitten |
| SVC-03 | Use-Case-Orchestrierung service-seitig | `JobController.submit` serialisiert gesamte Pipeline + State | konform | ignore | ja | `src/jobcontroller/jobcontroller.py` | `modules/documents/workflow_use_cases.py` | Transaktions-/Lock-Grenzen im Controller halten | Pipeline-Schritte in Adapter | nein | Stärke beibehalten |
| SVC-04 | Domain-Events nach erfolgreicher Persistenz | Kein Event-Bus; Job-JSON `steps[]` als Trace | teilweise | could_fix | optional | `jobs/<job_id>.json` | `modules/documents/eventing.py` | Informelles Trace dokumentieren | Event-Bus ohne Anforderung | nein | Phase 4 optional |

---

## 6. Adapter (CLI / GUI / Headless)

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| ADAPTER-01 | Dedizierter `interfaces/cli` mit dünnem Entry | `interfaces/cli/` vorhanden; Root-Entrys delegieren fuer `main02.py`, `rule_suite_main.py`, `rules_validate_main.py` | teilweise | should_fix | ja | `interfaces/cli/e2e.py`, `interfaces/cli/rule_suite.py`, `interfaces/cli/rules_validate.py` | `interfaces/cli/main.py` | `interfaces/cli/` schrittweise | Neue Logik in `main*.py` | ja | Phase 2 weitgehend umgesetzt |
| ADAPTER-02 | Ein kanonischer CLI-Entry + Subcommands | Mehrere unabhängige Entry-Skripte | abweichend | could_fix | optional | alle `*_main.py` | `interfaces/cli/main.py` | Wrapper belassen bis Phase 2 | Big-Bang-Merge ohne Tests | nein | Phase 2 |
| ADAPTER-03 | PyQt als GUI-Source-of-Truth | Tkinter: `rule_editor/`, `gui_min_ext.py` | N/A | ignore | nein | `rule_editor/`, `gui_min_ext.py` | `interfaces/pyqt/` | Tkinter beibehalten | PyQt-Migration ohne Auftrag | nein | Nicht umsetzen |
| ADAPTER-04 | Adapter importieren nur `*.api` (+ ggf. `contracts`) | Root-Adapter, `gui_min_ext.py` und `rule_editor/` nutzen nur `src.*.api` fuer fremde Produktionsmodule | konform | must_fix | ja | `tests/test_architecture_gates.py`, `gui_min_ext.py`, `rule_editor/*.py` | `interfaces/cli/commands/documents_commands.py` | Nur `*.api` in Adaptern | `runtime.*` direkt nach Phase 1 | ja | Erledigt mit Architecture-Gate |
| ADAPTER-05 | CLI-first vor GUI | Harness + Headless + Rule-CLI vorhanden; GUI für Distribution | teilweise | could_fix | optional | `main02.py`, `worker_main.py`, `gui_min.py` | `AGENTS.md` CLI-first | Neue Features zuerst CLI/Headless | GUI-only Features | nein | Bei neuen Features beachten |

---

## 7. Platform / Runtime

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| PLATFORM-01 | `qm_platform` mit Bootstrap, Container, Lifecycle | Kein DI-Container; Services werden inline instanziiert (`JobController()`) | abweichend | ignore | nein | alle `src/*/api.py` | `qm_platform/runtime/bootstrap.py` | Inline-Instanziierung beibehalten | Container ohne Mehrwert | nein | Nicht umsetzen |
| PLATFORM-02 | Settings-Registry mit Governance-Klassen | Env-Vars `ARE_*` via `load_runtime_config()` | teilweise | could_fix | optional | `src/runtime/config.py` | `qm_platform/settings/` | Env-Config dokumentieren | Settings-Registry ohne Multi-Modul-Bedarf | nein | Phase 4 optional |
| PLATFORM-03 | Event-Bus + `EventEnvelope` | Kein Event-Bus | N/A | ignore | nein | — | `qm_platform/events/event_bus.py` | — | — | nein | Nicht umsetzen |
| PLATFORM-04 | Audit-Logger für Compliance-Aktionen | Kein Audit-Log | N/A | ignore | nein | — | `qm_platform/logging/audit_logger.py` | — | — | nein | Nicht umsetzen |
| PLATFORM-05 | Zentrale Pfadauflösung / App-Home | `resolve_app_root()`, `ARE_HOME`, PyInstaller-Fallback | teilweise | could_fix | ja | `src/runtime/paths.py` | `qm_platform/runtime/paths.py` | Pattern beibehalten und testen | Harte cwd-Annahmen | nein | Bereits gut abgedeckt (`test_runtime_paths.py`) |

---

## 8. Auth / Rollen / Lizenz

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| AUTH-01 | Auth in Service-Schicht | Kein Auth | N/A | ignore | nein | — | `modules/usermanagement/` | — | Auth ohne Anforderung | nein | Nicht umsetzen |
| AUTH-02 | Rollen/QMB-Semantik | Keine Rollen | N/A | ignore | nein | — | `docs/MODULE_INTEGRATION_POLICY.md` §4 | — | — | nein | Nicht umsetzen |
| AUTH-03 | Lizenz-Guard für Module | Keine Lizenzierung | N/A | ignore | nein | — | `qm_platform/licensing/` | — | — | nein | Nicht umsetzen |

---

## 9. Events / Audit / Nachweis

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| EVID-01 | Domain-Events + Auditlog gekoppelt | Job-State `steps[]`, Queue `attempts`/`last_error` | teilweise | could_fix | optional | `jobs/*.json`, `jobs/queue/*.json` | `docs/AP-016_*` (QMToolV7) | Trace-Felder dokumentieren | QM-Audit-Stack übernehmen | nein | Ausreichend für Tool-MVP |
| EVID-02 | Correlation/Causation-IDs | Nur `job_id` (sha256-PDF, 16 hex) | N/A | ignore | nein | `src/jobcontroller/api.py` Docstring | `docs/AP-014_*` (QMToolV7) | — | — | nein | Nicht umsetzen |

---

## 10. Tests & Gates

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| TEST-01 | Tests nach Schicht: `tests/modules`, `platform`, `interfaces`, `e2e_cli` | Flache `tests/` (18 Dateien), 1:1 zu Modulen | abweichend | could_fix | optional | `tests/test_parser.py` … | `tests/modules/`, `tests/e2e_cli/` | Umbenennung nur mit Gate-Absicherung | Big-Bang-Test-Umzug | nein | Optional Phase 3 |
| TEST-02 | Automatisierte Architecture-Gates | `tests/test_architecture_gates.py` prueft Wrapper-Duenne und `src.*.api`-Grenzen fuer Adapter | konform | must_fix | ja | `tests/test_architecture_gates.py` | `tests/interfaces/test_architecture_gates.py` | AREV2-angepasste Gates anlegen | QMToolV7-Gates 1:1 kopieren | ja | Erledigt |
| TEST-03 | Build-Preflight mit Tests | `packaging/build_onedir.py` → pytest + Rules-Integrität | konform | ignore | ja | `packaging/build_onedir.py` | `packaging/build_onedir.py` (QMToolV7) | Preflight beibehalten | Build ohne Tests | nein | Stärke beibehalten |
| TEST-04 | Separater Integritäts-Gate | `rules_validate_main.py` + Build-Preflight | konform | ignore | ja | `rules_validate_main.py` | — | — | — | nein | Stärke beibehalten |
| TEST-05 | Kein erfundener Linter/Typechecker | Nur pytest (wie QMToolV7) | konform | ignore | ja | `requirements.txt` | `AGENTS.md` | pytest als Gate | ruff/mypy ohne Projektentscheid | nein | Beibehalten |

---

## 11. Packaging

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| PKG-01 | Onedir-Build + ZIP | `packaging/build_onedir.py` → `dist_output/`, ZIP | konform | ignore | ja | `packaging/build_onedir.py` | `packaging/build_onedir.py` | Kanonischen Build nutzen | Onefile als Default | nein | Beibehalten |
| PKG-02 | Bundle-Import-Verifikation | `REQUIRED_IMPORTS` in Preflight + `_verify_bundle` | konform | ignore | ja | `packaging/build_onedir.py` | `packaging/verify_bundle_imports.py` | Importliste pflegen | — | nein | Bei neuen Modulen erweitern |
| PKG-03 | Secret-Marker-Scan im Bundle | `SECRET_NAME_MARKERS` in Build | konform | ignore | ja | `packaging/build_onedir.py` | `packaging/verify_customer_bundle.py` | — | Secrets ins Bundle | nein | Beibehalten |
| PKG-04 | Ein kanonischer Build-Pfad | `packaging/build_onedir.py` ist dokumentiert als kanonischer Build; Legacy-`.spec` ist explizit deprecated | teilweise | should_fix | ja | `README.md`, `AnalyzerResultExtractorV2.spec`, `packaging/build_onedir.py` | `packaging/build_onedir.py` | `.spec` als deprecated markieren oder entfernen | Zwei konkurrierende Build-Wege ohne Doku | nein | Dokumentiert, finaler Gate-Status nach Build |
| PKG-05 | `pyproject.toml` mit Python-Pin | Minimales `pyproject.toml` fuer editable install und Build-Metadaten vorhanden | konform | could_fix | optional | `pyproject.toml`, `requirements.txt` | `pyproject.toml` | pyproject optional einführen | — | nein | Erledigt fuer Embedding-Vorbereitung |

---

## 12. Benennung & Konventionen

| id | qmtoolv7_rule | arev2_current | status | priority | qm_relevant | evidence_arev2 | evidence_qmtoolv7 | cursor_allowed | cursor_forbidden | gate_needed | restructure_hint |
|----|---------------|---------------|--------|----------|-------------|----------------|-------------------|----------------|------------------|-------------|------------------|
| NAME-01 | Modulordner lowercase snake_case | `assaychooser`, `jobcontroller`, `rulesuite` usw. | konform | ignore | ja | `src/*/` | `modules/incident_management/` | — | — | nein | Beibehalten |
| NAME-02 | Modul-Skeleton: `module.py`, `wiring.py`, `*_ops.py` | Nicht vorhanden; flache Modulstruktur | abweichend | ignore | nein | `src/parser/parser.py` | `modules/documents/module.py`, `wiring.py` | Flache Struktur bei kleinen Modulen | Künstliches Skeleton | nein | Nicht umsetzen |
| NAME-03 | Domain-Events `domain.<module>.<event>.v1` | Keine Domain-Events | N/A | ignore | nein | — | `modules/documents/eventing.py` | — | — | nein | Nicht umsetzen |

---

## Prioritäts-Zusammenfassung

### must_fix (9 Zeilen)

`API-01`, `API-02`, `API-04`, `BOUND-01`, `BOUND-02`, `BOUND-03`, `BOUND-04`, `ADAPTER-04`, `TEST-02`

### should_fix (10 Zeilen)

`DOC-01`, `DOC-02`, `LAYOUT-02`, `BOUND-05`, `BOUND-07`, `SVC-01`, `ADAPTER-01`, `PKG-04`

### could_fix / optional (12 Zeilen)

`LAYOUT-01`, `LAYOUT-04`, `API-03`, `API-05`, `BOUND-06`, `SVC-04`, `ADAPTER-02`, `ADAPTER-05`, `PLATFORM-02`, `EVID-01`, `TEST-01`, `PKG-05`

### ignore / N/A (14 Zeilen)

`LAYOUT-03`, `SVC-02`, `ADAPTER-03`, `PLATFORM-01`, `PLATFORM-03`, `PLATFORM-04`, `AUTH-01`–`AUTH-03`, `EVID-02`, `TEST-03`–`TEST-05`, `PKG-01`–`PKG-03`, `NAME-01`–`NAME-03` (teilweise konform)

---

## Modul-Inventar AREV2 (14 Module)

| Modul | api.py | Interne Kern-Dateien | Anmerkung |
|-------|--------|----------------------|-----------|
| `parser` | ja | `parser.py`, `model.py` | Pipeline Start |
| `normalizer` | ja | `normalizer.py` | — |
| `assaychooser` | ja | `assaychooser.py`, `model.py` | — |
| `ruleresolver` | ja | `ruleresolver.py`, `validator.py`, `model.py` | Validator nicht in Service-Klasse |
| `contentsplitter` | ja | `contentsplitter.py`, `model.py` | Legacy-APIs in `api.py` |
| `extractor` | ja | `extractor.py`, `model.py` | — |
| `writer` | ja | `writer.py`, `model.py` | Excel + File-Lock |
| `dbwriter` | ja | `dbwriter.py`, `model.py` | SQLite inline-Schema |
| `jobcontroller` | ja | `jobcontroller.py`, `model.py` | Pipeline-Orchestrator |
| `jobqueue` | ja | `queue.py`, `model.py` | JSON-Queue |
| `watchdog` | ja | `service.py` | — |
| `rulesuite` | ja | 8 interne Dateien | Größte Facade |
| `runtime` | **nein** | `config.py`, `paths.py`, `file_lock.py` | Infrastruktur |
| `testui` | **nein** | `helpers.py` | GUI-Helfer |

---

## Verwendung für Cursor-Agents

1. Vor Umbauarbeiten: betroffene `id`(s) in dieser Matrix nachschlagen.
2. Nur `cursor_allowed` befolgen; `cursor_forbidden` ist hart.
3. Nach Änderungen an Boundaries: `gate_needed=ja`-Zeilen mit Test abdecken.
4. Zeilen mit `qm_relevant=nein` oder `status=N/A` nicht „reparieren“, außer der Supervisor entscheidet anders.
5. Umsetzungsreihenfolge: siehe [`RESTRUCTURE_PLAN_EXTERNAL.md`](RESTRUCTURE_PLAN_EXTERNAL.md).
