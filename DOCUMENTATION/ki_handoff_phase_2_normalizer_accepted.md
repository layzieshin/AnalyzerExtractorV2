# KI-Handoff-Protokoll

## 0. Meta

- **Handoff-ID:** PH2-NORMALIZER-002
- **Projekt:** PDF Ergebnis-Extractor
- **Komponente / System:** Normalizer
- **Phase / Scope:** Phase 2 – Normalizer
- **Stand:** ACCEPTED
- **Gültig ab:** jetzt
- **Referenz-Regelwerk / Dev Guide:**
  - DevGuide – PDF Ergebnis-Extractor (FINAL)
  - Working Agreement – Phase 2: Normalizer
  - KI-Handoff Phase 1 – Parser
- **Erstellt von:** KI – Phase-2-Implementierung (revidiert)
- **Letzte Änderung:** heute

---

## 1. Ziel & Nicht-Ziel (verbindlich)

### Ziel

Bereitstellung eines **deterministischen Normalizers**, der:

- ausschließlich auf `list[str]` arbeitet
- **Whitespace innerhalb einzelner Zeilen** normalisiert
- die **Zeilenstruktur vollständig erhält**
- keine Fachlogik, Interpretation oder Layoutannahmen enthält
- ausschließlich über `src/normalizer/api.py` genutzt wird
- den DevGuide-Grundsatz **"Stable API Facade"** strikt einhält

### Nicht-Ziele

- ❌ Keine Zusammenführung oder Trennung von Zeilen
- ❌ Keine Assay-Erkennung
- ❌ Keine feldspezifische oder semantische Normalisierung
- ❌ Keine Abhängigkeit von PDF-, Seiten- oder Positionsinformationen

---

## 2. Übergabe-Garantie

Mit diesem Handoff wird garantiert:

- ☑ Der Normalizer ist **funktionsfähig**
- ☑ Das Verhalten ist **deterministisch**
- ☑ Die öffentliche API ist eine **reine Fassade ohne Logik**
- ☑ Fachlogik ist vollständig in interne Module ausgelagert
- ☑ Phase 3 darf **ohne Rückfragen** darauf aufbauen

Nicht garantiert wird alles, was hier **nicht explizit aufgeführt** ist.

---

## 3. Aktueller Ist-Zustand

### 3.1 Implementierte Komponenten

| Komponente | Verantwortlichkeit | Pfad | Status |
|----------|--------------------|------|--------|
| Normalizer API | Öffentlicher Contract + Delegation | `src/normalizer/api.py` | STABLE |
| Normalizer Impl | Whitespace-Normalisierung | `src/normalizer/_impl.py` | INTERNAL |

---

### 3.2 Öffentliche Contracts / Datenobjekte

| Contract | Typ | Stabilität | Quelle |
|---------|-----|-----------|--------|
| `normalize_lines(lines: list[str]) -> list[str]` | Funktion | STABLE | `src/normalizer/api.py` |

#### Garantiertes Verhalten

- Input- und Output-Liste haben **identische Länge und Reihenfolge**
- Pro Zeile:
  - Entfernen von führendem und nachgestelltem Whitespace
  - Jede Folge von Spaces oder Tabs → **genau ein** ASCII-Leerzeichen
- Keine zeilenübergreifenden Effekte
- Deterministisches Verhalten

---

## 4. Explizite Designentscheidungen (bindend)

1. `api.py` ist eine **stabile Fassade** ohne Implementierungslogik
2. Pro öffentlicher Funktion existiert **exakt eine Delegation**
3. Fachlogik liegt ausschließlich in **internen Modulen** (`_impl.py`)
4. Die Implementierung darf geändert werden, ohne den Contract zu ändern

---

## 5. Abweichungen vom Regelwerk

| Regel | Abweichung | Begründung | Rückbaubar |
|------|-----------|-----------|-----------|
| – | keine | – | – |

---

## 6. Stabil vs. Änderbar

### 6.1 Stabil (nicht ohne Analyse ändern)

- Signatur von `normalize_lines`
- Garantierte Semantik (Whitespace-only, zeilenstabil)
- Stable-API-Facade-Prinzip

### 6.2 Änderbar / offen

- Interne Regex-Strategie
- Interne Modulstruktur (`_impl.py` vs. `_service.py` etc.)

---

## 7. Tests & Reproduzierbarkeit

### 7.1 Tests

| Test | Typ | Pfad | Status |
|----|----|----|----|
| Normalizer Contract | pytest | `tests/test_normalizer_phase2.py` | PASS |
| Phase1→Phase2 Integration | pytest | `tests/test_phase1_phase2_integration.py` | PASS |

### 7.2 Reproduktion

```text
Command:
pytest -q

Input:
input/sample_single.pdf
input/sample_multi.pdf

Erwartetes Ergebnis:
Alle Tests grün
```

---

## 8. Artefakte & Outputs

| Artefakt | Pfad | Zweck | Persistenz |
|--------|-----|------|-----------|
| normalisierte Zeilen | RAM | Übergabe an AssayChooser | transient |

---

## 9. Failure Modes & bekannte Risiken

### 9.1 Definierte Failure States

- Übergabe von Nicht-`list[str]` → Python Exception

### 9.2 Bekannte Risiken

- Whitespace-Reduktion kann visuelle Abstände verlieren (bewusst akzeptiert)

---

## 10. Nächster empfohlener Schritt

**Phase 3 – AssayChooser**

- Arbeitet auf normalisierten Zeilen
- Darf auf stabile Zeilenstruktur bauen

---

## 11. Integrations-Check (KI-tauglich)

1. ☑ Ziel & Nicht-Ziel explizit
2. ☑ Klare Orchestrierungsstelle (JobController, extern)
3. ☑ Strikte Verantwortlichkeitstrennung
4. ☑ Öffentliche Contracts definiert
5. ☑ Keine Logik in `api.py`
6. ☑ Deterministisches Verhalten
7. ☑ Explizite Failure-States
8. ☑ Reproduzierbare Artefakte
9. ☑ Phase isoliert prüfbar
10. ☑ Übergabe an nächste Phase möglich

---

## 12. Abnahme / Sign-off

- **Übergeben von:** KI – Phase 2 Normalizer
- **Übernommen von:** Projektverantwortlicher
- **Datum:** heute
- **Status:** ACCEPTED

---

> **Leitregel:** Alles, was nicht explizit in diesem Dokument steht, gilt als **nicht garantiert**.

