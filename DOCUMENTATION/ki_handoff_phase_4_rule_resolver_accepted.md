# KI-Handoff-Protokoll – Phase 4: RuleResolver

## 0. Meta

- **Handoff-ID:** PH4-RULERESOLVER-004
- **Projekt:** PDF Ergebnis-Extractor
- **Komponente / System:** RuleResolver
- **Phase / Scope:** Phase 4 – RuleResolver
- **Stand:** ACCEPTED
- **Gültig ab:** 2026-01-28
- **Referenz-Regelwerk / Dev Guide:**
  - DevGuide – PDF Ergebnis-Extractor (FINAL)
  - Working Agreement – Phase 0: Architektur & Setup
  - KI-Handoff Phase 1 – Parser (ACCEPTED)
  - KI-Handoff Phase 2 – Normalizer (ACCEPTED)
  - KI-Handoff Phase 3 – AssayChooser (ACCEPTED)
- **Erstellt von:** KI – Phase-4-Implementierung
- **Letzte Änderung:** 2026-01-28

---

## 1. Ziel & Nicht-Ziel (verbindlich)

### Ziel

Bereitstellung eines **deterministischen RuleResolvers**, der:

- ein **RuleSet eindeutig über einen Assay** auflöst (Schlüssel: `assay.assay_key`)
- die **Struktur/Konsistenz** des RuleSets **validiert**, bevor es weitergegeben wird
- **keine** fachliche Extraktion, **keine** Assay-Erkennung, **keine** Normalisierung durchführt
- ausschließlich über `src/ruleresolver/api.py` genutzt wird
- den DevGuide-Grundsatz **Stable API Facade** strikt einhält (keine Logik in `api.py`)

### Nicht-Ziele

- ❌ Keine Erkennung von Assays (Phase 3)
- ❌ Keine feld-/fachliche Extraktion aus Dokumentzeilen (Phase 5)
- ❌ Keine Heuristiken/Fallbacks (kein Scoring, kein „best effort“)
- ❌ Kein IO (außer explizit als Contract definiert; MVP: Rules kommen als `rules_index`-Datenobjekt)

---

## 2. Übergabe-Garantie

Mit diesem Handoff wird garantiert:

- ☑ RuleResolver ist **funktionsfähig**
- ☑ Verhalten ist **deterministisch**
- ☑ Öffentliche API ist **stabil** und **Facade-only**
- ☑ Rules werden **fail-fast** validiert
- ☑ Phase 5 darf **ohne Rückfragen** darauf aufbauen

Nicht garantiert ist alles, was hier **nicht** explizit beschrieben ist.

---

## 3. Aktueller Ist-Zustand

### 3.1 Implementierte Komponenten

| Komponente | Verantwortlichkeit | Pfad / Modul | Status |
|---|---|---|---|
| RuleResolver API | Öffentlicher Contract + Delegation | `src/ruleresolver/api.py` | STABLE |
| RuleResolver Impl | Auflösen + Validieren | `src/ruleresolver/_impl.py` | INTERNAL |

### 3.2 Öffentliche Contracts / Datenobjekte

#### Funktion (STABLE)

```text
resolve_rules(assay, rules_index) -> RuleSet
```

- **Input (Edukte):**
  - `assay`: ein Objekt mit Attribut `assay_key: str` (typisch: `AssayMatch` aus Phase 3)
  - `rules_index: dict`: Indexdatenstruktur, die RuleSets nach `assay_key` enthält
- **Output (Produkt):**
  - `RuleSet`

#### Datentypen (STABLE)

```text
RuleSet:
- assay_key: str
- version: str
- fields: list[RuleField]

RuleField:
- field_name: str
- match_type: str
- pattern: str
- required: bool
```

### 3.3 Regeln für `rules_index` (Contract für Phase 4)

**MVP-Indexformat:**

```text
rules_index = {
  "<assay_key>": {
    "assay_key": "<assay_key>",
    "version": "<str>",
    "fields": [
      {
        "field_name": "<str>",
        "match_type": "<str>",
        "pattern": "<str>",
        "required": <bool>
      },
      ...
    ]
  },
  ...
}
```

- RuleResolver interpretiert **keine** Semantik von `match_type`/`pattern`.
- RuleResolver stellt nur sicher, dass die Struktur vorhanden und typkompatibel ist.

