# AREV2 Agent Guide

Entry point for AI-assisted and human work in **AnalyzerResultExtractorV2**.  
Step-by-step workflow and the per-layer verification matrix live in [`.cursor/rules/00-agent-workflow.mdc`](.cursor/rules/00-agent-workflow.mdc) (single source of truth for *how* to work and *which commands* to run).

Agent **execution contract** (roles, cost limits, stop statuses, gate reports): [`docs/AGENT_GOVERNANCE.md`](docs/AGENT_GOVERNANCE.md). Numeric limits and role models are normative in [`.cursor/agent-system.json`](.cursor/agent-system.json). This file does not restate those limits. Architecture boundaries remain here and in [`.cursor/rules/01-architecture-boundaries.mdc`](.cursor/rules/01-architecture-boundaries.mdc).

## Search before create (mandatory)

Before adding an entrypoint, CLI command, UI tab/button, public API, or parallel helper path:

1. **Search existing owners** — root `*_main.py`, `interfaces/cli/`, `interfaces/headless/`, `interfaces/tk/`, `rule_editor/`, `gui_min*.py`, and the relevant `src/*/api.py`.
2. **Extend, do not fork** — add subcommands to `interfaces/cli/rule_suite.py`, views/actions to the product shell in `interfaces/tk/test_app.py` (`AnalyzerDesktopApp` / `VIEW_KEYS`), legacy tab actions via `SECTION_KEYS` only when `ARE_LEGACY_UI` is active, or methods on existing services behind `api.py`. Do not add similarly named buttons, menus, flows, or root scripts.
3. **No new public surfaces without scope** — no new root `*_main.py`, wrapper scripts, `*_helper.py` export paths, or duplicate CLI mains unless the task explicitly requests it.
4. **Stop on overlap** — if two docs or two code paths could own the same user intent, stop and ask. Do not change behavior silently.

## Architecture essentials

Business logic lives in `src/<module>/` (pipeline, rules, queue, runtime helpers). Adapters live in root thin wrappers, `interfaces/`, `gui_min*.py`, and `rule_editor/`. Production code crosses module boundaries only via `src/<module>/api.py`. Adapters may import `src.*.api` and local adapter/UI packages, not foreign `model.py`, `service.py`, `helpers.py`, `config.py`, `paths.py`, or `file_lock.py`. Runtime paths/config from adapters only through `src.runtime.api`. Tkinter stays; no PyQt migration. `src/` stays `src/` (not `modules/`). There is no HTTP backend host in this repo.

## Entrypoints (discovered inventory)

| Role | Script / command | Delegates to |
|------|------------------|--------------|
| **Production UI (field trial)** | `test_app_main.py` | `interfaces/tk/test_app.py` → default `AnalyzerDesktopApp`; `LegacyTestApp` via `ARE_LEGACY_UI` |
| **Packaging EXE entry** | `test_app_main.py` | same (see `packaging/build_onedir.py`) |
| **Rule Editor UI** | `rule_editor_main.py` | `rule_editor/*` (+ `src.rulesuite.api`, `src.runtime.api`) |
| **Headless watch / worker** | `watchdog_main.py`, `worker_main.py` | `interfaces/headless/` |
| **CLI rule suite** | `rule_suite_main.py` | `interfaces/cli/rule_suite.py` |
| **CLI rules integrity** | `rules_validate_main.py` | `interfaces/cli/rules_validate.py` |
| **CLI rule matrix** | `rules_matrix_main.py` | `interfaces/cli/rules_matrix.py` |
| **E2E harness** | `main02.py` | `interfaces/cli/e2e.py` |
| **Minimal E2E harness** | `main.py` | `src.jobcontroller.api.submit` (legacy direct submit) |
| **Legacy smoke GUI** | `gui_min.py`, `gui_min_ext.py` | direct `src.*.api` (no queue-first UX) |
| **Build** | `packaging/build_onedir.py` | PyInstaller onedir + ZIP (not a product feature entry) |

No `__main__.py` packages. CLI subcommands for rule authoring are defined in `interfaces/cli/rule_suite.py` only — extend that file, do not add a second rule CLI entry.

## Public API surfaces

