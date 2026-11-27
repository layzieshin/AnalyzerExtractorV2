# Analyzer Result Extractor 2.3.0

Diese Ausgabe enthält den überarbeiteten lokalen Analyzer mit der integrierten RuleSuite und 25 im Verwaltungskatalog verzeichneten Herstellerkennungen.

- Der Regelarbeitsplatz zeigt Extraktionsfelder und Markierungen zusammen. Original-PDF und Text lassen sich umschalten; der Regex-Baukasten bleibt ein eigenes Fenster.
- Beim Prüfen einer Regel wählst du eine Test-PDF. Die RuleSuite sucht die zweite Gegenprüfung automatisch; eine fachliche Freigabe wird nicht durch den Download vorweggenommen.
- Neue Herstellerkennungen zu einem bekannten Assay sind unter **Änderungen** sichtbar und lassen sich dem passenden Regelwerk zuordnen.
- Parvovirus B19 IgM und die beiden Chlamydien-IgA-Regeln unterscheiden Kalibrator, positive und negative Ratio-Kontrolle. Einige weitere Regeln sind zum Vervollständigen in der RuleSuite vorbereitet.

**Windows:** Das portable ZIP vollständig in einen neuen Ordner entpacken und `AnalyzerResultExtractorV2.exe` starten. Die Datei benötigt die beiliegenden Ordner `_internal` und `rules`.

**Bestehende Installationen:** Diese Ausgabe veröffentlicht den lokal weiterentwickelten Produktstand, nicht eine Zusammenführung aller Funktionen aus 2.1/2.2. Eine Übernahme von Arbeitsdatenbanken aus 2.1/2.2 ist nicht qualifiziert. Bestehende Installation, Regeln und Arbeitsdaten behalten; 2.3 zunächst getrennt verwenden.
