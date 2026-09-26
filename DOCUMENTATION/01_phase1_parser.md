# Working Agreement – Phase 1: Parser

## Modul
src/parser/

## Verantwortung
- Positional / line-basierte PDF-Extraktion
- Keine Normalisierung
- Keine Fachlogik

## Öffentlicher Contract (api.py)
- parse(pdf_path: str) -> ParsedDocument

## ParsedDocument – Muss enthalten
- source_path: str
- pages: list[ParsedPage]
- meta: dict

ParsedPage:
- page_number: int
- lines: list[str]

## Garantien
- deterministisch
- zeilenstabil

## Tests
- Tests dürfen und sollen in Phase 1 neu angelegt werden
- sample_single.pdf
- sample_multi.pdf
