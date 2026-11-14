# Analyzer Result Extractor V2 2.2.0

## Einfacher Einstieg und optionale QK

Ein Profil kann vor dem ersten PDF-Import im ausdrücklich gewählten, noch nicht vorhandenen SQLite-Speicher angelegt werden. Assay, Profil-/Levelname und IST-Zuordnung genügen. Gerät, SOLL, MIN/MAX sowie Datums-/Zeitformat sind optional. Geräte brauchen nur einen unterscheidbaren Namen; SN, LNR und EVA können später ergänzt werden. Initialen gehören zur fachlichen Bedienhandlung, nicht zur Profil- oder Gerätepflege.

Profile gelten standardmäßig assayweit; Auswertungen bleiben je Gerät getrennt. Eine gemeinsame Einheit wird im Profil bestätigt, wenn die Werte statistisch verwendet werden, oder ausdrücklich als dimensionslos angegeben. Bestehende Profilfassungen bleiben unverändert; jede bewusste Speicherung im neuen Editor erzeugt die neue optionale Profilfassung und erhält explizite Format-/Zahleneinstellungen und die bisherige Westgard-Auswahl.

Entwürfe bleiben innerhalb der Sitzung erhalten, auch beim Inline-Anlegen eines fehlenden Geräts. Beim Schließen kann ein unvollständiger Entwurf ausdrücklich behalten werden. Er erscheint danach mit Namen unter **Assays & QK → Entwurf fortsetzen**.

## Berichtgerät und Validierung

Das physische Gerät wird in der Validierung für den gesamten Quellbericht bestätigt. Jeder Assay wird anschließend einzeln freigegeben. Ergebnisse führt auch nach vollständiger Freigabe in denselben Arbeitsbereich zur Korrektur. Ein Gerätewechsel zeigt die Auswirkungen, braucht einen Grund und erfordert eine erneute Freigabe aller betroffenen Messungen. Frühere Validierungen und archivierte Berichte bleiben erhalten.

Unterschiedliche PDF-Quellen mit derselben ursprünglichen Importidentität können erst nach belastbar bestätigter Gerätezuordnung eigene Messungen auf unterschiedlichen Geräten werden. Gleiche oder ungeklärte Geräte bleiben sichtbare Duplikat-/Klärfälle. Wiederholte identische PDF-Bytes werden nicht erneut gezählt. Ein dritter Bericht auf einem bereits belegten Gerät legt keine weitere Messung an; unabhängig verwertbare Assays desselben Berichts bleiben bearbeitbar.

## Kennzahlen ohne unnötige Pflichtfelder

IST-Werte, Zielabweichung, Herstellergrenzen und zeitabhängige Regeln haben eigene Voraussetzungen und Nenner. Das gilt bei neuen Live-Auswertungen auch für unverändert vorhandene Profile; ein erneutes Speichern ist dafür nicht erforderlich. Fehlende SOLL-/MIN-/MAX-Werte oder unbekannte Zeiten sperren keine ansonsten zulässigen deskriptiven Kennzahlen. Bekannte Datum-/Zeitformate werden automatisch erkannt; es werden weder Uhrzeiten noch Messreihenfolgen erfunden. Die tatsächlich angewandte Zahlenauslegung wird eingefroren.

Westgard ist für neue Profile ausgeschaltet und kann bewusst mit passender Referenz aktiviert werden. Inaktive Regel- und SD-Referenzblöcke entfallen im normalen Bericht und Diagramm. Ältere Analysemodelle und archivierte Original-PDFs bleiben lesbar und werden beim Originalexport bytegleich ausgegeben.

## Windows-Paket und Update

Das Release-ZIP vollständig entpacken und `AnalyzerResultExtractorV2.exe` starten. `_internal` und `rules` gehören zum Paket. Auf dem Ziel-PC ist keine Pythoninstallation nötig.

Für ein Update die Anwendung schließen und den bisherigen Ordner sichern. **EXE, `_internal` und `build-info.json` ersetzen; vorhandene `rules`, `storage`, `jobs`, `input` und `output` behalten**, einschließlich SQLite und eingefrorener Verarbeitungsbelege. Eigene Regelwerke und die historischen Quellpfade gehören zur bestehenden Installation.

Der Windows-Build prüft die vollständige Suite mit echtem Tk-Erstnutzungsablauf, Regeln, Bundle und eingefrorener EXE. Der beigefügte Buildnachweis nennt den tatsächlichen Commit und Eingabefingerprint; JUnit und Desktop-Start-/Schließnachweis dokumentieren die ausgeführte Abnahme. Feature-Builds werden als Actions-Artefakt bereitgestellt. Erst ein erfolgreicher Build des geprüften Master-Mergecommits veröffentlicht das Release.

## Bekannte Grenze

Die unveränderte Originalregel Anti-dsDNA-NcX IgG `(661f)` hat einen bereits vorhandenen Konflikt zwischen dem Startanker des Feldes `VALIDATION` und dem mit dem Assaynamen beginnenden PDF-Block. Ein echter PDF-Gesamtimport dieses Assays ist damit nicht abgenommen. Die explizite Altidentität ist an einem klar synthetischen Komponentenfall geprüft. Die echten Zwei-Assay-PDF-Abnahmen verwenden unveränderte ANA `(1c9e)` und Anti-DFS70 `(0437)`. Es wird keine vollständige klinische Abnahme aller elf Originalassays behauptet; Regel-JSONs und Extraktionspipeline wurden nicht umgebaut.
