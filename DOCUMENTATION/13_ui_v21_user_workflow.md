# UI 2.2 — Ablauf für die Produkt-Shell

**Stand:** 2026-11-14 (2.2.0; finaler Windows-Buildnachweis im Release)
**Gilt für:** `AnalyzerDesktopApp`, Fenster **Analyzer Result Extractor**  
**Nicht der Alltag:** Tab-Oberfläche `LegacyTestApp` (nur Support, siehe unten)

SQLite auf diesem PC ist die verbindliche Ablage neuer Ergebnisse und Validierungen. Das Original-PDF dient zur Prüfung. QK-Berichte werden unter **Statistik** vorbereitet und nach Bestätigung unveränderlich archiviert. Neue Verarbeitung und Validierung ändern keine Excel-Dateien; vorhandene Arbeitsmappen bleiben erhalten. Ein späteres QMTool oder PostgreSQL gehört nicht zu dieser Version.

## Start

`AnalyzerResultExtractorV2.exe` starten oder auf dem Entwicklungs-PC `python test_app_main.py`. Ohne gesetztes `ARE_LEGACY_UI` öffnet sich die Sidebar mit **Auswertung**, **Ergebnisse**, **Statistik**, **Validierung**, **Regelwerke**, **Einstellungen** und **Diagnose**.

## Einstellungen

Unter **Einstellungen** vor dem ersten Lauf prüfen und mit **Speichern** sichern:

| Feld | Bedeutung |
|------|-----------|
| **Automatischer Import aktiv** | Beobachtet den Eingabeordner |
| **Eingabeordner** / **Archivordner** | Quelle und Ziel für Auto-Import |
| **Unterordner einbeziehen** | Auch PDFs in Unterordnern |
| **Ablage** | Neue Ergebnisse und Validierungen werden immer in SQLite gespeichert |
| **Gerät** | Importvorschlag; das tatsächliche Gerät wird am Quellbericht bestätigt |
| **Operator-Initialen** | Vorschlag für die Validierung, keine Benutzerverwaltung |
| **SQLite-Pfad** unter **Erweitert** | Nur ändern, wenn die Datenbank nicht am üblichen Ort liegen soll |

**Ausgabeordner öffnen** zeigt den üblichen Ausgabeordner mit der Ergebnisdatenbank und vorhandenen historischen Dateien. Auto-Import ist standardmäßig aus, bis er hier aktiviert und gespeichert wird.

Alte Excel-Einstellungen werden beim Laden wirksam auf SQLite umgestellt, ohne die Einstellungsdatei zu verändern. Erst **Speichern** sichert SQLite und erhält die anderen Einstellungen. Es gibt keine Excel-Auswahl mehr.

## Manueller Mehrfachimport

1. **Auswertung** öffnen.
2. **PDFs auswählen**. Im Dialog können mehrere PDFs gewählt werden.
3. Die Verarbeitung startet von selbst. Der Hinweis wechselt von **Bereit.** zum laufenden Vorgang.
4. In **Letzte Verarbeitungen** den Status prüfen. **Aktualisieren** lädt die Liste neu. **Ergebnis öffnen** springt zum Bericht, sobald einer vorliegt.

Manuell gewählte PDFs werden nicht in den Archivordner verschoben.

## Auto-Import, Watch und Archiv

In **Auswertung** zeigt **Automatischer Import** den Zustand **Aktiv** oder **Inaktiv**, dazu Eingabe, Archiv und Unterordner. Die Ordner selbst stehen unter **Einstellungen**.

Neue PDFs im Eingabeordner werden im Hintergrund erkannt und verarbeitet. Nach erfolgreicher Verarbeitung wird die Watch-Datei archiviert; das wartet nicht auf die spätere menschliche Validierung. **Fertig** bestätigt den Abschluss. Bei einem SQLite-Fehler bleibt die PDF im Eingabeordner.

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

**Ergebnisse** listet die gespeicherten Berichte. **Details anzeigen** öffnet die Messungen eines Berichts. **PDF öffnen** und **Ausgabeordner öffnen** führen zum Original-PDF bzw. zum üblichen Ausgabeordner.

**In Validierung prüfen** öffnet Original-PDF und die Messungen des konkreten Berichts. Das Gerät einmal für den ganzen Bericht auswählen und bestätigen; danach jeden Assay mit Initialen und optionalem Kommentar einzeln freigeben. **Gerät hier anlegen** braucht nur einen unterscheidbaren Namen und erhält die begonnene Eingabe. Der Importvorschlag ist noch keine Gerätebestätigung.

Eine vollständige Freigabe entfernt die Messungen aus der offenen Arbeitsliste. In **Ergebnisse → Validierung / Berichtgerät korrigieren** bleibt der Bericht erreichbar. Der bisherige und neue Gerätestand, betroffene Messungen/Assays und bestehende Chargen werden angezeigt. Ein Gerätewechsel braucht einen Grund; jeder betroffene Assay muss danach erneut freigegeben werden. Frühere Validierungen und QK-Berichte werden nicht überschrieben. Die Hauptnavigation **Validierung** führt zurück zu allen offenen Berichten.

## Profil und Qualitätskontrolle

Auch vor dem ersten Import unter **Einstellungen → Assays & QK** einen Assay wählen. Profil-/Levelname und IST-Feld genügen. Profil und Gerät benötigen keine Initialen; Gerätename genügt, SN/LNR/EVA sind optional. Standard ist ein assayweites Profil, bei weiterhin gerätegetrennter Auswertung. SOLL/MIN/MAX, Datum-/Zeitformate und Westgard können später ergänzt werden. Für die Statistik eine gemeinsame Einheit bestätigen oder die Größe ausdrücklich dimensionslos markieren.

