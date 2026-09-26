# Working Agreement – Phase 6: Writer

## Modul
src/writer/

## Verantwortung
- Append-only Excel-Write
- Deduplikation
- Crash-Sicherheit

## Öffentlicher Contract (api.py)
- write_runrow(runrow, ruleset, output_dir)

## Regeln
- pro Assay eine Datei
- pro Lot ein Sheet
- dedupe_key verhindert Duplikate
- staging + commit unter globalem Excel-Lock
