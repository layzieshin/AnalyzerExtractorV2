# AP-6 RuleSuite Authoring Workflow Review

Stand: 2026-07-10  
Scope: Tkinter Rule Editor + Wizard + `src/rulesuite/api.py` — **kein** QMTool/PyQt, **keine** Assay-Bereinigung, **keine** Dedupe-/Excel-Migration.

Referenzen: [`DOCUMENTATION/09_rulesuite_authoring_workflow.md`](../DOCUMENTATION/09_rulesuite_authoring_workflow.md), [`docs/AP3_ACCEPTANCE.md`](AP3_ACCEPTANCE.md).

---

## Kurzfazit

**Taugt die RuleSuite für die Testphase: _teilweise_.**

Der Authoring-Kern ist vorhanden: Blank- und Similar-Modus erzeugen Drafts mit sechs Pflicht-Headern, Kandidaten bleiben bis zur manuellen Übernahme im Draft, Regex-Treffer werden im Wizard gelb markiert, Aktivierung schreibt produktive Rules und ergänzt den Index mit Bestätigungsdialog. API und Wizard-Flows sind durch 86 pytest-Tests und `rules_validate` abgesichert.

Für den operativen Alltag fehlen jedoch **P0-relevante GUI-Belastbarkeit**: Extract-Preview landet nur im Log-Tab, `var_draft_path` und `current_draft_path` können auseinanderlaufen, und die Aktivierung kann trotz fehlender PDF-Treffer der Pflichtfelder fortgesetzt werden (Editor erlaubt „Trotzdem fortfahren“ nach reiner Strukturvalidierung). Ohne kleine Tkinter-Fixes (AP-6.1) ist das Risiko von Fehlaktivierungen in der Testphase erhöht.

---

## Gate-Ergebnisse

| Gate | Befehl | Ergebnis |
|---|---|---|
| pytest | `.\.venv\Scripts\python.exe -m pytest -q` | **86 passed** (exit 0) |
| rules_validate | `.\.venv\Scripts\python.exe rules_validate_main.py` | **grün** — keine `missing_files`, `key_mismatches`, `content_errors`, `orphan_rulesets` |

Matrix-Preview wurde für AP-6 **nicht** als Pflicht-Gate gefahren (bewusst out of scope).

---

## Workflow-Review

