# AP-4 Reference Assays

## Ausgangslage

| Item | Wert |
|---|---|
| Datum | 2026-07-10 |
| Commit-Stand | `1a13151` |
| Analyse-Basis | Aktueller Worktree (keine AP-4-Änderungen an `rules/`; lokale uncommitted Rules-Diffs im Worktree waren bei der Laufzeit vorhanden) |

### Gates

| Gate | Ergebnis | Exit |
|---|---|---|
| `pytest -q` | **86 passed** | 0 |
| `rules_validate_main.py` | **OK** (alle Integritätslisten leer) | 0 |
| `rules_matrix_main.py --mode preview` | **0 green / 5 yellow / 3 red** | 1 (akzeptiert) |

Matrix-Report (frisch erzeugt):

- JSON: [`output/verification/rule_matrix_20260710_131857.json`](../output/verification/rule_matrix_20260710_131857.json)
- MD: [`output/verification/rule_matrix_20260710_131857.md`](../output/verification/rule_matrix_20260710_131857.md)

Preview-Evidenz (AP-4-Lauf):

- [`output/verification/ap4_preview_6bd7.json`](../output/verification/ap4_preview_6bd7.json)
- [`output/verification/ap4_preview_5f03.json`](../output/verification/ap4_preview_5f03.json)
- [`output/verification/ap4_preview_c4d1.json`](../output/verification/ap4_preview_c4d1.json)
- [`output/verification/ap4_preview_3c84.json`](../output/verification/ap4_preview_3c84.json)
- [`output/verification/ap4_preview_42d4.json`](../output/verification/ap4_preview_42d4.json)

### Hinweis: Zwei Bewertungssichten

**Matrix `required_fields`** prüft nur Felder mit `required: true` im jeweiligen Ruleset (z. B. bei 25-OH nur `test`; bei Legacy-Assays `plate_name`, `date`, `time`, `user`, `lot_id`, `lot_expiry_yymmdd`).

**Canonical-Header-Sicht (AP-2-Vertrag)** bewertet unabhängig die sechs Pflicht-Header `DATUM`, `ZEIT`, `ANWENDER`, `PLATTE`, `CHARGE`, `VALIDATION` — bei Legacy-Keys über Alias:

| Canonical | Legacy-Alias |
|---|---|
| DATUM | `date` |
| ZEIT | `time` |
| ANWENDER | `user` oder `ANWENDER` |
| PLATTE | `plate_name` oder `PLATTE` |
| CHARGE | `lot_id` oder `CHARGE` oder `preview.lot_id` |
| VALIDATION | kein Alias |

Bewertung Canonical: **grün** = Wert in `preview.data` (oder `lot_id` für CHARGE); **gelb** = Feld im Ruleset, Wert leer/null; **rot** = Pflichtfeld im Ruleset-Modell nicht vorhanden.

---

## 25-OH Vitamin D (`(6bd7)`)

| Item | Wert |
|---|---|
| PDF | `input/sample_single.pdf` |
| ruleset_file | `25-OH Vitamin D.json` |
| erkannt | **ja** (`detected_assays`: `["(6bd7)"]`) |
| block_split | **ja** (Matrix `block: green`) |
| ruleset_resolved | **ja** (`used_ruleset`: `25-OH Vitamin D.json`) |

### Canonical Pflichtfelder

| Feld | Ruleset-Key | Wert (Preview) | Status |
|---|---|---|---|
| DATUM | `date` | `14.01.2026` | grün |
| ZEIT | `time` | `20:42:24` | grün |
| ANWENDER | `ANWENDER` | `Fischer` | grün |
| PLATTE | `PLATTE` | `20260114_VitD` | grün |
| CHARGE | `CHARGE` | `E251127AF` (= `lot_id`) | grün |
| VALIDATION | `VALIDATION` | `null` | gelb |

### Matrix-Sicht (sample_single)

| Kriterium | Status |
|---|---|
| detected | green |
| block | green |
| lot_id | green (`E251127AF`) |
| required_fields | green (nur `test` ist `required: true`) |
| dedupe | yellow (fallback) |
| optional_missing | siehe unten |

**Issues:** `dedupe_fallback`, `optional_fields_missing`

### Zusatzfelder

