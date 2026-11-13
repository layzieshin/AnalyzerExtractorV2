# A1: Integrierte Abschlussprüfung 2.1.0

Stand: 13.11.2026. **GATE_PASSED – Root-GO für den Quellstand 2.1.0.** Die unabhängige P4-Druckabnahme und die abschließende native Vollsuite sind bestanden. Der GitHub-Upload folgt als separate Root-Aktion; eine Windows-EXE wurde nicht gebaut oder qualifiziert.

## Auftrag, Ausgangsstand und Zuständigkeit

Der Nutzer hat die vereinbarten Pakete P1/P2/P3/R1, das ergänzte P4-Drucklayout, die späteren Druckkorrekturen und den abschließenden GitHub-Upload ausdrücklich autorisiert. Ein Product-Writer implementiert; Root prüft und übernimmt die abschließende GitHub-Aktion. Governance-Dateien wurden nicht geändert. Angeforderte Modellrollen sind keine Laufzeitattestation; beobachtete Modell-/Effort-Telemetrie ist nicht verfügbar.

Die Arbeitskopie wurde aus dem bestätigten Remote-Stand `489ffe2a06ab166992b8eeb754bb0fb6ba2ecbfa` materialisiert und besitzt kein `.git`. Externe Safety-Snapshots und Hashmanifeste sichern Ausgangsstand und Phasen. Kein lokal beobachteter HEAD, keine Windows-EXE und kein abgeschlossener GitHub-Push werden vorweg behauptet. Alle Prüfdateien und Stores sind synthetisch; ausgelieferte Regel-JSONs, produktive Daten und historische Archivbytes bleiben erhalten.

## Paketabnahmen

| Paket | Vorliegender Nachweis |
|---|---|
| P1 | Root-Fach-/UI-GO und 45 native Reworkfälle ohne Skips; der damalige Vollsuitestand 1267 bestanden / 6 Fehler ist historisch dokumentiert. Ursachen der sechs Befunde wurden im später autorisierten R1 behandelt. |
| P2 | Root-GO; 72 native Tests ohne Skips, tatsächliche App- und PDF-Sichtprüfung. |
| P3 | Root-GO; 246 native Tests ohne Skips und 5 enge Reworkfälle; echter Preview-/Abbruch-/Erstabschluss-/Archiv-/bytegenauer UI-Exportablauf. |
| R1 | Root-GO; 424 native Tests und 148 native Reworkfälle ohne Skips; echte Worker-, Create-/Update-, Abbruch-, Referenzblocker- und History-Byteprüfungen bei 1024×768 und 1280×900. |
| P4 | Root-GO: unabhängig erzeugte Store-PDFs mit 11/60/2×30 Messungen auf 1/2/3 Seiten sowie 120 Punkten mit ungültigem Rohwert auf 4 Seiten; alle Seiten mit Poppler gerendert, repräsentative Ansichten in voller Größe geprüft, keine Randüberschreitungen. Historischer Writer-Fokus: 34 bestanden ohne Fehler/Skips in 44,20 s. |

Detailberichte: [P1](P1_ASSAYS_QK_RESULT_2026-11-13.md), [P2](P2_QK_LIMITS_RESULT_2026-11-13.md), [P3](P3_LOT_CLOSE_RESULT_2026-11-13.md), [R1](R1_RULE_RELEASE_RESULT_2026-11-13.md), [P4](P4_PDF_LAYOUT_RESULT_2026-11-13.md).

## Integrierte Nachweise

| Prüfung | Tatsächlich vorliegender Stand |
|---|---|
| Finale native Vollsuite | **1418 bestanden, 0 fehlgeschlagen, 0 Fehler, 0 Skips in 86,06 s**; externer JUnit-Beleg `test_runs/final_native.xml`. Eigenständiger Gesamtlauf, keine Summe fokussierter Ergebnisse. |
| CLI-Smokes im isolierten synthetischen Projekt | Root: `rules_validate_main.py`, `rules_matrix_main.py --mode preview --no-write-report`, `main02.py`, Watchdog und Worker jeweils Exit 0; beide Assays in der Matrix grün, drei verarbeitete PDF-Runs, drei SQLite-Zeilen. Alle 121 CLI-Owner-Dateien sind byteidentisch zur geprüften Ausführungskopie. |
| Ausgelieferte Rules-Integrität | Root: alle fünf Fehlerlisten leer. |
| P4 Standarddruck | Root: elf Messungen 1 Seite, 60 eines Levels 2 Seiten, 30 je zwei Level mit langen Namen 3 Seiten; zusätzlicher 120-Punkte-Stressfall mit ungültigem Rohwert 4 Seiten. Poppler-Prüfung aller zehn Seiten und Geometrieprüfung ohne Randüberschreitungen. Reine technische Zusatzbelege standardmäßig aus. |
| Archivkompatibilität | Echte vor P2/v1-v2 und vor P4/Schema-2-v3-Fixtures bleiben erhalten; normaler Export verwendet gespeicherte Originalbytes. |
| Funktionaler Freeze | Extern `tmp/P4_rework2_freeze.json`: alle 249 eingefrorenen Python-Hashes nach der Root-Abnahme unverändert bestätigt. Modell, Analyse, Store/API und alte Archivfixtures bleiben durch das Druck-Rework unverändert. |
| GitHub-Veröffentlichung | Ausstehend; separate Root-Aktion nach Abschlussprüfung. |
| Windows-/EXE-/Packaging-Qualifikation | Nicht durchgeführt. |

Abschließende Root-Entscheidung extern: `test_runs/root_final_review.json` (**GO**, Phase P4+A1). CLI-Beleg: `test_runs/root_final_cli_smokes.json`; PDF-Geometrie: `test_runs/root_p4_pdf_geometry_final.json`. Die isolierten CLI-Owner wurden gegen den finalen Quellstand geprüft. Die Beispiele sind keine Behauptung klinischer Regelabdeckung oder echter UNC-/Windows-Integration.

## Grenzen und Abschluss

Die vier ersten früheren Baselinefehler waren eng korrigierte Plattform-Testkontexte; zwei weitere erforderten echte Produktkorrekturen an schmalem Editorlayout und Draftnamensicherheit. Die historischen sechs Fehler bleiben dokumentiert. Es wurden keine künstlichen Skips oder globalen Produktions-Casefolds eingeführt.

P4 ändert die Standarddrucksemantik aufgrund der ausdrücklichen Nutzerkorrektur: wichtige fachliche Befunde bleiben sichtbar, vollständige digitale Evidenz bleibt erhalten, wiederholte technische Papierbelege sind optional. Kein Rohdatenanhang, keine neue Datenautorität oder API-Signatur. Eine technische Auswertung ersetzt weder menschliche Ergebnisvalidierung noch normative Gesamt-Konformitätsprüfung.

Aktueller Status: **GATE_PASSED** für die integrierte Quellfreigabe 2.1.0; Root hat **P4+A1-GO** erteilt. Der GitHub-Upload und sein tatsächlicher Nachweis bleiben die anschließende separate Root-Aktion. Windows-EXE-/Packaging-Qualifikation ist nicht Teil dieses Abschlussnachweises.
