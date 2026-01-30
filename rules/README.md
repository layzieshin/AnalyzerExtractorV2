QC:

* role_scope: OK
* assumptions: NONE
* rule_conflicts: NONE
* action_allowed: YES

Alles klar. Wir reden hier vom **RuleSet JSON pro Assay** (z. B. `Anti-TPO IgG.json`). Ich erkläre dir jetzt:

1. **Welche Teile es gibt** und **woher die Namen kommen** (`fields`, `key`, etc.)
2. **Warum `lot_rule` separat ist** und ob du es in `extract_rules` packen darfst
3. **Wie du neue Felder ergänzt** (inkl. Header-Felder als Beispiel)
4. **Ein besseres Template**, passend zu deinen echten Blocks

Ich beziehe mich dabei auf dein aktuelles `Anti-TPO IgG.json`  und auf den echten Block-Text aus `8fa223..._5f03_block.txt` .

---

## 1) Was ist ein RuleSet – und wofür sind `fields` und `key`?

Ein RuleSet ist **nur Konfiguration**, damit der Extractor ohne Code-Änderung weiß:

* **was** er aus dem Text holen soll
* **wie** er es im Text findet (Regex)
* **wie** es später in Excel heißen soll (Spaltenmapping)

### `extract_rules.fields`

Das ist eine Liste von “Feld-Definitionen”. Jede Definition sagt:

* `key`: interner Name des extrahierten Feldes (wird in `record.data[key]` gespeichert)
* `regex`: wie man den Wert aus dem Text zieht
* `required`: ob der Job **failen** soll, wenn das Feld nicht gefunden wird

Beispiel aus deinem aktuellen RuleSet :

* `key = "time"` → landet als `record.data["time"]`
* Der Writer kann dann diese Spalte schreiben (über `column_mapping`)

**Merke:**
`key` ist *dein* “Datenbank-Spaltenname im Record”. Excel-Spaltenname kann gleich sein – oder über `column_mapping` abweichen.

---

## 2) `lot_rule`: Muss das extra sein? Kann das in `extract_rules`?

### Warum `lot_rule` separat ist (guter Grund)

`lot_id` hat in deiner Architektur eine **Sonderrolle**:

* es bestimmt **das Sheet** (`sheetname_template = "{lot_id}"`)
* ohne Lot kann der Writer nicht korrekt routen
* deshalb wird `lot_id` bei uns als **Pflichtfeld außerhalb** der normalen “beliebigen Felder” behandelt

➡️ **Deshalb ist `lot_rule` separat sinnvoll**.

### Darf man es trotzdem in `extract_rules` integrieren?

Technisch: ja.
Architektonisch/vertraglich: **nein, wenn du Stabilität willst**.

Wenn du Lot in `extract_rules` “versteckst”, passiert schnell:

* der Writer erwartet `lot_id`, findet es aber nicht
* niemand weiß, ob es “nur ein Feld” ist oder Routing-Input
* Fehler werden später und unklarer

✅ Empfehlung: **`lot_rule` bleibt separat** (so wie jetzt).
Du kannst zusätzlich im `extract_rules.fields` das Lot als normales Feld *doppelt* extrahieren, wenn du es als Spalte willst (z. B. `key: "lot_id"`), aber die Routing-Quelle bleibt `lot_rule`.

---

## 3) Wie ergänze ich weitere Felder?

Du fügst in `extract_rules.fields` einfach neue Objekte hinzu.

### Regeln für gute Felder (damit es nicht nervt)

* Regex muss den **Wert in Gruppe 1** liefern (Klammern `(...)`), weil unser Extractor genau so arbeitet.
* Nutze möglichst “Label-basierte” Regex, weil dein Text feste Labels hat (`Plattenname:`, `Zeit:`, `Anwender:`, `Datum:`, `Test:`).
* Setze `required: true` für die Header, die du als Dedupe brauchst.

---

## 4) Header-Felder aus deinen echten Blocks – direkt als Beispiel-Regeln

Aus deinem Block :

```
Plattenname: 20260115TpoPr3MpoCen Zeit: 21:26:16 ...
Anwender: Fischer Datum: 15.01.2026 ...
Test: C:\ProgramData\...\Anti-TPO IgG.asy (5f03)
Kit E250829AV 260828
```

### Vorschlag: Header-Felder als `fields`

* `plate_name`
* `time`
* `user`
* `date`
* `test_path` (oder `test`)

**Robuste Regex (passt zu deinem Layout):**

