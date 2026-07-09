# AP-2 Acceptance Note — Rules Worktree Isolation

Date: 2026-07-09

## Scope of AP-2 (RuleSuite Focus Structure)

AP-2 changed only authoring/tooling code and documentation. It did **not** intend to modify active production rules.

Typical AP-2 paths:

- `src/rulesuite/required_fields.py`
- `src/rulesuite/templates.py`
- `src/rulesuite/api.py`
- `rule_editor/wizard.py`
- `rule_editor/wizard_ui.py`
- `tests/test_rulesuite.py`
- `tests/test_rule_editor_wizard_focus.py`
- `tests/test_embedding_smoke.py`
- `DOCUMENTATION/09_rulesuite_authoring_workflow.md`
- `docs/AP2_ACCEPTANCE.md`

## Pre-existing uncommitted rules changes (not AP-2)

`git status` shows tracked modifications (`M`) under `rules/` that are separate from AP-2 tooling code:

- `rules/index.json` — additional active entry for `(661f)` / `Anti-dsDNA-NcX IgG.json`
- multiple active `rules/*.json` files — column mapping / field normalization edits
- `rules/README.md` — authoring note update

AP-2 implementation files (`src/rulesuite/`, `rule_editor/`, related tests/docs) are currently **untracked** (`??`) in this worktree. None of the AP-2 code paths write to active `rules/*.json` or `rules/index.json` during pytest/gates.

These `rules/` diffs are **worktree dirt** from separate rule authoring work. They must not be attributed to AP-2 unless explicitly committed as a separate change set.

## Verification command

```powershell
git diff --name-only -- rules
git diff --name-only -- src/rulesuite rule_editor tests docs DOCUMENTATION
```

AP-2 acceptance for "no active rules JSON changes by AP-2" means:

1. AP-2 code paths do not write to `rules/*.json` or `rules/index.json` during tests/gates.
2. Any current `git diff` under `rules/` is documented here as pre-existing local state.
3. Final production rule updates remain a separate, explicit Chef/authoring step.

## Gates (AP-2)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe rules_validate_main.py
.\.venv\Scripts\python.exe rules_matrix_main.py --mode preview
```

Expected at time of writing:

- pytest: all green
- rules_validate: green against current worktree (including pre-existing rules edits)
- matrix preview: `0 green / 5 yellow / 3 red`, exit code 1 accepted (sample coverage gaps)