Nineteen modules expose `src/<name>/api.py`: `parser`, `normalizer`, `assaychooser`, `ruleresolver`, `contentsplitter`, `extractor`, `writer`, `dbwriter`, `jobcontroller`, `jobqueue`, `watchdog`, `rulesuite`, `runtime`, `testui`, `assaycandidate`, `resultstore`, `processing`, `application`, `ingestion`. UI formatting/presenters for adapters: `src/testui/api.py`. Embedding contract: [`docs/EMBEDDING.md`](docs/EMBEDDING.md).

New views should orchestrate through `src.application.api` (four controllers: extraction, results, rules, settings). Queue/worker processing is owned by `src.processing.api`; `interfaces/common/queue_worker.py` is a thin compatibility re-export only.

## UI ownership (Tkinter)

- **Product shell** — `AnalyzerDesktopApp` in `interfaces/tk/test_app.py`; five views (`dashboard`, `results`, `rules`, `settings`, `diagnostics`). Default start via `test_app_main.py` → `run_entry` → `main()`. No duplicate shell.
- **Legacy Test-App** — `LegacyTestApp` (`TestApp`) in the same module; opt-in via `ARE_LEGACY_UI=1|true|yes`. Tabbed `BASE_SECTION_KEYS` UI; optional `ADMIN` tab only when `ARE_SHOW_ADMIN=1|true|yes` (legacy-only).
- **Rule Editor** — `rule_editor/` + `rule_editor_main.py`; reachable from the Rules view and via `ARE_START_RULE_EDITOR=1` on the packaged EXE.
- **Legacy smoke** — `gui_min*.py` for direct submit only; not the packaging entry.

## Environment

- OS/shell: **Windows / PowerShell** — chain commands with `;`, not `&&`.
- Python: `>=3.11` per `pyproject.toml`; use workspace venv: `.\.venv\Scripts\python.exe`.
- App root: respect `ARE_HOME`; use `src.runtime.api.resolve_app_root()` semantics (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)).
- No configured linter/typechecker — do **not** invent ruff/mypy/pre-commit steps.

## Quick verification (every structural change)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe rules_validate_main.py
```

Broader gates (adapter smoke, packaging, rule matrix): see [`.cursor/rules/00-agent-workflow.mdc`](.cursor/rules/00-agent-workflow.mdc).

## Scope restrictions

- Work only in this repository.
- Do **not** manually rewrite `rules/*.json`, `rules/index.json`, or `rules/template.json` unless the task explicitly requires it.
- Standalone entrypoints and `packaging/build_onedir.py` must keep working after adapter/packaging changes.
- Do not combine unrelated roadmap/work packages in one task.

## Canonical docs (priority)

| Priority | Document | Use for |
|----------|----------|---------|
| **P0** | [`README.md`](README.md) | Human onboarding, launch commands |
| **P0** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Pipeline, modules, entrypoints, runtime |
| **P0** | [`docs/AGENT_GOVERNANCE.md`](docs/AGENT_GOVERNANCE.md) | Agent execution contract (roles, limits, stops, gates) |
| **P0** | [`docs/TESTBASELINE.md`](docs/TESTBASELINE.md) | Expected pytest / matrix baseline |
| **P0** | [`docs/EMBEDDING.md`](docs/EMBEDDING.md) | Public API / embedding rules |
| **P1** | [`docs/DEDUPE_POLICY.md`](docs/DEDUPE_POLICY.md), [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) | Test interpretation |
| **P1** | [`docs/AP14_TEST_APP.md`](docs/AP14_TEST_APP.md), [`docs/AP17A_FIELD_TRIAL_PACKAGE.md`](docs/AP17A_FIELD_TRIAL_PACKAGE.md) | Test-App / field trial |
| **P2** | [`docs/QMTOOLV7_STRUCTURE_COMPARISON_MATRIX.md`](docs/QMTOOLV7_STRUCTURE_COMPARISON_MATRIX.md), [`DOCUMENTATION/*`](DOCUMENTATION/) | Benchmark / phase history — not onboarding defaults |

When docs disagree on **boundaries or verification**, P0 wins; ask if still unclear. When they disagree on **agent role limits or models**, `.cursor/agent-system.json` is normative.
