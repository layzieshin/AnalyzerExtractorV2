# UI V2.1 — Ablauf für die Produkt-Shell

**Stand:** 2026-09-24  
**Gilt für:** `AnalyzerDesktopApp`, Fenster **Analyzer Result Extractor**  
**Nicht der Alltag:** Tab-Oberfläche `LegacyTestApp` (nur Support, siehe unten)

SQLite auf diesem PC ist die führende, strukturierte Ablage der Ergebnisse und Validierungen. Excel ist ein nachgelagerter Export. Ein späteres QMTool oder PostgreSQL gehört nicht zu dieser Version und ist hier keine zweite Wahrheit.

## Start

`AnalyzerResultExtractorV2.exe` starten oder auf dem Entwicklungs-PC `python test_app_main.py`. Ohne gesetztes `ARE_LEGACY_UI` öffnet sich die Sidebar mit **Auswertung**, **Ergebnisse**, **Regelwerke**, **Einstellungen** und **Diagnose**.

## Einstellungen

Unter **Einstellungen** vor dem ersten Lauf prüfen und mit **Speichern** sichern:

| Feld | Bedeutung |
|------|-----------|
| **Automatischer Import aktiv** | Beobachtet den Eingabeordner |
| **Eingabeordner** / **Archivordner** | Quelle und Ziel für Auto-Import |
| **Unterordner einbeziehen** | Auch PDFs in Unterordnern |
| **Ausgabemodus** | `both` (SQLite und Excel), `sqlite` (nur Datenbank) oder `excel` (nur Excel) |
| **Gerät** | Gerätezuordnung; **Neu laden** aktualisiert die Liste |
| **Operator-Initialen** | Vorschlag für die Validierung, keine Benutzerverwaltung |
| **SQLite-Pfad** unter **Erweitert** | Nur ändern, wenn die Datenbank nicht am üblichen Ort liegen soll |

**Ausgabeordner öffnen** zeigt den Excel-Ordner. Auto-Import ist standardmäßig aus, bis er hier aktiviert und gespeichert wird.

## Manueller Mehrfachimport

1. **Auswertung** öffnen.
2. **PDFs auswählen**. Im Dialog können mehrere PDFs gewählt werden.
3. Die Verarbeitung startet von selbst. Der Hinweis wechselt von **Bereit.** zum laufenden Vorgang.
4. In **Letzte Verarbeitungen** den Status prüfen. **Aktualisieren** lädt die Liste neu. **Ergebnis öffnen** springt zum Bericht, sobald einer vorliegt.

Manuell gewählte PDFs werden nicht in den Archivordner verschoben.

## Auto-Import, Watch und Archiv

In **Auswertung** zeigt **Automatischer Import** den Zustand **Aktiv** oder **Inaktiv**, dazu Eingabe, Archiv und Unterordner. Die Ordner selbst stehen unter **Einstellungen**.

Neue PDFs im Eingabeordner werden im Hintergrund erkannt und verarbeitet. Erst ein erfolgreich abgeschlossener Watch-Import (**Fertig**) wird in den Archivordner gelegt. Schlägt die Verarbeitung fehl, bleibt die PDF im Eingabeordner.

| Status | Bedeutung | Nächste Aktion |
|--------|-----------|----------------|
| **Wartet** | Eingereiht, noch nicht in Arbeit | Abwarten oder **Aktualisieren** |
| **Wird verarbeitet** | Lauf ist aktiv | Abwarten |
| **Verarbeitet - wird archiviert** | Ergebnis fertig, Archivierung läuft | Abwarten |
| **Fertig** | Verarbeitung abgeschlossen; Watch-Datei ist archiviert oder Archiv war nicht nötig | Ergebnis unter **Ergebnisse** prüfen |
| **Verarbeitung fehlgeschlagen** | Der Lauf ist nicht abgeschlossen | **Diagnose** |
| **Verarbeitet - Archivierung fehlgeschlagen** | Ergebnis ist da, die Datei konnte nicht archiviert werden | Archivordner und Datei prüfen; nicht manuell verschieben |
| **Klaerung erforderlich** | Quelle und Archivziel sind nicht eindeutig wiederherstellbar | Nicht manuell verschieben; Support |

## Ergebnisse und Validierung

**Ergebnisse** listet die gespeicherten Berichte. **Details anzeigen** öffnet die Messungen eines Berichts. **PDF öffnen** und **Ausgabeordner öffnen** führen zur Quelle bzw. zur Excel-Ausgabe.