**Treffer:** `test`, `Haltbarkeit`, `UG_PCQ1`, `ZIEL_PCQ1`, `OG_PCQ1`, `SOLL_S1`, `IST_S1`, `S1_MIN`, `IST_S2`, `SOLL_S3`, `IST_S3`

**Missing (null in Preview / Matrix optional_missing):** `VALIDATION`, `UG_NCQ1`, `ZIEL_NCQ1`, `OG_NCQ1`, `PCQ1`, `NCQ1`, `SOLL_S2`, `S2_MIN`, `FILE_NAME`

### Dedupe

| Item | Wert |
|---|---|
| Policy | **fallback** (`dedupe_fields` nicht gesetzt) |
| Fallback-Felder (Extractor) | `test`, `date`, `time` (Reihenfolge in `data`) |
| dedupe_key | `(6bd7)\|E251127AF\|C:\ProgramData\Euroimmun_Analyzer_I\Assays\25-OH Vitamin D.asy (6bd7)\|14.01.2026\|20:42:24` |

### Excel mapping

`column_mapping` deckt alle extrahierten Keys ab (inkl. Legacy `time`/`date`). Für befüllte `data`-Keys sind Spalten vorhanden.

**Auffällig (nicht blockierend):**

- `FILE_NAME`: Platzhalter-Regex, erwartbar leer
- `NCQ1`/`PCQ1`/`UG_NCQ1`/…: Mapping vorhanden, Werte fehlen im Sample-Text → Spalten würden leer bleiben
- Gemischte Legacy/canonical Header-Keys im Ruleset (`date`/`time` neben `ANWENDER`/`PLATTE`/`CHARGE`)

Historische E2E-Evidenz: `output/final/25-OH_Vitamin_D.xlsx` (siehe `docs/TESTBASELINE.md`).

### Matrix gesamt

**yellow** — begründet durch `dedupe_fallback` und `optional_fields_missing` im erkannten Pfad `input/sample_single.pdf` (detect/block/lot_id/required_fields dort green).

Die Nicht-Erkennung in `input/sample_multi.pdf` ist **erwartbar** (Assay gehört nicht in diese PDF) und **kein eigener Matrix-Issue** sowie **keine AP-4-Auffälligkeit**, solange `(6bd7)` in `sample_single.pdf` erkannt wird.

### Befund-Kategorie

| Anteil | Kategorie |
|---|---|
| Pipeline/Tooling | Kein Abbruch — detect, split, resolve, extract OK |
| Rule-Problem | Dedupe nur fallback; gemischte Header-Key-Konvention |
| Sample-Coverage | Nicht-Erkennung in `sample_multi` erwartbar — **nicht** Ursache des Matrix-yellow; kein AP-4-Befund |
| Regex-Freigabe nötig | **VALIDATION** (gelb); optional **NCQ1/PCQ1**-Block und **SOLL_S2/S2_MIN** |

---

## Anti-TPO IgG (`(5f03)`)

| Item | Wert |
|---|---|
| PDF | `input/sample_multi.pdf` |
| ruleset_file | `Anti-TPO IgG.json` |
| erkannt | **ja** |
| block_split | **ja** |
| ruleset_resolved | **ja** |

### Canonical Pflichtfelder

| Feld | Ruleset-Key | Wert | Status |
|---|---|---|---|
| DATUM | `date` | `15.01.2026` | grün |
| ZEIT | `time` | `21:26:16` | grün |
| ANWENDER | `user` | `Fischer` | grün |
| PLATTE | `plate_name` | `20260115TpoPr3MpoCen` | grün |
| CHARGE | `lot_id` | `E250829AV` | grün |
| VALIDATION | — | — | **rot** (nicht im Ruleset) |

### Matrix-Sicht (sample_multi)

detect/block/lot_id/required_fields: **green**; dedupe: **yellow**; Issues: `dedupe_fallback`; keine `optional_missing`.

### Zusatzfelder

**Treffer:** `test`, `lot_expiry_yymmdd` — alle Ruleset-Felder extrahiert.

**Missing:** keine (alle definierten Felder befüllt).

### Dedupe

**fallback** — Key: `(5f03)|E250829AV|...\Anti-TPO IgG.asy (5f03)|15.01.2026|21:26:16`

