# Working Agreement – Phase 3: AssayChooser

## Modul
src/assaychooser/

## Verantwortung
- Erkennung von Assays im Dokument
- Unterstützung von Multi-Assay PDFs

## Öffentlicher Contract (api.py)
- detect_assays(doc: ParsedDocument, rules_index) -> list[AssayMatch]

## Matching
- contains(assay_name)

## Output
AssayMatch:
- assay_key
- assay_name
- occurrence_index (immer 1)
