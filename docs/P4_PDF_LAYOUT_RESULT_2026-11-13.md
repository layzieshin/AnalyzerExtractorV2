# P4: Kompakter A4-Ausdruck und eingefrorene Kennzahlen

Stand: 13.11.2026. **GATE_PASSED – unabhängige Root-Abnahme abgeschlossen.** Die spätere ausdrückliche Nutzerkorrektur ersetzt den ursprünglichen Plan obligatorischer Papiernachweise: elf normale Messungen auf einer Seite; 60 Messwertzeilen insgesamt auf höchstens drei Seiten. Technische Einzelprobenbelege sind optional und standardmäßig aus.

## Modell und bestehende Owner

Neue Analysen verwenden Schema 3 / `arev2-qc-analysis-v4` / `arev2-qc-pdf-v4`. Das historische Tupel Schema 2 / analysis-v3 / pdf-v3 bleibt literal unterstützt, ebenso die vier alten Schema-1-Tupel. Eine echte vor P4 erstellte Schema-2/v3-Modell-/PDF-Fixture bleibt unverändert.

`qualitycontrol.analysis` friert pro Level n, Mittelwert, empirische SD (n−1), VK, Zeitraum und Mittelwertlinie sowie pro Punkt Darstellungsposition, echte Datums-/Zeitpräzision und absolute/relative Abweichung ein. Nur bereits geeignete Werte gehen in die Statistik ein; n < 2, nichtpositiver Mittelwert und nichtpositiver SOLL erhalten passende Nichtverfügbarkeit statt Ersatzwerten. QMMA, SD-Herkunft und Westgard bleiben unabhängig. UI und Renderer berechnen diese Werte nicht erneut.

## Druckverhalten nach Nutzerkorrektur

Der bestehende begrenzte Spawn-Renderer zeichnet A4 mit belegten Stammdaten, Diagramm/rechter Legende, zwei Kennzahlspalten, Messwerttabelle und leeren Unterschriftsfeldern. Eingebaute Times-Roman/Times-Bold benötigen keine externen Fontdateien. Messwerte sind 7,5 pt, normale Zeilen 14 pt; Datum und tatsächliche Zeit bleiben in einer Zeile einschließlich belegter Sekunden. Enge Achsenbeschriftungen werden ausgelassen, reale Koordinaten nicht verschoben.

Fortsetzungen wiederholen Gerät, Assay, Kit-/Reagenzcharge, Level und Tabellenkopf. Ein weiteres Level kann auf derselben Seite beginnen, wenn sein vollständiger Kopf, Diagramm, Statistik und mindestens eine Tabellenzeile passen. Seine Signaturfelder folgen seiner letzten Messwertgruppe. Ausschlüsse, Grenzverletzungen, Westgard-Ablehnungen/Warnungen und mehrdeutige Anwender bleiben mit Position und verständlichem Hinweis sichtbar; gekürzte Rohangaben tragen eine Ellipse. SD-/Westgard-Nichtverfügbarkeit wird knapp und wahrheitsgemäß genannt.

Standarddruck enthält keine wiederholte Papierliste aller Rohwerte, Hashes, Tokens oder Validatorzeiten. Der vollständige Nachweis bleibt im bestehenden eingefrorenen Analysemodell und beim Abschluss im selben autoritativen SQLite-Nachweis. Der PDF-Fuß bindet die Modellkennung. Es wurde kein automatischer JSON-/Rohdatenanhang und keine neue Exportoberfläche eingeführt.

`include_explanations=True` ergänzt die positionsgebundene vollständige technische Evidenz, Methoden und vollständigen Regelbefunde. Identische Angaben werden gruppiert, vollständige Tokens/Hashes erhalten, lange Ausnahmen in positionsgebundenen Zusatzblöcken ausgegeben. Diese bewusste Zusatzfassung unterliegt nicht der Drei-Seiten-Anforderung für den Standarddruck. Die vorhandene Checkbox heißt **Erläuterungen und zusätzliche Nachweise mitdrucken**, beginnt mit false und wird nach erfolgreichem Export zurückgesetzt; bei Fehler bleibt sie für Retry erhalten.