### Excel mapping

Vollständig für extrahierte Legacy-Keys (`plate_name`, `date`, `time`, `user`, `test`, `lot_id`, `lot_expiry_yymmdd`).

### Matrix / Befund

**yellow** | Rule-Problem: kein `VALIDATION`, Dedupe fallback, Legacy-Schema | Tooling OK | Regex-Freigabe: nicht für Pflicht-Extraktion nötig (Schema-Gap vor Regex)

---

## Anti-PR3-hn-hr IgG (`(c4d1)`)

| Item | Wert |
|---|---|
| PDF | `input/sample_multi.pdf` |
| ruleset_file | `Anti-PR3-hn-hr IgG.json` |
| erkannt | **ja** |
| block_split | **ja** |
| ruleset_resolved | **ja** |

### Canonical Pflichtfelder

| Feld | Status | Wert-Kurz |
|---|---|---|
| DATUM | grün | `15.01.2026` |
| ZEIT | grün | `21:26:16` |
| ANWENDER | grün | `Fischer` |
| PLATTE | grün | `20260115TpoPr3MpoCen` |
| CHARGE | grün | `E251027AG` |
| VALIDATION | **rot** | nicht im Ruleset |

### Matrix-Sicht

Wie TPO: alles green außer dedupe yellow; `dedupe_fallback`.

### Zusatzfelder

Alle 7 Ruleset-Felder mit Treffer; keine Missing.

### Dedupe

**fallback** — `(c4d1)|E251027AG|...|15.01.2026|21:26:16`

### Excel mapping

Vollständig für extrahierte Felder.

### Befund

**yellow** | Rule-Problem (Legacy-Schema, Dedupe fallback) | Tooling OK

---

## Anti-MPO IgG (`(3c84)`)

| Item | Wert |
|---|---|
| PDF | `input/sample_multi.pdf` |
| ruleset_file | `Anti-MPO IgG.json` |
| erkannt | **ja** |
| block_split | **ja** |
| ruleset_resolved | **ja** |

### Canonical Pflichtfelder

| Feld | Status | Wert-Kurz |
|---|---|---|
| DATUM | grün | `15.01.2026` |
| ZEIT | grün | `21:26:16` |
| ANWENDER | grün | `Fischer` |
| PLATTE | grün | `20260115TpoPr3MpoCen` |
| CHARGE | grün | `E251027AI` |
| VALIDATION | **rot** | nicht im Ruleset |

### Matrix-Sicht

Wie TPO/PR3: green bis auf dedupe yellow.

### Zusatzfelder

Alle definierten Felder mit Treffer.

### Dedupe

**fallback** — `(3c84)|E251027AI|...|15.01.2026|21:26:16`

### Excel mapping

Vollständig.

### Befund

**yellow** | Rule-Problem (Legacy-Schema, Dedupe fallback) | Tooling OK

---

## Anti-Centromeres IgG (`(42d4)`)

| Item | Wert |
|---|---|
| PDF | `input/sample_multi.pdf` |
| ruleset_file | `Anti-Centromeres IgG.json` |
| erkannt | **ja** |
| block_split | **ja** |
| ruleset_resolved | **ja** |

**CenPB-Hinweis:** CenPB ist im aktuellen Rule-/Index-Modell kein eigener Assay; keine separate Bewertung. Bewertung erfolgt nur über Anti-Centromeres IgG `(42d4)`.

### Canonical Pflichtfelder

| Feld | Ruleset-Key | Wert | Status |
|---|---|---|---|
| DATUM | `date` | `15.01.2026` | grün |
| ZEIT | `time` | `21:26:16` | grün |
| ANWENDER | `ANWENDER` | `Fischer` | grün |
| PLATTE | `PLATTE` | `20260115TpoPr3MpoCen` | grün |
| CHARGE | `CHARGE` | `E250804AU` | grün |
| VALIDATION | `VALIDATION` | `Validationskriterien erfüllt` | grün |

### Matrix-Sicht (sample_multi)

detect/block/lot_id/required_fields: green; dedupe: yellow; optional_missing: `SOLL_S3`, `FILE_NAME`.

### Zusatzfelder

