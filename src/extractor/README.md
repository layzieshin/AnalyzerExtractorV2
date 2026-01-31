# Extractor (src/extractor)

Der **Extractor** ist das Modul, das aus einem **Assay-Textblock** (z. B. aus einem Euroimmun-Report) anhand eines **Rulesets** strukturierte Werte (`record.data`) extrahiert.

Wichtiges Ziel: **Regeln gehören ins Ruleset**, nicht in die Code-API. Der Extractor bleibt generisch.

---

## 1. Überblick

### Input
- `text` (String): der Text, in dem gesucht wird
  - typischerweise **nicht der komplette PDF-Text**, sondern ein bereits auf das Assay begrenzter Block (Assay-Block).
- `extract_rules` (Dict): aus dem Ruleset-JSON, enthält mindestens `fields`.

### Output
- `Dict[str, Any]`: Key-Value-Paare, die später in `record.data` landen.

### Grundprinzip
- Für jeden Eintrag in `extract_rules.fields` wird **eine** Regex angewendet.
- Standardmäßig wird **im gesamten Text** gesucht.
- Optional kann die Suche **ab einer bestimmten Zeile** oder **ab einem Marker** beginnen (`search_from`).

---

## 2. Ruleset-Struktur (relevanter Ausschnitt)

Ein Ruleset enthält mindestens:

- `assay_name`: Anzeigename
- `assay_key`: eindeutiger Key
- `extract_rules.fields`: Liste der Extraktionsregeln
- optional: `excel_rules` (Mapping/Output)

Beispiel (Minimal):

```json
{
  "assay_name": "25-OH Vitamin D",
  "assay_key": "(6bd7)",
  "extract_rules": {
    "fields": [
      {
        "key": "date",
        "regex": "Datum:\\s*(\\d{2}\\.\\d{2}\\.\\d{4})",
        "required": true
      }
    ]
  }
}
```

---

## 3. Field-Regeln (extract_rules.fields)

Jedes Field ist ein Objekt mit:

| Feld | Typ | Pflicht | Bedeutung |
|---|---:|---:|---|
| `key` | string | ✅ | Ziel-Key in `record.data` |
| `regex` | string | ✅ | Regex zur Extraktion |
| `required` | bool | ❌ | Wenn true: fehlender Treffer ist ein Fehler |
| `search_from` | object | ❌ | Startpunkt der Suche (siehe unten) |

### 3.1 Treffer-Logik (Single-Hit)
- Es wird **genau ein** Treffer verwendet.
- **Wenn die Regex Gruppen enthält**, wird standardmäßig `group(1)` genommen.
- **Wenn keine Gruppe existiert**, wird `group(0)` (gesamter Match) genommen.
- Ergebnis wird `.strip()` bereinigt.

**Beispiel:**

```json
{
  "key": "user",
  "regex": "Anwender:\\s*([^\\s]+)",
  "required": true
}
```

---

## 4. Suche ab bestimmter Stelle (`search_from`)

Manche Begriffe kommen mehrfach vor (z. B. Kopfzeilen pro Seite). Dann kann man festlegen, **ab welcher Stelle** im Text gesucht werden soll.

Der Extractor unterstützt dafür `search_from` als Objekt. Unterstützte Varianten:

### 4.1 Ab Zeilennummer suchen (`line`)
- `line` ist **0-basiert**.
- Beispiel: ab Zeile 10 suchen.

```json
{
  "key": "pcq1_line",
  "regex": "\\bPCQ1\\b.*",
  "required": false,
  "search_from": { "line": 10 }
}
```

### 4.2 Ab erstem Marker suchen (`after`)
- Suche beginnt **nach der ersten Zeile**, die den Marker matcht.
- Marker ist ein Regex (oder normaler Text, der als Regex interpretiert wird).

```json
{
  "key": "UG_PCQ1",
  "regex": "\\bPCQ1\\s+(\\d+(?:[\\.,]\\d+)?)<=PCQ1<=",
  "required": false,
  "search_from": { "after": "Validierungskriterien" }
}
```

