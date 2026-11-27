# Eingang aufräumen (ab 2.4.0)

Unter **Ergebnisse → Eingang aufräumen** einen Stichtag einschließlich wählen und
die Vorschau prüfen. Der Eingangsordner darf zugleich Archivstamm sein: lose
PDF-/RES-Dateien liegen beispielsweise neben `Result/2026/11_November/res/`.
Nur lose Dateien werden betrachtet, keine bisherigen Jahres-/Monatsarchive.
Die Vorschau schreibt nichts und läuft außerhalb des Tk-Ereignisthreads.

Vollständige Läufe sind vorausgewählt. Monatsziel und Prüfstatus sind je Platte
sichtbar; die ausgewählte Zeile zeigt den vollständigen Zielpfad und Prüfgrund.
**Ausgewählte Läufe ablegen** bestätigt. Platte und Messdatum stammen aus echten
PDF-Köpfen bzw. widerspruchsfreien validierten Feldern, niemals aus einem
zufälligen PDF-Dateinamen. Jedes erwartete Ergebnis muss vollständig importiert
und in seiner ausgewählten Fassung validiert sein. Ungeklärte Duplikate,
fehlende Importe oder widersprüchliche Kopffeld-Aliasse sperren die Platte.

RES-Stamm und Platte müssen exakt übereinstimmen, Groß-/Kleinschreibung wird
ignoriert. Abweichende RES können ausdrücklich zugeordnet werden; die bestätigte
Verbindung bleibt für spätere Exporte derselben Platte, desselben Datums und
Ergebnisspeichers erhalten. Ohne RES ist nur eine ausdrückliche Ausnahme **für
die konkrete PDF** möglich, mit Initialen und UTC-Zeitpunkt. Sie wird nicht auf
nachgereichte Dateien übertragen. Alleinige RES im Format `YYYYMMDD_Test.res`
werden nach ihrem Datum abgelegt. Eindeutige vorhandene Monatsordner-Varianten
werden verwendet; andere Inhalte werden nie überschrieben.

Zuerst werden **alle** Gruppenziele exklusiv als private Teilkopien erstellt,
synchronisiert und mit vollständigem SHA geprüft. Erst nach erneutem Gruppen-,
RES- und Nachweisabgleich werden Originale entfernt. Windows-Dateihandles und
eine erneute Identitätsprüfung beim Entfernen schützen gegen Ersetzungen.
Das private Ingestion-Journal protokolliert jede Datei. Nach einem Abbruch
**Unterbrochenen Vorgang fortsetzen** verwenden; geänderte Quellen oder Ziele
bleiben zur Klärung erhalten. Die Wache muss nicht eingeschaltet sein. Links
und Junctions sind keine zulässigen Quellen oder Archivpfade.

## Importmodus

**Einstellungen → Import** bietet den bisherigen Sofortarchivmodus und optional
den Monatsmodus. Neue Ordnerimporte bleiben im Monatsmodus nach Verarbeitung im
Eingang bis zum ausdrücklichen Aufräumen. Monatsziel ist der konfigurierte
Eingang selbst. Unterordner werden nicht gescannt; die bestehende Unterordner-
Option ist nur beim Sofortarchiv wirksam. Schon registrierte alte Importe behalten
ihre damals bestätigte Sofortarchivroute, sie werden nicht heimlich umgestellt.
Headless gilt derselbe gespeicherte Modus; ohne gespeicherte Vorgabe ist
`ARE_ARCHIVE_MODE=monthly` möglich. Standard bleibt `immediate`.

## PDF wiederfinden

In Ergebnisdetails und bei betroffenen PDFs eines Herstellerkennungsfalls steht
**PDF wiederfinden** zur Verfügung. Eine Datei oder ein rekursiv zu durchsuchender
Ordner kann gewählt werden. Nur ein eindeutiger Treffer mit exaktem vollständigem
Original-SHA wird zugeordnet. Bei mehreren Treffern eine konkrete Datei wählen.
Ein verlorener neuer Ort fällt nicht auf fremde Bytes am alten Dateinamen zurück.

Der aktuelle Ort ist ein privater Ingestion-Betriebsbeleg. Historische Job-/Queue-/
Result-/Regelprüfbelege und Rohwerte werden nicht umgeschrieben. Die Vorschau
rendert einen verifizierten Byte-Snapshot; der externe Viewer bekommt den echten
geprüften Pfad unter Leseschutz während der Übergabe. Neuanalyse, Herstellerfall-
Wiederverarbeitung und RuleSuite-Zweitprüfung verwenden denselben verifizierten
Ort. Der ursprüngliche Pfad bleibt die Quellenidentität, der neue Ort liefert nur
die hashgebundenen Bytes.