**Treffer:** `test`, `Haltbarkeit`, `UG_PCQ1`, `ZIEL_PCQ1`, `OG_PCQ1`, `UG_NCQ1`, `ZIEL_NCQ1`, `OG_NCQ1`, `PCQ1`, `NCQ1`, `SOLL_S1`, `IST_S1`, `S1_MIN`, `SOLL_S2`, `IST_S2`, `S2_MIN`, `IST_S3`

**Missing:** `SOLL_S3`, `FILE_NAME`

### Dedupe

**fallback** (`dedupe_fields: []` explizit leer) — `(42d4)|E250804AU|...|15.01.2026|21:26:16`

### Excel mapping

Vollständig für befüllte Keys; auffällig nur `SOLL_S3`/`FILE_NAME` ohne Wert (FILE_NAME erwartbar leer).

### Befund

**yellow** | Rule-Problem: Dedupe fallback | Regex-Freigabe optional: `SOLL_S3` | Tooling OK

---

## Ausgeklammerte Matrix-Rotfälle

| Assay | Key | Grund |
|---|---|---|
| Anti-Nucleosomes IgG | `(3ccc)` | `not_detected_in_selected_pdfs` |
| Rheumatoid Factor IgA | `(6a74)` | `not_detected_in_selected_pdfs` |
| Anti-dsDNA-NcX IgG | `(661f)` | `not_detected_in_selected_pdfs` |

Diese Rotfälle sind **reine Sample-Coverage** in den beiden Referenz-PDFs — kein AP-4-Referenzumfang und kein Tooling-Regressionssignal für die fünf geprüften Assays.

---

## Klassifikation

| Kategorie | Definition |
|---|---|
| **Tooling-Problem** | detect / split / resolve / extract / write bricht ab |
| **Rule-Problem** | Dedupe nicht explizit, canonical Header fehlt im Schema, Mapping-Inkonsistenz |
| **Sample-Coverage** | Assay nicht in gewählter PDF |
| **Regex-Freigabe nötig** | Feld im Ruleset, Pipeline läuft, Wert fehlt trotz erwartbarem PDF-Inhalt |

---

## Empfehlung

### 1. Als Referenz verwendbar?

| Assay | Eignung |
|---|---|
| **Anti-Centromeres IgG `(42d4)`** | **Beste Referenz** für vollständigen modernen Ruleset-Pfad: alle 6 canonical Header grün, reiche Zusatzfeld-Abdeckung, Multi-PDF-E2E historisch DONE |
| **25-OH Vitamin D `(6bd7)`** | **Gute Single-PDF-Referenz** für End-to-End-Tooling; Canonical 5/6 grün, `VALIDATION` gelb, Dedupe fallback, optionale NCQ-Lücken |
| **TPO / PR3 / MPO** | **Legacy-Referenz** für Minimal-Extraktion (7 Felder); Tooling OK, aber canonical `VALIDATION` rot (Schema-Gap) und Dedupe fallback |

### 2. Nächste fachliche Chef-Freigabe (konkret)

| Priorität | Ruleset | Feld(er) | Begründung |
|---|---|---|---|
| P1 | `25-OH Vitamin D.json` | `VALIDATION` | Canonical Pflichtfeld definiert, Preview `null` — Regex/`search_from` prüfen |
| P2 | `25-OH Vitamin D.json` | `NCQ1`, `UG_NCQ1`, `ZIEL_NCQ1`, `OG_NCQ1`, `PCQ1` | Optional missing im Referenz-PDF |
| P3 | `Anti-Centromeres IgG.json` | `SOLL_S3` | Optional missing trotz `IST_S3`-Treffer |
| P4 | Alle fünf Referenz-Rulesets | `dedupe_fields` explizit setzen | Derzeit durchgängig fallback — Rule-Policy, keine Pipeline-Änderung |
| P5 | TPO / PR3 / MPO | `VALIDATION` + canonical Header-Migration | Schema-Gap, nicht primär Regex |

### 3. Reine Sample-Coverage

Matrix-Rot **nur** für `(3ccc)`, `(6a74)`, `(661f)` — keine Bewertung im AP-4-Scope erforderlich, bis passende PDFs vorliegen.

---

*AP-4 abgeschlossen: nur diese Dokumentdatei neu erstellt; keine Rules-, Pipeline- oder GUI-Änderungen.*