---

## 4. Garantiertes Verhalten (verbindlich)

1. **Auswahlprinzip:**
   - RuleSet wird ausschließlich über `assay.assay_key` aufgelöst.
2. **Eindeutigkeit:**
   - Für einen `assay_key` existiert entweder **genau ein** RuleSet oder es wird ein Fehler geworfen.
3. **Validierung:**
   - Vor Rückgabe wird die Struktur validiert:
     - Top-Level Keys: `assay_key`, `version`, `fields`
     - `fields` ist eine `list`
     - jedes Field enthält `field_name`, `match_type`, `pattern`, `required`
4. **Determinismus:**
   - Gleicher Input (`assay`, `rules_index`) → gleicher Output bzw. gleicher Fehler.
5. **Kein Fallback:**
   - Keine Defaults, keine stillen Reparaturen.

---

## 5. Failure Modes (definiert)

- `assay.assay_key` nicht in `rules_index` → **Exception**
- `rules_index[assay_key]` ist nicht `dict` → **Exception**
- RuleSet fehlt Pflichtkeys → **Exception**
- `fields` ist nicht `list` → **Exception**
- Field fehlt Pflichtkeys → **Exception**

**Hinweis:** Exceptions werden bewusst nicht „verschönert“ oder abgefangen (fail-fast).

---

## 6. Explizite Designentscheidungen (bindend)

1. `api.py` ist **Facade-only**: genau eine Delegation pro öffentlicher Funktion.
2. RuleResolver **verändert** keine Regeldefinitionen (keine Normalisierung, keine Defaults).
3. RuleResolver ist **rein synchron** und **deterministisch**.
4. RuleResolver kennt keine Dateipfade/IO im MVP-Contract; Regeln werden als `rules_index` übergeben.

---

## 7. Tests & Reproduzierbarkeit

### 7.1 Tests (pytest)

| Test | Typ | Pfad | Status |
|---|---|---|---|
| RuleResolver: Happy Path | Unit | `tests/test_ruleresolver_phase4.py` | PASS |
| RuleResolver: Missing AssayKey | Unit | `tests/test_ruleresolver_phase4.py` | PASS |
| RuleResolver: Invalid Structure | Unit | `tests/test_ruleresolver_phase4.py` | PASS |

### 7.2 Reproduktion

```text
Command:
pytest -q

Erwartet:
Alle Tests grün
```

---

## 8. Artefakte & Outputs

| Artefakt | Zweck | Persistenz |
|---|---|---|
| `RuleSet` | Übergabe an Extractor (Phase 5) | transient |

---

## 9. Stabil vs. Änderbar

### 9.1 Stabil (nicht ohne Analyse ändern)

- Signatur von `resolve_rules`
- Struktur von `RuleSet` und `RuleField`
- Auflösung ausschließlich über `assay.assay_key`
- Fail-fast Validierung + deterministisches Fehlerverhalten

### 9.2 Änderbar / offen

- Interne Implementierungsdetails (`_impl.py`)
- Spätere Erweiterung: Laden aus Dateien/Verzeichnissen (nur mit expliziter Contract-Rezension)
- Zusätzliche Validierungsregeln (nur wenn vertraglich dokumentiert)

---

## 10. Nächster empfohlener Schritt

**Phase 5 – Extractor**

- Nimmt `RuleSet` als Input
- Implementiert feldweise Extraktion gemäß `RuleField`
- Keine Kenntnis vom `rules_index` nötig

---

## 11. Integrations-Check (KI-tauglich)

1. ☑ Ziel & Nicht-Ziel explizit
2. ☑ Klare Verantwortlichkeit (nur Rules-Auflösung + Validierung)
3. ☑ Öffentliche Contracts definiert
4. ☑ Keine Logik in `api.py`
5. ☑ Deterministisches Verhalten
6. ☑ Explizite Failure-States
7. ☑ Phase isoliert prüfbar
8. ☑ Übergabe an nächste Phase möglich

---

## 12. Abnahme / Sign-off

- **Übergeben von:** KI – Phase 4 RuleResolver
- **Übernommen von (Mensch / KI):** Projektverantwortlicher
- **Datum:** 2026-01-28
- **Status:** ACCEPTED

> Leitregel: Alles, was nicht explizit in diesem Dokument steht, gilt als nicht garantiert.