## Historischer fokussierter Writer-Stand

Final fokussiert: **34 bestanden, 0 Fehler, 0 Skips in 44,20 s**. Auswahl: sämtliche `tests/test_qualitycontrol_pdf.py` plus der bestehende Shell-Exporttest mit Capture, erfolgreichem Reset und erhaltenem Fehler-Retry. Beleg außerhalb des Repositories: `test_runs/p4_rework2_focused.xml`.

Echte synthetische SQLite-Store-Beispiele erzeugten **11 = 1 Seite**, **60 eines Levels = 2 Seiten**, **2 × 30 = 3 Seiten**. Alle sechs Standardseiten wurden mit Poppler gerendert und visuell geprüft. Die neuen Regressionen zählen alle 60 Tabellenpositionen, prüfen lange Bezeichnungen, sichtbare Ausschluss-/Grenzgründe, unveränderte Modellbytes/-hashes, Randgeometrie, fehlende technische Standardlisten und keine PDF-Anlagen. Der optionale 120-Punkte-Test prüft vollständige Hashes/Tokens/point_key, Validatorbindung und lange Rohwertausnahmen ohne Modellmutation.

Unabhängige vorangegangene Root-Nachweise bleiben für unveränderte Analyse-/Versionsowner gültig: acht numerische Vektoren plus Ausreißer, 48 Versionstupel und 242 native fokussierte Fälle ohne Skips. Diese historischen Auswahlen werden nicht zum späteren Vollsuiteresultat aufsummiert. Keine Vollsuite oder Git-Aktion durch den Writer.

## Abschließende unabhängige Root-Abnahme

Root erzeugte die PDFs eigenständig aus synthetischen realen SQLite-Stores:

| Fall | Beobachteter Umfang |
|---|---|
| 11 normale Messungen | 1 Seite |
| 60 Messungen eines Levels | 2 Seiten |
| 2 × 30 Messungen mit langen Bezeichnungen | 3 Seiten |
| 120 Punkte einschließlich ungültigem Rohwert | 4 Seiten |

Alle zehn Seiten wurden mit Poppler gerendert und repräsentative Ansichten in voller Größe geprüft. Die Geometrieprüfung fand **keine Randüberschreitungen**. Vollständige Rohdaten blieben im eingefrorenen Modell; keine PDF-Rohdatenanlage wurde eingebettet und das Rendern änderte das Modell nicht. Externe Belege: `test_runs/root_p4_pdf_geometry_final.json` und `test_runs/root_final_review.json`.

Die abschließende native Vollsuite bestand mit **1418 bestanden, 0 fehlgeschlagen, 0 Fehler, 0 Skips in 86,06 s** (`test_runs/final_native.xml`). Anschließend bestätigte Root sämtliche **249 Python-Hashes** des funktionalen Freeze `tmp/P4_rework2_freeze.json`. Modell-/Analyse-/Store-/API-Verträge und echte alte Archivfixtures bleiben durch das Druck-Rework unverändert. Root erteilte **P4+A1-GO** für den Quellstand 2.1.0; Status **GATE_PASSED**. Gesamtbelege und getrennte Veröffentlichungsgrenze: [A1-Prüfbericht](A1_FINAL_VERIFICATION_2026-11-13.md).

## Historie und Grenzen

Normaler Archivexport verwendet weiterhin exakte gespeicherte Originalbytes, ohne Quellenread, Neuberechnung oder Rendereraufruf. Optionaler Altmodelldruck erfindet keine fehlenden Kennzahlen. Analyse/Modell/Store/API-Signaturen und Archivfixtures wurden im Druck-Rework nicht geändert. Seiten-/Byte-/Zeitlimits, Prozessabbruch und No-Clobber-Export bleiben erhalten. Synthetische Linux-/Tk-/PDF-Nachweise sind keine Windows-EXE- oder klinische Konformitätsqualifikation.