| Workflow-Schritt | Aktueller Zustand | Problem/Lücke | Risiko | Empfohlene kleine Maßnahme | Priorität |
|---|---|---|---|---|---|
| **1. Neuer Assay von Grund auf** | Wizard-Modus `blank` → `create_draft_from_template()` legt alle 6 `REQUIRED_HEADER_FIELD_KEYS` (`DATUM`, `ZEIT`, `ANWENDER`, `PLATTE`, `CHARGE`, `VALIDATION`) im Draft an (`rules/drafts/{key}.draft.json`). Confirm-Step: Regex einzeln testen (`_locate_and_highlight`), Treffer als `TREFFER: {value}` + gelbe Markierung. Pflichtfelder im Wizard: `btn_remove_field`/`chk_required` deaktiviert, `required=True` erzwungen. | **Editor:** `FieldsMixin.on_remove_field()` ruft `remove_field()` ohne Schutz für Contract-Keys auf — Pflichtheader können außerhalb des Wizards gelöscht werden. **Defekt:** `wizard_ui.py` bindet `Feld entfernen` an `_on_remove_field`, Methode existiert nicht — Button im Confirm-Step ist **disabled**, daher kein Normalpfad-Crash; trotzdem technische Inkonsistenz für AP-6.1. Frische Template-Drafts scheitern an `validate_draft`, solange Regexe leer — strukturell korrekt, vom Pflichtfeld-Fortschritt zu trennen. | mittel (Editor-Löschung); niedrig (fehlender Handler) | Editor: Löschen von `REQUIRED_HEADER_FIELD_KEYS` blockieren. Wizard: toten Handler entfernen oder Stub mit Hinweis (AP-6.1). | P1 (Editor-Guard); P1 (Handler-Wiring bereinigen) |
| **2. Neuer Assay ähnlich wie Vorlage** | Modus `similar` → `create_draft_from_ruleset()` mit `resolve_required_headers_from_source()` (Legacy-Alias → canonical). Zusatzfelder via `read_candidate_fields` / `check_candidates`; Schritt 4: Test (`_on_test_candidate`), Übernehmen (`adopt_candidate_field` → nur Draft), Verwerfen (session-only `_dismissed_candidates`). Kein Schreiben nach `rules/*.json` bis explizite Aktivierung. | Kandidaten in Schritt 2 nur Leseliste (Preview), Adopt erst in Schritt 4 — erwartbar, aber nicht sofort intuitiv. Dismiss-Liste nicht persistent über Wizard-Neustart. | niedrig | Kurzer Hinweistext in Schritt 2; optional später Dismiss in Draft-Meta (out of scope AP-6). | P2 |
| **3. Draft speichern/laden** | Drafts unter `rules/drafts/` (atomisches JSON-Schreiben bei Feld-Updates). Editor: `current_draft_path` ist operativer State; `var_draft_path` im Entry-Feld; Laden nur via `on_load_draft_into_editor()`. Autosave alle 45s wenn `current_draft_path` gesetzt. Wizard speichert inkrementell; Abbruch behält Draft. | **`var_draft_path` ist editierbar**, `current_draft_path` wird nicht automatisch synchronisiert — Nutzer kann Pfad im Entry ändern, während Editor weiter alten Draft bearbeitet/speichert. Kein sichtbarer „ungespeichert“-Indikator trotz `_dirty`-Tracking. | **hoch** (falscher Draft / Datenverlust wahrgenommen) | Entry readonly machen oder bei Pfad-Änderung Warnung + Reload erzwingen; Dirty-Label neben Autosave-Zeitstempel. | **P0** (Pfad-Sync); P1 (Dirty-Feedback) |
| **4. Aktivieren / produktiv machen** | Editor `on_activate()`: `_quick_validate` (strukturell) → Diff-Anzahl → `askyesno` → `activate_draft` (Update, überschreibt bestehende `rules/{file}`) oder `activate_new_draft` (neu + append `index.json`). Duplikat-/Dateiname-Checks in API. Wizard blockiert **direkte** Aktivierung ohne `all_confirmed`, wenn Beispiel-PDF geladen wurde. | **Strukturvalidierung ≠ Pflichtfeld-Treffer:** `validate_draft` prüft JSON/Regex-Syntax, nicht ob die 6 Header im PDF treffen. Editor erlaubt nach Fehlern **„Trotzdem fortfahren?“** auch für Aktivierung — damit kann ein strukturell valider, funktional leerer Draft live gehen. `activate_draft`/`activate_new_draft` kennen keinen PDF-Kontext; blindes `check_required_fields` in `activate_draft` wäre ohne Assay-Text unvollständig. | **hoch** | **Editor-Readiness:** Bei geladenem Beispiel-PDF `check_required_fields` vor Activate erzwingen (kein Override). Optional separate Readiness-API `(draft_path, assay_text?)` — nicht in `activate_draft` ohne Text. Default Wizard-Finish: „Im Editor öffnen“. | **P0** (Activate-Gate im Editor); P1 (Wizard-Default) |
| **5. Preview / Testlauf** | Editor `on_preview()` → `preview_extract()` liefert vollständiges Dict (`detected_assays`, `used_ruleset`, `lot_id`, `dedupe_key`, `data`). Wizard: Regex-Einzeltreffer im Textpanel, **kein** Extract-Preview im Wizard. | Erfolg wird als **JSON-Dump nur im Log-Tab** geschrieben (`_finish_preview_success`); Nutzer muss Tab wechseln, keine Feld-Tabelle. Fehler: `[ERROR] preview: …` im Log — verständlich, aber leicht übersehen. Kein dedizierter Unit-Test für `preview_extract`-Output. | **hoch** (Usability); mittel (Testlücke) | Kompaktes Preview-Panel (Pflicht-Header, `VALIDATION`, `lot_id`, `dedupe_key`, Fehlerliste) im Validate-Tab. `preview_extract`-Test in `test_rulesuite.py`. Wizard-Finish: optional Extract-Preview. | **P0** (Preview-Anzeige); P1 (Tests + Wizard) |
| **6. UX/GUI** | 5-Schritt-Wizard mit Statuszeile; Editor mit Tabs (Draft, Felder, Meta, PDF, Validate). Regex-Treffer auch im Felder-Tab (`txt_field_preview`). Guide-Hilfen (`?`-Buttons) vorhanden. | Unklare Button-Differenz: „Pflichtfeld prüfen“ / „Erneut testen“ / „Passt - weiter“. Klick auf Pflichtfeld-Liste in Schritt 2 springt zu Confirm ohne explizites „Weiter“. Zwei Preview-UX-Pfade (Wizard vs. Editor Felder-Tab). Listbox-lastige UI, wenig Fortschrittsvisualisierung. | mittel | Tooltips/Button-Umbenennung; Finish-Default Editor; Schritt-Indikator; provisorischen Log-only-Preview-Pfad durch Panel ersetzen (siehe AP-6.1). | P1 (Labels/Flow); P2 (Komfort) |

