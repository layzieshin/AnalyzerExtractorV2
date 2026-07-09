# RuleSuite Authoring Workflow

Dieses Dokument beschreibt den aktuellen Workflow fuer die Regelerstellung.

## Ziel
- RuleSet-JSONs pro Assay kontrolliert bearbeiten.
- Regex-Aenderungen gegen echte Test-PDFs pruefen.
- Draft und produktive Regeldatei trennen.

## Einstiegspunkte
- Visueller Editor: `rule_editor_main.py`
- CLI: `rule_suite_main.py`
- API: `src/rulesuite/api.py`
- Implementierung: `src/rulesuite/rulesuite.py`

## Gefuehrter Anlage-Wizard (Neues Regelset)
- Start ueber den Button `Neues Regelset (gefuehrt)...` in der Kachel `Regelset-Verwaltung` (Tab `Draft`).
- Eigenes modales Fenster mit 5 Schritten (Zurueck/Weiter/Abbrechen):
  1. Grunddaten: `assay_key` + `assay_name`; Wahl zwischen
     - "Aehnlich wie ein bestehendes Regelset" (alle Regeln der Vorlage werden uebernommen) oder
     - "Von Grund auf neu" (sechs Pflicht-Headerfelder aus `rules/template.json`: `DATUM`, `ZEIT`, `ANWENDER`, `PLATTE`, `CHARGE`, `VALIDATION` + `lot_rule` und passende `column_mapping`-Eintraege; jeweils `required: true`).
       Fehlende Pflichtfelder im Template werden im Draft mit leerer Regex angelegt — Regex-Inhalte pflegt der Chef manuell.
       Optionale Header wie `Haltbarkeit` und `FILE_NAME` gehoeren nicht mehr zur Pflichtbasis.
  2. Beispiel-PDF waehlen und Text laden (mit Volltext-Fallback, wenn der Assay-Block nicht getrennt werden kann).
     Danach erscheint eine Pflichtfeld-Checkliste (Treffer / Regex fehlt / kein Treffer / Fehler).
  3. Pflichtfelder bestaetigen (Focus Mode): Feld waehlen, Regex manuell pflegen, Treffer im Text pruefen;
     Buttons `Pflichtfeld pruefen`, `Passt - weiter`, `Erneut testen`, `Suche ab Cursor-Zeile`, `Suche ab vorheriger Zeile`.
     Pflichtfelder koennen nicht entfernt werden. Direkte Aktivierung bleibt blockiert, solange nicht alle Pflichtfelder Treffer haben.
  4. Eigene Felder hinzufuegen (optional): Regex-Test mit Treffer-Markierung + Zugriff auf die Regex-Bibliothek.
  5. Abschluss: Zusammenfassung + Validierung + Pflichtfeld-Status; Draft im Editor oeffnen (empfohlen) oder direkt aktivieren (nur bei vollstaendigen Pflichtfeld-Treffern).
- Abbruch laesst den bisherigen Stand als Draft unter `rules/drafts/` liegen.

## Pflichtfeld-Vertrag (neue Assays)

Sechs Header-Pflichtfelder fuer "von Grund auf neu":

| Feld | Rolle |
|---|---|
| `DATUM` | Datum im Ergebnisblock |
| `ZEIT` | Uhrzeit im Ergebnisblock |
| `ANWENDER` | Anwender/Kuerzel |
| `PLATTE` | Plattenname |
| `CHARGE` | Charge/Lot als Ergebnisfeld (eigenes Feld, auch wenn `lot_id` denselben Wert nutzt) |
| `VALIDATION` | Validierungstext (kein Boolean) |

API:

- Konstante: `REQUIRED_HEADER_FIELD_KEYS` in `src/rulesuite/api.py`
- Draft aus Template: `create_draft_from_template()` — garantiert alle sechs Felder (`required: true`); fehlende Template-Eintraege werden mit leerer Regex angelegt
- Struktureller Check: `check_required_fields(draft_path, assay_text)` — nutzt `locate_fields`, erzeugt keine Regex-Inhalte

Status pro Pflichtfeld:

| Status | Bedeutung |
|---|---|
| `confirmed` | Regex vorhanden und Treffer im Text |
| `missing_regex` | Feld im Draft, Regex leer |
| `miss` | Regex vorhanden, kein Treffer |
| `error` | Regex oder `search_from` fehlerhaft |
| `missing_field` | Pflichtfeld fehlt im Draft (sollte nach Template-Draft nicht vorkommen) |

Zeilennummern dienen nur als Orientierung und `search_from`-Hilfe (`{"line": N}` oder `{"after": "..."}`), nicht als Primaervertrag.

Siehe auch: `docs/AP2_ACCEPTANCE.md` (Abgrenzung zu pre-existing `rules/`-Diffs im Worktree).

## Regex-Bibliothek
- Popup mit gaengigen Regex-Bausteinen und Mini-Erklaerung in einfachem Deutsch.
- Zugang: Button `Regex-Bibliothek...` im Felder-Tab, `Bib...` im Markierungs-Panel sowie in den Wizard-Schritten 3 und 4.
- `Einfuegen` setzt das Muster an der Cursorposition in das Regex-Feld.