Leere Datums-/Zeitformatfelder bedeuten automatische Erkennung bekannter Formate. Vorhandene bewusste Overrides bleiben erhalten. Unbekannte Uhrzeiten werden nicht erfunden. Fehlende Grenzen oder Zeitangaben sperren nur die Funktionen, die diese Angaben wirklich benötigen. Neue Profile haben Westgard ausgeschaltet.

Ein begonnener Entwurf bleibt in der Sitzung erhalten, auch bei Inline-Geräteanlage oder Eingabefehlern. Beim Schließen kann **Entwurf behalten** gewählt werden. Der benannte Entwurf erscheint danach in derselben Übersicht mit **Entwurf fortsetzen**. **Weiteres Profil** kann bestehende Zuordnungen als neue Kopie übernehmen; veröffentlichte Fassungen bleiben erhalten.

Unter **Statistik** Gerät/Assay/Kit-Charge auswählen. Kontrollserien und Kennzahlen verwenden nur freigegebene, passend zugeordnete Messungen dieses Geräts. **Abschluss prüfen** zeigt eine unverbindliche Vorschau; erst die Bestätigung speichert Modell und PDF zusammen. Geänderte Quellen oder Gerätestände erfordern eine neue Prüfung. Historische Original-PDFs werden bytegleich unter neuem Dateinamen exportiert.

## Diagnose und Nacharbeit

**Diagnose** hat zwei Bereiche: **Fehlgeschlagene Verarbeitungen** und **Klärfälle (Duplikate)**.

Bei einem fehlgeschlagenen Lauf den Eintrag wählen:

1. **Details** zeigt Fehlerart, Hinweis und, falls vorhanden, Assay-Kandidaten.
2. Fehlt ein Regelwerk: Kandidat wählen, **Draft aus Kandidat** bestätigen, im Rule Editor ergänzen und aktivieren, danach hier **Erneut versuchen**.
3. Liegt der Fehler nicht am Regelwerk und handelt es sich um einen neuen Verarbeitungsfehler: **Erneut versuchen**. Die Oberfläche meldet `Fehlerhafte Verarbeitung wird erneut ausgeführt …`.

Erneutes Auswählen derselben PDF oder ein neuer Auto-Import setzt einen fehlgeschlagenen Lauf nicht von selbst zurück.

## Historische Excel-Fehler

Alte Fehler und eingefrorene Ausgabepläne bleiben zur Diagnose lesbar. **Details** zeigt den gespeicherten technischen Stand. Die Anzeige erklärt, dass der historische Ausgabeplan schreibgeschützt ist; **Erneut versuchen** ist dafür deaktiviert.

Es wird kein alter Export fortgesetzt, keine Arbeitsmappe geändert und keine PDF erneut extrahiert, um Excel zu reparieren. Vorhandene Dateien und gespeicherte Zustände bleiben durch die Umstellung erhalten. Ein alter fehlgeschlagener Stand wird nicht automatisch als fertig markiert.

## Offene Messungen erneut analysieren

In **Validierung** bleiben links das Original-PDF und rechts die Arbeitsliste.
Eine oder mehrere noch unvalidierte Messungen mit Strg/Umschalt markieren und
**Erneut analysieren** wählen. Die Fälle werden nacheinander mit dem jetzt
aktiven Regelwerk und ihrem ursprünglichen Gerät geprüft. Die fokussierte
markierte Zeile bestimmt PDF, Vergleich und spätere Einzelentscheidung.

Der Vergleich zeigt sämtliche alten und neuen Felder sowie Quellen-, Regel- und
Identitätsnachweise. Geänderte Werte sind hervorgehoben. **Alte Werte behalten**
oder **Neue Werte übernehmen** wählt jeweils das ganze Ergebnis. Danach die
gewählten Werte prüfen und separat **Validierung speichern** wählen. Die
Neuanalyse und die Auswahl erzeugen keine automatische Validierung.

Jedes im Regelwerk konfigurierte Feld muss gefüllt sein, auch ein dort als
optional bezeichnetes Feld. Das gilt für die alten und die neuen Werte. Bei
fehlenden Feldern **Regelwerk bearbeiten**, die Regel prüfen/aktivieren und
erneut analysieren. Vollständige alte Werte können nach belegter Quelle
ausdrücklich beibehalten werden, wenn die neue Extraktion fehlschlägt.

Fehlende/mehrdeutige Originalquellen, ein abweichender PDF-Nachweis oder eine
Kollision der korrigierten Messungsidentität mit einer anderen Messung müssen
zuerst geklärt werden. Alte Ergebnisse, Analyseversuche und Entscheidungen
bleiben in der Historie. Bereits validierte Messungen sind nicht für diese
Neuanalyse freigegeben. Nach einem Wechsel der Datenbank oder einem inzwischen
geänderten Ergebnis fordert die Anwendung zum Aktualisieren auf.

## Klärfälle und Duplikate

Unter **Klärfälle (Duplikate)** stehen ausstehende Duplikate. **Details** zeigt den Vergleich. **Verwerfen** entfernt den Klärfall nach Bestätigung (`Duplikat-Kandidat … wirklich verwerfen?`).

Es gibt kein manuelles Überschreiben oder willkürliches Zusätzlich-Anlegen. Ein eigener Quellbericht steht auch in der Validierung. Nur ein belegbar anderes bestätigtes Gerät kann aus einem qualifizierten Kandidaten eine eigene Messung machen. Ein gleiches oder ungeklärtes Gerät bleibt ein Klärfall; identische PDF-Bytes werden nicht erneut gezählt.

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
