# PDF Ergebnis-Extractor (Projekt)

- Windows 11 Zielumgebung
- `src/` ist Project Root (in PyCharm markieren)
- Public APIs existieren ausschließlich in `src/<module>/api.py`
- `api.py` enthält keine Logik außer **eine Delegationszeile** auf interne Klassen (one-class-one-file).
- `main.py` und `main02.py` sind Harnesses für den End-to-End Lauf (immer `sample_single.pdf` + `sample_multi.pdf`)
- Tests liegen unter `/tests` (pytest)

## Start
1. Lege PDFs ab:
   - `input/sample_single.pdf`
   - `input/sample_multi.pdf`
2. Pflege `rules/index.json` und die referenzierten RuleSet JSONs unter `rules/`
3. Install:
   - `pip install -r requirements.txt`
4. Run:
   - `python main02.py` (empfohlen für bessere CLI-Übersicht)
