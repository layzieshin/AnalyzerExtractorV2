# KI-Handoff-Protokoll

## 0. Meta

- **Handoff-ID:** PH1-PARSER-001
- **Projekt:** PDF Ergebnis-Extractor
- **Komponente / System:** Parser
- **Phase / Scope:** Phase 1 – Parser
- **Stand:** ACCEPTED
- **Gültig ab:** jetzt
- **Referenz-Regelwerk / Dev Guide:**
  - Working Agreement Phase 1 – Parser
  - DevGuide – PDF Ergebnis-Extractor
- **Erstellt von:** KI (Phase-1-Implementierung)
- **Letzte Änderung:** heute

---

## 1. Ziel & Nicht-Ziel (verbindlich)

### Ziel

Bereitstellung eines **deterministischen, zeilenstabilen, positionsbasierten PDF-Parsers**, der:

- PDFs seitenweise verarbeitet
- visuell rekonstruierte **Textzeilen (`list[str]`) pro Seite** liefert
- **keine Normalisierung**, **keine Fachlogik**, **keine Interpretation** enthält
- ausschließlich über `src/parser/api.py` genutzt wird

### Nicht-Ziele

- ❌ Keine Whitespace-Normalisierung  
- ❌ Keine Assay-Erkennung  
- ❌ Keine Extraktion fachlicher Felder  
- ❌ Keine Layout-Heuristiken über Zeilenrekonstruktion hinaus  
- ❌ Keine Korrektur / Säuberung von Textinhalten

---

## 2. Übergabe-Garantie

Mit diesem Handoff wird garantiert:

- ☑ Parser ist **funktionsfähig**
- ☑ Parser ist **deterministisch** (gleicher Input → identischer Output)
- ☑ Öffentlicher Contract ist **stabil**
- ☑ Phase 2 darf **ohne Rückfragen** darauf aufbauen

Nicht garantiert ist alles, was hier nicht explizit genannt ist.

---

## 3. Aktueller Ist-Zustand

### 3.1 Implementierte Komponenten

| Komponente | Verantwortlichkeit | Pfad | Status |
|-----------|--------------------|------|--------|
| Parser API | Öffentlicher Contract | `src/parser/api.py` | STABLE |
| Positional Extractor | interne Umsetzung | `src/parser/_positional.py` | STABLE |

---

### 3.2 Öffentliche Contracts / Datenobjekte

| Contract | Typ | Stabilität | Quelle |
|--------|-----|-----------|-------|
| `parse(pdf_path: str) -> ParsedDocument` | Funktion | STABLE | `src/parser/api.py` |
| `ParsedDocument` | Dataclass | STABLE | `src/parser/api.py` |
| `ParsedPage` | Dataclass | STABLE | `src/parser/api.py` |

#### Garantierte Struktur

```text
ParsedDocument:
- source_path: str
- pages: list[ParsedPage]
- meta: dict

ParsedPage:
- page_number: int   # 1-basiert
- lines: list[str]
```

---

## 4. Explizite Designentscheidungen (bindend)

Diese Entscheidungen gelten ab jetzt als **nicht verhandelbar**:

1. `page_number` ist **1-basiert** (erste Seite = 1)
2. Parser nutzt **PyMuPDF (`fitz`)**
3. Text wird **positionsbasiert** extrahiert (Spans → Fragmente → Linien)
4. Parser verändert Text **nicht semantisch**, erlaubt sind nur:
   - Zusammenfügen von Fragmenten
   - Einfügen von Leerzeichen basierend auf X-Abständen
5. Reihenfolge der Zeilen ist **top-to-bottom**, innerhalb der Zeile **left-to-right**

---

## 5. Abweichungen vom Regelwerk

| Regel | Abweichung | Begründung | Rückbaubar |
|-----|-----------|-----------|-----------|
| – | keine | – | – |

---

## 6. Stabil vs. Änderbar

### 6.1 Stabil (Phase 2 darf NICHT darauf bauen, dass es sich ändert)

- Struktur von `ParsedDocument` und `ParsedPage`
- `lines: list[str]` enthält **rohen Text**, nicht normalisiert
- Determinismus (gleicher Input → gleicher Output)
- 1-basierte Seitenzählung

### 6.2 Änderbar / offen (Phase 2 darf NICHT annehmen, dass dies stabil ist)

- Anzahl der Leerzeichen innerhalb einer Zeile
- Exakte Zeilentrennung bei grenzwertigen Y-Abständen
- Inhalt und Struktur von `meta` (außer `page_count`)

---

## 7. Tests & Reproduzierbarkeit

### 7.1 Tests

| Test | Typ | Pfad | Status |
|----|----|----|----|
| Parser Contract + Determinismus | pytest | `tests/test_parser_phase1.py` | PASS |

- Tests verwenden **ausschließlich**:
  - `input/sample_single.pdf`
  - `input/sample_multi.pdf`

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
| ParsedDocument | RAM | Übergabe an Normalizer | transient |

---

## 9. Failure Modes & bekannte Risiken

### 9.1 Definierte Failure States

- PDF kann nicht geöffnet werden → Exception von PyMuPDF
- PDF ohne Textlayer → `pages[*].lines` kann leer sein

### 9.2 Bekannte Risiken

- Unterschiedliche PDFs können stark variierende Fragmentierung erzeugen
- Leerzeichen-Rekonstruktion ist visuell, nicht semantisch

---

## 10. Nächster empfohlener Schritt

**Phase 2 – Normalizer**

- Arbeitet ausschließlich auf `ParsedDocument`
- Darf **nur Whitespace innerhalb von Zeilen** verändern
- Darf **keine Zeilen zusammenführen oder trennen**

---

## 11. Integrations-Check (KI-tauglich)

1. ☑ Ziel & Nicht-Ziel explizit
2. ☑ Klare Orchestrierungsstelle (JobController, außerhalb dieser Phase)
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

- **Übergeben von:** KI – Phase 1 Parser
- **Übernommen von:** Phase-2-Entwickler (Normalizer)
- **Datum:** heute
- **Status:** ACCEPTED