Eine Messung auswählen. Der Bereich **Validierung** zeigt Initialen, Kommentar und die Historie.

| Berichtstatus | Bedeutung | Nächste Aktion |
|---------------|-----------|----------------|
| **Unvalidiert** | Noch keine gültige Validierung | Initialen prüfen, optional Kommentar, **Validierung speichern** |
| **Teilweise validiert** | Nur ein Teil der Messungen ist validiert | Offene Messung wählen und speichern |
| **Validiert** | Alle Messungen des Berichts sind validiert | Keine weitere Pflicht |
| **Prüfung erforderlich** | Fehler, Klärfall oder uneindeutige Historie | **Diagnose** bzw. Historie lesen, nicht still überschreiben |

Eine vorhandene Validierung wird nicht überschrieben. **Validierung korrigieren** fragt nach und legt einen neuen Eintrag an, der auf den bisherigen verweist.

## Diagnose und Nacharbeit

**Diagnose** hat zwei Bereiche: **Fehlgeschlagene Verarbeitungen** und **Klärfälle (Duplikate)**.

Bei einem fehlgeschlagenen Lauf den Eintrag wählen:

1. **Details** zeigt Fehlerart, Hinweis und, falls vorhanden, Assay-Kandidaten.
2. Fehlt ein Regelwerk: Kandidat wählen, **Draft aus Kandidat** bestätigen, im Rule Editor ergänzen und aktivieren, danach hier **Erneut verarbeiten**.
3. Liegt der Fehler nicht am Regelwerk: **Erneut verarbeiten**. Die Oberfläche meldet `Fehlerhafte Verarbeitung wird erneut ausgeführt …`.

Erneutes Auswählen derselben PDF oder ein neuer Auto-Import setzt einen fehlgeschlagenen Lauf nicht von selbst zurück.

## Export-only Retry

Sind die strukturierten Daten gespeichert und scheitert nur Excel, lautet der Hinweis genau:

`Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen`

Die Fehlerart ist **Excel-Ausgabe**. **Erneut verarbeiten** wiederholt dann nur diese Excel-Ausgabe. Die PDF wird nicht neu gelesen, die aktuellen Regelwerke werden nicht neu angewendet, und das bereits gespeicherte SQLite-Ergebnis wird nicht noch einmal geschrieben. Bereits geschriebene Excel-Zeilen werden nicht doppelt angelegt.

Bleibt die Excel-Datei gesperrt, bleibt der Eintrag fehlgeschlagen. Dieselbe Aktion nach dem Freigeben der Datei erneut ausführen. Danach soll der Status **Fertig** sein. Ein Watch-Import wird erst dann archiviert.

`Excel-Ausgabe fehlgeschlagen` ohne den Zusatz „Ergebnis gespeichert“ heißt: für diesen Lauf liegt kein erfolgreiches SQLite-Ergebnis vor. **Erneut verarbeiten** ist weiterhin dieselbe Schaltfläche.

## Klärfälle und Duplikate

Unter **Klärfälle (Duplikate)** stehen ausstehende Duplikate. **Details** zeigt den Vergleich. **Verwerfen** entfernt den Klärfall nach Bestätigung (`Duplikat-Kandidat … wirklich verwerfen?`).

Es gibt keine Schaltfläche, um ein vorhandenes Ergebnis zu überschreiben oder das neue Ergebnis zusätzlich anzulegen. Overwrite und Add sind nicht verfügbar.

## Regelwerke und Rule Editor

**Regelwerke** zeigt das Inventar. **Integrität prüfen** kontrolliert die Regeldateien. **Rule Editor öffnen** startet den Editor.

Im portablen Paket öffnet dieselbe EXE den Editor erneut. Auf dem Entwicklungs-PC geht auch `python rule_editor_main.py`. Aktivieren, Inaktivieren und Löschen bleiben im Editor: aktive Regelwerke werden inaktiviert, nicht gelöscht; Löschen gilt für Entwürfe und inaktive Stände und legt sie nach `rules/trash/`.

## Support-Fallback

Die alte Tab-Oberfläche ist nur für Support und Vergleich:

```powershell
$env:ARE_LEGACY_UI = "1"
.\AnalyzerResultExtractorV2.exe
```

Optionaler Tab **ADMIN** nur zusätzlich mit `ARE_SHOW_ADMIN=1`. Das ist nicht die normale Produkt-Oberfläche. `gui_min.py` gehört nicht zum Feldversuch-Paket.

Technische Einordnung: `docs/ARCHITECTURE.md`, Feldversuch: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`.
