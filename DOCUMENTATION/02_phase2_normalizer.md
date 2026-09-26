# Working Agreement – Phase 2: Normalizer

## Modul
src/normalizer/

## Verantwortung
- Whitespace-Normalisierung innerhalb von Zeilen
- Zeilenumbrüche bleiben erhalten

## Öffentlicher Contract (api.py)
- normalize_lines(lines: list[str]) -> list[str]

## Garantien
- gleiche Anzahl Zeilen
- deterministisch
