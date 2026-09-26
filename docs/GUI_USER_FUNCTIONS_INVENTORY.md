# GUI-Nutzerfunktionen — Inventar (AREV2)

Vollständige Liste interaktiver Funktionen für GUI-Aufräumen und UX-Planung.

**Produktions-GUI:** `test_app_main.py` → `interfaces/tk/test_app.py`  
**Regelwerk-GUI:** `rule_editor_main.py` → `rule_editor/`  
**Legacy (Smoke):** `gui_min_ext.py` — Direct Mode ohne Queue-First

Siehe auch: [`GUI_IA_PROPOSAL.md`](GUI_IA_PROPOSAL.md)

---

## A. Test-App — Tabs (Standard ohne `ARE_SHOW_ADMIN`)

### Global

| Funktion | Nutzerwirkung |
|----------|----------------|
| Tab wechseln | Arbeitsbereich wechseln |
| Statuszeile | Letzte Meldung, Zustand `idle` / `running` |
| Fortschrittsbalken | Hintergrundarbeit sichtbar (Extraktion) |
| Fenster schließen | App beenden; Auto-Suche stoppen |

### EXTRACTOR — PDFs finden und verarbeiten

| Funktion | Nutzerwirkung |
|----------|----------------|
| **Ergebnisse suchen** | Watch-Ordner scannen, neue PDFs in Queue (`Wartet`) |
| **Dateien hinzufügen** | PDFs per Dialog zur Queue |
| **Unterordner einbeziehen** | Rekursiver Scan (mit Ausschlüssen) |
| **Extraktion starten** | Wartende Jobs verarbeiten (Pipeline → Excel/SQLite) |
| **Extraktion stoppen** | Nach aktuellem Job stoppen |
| **Fehler erneut verarbeiten** | Ausgewählte fehlgeschlagene Zeilen → `Wartet` |
| **Aktualisieren** | Queue-Status in Arbeitsliste neu laden |
| **Automatische Suche starten/stoppen** | Periodischer Watch-Scan in der App |
| **Ergebnis-Tabelle** | Übersicht; Sortieren per Spaltenkopf |

### OPTIONS — Konfiguration

| Funktion | Nutzerwirkung |
|----------|----------------|
| **Output-Modus** | `excel` / `sqlite` / `both` |
| **SQLite-Pfad** | Zieldatei für DB/Duplikate/DATENBANK |
| **Watch-Ordner** + **Ordner** | Pfad für Suche/Auto-Suche |
| **Gerät** + **Neu laden** | Analyzer-Profil für Extraktion |
| **Anzeigen** | Zusammenfassung der Einstellungen |

### RULE SUITE — Nacharbeit

| Funktion | Nutzerwirkung |
|----------|----------------|
| **Nacharbeit aktualisieren** | Fehlgeschlagene Jobs mit Kontext laden |
| **Filter** | Nach Fehlerart filtern |
| **Kontext anzeigen** | Dump/Detail des Jobs |
| **Rule Editor öffnen** | Externes Regelwerk-Fenster |
| **Nacharbeit wiederholen** | Ausgewählte Nacharbeit-Jobs erneut starten |
| **Rules validieren** | Integrität `rules/index.json` |
| **Assay-Kandidaten prüfen** | Vorschläge bei „Assay nicht erkannt“ |
| **Draft aus Kandidat erstellen** | Regelwerk-Draft anlegen |

### LOGS / DUPLIKATE / DATENBANK

- **LOGS:** Protokoll (read-only, kopierbar)
- **DUPLIKATE:** Kandidaten listen, verwerfen, Feldvergleich
- **DATENBANK:** SQLite-Ergebnisse lesen (Assay, CHARGE, Spaltenauswahl)

### ADMIN (nur mit `ARE_SHOW_ADMIN=1`)

Technische Queue-Rohdaten — für Support/Debug, nicht Feldversuch-Default.

---

## B. Rule Editor

Siehe [`DOCUMENTATION/09_rulesuite_authoring_workflow.md`](../DOCUMENTATION/09_rulesuite_authoring_workflow.md) und Rule-Editor-Tabs: Draft, PDF, Felder, Meta & Excel, Validierung, Log plus Wizard/Clone/Regex-Dialoge.

---

## C. Legacy `gui_min_ext.py`

Direct-Submit ohne Queue — Entwickler/Smoke only; Overlap mit Test-App bewusst reduziert.

---

## D. Bekannte UX-Doppelungen (Stand nach Aufräumen)

| Intention | Owner |
|-----------|--------|
| Queue aktualisieren | EXTRACTOR **Aktualisieren** (ADMIN optional) |
| Fehlgeschlagene Jobs wiederholen | EXTRACTOR vs. RULE SUITE — unterschiedliche Labels |
| Rules validieren | RULE SUITE (Test-App) |
| Regelwerk pflegen | Rule Editor |