* Plattenname (bis vor “Zeit:”):

  * `Plattenname:\s*(.+?)\s+Zeit:`
* Zeit:

  * `Zeit:\s*(\d{2}:\d{2}:\d{2})`
* Anwender:

  * `Anwender:\s*([^\s]+)`
* Datum (DD.MM.YYYY):

  * `Datum:\s*(\d{2}\.\d{2}\.\d{4})`
* Test (ganze Zeile nach `Test:`):

  * `Test:\s*(.+)`

### Lot / Kit / Charge

In deinem Block steht kein “LOT: …”, sondern:
`Kit E250829AV 260828` 

Das heißt: deine aktuelle `lot_rule.regex = LOT...` wird **niemals** matchen. 

Wenn “Lot” bei euch faktisch die zweite Zahl ist (z. B. `260828`), dann wäre eine passende MVP-Regel:

* `Kit\s+\S+\s+(\d{6})`

Das extrahiert `260828` als Lot-ID.

Wenn du stattdessen `E250829AV` als Lot willst:

* `Kit\s+(\S+)\s+\d{6}`

Wir müssen nur entscheiden, was “Lot” in deinem Kontext ist. Aus deinen Zeilen wirkt es so, als wäre:

* `E250829AV` = Kit-Lot/Artikel
* `260828` = Verfallsdatum (YYMMDD) oder Charge?
  Das ist fachlich nicht 100% sicher → sag kurz, welcher Teil dein Sheet-Name werden soll.

---

## 5) Aktualisiertes Anti-TPO RuleSet (Template + Headerfelder)

Hier eine Version deines RuleSets, die:

* `assay_name`/`assay_key` enthält
* Headerfelder ergänzt
* `lot_rule` auf `Kit ...` umstellt (MVP)
* Excel Mapping ergänzt

```json
{
  "assay_name": "Anti-TPO IgG",
  "assay_key": "(5f03)",

  "lot_rule": {
    "regex": "Kit\\s+\\S+\\s+(\\d{6})"
  },

  "extract_rules": {
    "fields": [
      {
        "key": "plate_name",
        "regex": "Plattenname:\\s*(.+?)\\s+Zeit:",
        "required": true
      },
      {
        "key": "time",
        "regex": "Zeit:\\s*(\\d{2}:\\d{2}:\\d{2})",
        "required": true
      },
      {
        "key": "user",
        "regex": "Anwender:\\s*([^\\s]+)",
        "required": true
      },
      {
        "key": "date",
        "regex": "Datum:\\s*(\\d{2}\\.\\d{2}\\.\\d{4})",
        "required": true
      },
      {
        "key": "test",
        "regex": "Test:\\s*(.+)",
        "required": true
      }
    ]
  },

  "excel_rules": {
    "excel_filename_template": "{assay_key}.xlsx",
    "sheetname_template": "{lot_id}",

    "column_mapping": {
      "plate_name": "Plattenname",
      "time": "Zeit",
      "user": "Anwender",
      "date": "Datum",
      "test": "Test",
      "dedupe_key": "DedupeKey",
      "lot_id": "Lot"
    }
  }
}
```

Warum ist das ein besseres Template?

* Es orientiert sich an euren **festen Labels** (sehr stabil)
* Es ignoriert die dynamische Ergebnisliste erstmal (QC/Patienten), wie du es wolltest (“später”)
* Es löst dein aktuelles Blocker-Problem `lot_id not found`, weil es “Kit … …” matcht

---

## 6) Wie erweiterst du später um Ergebnis-/QC-Listen?

Für variable Teile (S1/S2/S3, PCQ1/NCQ1, Patienten) ist dein aktueller `fields`-Ansatz zu simpel, weil du dafür **Listen/Tabellen** extrahieren willst.

Dafür ist ein Template besser, das zwei Bereiche trennt:

* `header_fields`: einzelne Werte (1x)
* `row_sets`: wiederholte Zeilen (Nx)

Das wäre ein besseres “Ziel-Template”, aber wir müssen das erst implementieren (Extractor kann aktuell nur “single fields”). Für jetzt ist obiges Header-Template der richtige Schritt.

---

## Quick Clarification (1 Entscheidung, damit Lot sauber ist)

Bei `Kit E250829AV 260828`:
Welcher Teil soll dein `lot_id` sein (Sheet-Name)?

* **A)** `E250829AV`
* **B)** `260828`

Sag A oder B, dann gebe ich dir die exakt richtige `lot_rule.regex` (und ggf. zusätzlich ein Feld, um den anderen Wert als Spalte mitzuschreiben).
