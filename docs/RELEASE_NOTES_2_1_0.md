# Analyzer Result Extractor 2.1.0

Stand: 13.11.2026. **GATE_PASSED – Root-GO für den Quellstand 2.1.0** mit dem vereinbarten Gesamtpaket P1/P2/P3/R1/P4. Die abschließende native Vollsuite bestand mit **1418 bestanden, 0 fehlgeschlagen, 0 Fehler, 0 Skips in 86,06 s**. Die unabhängige Druckabnahme und fünf CLI-Smokes sind bestanden; Einzelbelege stehen im [A1-Prüfbericht](A1_FINAL_VERIFICATION_2026-11-13.md). Der GitHub-Upload folgt separat durch Root. Eine Windows-EXE wurde für diesen Quellstand nicht gebaut oder qualifiziert.

## Assays und Qualitätskontrolle

- **Assays & QK** zeigt konfigurierte und unkonfigurierte Assays. Frei benannte Profile/Level verwenden ausschließlich passende aktuelle Assayfelder; bestehende Bindungen und historische Fassungen bleiben erhalten.
- Herstellergrenzen und Einzelwert-Prozentgrenzen werden unabhängig von der bisherigen QMMA-Schwelle und SD/Westgard ausgewertet. Prozentgrenzen verwenden SOLL × (1 ± p/100); ein auffälliger Einzelwert bleibt bei sonstiger Eignung Bestandteil der Statistik.
- Neue eingefrorene Analysen ergänzen n, Mittelwert, empirische SD (n−1), VK, absolute/relative Abweichung, Zeitraum und echte Datums-/Zeitpräzision. Die empirische SD ersetzt keine freigegebene Westgard-Referenz.

## Chargenabschluss und Nachweise

**Abschluss prüfen** erstellt eine unverbindliche Vorschau anhand des vollständigen relevanten Nutzungsverlaufs. Ein sicher späterer Nutzungszeuge kann unvalidiert oder numerisch ungeeignet sein. Vorschau und Abbruch schreiben nichts; die abschließende Zustimmung publiziert exakt das vorbereitete Modell und PDF. Änderungen am geprüften Kontext blockieren veraltete Vorschauen.

Der Standardausdruck **KONTROLLPROBENEINZELMESSUNG** verwendet kompakte A4-Seiten, eine druckbare Serifentypografie, Diagramm mit Legende, Kennzahlen, einzeiliges Datum/Zeit, gleichmäßige Tabellenzeilen und leere Unterschriftsfelder. Ausschlüsse und wichtige Befunde sind positionsbezogen sichtbar. Zusätzliche Einzelprobenbelege und technische Identitäten werden nur auf Wunsch mitgedruckt; der vollständige digitale Nachweis bleibt im unveränderten Analysemodell. Es gibt keinen neuen PDF-Rohdatenanhang.

Beobachtete synthetische Druckbeispiele: **11 Messungen auf 1 Seite**, **60 Messungen eines Levels auf 2 Seiten**, **30 Messungen je zwei Level auf 3 Seiten**, auch mit längeren Bezeichnungen. Die ausdrücklich gewählte Option **Erläuterungen und zusätzliche Nachweise mitdrucken** darf mehr Papierseiten erzeugen und wird nach erfolgreichem Export zurückgesetzt.

Gespeicherte Original-PDFs werden weiterhin bytegenau exportiert. Alte Modellfassungen werden weder migriert noch um neue Statistik ergänzt. Zusätzliche Druckfassungen verwenden ausschließlich das gespeicherte Modell.

## Regelwerke

Der geladene Entwurf wird mit echten PDFs geprüft, bevor genau eine abschließende Aktivierungsbestätigung angeboten wird. Ein Update braucht eine eigenständige passende Referenz. Der Nachweis bindet eingefrorene Eingabebytes, Modus und aktive Bindung; veraltete und überholte Prüfversuche können keinen neueren Stand freigeben. Erfolgreiche Prüfung allein aktiviert nichts. Ein Update erhält die exakten alten Active-Bytes in der History.

Der echte Worker liefert seine Ergebnisse über den bestehenden TkTaskRunner auf dem Hauptthread aus. Schmale Editoransichten und hostunabhängige Draftnamenprüfung wurden korrigiert. Vier frühere plattformabhängige Testkontexte wurden gezielt portabel gemacht; es wurden keine fachlichen Fehler durch zusätzliche Skips verborgen.

## Kompatibilität und Grenzen

Vier Controller, sieben Hauptansichten, bestehende öffentliche API-Grenzen und der ausdrücklich ausgewählte SQLite-Store bleiben erhalten. Ausgelieferte Regel-JSONs, produktive Eingaben, historische Archivbytes und Governance-Dateien wurden nicht umgeschrieben. Die technischen Berechnungen und Anzeigen sind keine neue normative Rili-BÄK-Konformitätszusage. Native Linux-/Tk-Prüfungen ersetzen keine Windows-/EXE-/Netzlaufwerksqualifikation.
