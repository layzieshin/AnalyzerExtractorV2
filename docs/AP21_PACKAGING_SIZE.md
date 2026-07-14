# AP-21: Packaging-Groesse und sichere Ausschluesse

## Ziel

Der Default-Build von `packaging/build_onedir.py` bleibt stabil und voll funktionsfaehig.
AP-21 ergaenzt:

- einen Groessenbericht nach dem Build,
- das sichere Entfernen von Tcl-`tzdata` aus dem Bundle,
- einen optionalen `--diet-experiment`-Modus fuer PyMuPDF-Sammelvarianten.

UPX und `--onefile` sind bewusst **nicht** Default, weil sie Smoke-/Support-Risiken erhoehen.

## Build-Befehle

Default (produktionsnah):

```powershell
.\.venv\Scripts\python.exe packaging\build_onedir.py
```

Optionaler Groessenvergleich:

```powershell
.\.venv\Scripts\python.exe packaging\build_onedir.py --diet-experiment
```

Beide Modi durchlaufen dieselbe Verify- und Smoke-Pipeline (`_verify_bundle`, `ARE_SMOKE_EXIT=1`).

## Was geaendert wird

### Tcl-`tzdata`-Prune

Nach PyInstaller entfernt `_prune_unneeded_bundle_payload()` nur:

`packaging/dist_output/AnalyzerResultExtractorV2/_internal/_tcl_data/tzdata`

Nicht entfernt werden `_tcl_data` insgesamt oder `_tk_data`. AREV2 nutzt Tkinter, aber keine Zeitzonen-Datenbank aus Tcl-`tzdata`. Der Bundle-Smoke-Test faengt Regressionen ab.

`_verify_bundle()` prueft, dass `tzdata` nach dem Prune nicht mehr existiert.

### Groessenbericht

`_print_size_report()` loggt nach `_write_zip()`:

- Onedir-Gesamtgroesse,
- groesste Top-Level-Eintraege unter `_internal`,
- Top-N groesste Dateien im Bundle,
- ZIP-Groesse.

### `--diet-experiment`

| Modus | `--collect-all` |
| --- | --- |
| Default | `fitz`, `pymupdf`, `openpyxl` |
| `--diet-experiment` | nur `openpyxl` |

Hidden Imports (`fitz`, `pymupdf`, `openpyxl`, `rule_editor_main`) bleiben in beiden Modi gesetzt.
Der Experiment-Modus dient dem Groessenvergleich, nicht dem produktiven Default.

## Groessen-Baseline

Messung nach erfolgreichem Default-Build (Python 3.14, PyInstaller 6.18, PyMuPDF 1.26.7):

| Kennzahl | Groesse |
| --- | --- |
| Onedir gesamt | 76.81 MB |
| ZIP | 32.90 MB |
| `tzdata`-Prune | 609 Dateien, 1.13 MB |
| Groesster Block `_internal` | `pymupdf` 44.63 MB |
| Groesste Einzeldatei | `mupdfcpp64.dll` 23.70 MB |

Typische Groessenblocker:

1. **PyMuPDF / fitz** – groesster Anteil unter `_internal` (DLLs, eingebettete Ressourcen).
2. **Python-Runtime und Abhaengigkeiten** – Standardbibliothek, `openpyxl`, Projektmodule.
3. **Tk/Tcl** – `_tk_data` und `_tcl_data` ohne `tzdata`.

Der `tzdata`-Prune spart typischerweise mehrere MB, aendert aber nicht den PyMuPDF-Anteil.

## Akzeptanz Default-Build

- Build laeuft durch.
- EXE-Smoke mit `ARE_SMOKE_EXIT=1` laeuft durch.
- ZIP wird erzeugt.
- `_internal/_tcl_data/tzdata` fehlt.
- Groessenbericht erscheint im Log.
- `rules_validate` im Preflight bleibt gruen.
