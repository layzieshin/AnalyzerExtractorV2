# P2: Gefrorene Einzelwertgrenzen, Statistik und PDF

Stand: 13.11.2026. Paketstatus: **ROOT-GO**. Das unabhängige Root-Review einschließlich nativer Tk-Prüfung und tatsächlicher Voll-App-/PDF-Sichtprüfung ist bestanden. Eine integrierte Vollsuite erfolgt erst im Abschluss-Paket.

## Auftrag und Vorbedingungen

Die aktuelle ausdrückliche Nutzerfreigabe umfasst die Umsetzung aller vereinbarten Pakete und den abschließenden GitHub-Upload. Dieses Paket setzt ausschließlich P2 um. Astra plant lesend, Sol ist der einzige Product-Writer, Root prüft unabhängig. Die aktuellen Rollen und die Gesamtfreigabe ersetzen die älteren Rollen- und Einzelfreigaben im Repository; Governance-Dateien bleiben unverändert. Beobachtete Modell-/Effort-Telemetrie ist nicht verfügbar.

Remote-Ausgangs-HEAD: `489ffe2a06ab166992b8eeb754bb0fb6ba2ecbfa`, vom Root erneut geprüft. Die materialisierte Arbeitskopie hat kein `.git`; ein lokal beobachteter HEAD wird nicht behauptet. Der vollständige externe Safety-Checkpoint des geprüften P1-Stands umfasst 334 Quelldateien. Nur der benannte Writer hat Produktdateien geändert. Keine Git-Schreibaktion, Regel-JSON-Änderung, SQLite-Migration, Runtime-/Patientendatenänderung, neue Datenautorität, Shell oder Controller.

## Verhalten und Owner

- `sources.py` erzeugt `qc-sources-v2`. Die bestehende SOLL-/Einheiten-Konstanzpolicy gilt nun ebenso für Hersteller-MIN/MAX: unterschiedliche Decimal-Werte einer ansonsten geeigneten Kontrollserie schließen deren geeignete Punkte mit sichtbaren Konfliktgründen aus. `30` und `30.0` sind äquivalent. MIN größer MAX wird am betroffenen Punkt beanstandet. Rohwerte, Quellen, Hashes und bereits vorhandene Ausschlussgründe bleiben erhalten; andere konfliktfreie Level bleiben auswertbar.
- `analysis.py` prüft dieselben Voraussetzungen defensiv und friert Hersteller- und Prozentgrenzen getrennt in `series.limits.manufacturer` und `series.limits.single_value` ein. Der Profilwert `single_value_limit_percent` gilt gemeinsam für alle Level; jedes Level verwendet seinen eigenen konsistenten SOLL: `SOLL × (1 ± p / 100)`. Das Rechenbudget berücksichtigt p sowie die vorhandene QMMA-Prozentschwelle. Gleichheit liegt innerhalb, Entscheidungen verwenden ungerundete Decimal-Werte. p größer 100 ist zulässig. SOLL null liefert Prozentgrenzen null/null; eine fehlende relative QMMA verhindert dies nicht. Negative SOLL mit p null liefern gleiche gültige negative Grenzen. Tatsächlich vertauschte berechnete Grenzen erhalten einen erklärten Nichtverfügbarkeitsstatus und werden weder sortiert noch mit Absolutwerten ersetzt.
- Jeder Punkt erhält unabhängige `limit_findings` für Hersteller und Prozentgrenzen. Reine Grenzüberschreitungen ändern weder seine statistische Eignung noch QMMA, SD oder den Westgard-`run_status`. Die bisherige QMMA-Formel, Bestandskonfiguration und SD-Herkunftsprüfung bleiben erhalten. Die neue Prozentgrenze wird nicht aus einer bisherigen QMMA-Schwelle übernommen.
- `chart.reference_lines` enthält die bereits berechneten Werte und Bezeichnungen für SD, SOLL, Hersteller und Prozentgrenzen. Die eingefrorene Achsenskalierung schließt diese Linien ein. `StatisticsView` und `pdf_report.py` zeichnen diese Modellwerte; sie berechnen keine Grenzen. Orange Ringe markieren Grenzüberschreitungen getrennt von der Westgard-Punktfarbe. UI und Standard-PDF zeigen Legende, Grenzwerte und unabhängige Punktbefunde; die Statistik zeigt außerdem die bestehende QMMA-Schwelle mit ihrer eigenen Bewertung. Roh-MIN/MAX und Konfliktgründe bleiben sichtbar. Der bestehende Profileditor erklärt die nun verfügbare Kurven-/PDF-Darstellung.

Die vorhandenen API- und ResultsController-Pfade bleiben unverändert. Chronologie, Chargenabschluss und Regelfreigabe gehören nicht zu P2. Es werden keine neuen normativen Grenzwerte und kein Nachweis vollständiger Richtlinienkonformität eingeführt.

## Versionen und echte Altnachweise

| Modell | Analyse | PDF-Modellkennung | Lesestatus |
|---|---|---|---|
| 1 | v1 oder v2 | v1 oder v2 | Alle vier bisher unterstützten Kombinationen bleiben lesbar |
| 2 | v3 | v3 | Neu erzeugte Auswertung |
| Alle übrigen Kombinationen | | | Kontrolliert abgewiesen |

Die Kennungen lauten vollständig `arev2-qc-analysis-vN` und `arev2-qc-pdf-vN`. Neue Quellen verwenden `qc-sources-v2`; archivierte v1-Manifeste und Modelle werden beim Lesen nicht verändert. Alte Modelle behalten ihre vorhandenen SOLL-/SD-Linien. Auch eine neu erzeugte erläuterte Druckfassung verwendet ausschließlich das alte FrozenModel und ergänzt keine heutigen Grenzen. Der normale Export schreibt weiterhin exakt die gespeicherten PDF-Bytes.

