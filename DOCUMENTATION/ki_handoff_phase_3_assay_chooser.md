# KI-Handoff-Protokoll

## 0. Meta

- **Handoff-ID:** PH3-ASSAYCHOOSER-003
- **Projekt:** PDF Ergebnis-Extractor
- **Komponente / System:** AssayChooser
- **Phase / Scope:** Phase 3 – AssayChooser
- **Stand:** ACCEPTED
- **Gültig ab:** 2026-01-28
- **Referenz-Regelwerk / Dev Guide:**
  - DevGuide – PDF Ergebnis-Extractor (FINAL)
  - Working Agreement – Phase 3: AssayChooser
  - KI-Handoff Phase 1 – Parser (ACCEPTED)
  - KI-Handoff Phase 2 – Normalizer (ACCEPTED)
- **Erstellt von:** KI – Phase-3-Implementierung
- **Letzte Änderung:** 2026-01-28

---

## 1. Ziel & Nicht-Ziel (verbindlich)

### Ziel

Bereitstellung eines **deterministischen AssayChoosers**, der:

- Assays im Dokument erkennt
- **Multi-Assay PDFs** unterstützt (mehrere Assays können erkannt werden)
- **MVP-Matching:** `contains(assay_name)`
- ausschließlich über `src/assaychooser/api.py` genutzt wird
- den DevGuide-Grundsatz **"Stable API Facade"** strikt einhält (keine Logik in `api.py`)

### Nicht-Ziele

- ❌ Keine Normalisierung von Text (kommt aus Phase 2)
- ❌ Keine feld-/fachliche Extraktion (kommt später)
- ❌ Keine RuleSet-Auflösung / kein Laden/Validieren von Rules (kommt in Phase 4: RuleResolver)
- ❌ Keine Heuristiken (Fuzzy-Matching, Regex-Interpretation, Scoring)
- ❌ Kein IO

---

## 2. Übergabe-Garantie

Mit diesem Handoff wird garantiert:

- ☑ AssayChooser ist **funktionsfähig**
- ☑ Verhalten ist **deterministisch**
- ☑ Öffentliche API ist eine **reine Fassade ohne Logik** (exakt eine Delegation pro Funktion)
- ☑ Ausgabe entspricht dem Working Agreement Phase 3
- ☑ Phase 4 darf **ohne Rückfragen** darauf aufbauen

Nicht garantiert wird alles, was hier **nicht explizit aufgeführt** ist.

---

## 3. Aktueller Ist-Zustand

### 3.1 Implementierte Komponenten

| Komponente | Verantwortlichkeit | Pfad / Modul | Status |
| ---------- | ------------------ | ------------ | ------ |
| AssayChooser API | Öffentlicher Contract + Delegation | `src/assaychooser/api.py` | STABLE |
| AssayChooser Impl | contains-Matching über Dokumentzeilen | `src/assaychooser/_impl.py` | INTERNAL |

---

### 3.2 Öffentliche Contracts / Datenobjekte

| Contract | Typ | Stabilität | Quelle |
| -------- | --- | ---------- | ------ |
| `detect_assays(doc: ParsedDocument, rules_index) -> list[AssayMatch]` | Funktion | STABLE | `src/assaychooser/api.py` |
| `AssayMatch` | Dataclass | STABLE | `src/assaychooser/api.py` |

#### Garantierte Struktur (AssayMatch)

```text
AssayMatch:
- assay_key: str
- assay_name: str
- occurrence_index: int  (immer 1)
```

#### Garantiertes Verhalten (detect_assays)

- Input: `doc: ParsedDocument` (aus Phase 1 Contract)
- Matching: `contains(assay_name)` über alle Seiten/Zeilen
- Output: Liste von `AssayMatch` für alle erkannten Assays
- `occurrence_index` ist **immer 1**
- Deterministisch: gleicher Input → gleicher Output

**Wichtig:** Die **Struktur von `rules_index`** ist in Phase 3 **nicht** festgelegt; die Festlegung erfolgt planmäßig in **Phase 4 (RuleResolver)**.

---