## Regelset-Verwaltung
- Kachel `Regelset-Verwaltung` im Tab `Draft`: Liste aller registrierten Rulesets (Key, Name, Datei, Felderzahl, Status).
- `Ansehen/Bearbeiten` laedt das Regelset als Draft in den Editor (Aenderungen wirken erst nach Aktivierung).
- `Loeschen...` mit doppelter Bestaetigung (Ja/Nein-Dialog + exaktes Eintippen des Assay-Keys):
  - Eintrag wird aus `rules/index.json` entfernt.
  - Die JSON-Datei wird nach `rules/trash/<name>.<timestamp>.json` verschoben (wiederherstellbar, nichts wird endgueltig geloescht).
  - `template.json` und nicht registrierte Dateien sind geschuetzt.

## Empfohlener Editor-Flow
1. `python rule_editor_main.py` starten.
2. Ueber Tabs/Schnellnavigation arbeiten:
   - `Draft`
   - `PDF / Assay-Text`
   - `Felder`
   - `Meta & Excel`
   - `Validierung & Aktivierung`
   - `Log`
3. Draft erstellen:
   - aus aktivem Assay
   - oder neues leeres Assay
   - oder aus bestehendem Assay ableiten.
4. Test-PDF laden und Assay-Block extrahieren.
   - Im Tab `PDF / Assay-Text` kann die Markierungs-Ansicht ein-/ausgeblendet werden.
   - Text markieren, `Regex aus Auswahl` nutzen, Feldname setzen und `Neues Feld anlegen` oder `Feld uebernehmen`.
   - `Suche ab: Zeile` bzw. `Suche ab: Zeile davor` setzen den Suchstart aus der Auswahl.
   - Bestehende Felder erscheinen farbig; Klick auf Markierung/Legende laedt das Feld ins Bearbeitungsformular.
5. Felder bearbeiten (key/regex/required/search_from), `lot_rule`, `dedupe_fields`, `excel_rules.column_mapping` pflegen.
6. Regex mit Highlight im Assay-Block testen (optional mit `regex_group=0` fuer Gesamttreffer).
   - Jeder Testlauf erscheint zusaetzlich in einer Ergebnistabelle im Felder-Tab.
   - Ergebnis/Kontext stehen direkt im Felder-Tab im Mini-Preview.
   - Das Log nutzt das 3-Zeilen-Schema:
     - `getesteter regex "/.../"`
     - `Kontext: ...`
     - `Ergebnis: ...`
7. Draft validieren (Fehlerliste im Editor beachten).
8. Draft aktivieren:
   - bestehendes Assay aktualisieren oder
   - neues Assay aktivieren (inkl. `rules/index.json`-Eintrag).

## UX-/Safety-Verbesserungen
- Enter beschleunigt Feld-Workflow (`Feld uebernehmen`) bzw. Regex-Test.
- Esc setzt das Feldformular schnell zurueck.
- Undo/Redo fuer Draft-Aenderungen (`Ctrl+Z`, `Ctrl+Y`).
- Feld-Duplizieren und Feld-Reihenfolge per Up/Down.
- Vor `Preview` und `Aktivieren` erfolgt ein Quick-Validierungscheck.
- Vor Aktivierung kann ein Draft-vs-Active-Diff angezeigt werden.
- Batch-Regex-Check zeigt Treffer/Misses ueber alle Felder.
- Auto-Save sichert Draft-Aenderungen periodisch mit Zeitstempel.
- Hybrides Help-UX:
  - einklappbare Kurz-/Langhilfe pro Hauptbereich (`Mehr/Weniger`)
  - Info-Buttons (`i`) fuer vertiefte Erklaerungen zu Bereichen/Funktionen
- Hybrid-Navigation:
  - Tabs fuer die Hauptbereiche
  - Schnellnavigation (Schritte 1-6) fuer direkten Bereichswechsel
  - Step-by-Step Popup mit "Zum passenden Tab"-Sprung
- Kontext-Hinweise in der Hint-Zeile geben bei typischen Fehlern konkrete "Wie beheben"-Tipps.
- Feld-Fuehrung im Felder-Tab: Beim Auswaehlen eines Feldes zeigt eine Hinweiszeile, ob es eine Fundstelle im geladenen Beispiel-PDF gibt; `Im PDF-Tab zeigen/hinterlegen` springt in den PDF-Tab und hebt den Treffer hervor bzw. fuehrt zum Markieren einer fehlenden Stelle.
- Aktivierungsdialog zeigt explizit, ob ein bestehendes Assay ueberschrieben oder ein neues Assay angelegt wird.
- Guardrails fuer neue Assays:
  - `assay_key`-Duplikate werden blockiert.
  - Regelnamen-Kollisionen (auch case-insensitive) werden blockiert.
  - ungueltige Dateinamen aus `assay_name` werden abgelehnt.

## CLI-Draft-Flow (alternativ)
1. Draft aus aktiver Regel erzeugen:
   - `python rule_suite_main.py create-draft --assay-key "(6bd7)"`
2. Felder anzeigen:
   - `python rule_suite_main.py list-fields --assay-key "(6bd7)"`
3. Feld-Regex im Draft anpassen:
   - `python rule_suite_main.py set-regex --draft-path <draft> --field-key test --regex "Test:\\s*(\\w+)"`
4. Extraktion preview gegen Test-PDF:
   - `python rule_suite_main.py preview --pdf input/sample_single.pdf --assay-key "(6bd7)" --draft-path <draft>`
5. Draft aktivieren:
   - `python rule_suite_main.py activate-draft --assay-key "(6bd7)" --draft-path <draft>`

## Sicherheitsgelander
- Drafts liegen getrennt unter `rules/drafts/`.
- Produktive Rulesets werden erst per Aktivierung ersetzt.
- Neue Assays werden nur bei erfolgreicher Validierung in `rules/index.json` eingetragen.