### Detailantworten auf Review-Fragen

**1. Von Grund auf** — Ja / Ja / Ja (Wizard) / Ja (Wizard) / **Nein** (normaler Editor ohne Contract-Guard).

**2. Ähnlich wie Vorlage** — Ja (Alias-Normalisierung) / Ja / Ja (Test/Übernehmen/Verwerfen) / Ja (nur Draft bis Activate).

**3. Draft** — Pfad im Entry sichtbar, aber **State kann inkonsistent sein** / **nicht garantiert konsistent** / **Ja, falscher Pfad möglich** / Autosave-Zeitstempel ja, explizites „ungespeichert“ nein.

**4. Aktivieren** — Struktur ja, PDF-Treffer nein / Diff+Dialog ja / Index bei neuem Assay ja / Überschreiben mit Dialog ja / **Lücke klar:** `validate_draft` ≠ Pflichtfeld-Treffer; Lösung über Editor-Readiness mit Beispieltext, nicht blind in `activate_draft`.

**5. Preview** — Ja (Editor) / alle Keys in JSON ja, **UI lesbar nein** / nur Log / Fehler im Log mit Hint.

**6. UX** — siehe Tabelle; minimale Testphase-Fixes = AP-6.1 (Pfad, Preview-Panel, Activate-Readiness, Handler).

---

## Wichtigste Risiken

1. **Falscher Draft-State** durch editierbares `var_draft_path` ohne Reload — Speichern/Aktivieren am falschen oder nicht geladenen Draft.
2. **Aktivierung ohne PDF-Treffer** — Editor-Override nach struktureller Validierung; produktives Ruleset ohne funktionierende Pflicht-Extraktion.
3. **Preview nur im Log** — Extract-Ergebnis wird in der Testphase übersehen; Fehlinterpretation von „Preview erfolgreich“.
4. **Pflicht-Header im Editor löschbar** — Contract nur im Wizard geschützt, nicht im Felder-Tab.
5. **API vs. Wizard-Gate asymmetrisch** — Wizard blockiert direkte Activate bei fehlenden Treffern; Editor-Pfad nicht gleichwertig.

---

## Nächste Arbeitspakete

| Paket | Inhalt | Ziel |
|---|---|---|
| **AP-6.1 Editor-Belastbarkeit** | `var_draft_path`/`current_draft_path`-Sync; Preview-Panel statt Log-only; Activate-Readiness bei geladenem PDF (ohne „Trotzdem“); `_on_remove_field`-Wiring; Editor-Guard für 6 Pflicht-Keys | P0-Fixes für testphasen-taugliches Authoring |
| **AP-6.2 Tests / API-Support** | Unit-Tests für `preview_extract`-Shape; `activate_draft` Success-Path; optionale `check_authoring_readiness(draft_path, assay_text?)` (getrennt von `activate_draft`) | Regression-Schutz ohne PDF-Pflicht in Activate-API |
| **AP-6.3 Wizard-Finish / UX** | Default Finish → „Im Editor öffnen“; klarere Button-Texte; optional Extract-Preview im Finish-Step; Hinweis Kandidaten Schritt 2→4 | Geringere Fehlbedienung, kein Bypass der Editor-Review |

---

## Architektur (Kurz)

```
rule_editor_main.py
  ├── NewRulesetWizard (wizard.py)     → create_draft_from_* / check_required_fields / adopt_candidate_field
  ├── DraftMixin (draft_actions.py)    → laden, current_draft_path
  ├── ReleaseMixin (release_actions.py)→ validate_draft, preview_extract, activate_*
  └── ManageMixin (manage_actions.py)  → Wizard starten, Aktivierung delegieren

src/rulesuite/api.py → RuleSuite (rulesuite.py, required_fields.py, candidates.py)
```

Draft-Artefakte: `rules/drafts/` (seit B3.5 in `.gitignore`).

---

## Abgrenzung (bewusst nicht bewertet)

- Bestehende `rules/*.json` bereinigen oder Regex korrigieren
- Dedupe-Policy / Excel-`column_mapping`-Migration
- Matrix als Authoring-Gate
- QMTool / PyQt-Integration