### 4.3 Ab letztem Marker suchen (`after_last`)
- Suche beginnt **nach der letzten Zeile**, die den Marker matcht.
- Nützlich, wenn Marker pro Seite wiederholt wird und du sicher den letzten Block willst.

```json
{
  "key": "VALIDATION_LINE",
  "regex": "Validationskriterien.*",
  "required": true,
  "search_from": { "after_last": "^Validationskriterien" }
}
```

> Empfehlung:
> - Wenn etwas **nur einmal** vorkommt: kein `search_from`.
> - Wenn es pro Seite im Header wiederholt wird: `after_last` (oder gezielt `after` in Kombination mit spezifischerem Marker).

---

## 5. Template: Controls / Validierung (typische Euroimmun-Pattern)

### 5.1 Validierungskriterien-Status (erste Zeile)

```json
{
  "key": "VALIDATION",
  "regex": "^(Validationskriterien\\s+(?:nicht\\s+)?erfüllt)",
  "required": true,
  "search_from": { "line": 0 }
}
```

### 5.2 PCQ1 UG / ZIEL / OG aus Validierungskriterien

Für Zeilen wie:

`PCQ1 71<=PCQ1<=133 71<=105,061<=133 INVALIDE`

```json
{
  "key": "UG_PCQ1",
  "regex": "\\bPCQ1\\s+(\\d+(?:[\\.,]\\d+)?)<=PCQ1<=",
  "required": false,
  "search_from": { "after": "Validierungskriterien" }
},
{
  "key": "ZIEL_PCQ1",
  "regex": "\\bPCQ1\\s+\\d+(?:[\\.,]\\d+)?<=PCQ1<=\\d+(?:[\\.,]\\d+)?\\s+\\d+(?:[\\.,]\\d+)?<=\\s*(\\d+(?:[\\.,]\\d+)?)\\s*<=",
  "required": false,
  "search_from": { "after": "Validierungskriterien" }
},
{
  "key": "OG_PCQ1",
  "regex": "\\bPCQ1\\s+\\d+(?:[\\.,]\\d+)?<=PCQ1<=(\\d+(?:[\\.,]\\d+)?)",
  "required": false,
  "search_from": { "after": "Validierungskriterien" }
}
```

Analog für NCQ1: ersetze `PCQ1` durch `NCQ1`.

### 5.3 INVALIDE-Flag (Test invalide)

```json
{
  "key": "INVALIDE_FLAG",
  "regex": "\\bINVALIDE\\b",
  "required": false,
  "search_from": { "after": "Validierungskriterien" }
}
```

Interpretation:
- `None` → kein INVALIDE gefunden → valide
- Treffer → invalide

---

## 6. Excel-Output (Kurz)

Der Extractor schreibt **nur** `record.data`. Wie das nach Excel geht, definiert `excel_rules` im Ruleset.

Beispiel:

```json
"excel_rules": {
  "excel_filename_template": "{assay_name}.xlsx",
  "sheetname_template": "{lot_id}",
  "column_mapping": {
    "date": "Datum",
    "time": "Zeit",
    "user": "Anwender",
    "UG_PCQ1": "UG PCQ1",
    "ZIEL_PCQ1": "ZIEL PCQ1",
    "OG_PCQ1": "OG PCQ1"
  }
}
```

> Hinweis: Der Writer nutzt die Keys aus `record.data` und mappt sie über `column_mapping` in Spaltennamen.

---

## 7. Regex Mini-How-To

### 7.1 Basics
- `\\s*` = beliebig viele Whitespaces
- `\\d+` = eine oder mehr Ziffern
- `.` = beliebiges Zeichen (außer Zeilenumbruch)
- `.*?` = „so wenig wie möglich“ (non-greedy)