Vor der ersten P2-Modell-/Analyse-/Rendereränderung entstand `tests/fixtures/qc_pre_p2_schema1_v2.json` mit dem damals unveränderten Code: synthetische Messungen 100/100/100/112, echte PDF aus frischem Spawn, eine Seite, 46.918 PDF-Bytes, Schema 1 / Analyse v2 / PDF v2. Ein zweiter echter Archivfall stammt aus dem unveränderten externen P1-Codecheckpoint und enthält den Textdump eines vollständig synthetischen, mit realem PDF abgeschlossenen Stores. Er ersetzt im Anwendungstest das frühere bloße Umschreiben von Versionskennungen. Aus der echten Altfixture abgeleitete v1-Kompatibilitätsvarianten sind ausdrücklich synthetisch bezeichnet.

| Echte Fixture | Modell-SHA-256 | PDF-SHA-256 |
|---|---|---|
| `qc_pre_p2_schema1_v2.json` | `f2f24aff7b6eeca0393691ba503ec279d0c1b9de827bbe7cc42ef853a2997d2e` | `6b8b34cd4d0d4ef8e2fb36af601e67ebfa8b3f1edecff843abb54af903170459` |
| `qc_pre_p2_sd_archive_schema1_v2.json` | `db5d48ee44b0865ab1d764035cb65d3766201ccb7a31bf8522e55c72559d1646` | `3ee456436b8c9dda984f598c2e883dfaad9f2a69204ec373cdc268c41de797e1` |

Der zweite Test stellt ausschließlich eine temporäre Testdatenbank aus dem synthetischen Dump wieder her. Produktive Daten wurden nicht gelesen oder migriert. Das alte Archiv bleibt nach Profil-/Einheitenänderung und Wiederöffnung über den bestehenden ResultsController byte- und modellgenau abrufbar.

## Funktionsnachweise und offene Abnahme

Testumgebung: Python 3.12.14, `PYTHONPATH` mit den extern bereitgestellten Testabhängigkeiten, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTHONDONTWRITEBYTECODE=1`, pytest-Cache deaktiviert und temporäre Dateien außerhalb des Produkts.

- Kernprüfung `test_qualitycontrol_analysis.py` und `test_qualitycontrol_profiles_lots.py`: 160 bestanden.
- Danach gezielte Analyse-/Quellen-/PDF-/Architekturtests einschließlich echtem Altarchiv-Controllerpfad: 247 bestanden.
- Letzter breiter fokussierter CLI-Lauf über Analyse, Grenzen, Profile, echte PDFs, Anwendung und Architektur: 267 bestanden, 8 bestehende Tk-Umgebungsskips, 12 gezielt ausgeblendete UI-Fälle. Es wurden keine Skips hinzugefügt. Die nativen UI-Fälle führt Root im Desktop-Namespace aus.
- Abschließende Grenzfallprüfung `test_qualitycontrol_limits.py`: 22 bestanden. Darin 100/100/100/112 mit SOLL 100/p 10/Hersteller 80–120 ohne SD → 90–110, 112 auffällig und QMMA 6/6 %, mehrere Level, Gleichheiten, präzises p über 120 Nachkommastellen, unabhängige Herstellerbefunde, p größer 100, SOLL null/negativ und p null, Konflikte/äquivalente Schreibweisen, bestehende Ausschlüsse, SD-/Westgard-Unabhängigkeit und erlaubte Versionstupel.
- Echte PDF-Geometrie wird gegen jede eingefrorene Referenzlinie geprüft. Konflikt-PDFs enthalten die Rohbereiche und sämtliche Ausschlussgründe. Normaler Altarchiv-Export und erläuterte Altmodell-Druckfassung sind getrennt geprüft. PDF-Seiten wurden zusätzlich mit Poppler gerendert und visuell kontrolliert. Dabei wurde vor Review eine fehlerhafte Dash-Syntax korrigiert; der erneute Poppler-Render enthält alle Linien, Punkte, Ringe und Tabellen ohne Syntaxmeldung.
- Alle elf geänderten Python-Dateien wurden auf Syntax und nachgestellte Leerzeichen geprüft.

Root-Nachweis: native unabhängige P2-Auswahl **72 bestanden, 0 Skips in 5,67 s**, einschließlich Grenzfällen, drei Tk-Abnahmen, echtem Altarchivpfad, echten PDF-Linien/Konflikten, Quellkonstanz und Architektur. Root hat außerdem die tatsächliche AnalyzerDesktopApp mit einem eigenen synthetischen Vier-Messungen-Store und die aus dessen FrozenModel erzeugte PDF visuell geprüft; normale Grenzkurve, Punkt 112 mit Ring und Legende sind lesbar. Externe Nachweise: `test_runs/native_p2review.log`, `p2_native_review.xml` und `test_runs/root_p2_review.json`. Kein P2-Rework erforderlich. Noch offen: integrierte Abschlussprüfung. Größere endliche Werte bleiben exakt auswertbar; überschreiten ihre Float-Diagrammskalen die Darstellbarkeit, bleiben die bestehenden sichtbaren UI-/PDF-Fehlerpfade erhalten. Windows-Zielqualifikation bleibt wie beim Ausgangsstand erforderlich. Keine Vollsuite und kein Build in P2 gestartet.

Status: **ROOT-GO**. Der damalige Paketübergang und die folgenden Arbeitspakete sind historisch; den aktuellen integrierten Abschluss dokumentiert der [A1-Prüfbericht](A1_FINAL_VERIFICATION_2026-11-13.md).