## 4. Explizite Designentscheidungen (bindend)

Diese Entscheidungen gelten ab jetzt als **bindend**, bis sie explizit revidiert werden:

1. `api.py` ist eine **stabile Fassade** ohne Implementierungslogik (DevGuide 6.x)
2. Pro öffentlicher Funktion existiert **exakt eine Delegation** auf eine interne Implementierung
3. Matching erfolgt ausschließlich via **`contains(assay_name)`**
4. `occurrence_index` ist **immer 1** (MVP; keine Mehrfachvorkommen-Zählung)

---

## 5. Abweichungen vom Regelwerk

| Regel | Abweichung | Begründung | Rückbaubar |
| ----- | ---------- | ---------- | ---------- |
| – | keine | – | – |

---

## 6. Stabil vs. Änderbar

### 6.1 Stabil (nicht ohne Analyse ändern)

- Signatur von `detect_assays`
- Struktur von `AssayMatch`
- Matching-Semantik: `contains(assay_name)`
- `occurrence_index` immer 1
- Stable-API-Facade-Prinzip (keine Logik in `api.py`)

### 6.2 Änderbar / offen

- Konkrete Form/Typ von `rules_index` (wird in Phase 4 finalisiert)
- Interne Implementierungsdetails (`_impl.py`)

---

## 7. Tests & Reproduzierbarkeit

### 7.1 Tests

| Test | Typ | Pfad | Status |
| ---- | --- | ---- | ------ |
| AssayChooser Contract & Verhalten | pytest | `tests/test_assaychooser_phase3.py` | PASS |

### 7.2 Reproduktion

```text
Command:
pytest -q

Input:
- Unit-Test-Dokumente via ParsedDocument/ParsedPage Test-Fixtures

Erwartetes Ergebnis:
Alle Tests grün
```

**Hinweis:** Ein Phase-1→2→3 Integrationstest, der ein echtes `rules_index` nutzt, wird planmäßig erst nach Festlegung von `rules_index` in Phase 4 möglich.

---

## 8. Artefakte & Outputs

| Artefakt | Pfad | Zweck | Persistenz |
| -------- | ---- | ----- | ---------- |
| `list[AssayMatch]` | RAM | Übergabe an RuleResolver/Extractor-Pipeline | transient |

---

## 9. Failure Modes & bekannte Risiken

### 9.1 Definierte Failure States

- Übergabe eines inkompatiblen `doc` (kein ParsedDocument) → Python Exception
- Übergabe eines nicht-iterierbaren `rules_index` → Python Exception

### 9.2 Bekannte Risiken

- `contains` ist case-/format-sensitiv (bewusst MVP)
- Die genaue Struktur von `rules_index` ist bis Phase 4 offen; Phase 3 behandelt sie als Dependency

---

## 10. Nächster empfohlener Schritt

**Phase 4 – RuleResolver**

- `rules_index` (Typ/Schema) finalisieren
- Rules laden/validieren (z. B. via `rules/index.json` → RuleSet)
- Danach: echter Phase-1→2→3→4 Integrationstest möglich

---

## 11. Integrations-Check (KI-tauglich)

1. ☑ Ziel & Nicht-Ziel explizit
2. ☑ Klare Orchestrierungsstelle (JobController, extern)
3. ☑ Strikte Verantwortlichkeitstrennung
4. ☑ Öffentliche Contracts definiert
5. ☑ Keine stillen Contract-Änderungen
6. ☑ Deterministisches Verhalten
7. ☑ Explizite Failure-States
8. ☑ Reproduzierbare Artefakte
9. ☑ Phase isoliert prüfbar
10. ☑ Übergabe an nächste Phase möglich

---

## 12. Abnahme / Sign-off

- **Übergeben von:** KI – Phase 3 AssayChooser
- **Übernommen von (Mensch / KI):** Projektverantwortlicher
- **Datum:** 2026-01-28
- **Status:** ACCEPTED

---

> **Leitregel:** Alles, was eine KI oder ein Entwickler **nicht eindeutig aus diesem Dokument ableiten kann**, gilt als **nicht Teil der Übergabe**.
