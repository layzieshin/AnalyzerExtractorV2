# Working Agreement – Phase 5: Extractor

## Modul
src/extractor/

## Verantwortung
- Fachliche Extraktion pro Assay

## Öffentlicher Contract (api.py)
- extract_runrow(doc, assay_match, ruleset) -> RunRow

## RunRow – Pflichtfelder
- assay_key
- lot_id
- dedupe_key
- data (Spalten -> Werte)

## Garantien
- Genau eine Zeile pro Assay und PDF