### 7.2 Gruppen
- `( ... )` erzeugt eine Capture-Group.
- Der Extractor nimmt standardmäßig `group(1)`.

Beispiel:

Regex: `Datum:\\s*(\\d{2}\\.\\d{2}\\.\\d{4})`
- Match: `Datum: 22.07.2024`
- Group(1): `22.07.2024`

### 7.3 Dezimalzahlen (Komma oder Punkt)

```regex
\d+(?:[\.,]\d+)?
```

- `105` oder `105,061` oder `105.061`

### 7.4 Wortgrenzen
- `\\bPCQ1\\b` verhindert Matches in längeren Tokens.

### 7.5 Zeilenanfang
- `^` = Zeilenanfang (mit `re.MULTILINE`)

Beispiel Marker:
- `^Validierungskriterien`

### 7.6 Typische Stolperfalle: Backslashes in JSON
In JSON musst du `\\` schreiben, um im Regex ein `\` zu bekommen.

- Python Regex: `\d{2}`
- JSON String: `\\d{2}`

---

## 8. Debugging / Vorgehensweise

1) Nimm den erzeugten `*_normalized.txt` oder `*_block.txt` und teste deine Regex dagegen.
2) Wenn ein Feld mehrfach vorkommt:
   - nutze `search_from.after` oder `search_from.after_last`
3) Wenn ein Feld optional ist:
   - `required: false`
4) Wenn ein Feld Pflicht ist:
   - `required: true` (Import bricht beim Assay ab, wenn nicht gefunden)

---

## 9. Copy-Paste Template (kompakt)

```json
"extract_rules": {
  "fields": [
    {"key": "plate_name", "regex": "Plattenname:\\s*(.+?)\\s+Zeit:", "required": true},
    {"key": "date", "regex": "Datum:\\s*(\\d{2}\\.\\d{2}\\.\\d{4})", "required": true},
    {"key": "time", "regex": "Zeit:\\s*(\\d{2}:\\d{2}:\\d{2})", "required": true},
    {"key": "user", "regex": "Anwender:\\s*([^\\s]+)", "required": true},

    {"key": "VALIDATION", "regex": "^(Validationskriterien\\s+(?:nicht\\s+)?erfüllt)", "required": true, "search_from": {"line": 0}},

    {"key": "UG_PCQ1", "regex": "\\bPCQ1\\s+(\\d+(?:[\\.,]\\d+)?)<=PCQ1<=", "required": false, "search_from": {"after": "Validierungskriterien"}},
    {"key": "ZIEL_PCQ1", "regex": "\\bPCQ1\\s+\\d+(?:[\\.,]\\d+)?<=PCQ1<=\\d+(?:[\\.,]\\d+)?\\s+\\d+(?:[\\.,]\\d+)?<=\\s*(\\d+(?:[\\.,]\\d+)?)\\s*<=", "required": false, "search_from": {"after": "Validierungskriterien"}},
    {"key": "OG_PCQ1", "regex": "\\bPCQ1\\s+\\d+(?:[\\.,]\\d+)?<=PCQ1<=(\\d+(?:[\\.,]\\d+)?)", "required": false, "search_from": {"after": "Validierungskriterien"}},

    {"key": "INVALIDE_FLAG", "regex": "\\bINVALIDE\\b", "required": false, "search_from": {"after": "Validierungskriterien"}}
  ]
}
```

---

## 10. FAQ

### „Kann ich nur ab einer bestimmten Zeile suchen?“
Ja: `"search_from": {"line": N}`.

### „Kann ich ab einem Marker suchen?“
Ja: `"search_from": {"after": "MarkerRegex"}`.

### „Marker kommt mehrfach vor – ich will nach dem letzten Marker suchen.“
Ja: `"search_from": {"after_last": "MarkerRegex"}`.

### „Ich will mehrere Treffer sammeln.“
Aktuell ist die Logik bewusst **Single-Hit**. Falls du später Multi brauchst, erweitern wir das explizit und kontrolliert.

