# AREV2 Known Issues

This list tracks operational risks for the Tkinter/standalone test phase. It is not a QMTool integration plan.

| Issue | Symptom | Workaround | Priority |
|---|---|---|---|
| DONE without output check | `SKIPPED: already_done` even when Excel was deleted after a previous run | Force rerun for the PDF; verify or recreate output files | P1 |
| Partial writes | Earlier assays may already be written when a later assay fails | Use matrix preview before E2E; inspect `partial_writes` and rerun intentionally | P1 |
| Split is case-sensitive | `assay_name` must match normalized PDF text exactly | Check active ruleset names in Rule Editor and use block dumps for diagnosis | P2 |
| Excel lock has no TTL | `.excel_writer.lock` can block writes after abrupt termination | Close Excel/processes; remove stale lock manually after verification | P2 |
| SQLite runs after Excel in `both` mode | Excel can be OK while SQLite write fails | Use `rules_matrix_main.py --mode e2e` for release checks | P2 |
| Dedupe fallback | Most rulesets rely on implicit fallback fields | Define explicit dedupe policy per ruleset | P1 |
| Rules are structurally green but functionally uneven | `rules_validate_main.py` passes while extraction matrix has yellow/red rows | Use `rules_matrix_main.py --mode preview` as functional check | P0 |
| Sample coverage incomplete | Active assays `(3ccc)`, `(6a74)`, `(661f)` are not detected in current sample PDFs | Add representative PDFs or mark coverage gap in baseline | P0 |

Recommended gate during stabilization:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe rules_validate_main.py
.\.venv\Scripts\python.exe rules_matrix_main.py --mode preview
```

The matrix exits with code 1 while red rows exist. That is expected until sample coverage and rule policy are resolved.
