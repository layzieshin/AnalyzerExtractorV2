# P1: Assays und QK-Level – historischer Paketbericht

Historischer P1-Prüfstand vom 13.11.2026: damaliger Paketstatus **REVIEW**, damaliger Gatestatus **GATE_FAILED** wegen sechs bestätigter Baselinefehler. Das unabhängige P1-Fach-/Codereview hatte GO. Die ursprünglichen Prüfergebnisse bleiben unten unverändert belegt. P2/P3/R1 wurden anschließend autorisiert und haben Root-GO; die sechs Ursachen wurden im R1-Paket behandelt. Aktueller integrierter Stand: [A1-Prüfbericht](A1_FINAL_VERIFICATION_2026-11-13.md).

## Auftrag und Vorbedingungen

Zum hier dokumentierten P1-Zeitpunkt war ausschließlich P1 des UX-Vorschlags E01 freigegeben: verständliche Assay-/QK-Konfiguration in den vorhandenen Einstellungen. P2 (Grenzberechnung, Kurven, PDF), P3 (Chargenabschluss) und R1 (Regelfreigabe) waren damals noch nicht umgesetzt. Gegenwartsformulierungen im weiteren historischen Prüfprotokoll beziehen sich auf diesen P1-Stand.

Ausgangsbasis ist `master` bei `489ffe2a06ab166992b8eeb754bb0fb6ba2ecbfa`. Der Orchestrator hat 333 Text-Blobs über die GitHub-Anbindung materialisiert und ihre Git-Blob-SHAs geprüft. Die Arbeitskopie besitzt kein `.git`; der externe Safety-Snapshot und das Manifest liegen außerhalb der Arbeitskopie. Daher wird kein lokal beobachteter HEAD behauptet. Produktive Eingaben, Beispiel-PDFs und Laufzeitdaten wurden nicht für die Umsetzung gelesen oder migriert; alle Prüfdaten sind synthetisch.

Aktuelle ausdrückliche Nutzerentscheidung: Astra Ultra plant lesend, ein einziger Sol Ultra implementiert, Root prüft unabhängig. Diese Rollenentscheidung hat Vorrang vor den älteren Modellzuweisungen im Repository. Governance-Dateien wurden dafür nicht geändert. Beobachtete Modell-/Effort-Telemetrie: nicht verfügbar. Ein Product-Writer, keine Git-Schreibaktion, keine neue Datenautorität oder Workflowengine.

## Umgesetztes Verhalten und bestehende Owner

1. `SettingsView` hat innerhalb der bestehenden Hauptansicht die Unteransichten „Allgemein & Geräte“ und „Assays & QK“. Alle aktiven Assays erscheinen, einschließlich unkonfigurierter Assays. Jede bestehende Geräte-/Assay-/Profilbindung erhält eine eigene Zeile mit technischen Kennungen. Entfallene Regeln oder Felder werden sichtbar beanstandet.
2. `SettingsController` lädt den aktuellen Assaykatalog über den bereits vorhandenen `RuleSuiteController`. Der bisherige asynchrone Shellweg öffnet den vorhandenen Profileditor direkt mit der ausgewählten Profilidentität beziehungsweise dem ausgewählten Assay für eine neue Konfiguration. Store- und Generationsschutz bleiben erhalten; erfolgreiche Speicherung erneuert die Übersicht.
3. Der Profileditor ordnet die QK-Level zuerst und technische Einstellungen unter „Erweitert“ an. Frei benannte Level können ergänzt und entfernt werden; das letzte Level bleibt erforderlich. Vorhandene `control_id` bleiben bei Umbenennung erhalten, neue IDs entstehen einmalig pro neuem Level. Entfernen erzeugt erst beim Speichern eine neue vollständige Profilfassung.
4. MIN, MAX, SOLL und IST werden aus vier `readonly`-Dropdowns des eigenen Assays gewählt. Ein veralteter bisheriger Schlüssel bleibt sichtbar, gehört aber nicht zu den gültigen Auswahlwerten. Bestehende Profilbindungen sind gesperrt. Beim Assaywechsel eines neuen Profils werden abhängige Zuordnungen und SD sichtbar zur erneuten Auswahl zurückgesetzt.
5. Die neue Checkbox „RiliBÄK-Grenzen vorhanden“ aktiviert ein gemeinsames Pflicht-Prozentfeld pro Profil. Die Konfiguration heißt `single_value_limits_enabled` und `single_value_limit_percent`. Aktiviertes p muss endlich und nicht negativ sein; Punkt und Komma werden unabhängig von der Messwertschreibweise akzeptiert. Gemischte Trennzeichen, NaN und Infinity werden abgewiesen. Deaktiviert wird p als `None` gespeichert. Die neue Konfiguration wird in P1 noch nicht ausgewertet; der Dialog nennt die aktuell fehlende Darstellung in Kurve/PDF ausdrücklich.
6. `rili_applicable`, `relative_enabled`, `relative_limit_percent` und `guideline_reference` behalten ihre bisherige QMMA-Bedeutung und bleiben in „QMMA-Bestandskonfiguration“ bedienbar. Leere Bestandsgrenzen werden nicht nachträglich verboten. Es gibt keine Migration und keine Übertragung der bisherigen Schwelle in p.
7. Der Editor bearbeitet eine tiefe Kopie des vorhandenen Profil-/Level-Snapshots. Individuelle Einheit, Einheitenfeld, SD-Referenz samt Referenztext, Zeit-/Zahlenformat, Gruppierung und Westgard-Auswahl bleiben bei unabhängigen Änderungen erhalten. Historische Profilfassungen und eingefrorene Nachweise werden nicht umgeschrieben.
8. `src.qualitycontrol` bleibt einzige fachliche und persistente QC-Instanz im ausdrücklich gewählten SQLite-Store. `save_profile` hat den kompatiblen optionalen Parameter `available_field_keys=None`. Produktive `SettingsController`-Writes laden die aktuellen Felder bei jedem Save frisch und übergeben sie zwingend; Ladefehler blockieren ohne kataloglosen Fallback. Historische Leser prüfen ihre alten Mappings nicht gegen den heutigen Katalog. Vier Controller, sieben Hauptansichten und die bestehenden API-Grenzen bleiben erhalten.

## Dateiliste

| Datei | Änderung |
|---|---|
| `src/qualitycontrol/profiles.py` | Additive p-Konfiguration und Feldkatalogprüfung beim aktuellen Speichern |
| `src/application/settings_controller.py` | Assayübersicht und zwingend frischer Feldkatalog für Settings-Writes |
| `src/application/models.py` | Präsentationsmodell für eindeutig gebundene Assay-/Profilzeilen und Katalogkontext |
| `src/application/api.py` | Export des Präsentationsmodells |
| `interfaces/tk/views/settings_view.py` | Unteransicht „Assays & QK“, Status und Identitätsauswahl |
| `interfaces/tk/widgets/dialogs.py` | Vorhandenen Profileditor vereinfachen, vollständigen Snapshot erhalten |
| `interfaces/tk/test_app.py` | Bestehende asynchrone Lade-/Speichervorgänge und Auswahl verdrahten |
| `tests/test_qualitycontrol_profiles_lots.py` | Fachvalidierung, additive Semantik und unveränderte historische Snapshots |
| `tests/test_application_qualitycontrol.py` | Frischer Katalog, Übersicht, Identitätsrouting, Level- und vollständige UI-Roundtrips |
| `tests/test_desktop_ui_v21.py` | Vorhandene Service-/View-Testdoubles um den Settings-Unterbereich ergänzen |
| `docs/P1_ASSAYS_QK_RESULT_2026-11-13.md` | Phasengleicher Prüf- und Ergebnisstand |

Keine Änderung an Governance, Regeln, Root-Entrypoints, Packaging oder Produkt-/Laufzeitdaten.

## Prüfbelege vor Root-Review

Systeminterpreter: Python 3.12.14 unter Linux. Pytest liegt ausschließlich im externen Testabhängigkeitsverzeichnis. Die Befehle wurden vom Repositoryroot mit `PYTHONPATH=/workspace/scratch/a7aba0e0a90e/test_dependencies:$PYTHONPATH`, `PYTHONDONTWRITEBYTECODE=1` und, ab dem zweiten Lauf, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` ausgeführt. Alle Tempverzeichnisse liegen außerhalb des Produktbestands.

| Befehl, jeweils mit `python3 -m pytest`, `-q -p no:cacheprovider` und externem `--basetemp` | Ergebnis |
|---|---|
| `tests/test_qualitycontrol_profiles_lots.py` | 93 passed; 1 externe anyio-/Pytest-Deprecation im ersten Lauf |
| `tests/test_application_qualitycontrol.py tests/test_architecture_gates.py` nach Controller-Schritt | 57 passed, 12 Tk-Skips |
| `tests/test_application_qualitycontrol.py tests/test_desktop_ui_v21.py tests/test_test_app_smoke.py tests/test_architecture_gates.py` vor neuen UI-Abnahmen | 148 passed, 69 Tk-Skips |
| Derselbe Viererblock nach neuen UI-Abnahmen | 148 passed, 73 Tk-Skips |

Der letzte CLI-Lauf ohne Display beweist keine native Bedienbarkeit. Root hat für den unveränderten Safety-Snapshot `test_application_qualitycontrol.py` im Desktop mit 27 passed und ohne Skips geprüft. Der erste native P1-Viererblock ergab **220 passed, 1 failed, 0 skipped** in 9,64 s. Der einzelne Fehler betraf eine veraltete Testannahme zu Assayanzeigen und zum Wechsel der Bindung eines bestehenden Profils; siehe Nacharbeit. Die Vollsuite wurde vom Writer nicht gestartet; sie darf höchstens einmal nach Root-Review-GO folgen.

Neu vorgesehene gemappte Tk-Abnahmen prüfen den vollständigen Advanced-Roundtrip einschließlich unterschiedlicher Level-Einheiten und SD-Herkunft, bedingtes p, Hinzufügen/Entfernen mit stabilen IDs, Assaywechsel ohne fremde Mappings, sichtbare entfallene Schlüssel und korrektes Öffnen gleichnamiger Profile aus der neuen Unteransicht. Bestehende kleine Dialog-/Footer- und Zeitformatprüfungen bleiben Bestandteil des Zielblocks.

Root hat im unveränderten CLI-Baselineblock einen bestehenden Linux-/Windows-Unterschied gemeldet: `test_validate_watch_paths_rejects_settings_case_variant_child` erwartet Windows-Pfad-Groß-/Kleinschreibung. Dieser Befund wird nicht im P1-Scope repariert.

## Root-Review und fokussierte Nacharbeit 1

Root hat die Oberfläche tatsächlich im Linux-Desktop bei 1280 × 900 geprüft: konfigurierte und unkonfigurierte Assays, richtige Profilöffnung mit Fassung, zwei Level und vier ausschließlich assaybezogene readonly-Dropdowns, Aktivierung des p-Felds mit `12,5`, Levelwechsel sowie die getrennte alte QMMA-Schwelle unter „Erweitert“. Abbrechen erhielt die synthetische Revisionszahl von zwei Fassungen. Dies ersetzt keine Windows-Abnahme.

Der Reviewauftrag bündelte drei Befunde; derselbe Writer hat ausschließlich diese nachgearbeitet:

1. Der alte Test `test_profile_same_assay_names_bind_stable_keys_by_option_index` prüft jetzt die aktuellen Verträge mit vollständigen A-/B-Katalogen: eindeutige Anzeigen mit Assaykey, gesperrte und unveränderte Bestandsbindung, explizites Neuprofil für einen Wechsel und Zurücksetzen seiner Feld-/SD-Zuordnungen. Die Produktionssperre wurde nicht gelockert.
2. Bei fehlender oder beschädigter `rules/index.json` ließ der neue QC-Katalogread zunächst den gesamten allgemeinen Settings-/Geräterefresh scheitern. Der bestehende Controller liefert jetzt einen expliziten `catalog_error` ohne QC-Zeilen oder Dropdownkatalog. Die View löscht veraltete Zeilen, zeigt den Fehler und sperrt Einrichten/Weiteres Profil; allgemeine Settings, Geräte und Neu laden bleiben bedienbar. Direktes Öffnen eines Profileditors blockiert ebenfalls. Der Save liest weiterhin den aktuellen Katalog und lehnt Ladefehler ab.
3. Der technische Hinweis auf ein „nächstes Paket“ wurde durch den nutzerbezogenen Hinweis auf die aktuell fehlende Kurven-/PDF-Darstellung ersetzt. P2 bleibt unberührt.

Parametrische synthetische Abnahmen decken fehlenden und beschädigten Index ab: allgemeine Werte unverändert lesbar, alte QC-Anzeige entfernt, klare Sperre, Geräte-Reload möglich und abgewiesener Save ohne neue Datenbankfassung. CLI-Zielprüfung nach Nacharbeit: `tests/test_architecture_gates.py` plus die drei Selektoren `test_catalog_failure_keeps_general_settings_readable_and_profile_save_blocked`, `test_catalog_error_clears_stale_qc_rows_and_keeps_general_settings_and_devices_visible` und `test_profile_same_assay_names_bind_stable_keys_by_option_index`; Ergebnis **42 passed, 3 Tk-Skips**. Root führte denselben fokussierten Block anschließend im tatsächlichen Desktop aus: **45 passed, 0 skipped** in 2,40 s (`test_runs/native_p1rework.log`, `p1_native_rework.xml`). Danach erteilte Root das P1-Review-GO für den einmaligen erforderlichen Vollsuitelauf.

## Einmalige Vollsuite und Baselinezuordnung

Root führte nach dem Review-GO genau einmal die vollständige Suite im Linux-Desktop mit `DISPLAY=:0` aus. Der externe, spawn-geschützte Runner nutzte denselben Python-Interpreter und die oben genannten externen Testabhängigkeiten. Pytestargumente:

```text
-q -p no:cacheprovider --basetemp=/workspace/scratch/a7aba0e0a90e/test_runs/p1_native_full --junitxml=/workspace/scratch/a7aba0e0a90e/test_runs/p1_native_full.xml -o faulthandler_timeout=30 --tb=short -rs
```

Ergebnis: **1267 passed, 6 failed, 0 skipped** in 49,53 s. Belege: `test_runs/native_p1full.log` und `p1_native_full.xml`. Anschließend wurden ausschließlich die sechs fehlgeschlagenen Selektoren im unveränderten externen Baseline-Snapshot und demselben nativen Desktop geprüft: **dieselben sechs Fehler**, 1,03 s (`test_runs/native_baseline_failures.log`, `baseline_native_failures.xml`). Es fand keine zweite Vollsuite statt.

| Exakter fehlgeschlagener Selektor | Unveränderte Baseline |
|---|---|
| `tests/test_application_settings_controller.py::test_validate_watch_paths_rejects_settings_case_variant_child` | Derselbe fehlende SettingsValidationError bei Groß-/Kleinschreibungsvariante |
| `tests/test_ingestion.py::test_validate_watch_paths_rejects_case_and_parent_child` | Derselbe fehlende IngestionError bei Groß-/Kleinschreibungsvariante |
| `tests/test_resultstore.py::test_unc_path_uses_direct_connect_not_uri` | Derselbe UNC-Verfügbarkeitsfehler |
| `tests/test_resultstore.py::test_direct_connect_sets_query_only` | Dieselbe fehlende query_only-Beobachtung |
| `tests/test_rule_editor_phase6_layout.py::test_phase6_shell_is_inventory_and_three_column_workspace` | Derselbe abgeschnittene „PDF auswählen …“-Button |
| `tests/test_rulesuite.py::test_open_history_as_draft_contains_manipulated_assay_key` | Derselbe fehlende RuleSuiteError für manipulierten Assaykey |

Damit wurde keine zusätzliche P1-Regression gefunden. Dies macht die Vollsuite nicht grün und behauptet nicht, dass alle sechs Befunde ausschließlich durch das Betriebssystem verursacht werden. Die bestätigten Baselinebefunde liegen außerhalb des freigegebenen P1-Umfangs; es wurde dafür keine zweite Produktnacharbeit begonnen. `rules_validate_main.py` war grün, alle fünf Fehlerlisten leer.

Root führte beide geforderten Headless-Adapter-Smokes mit isoliertem `ARE_HOME=/workspace/scratch/a7aba0e0a90e/test_runs/adapter_smoke` erfolgreich aus:

| Befehl bei gesetztem isoliertem ARE_HOME | Ergebnis |
|---|---|
| `ARE_WATCHDOG_ONCE=1 python3 watchdog_main.py` | Exit 0; `[watchdog] watch_disabled reason=watch_disabled` |
| `ARE_WORKER_ONCE=1 python3 worker_main.py` | Exit 0; `[worker] no_pending_jobs` |

Diese Smokes belegen den Start der Adapter bei deaktiviertem Watch beziehungsweise ohne wartende Jobs; sie sind kein Import-/Verarbeitungs-E2E-Nachweis.

Der abschließende Root-Freezeaudit ist abgeschlossen: Alle 333 Baseline-Blobs im Safety-Snapshot sind unverändert. Es gibt keine Änderungen an geschützten oder ungeplanten getrackten Dateien; exakt zehn bestehende Quell-/Testdateien wurden geändert und dieser P1-Bericht neu hinzugefügt, insgesamt elf Dateien. Governance und Regeln sind unverändert. Produkt-/Teststand bleibt eingefroren; der letzte Nachtrag betraf ausschließlich diesen Bericht.

## Historisch offene Abnahme und Grenzen

- Unabhängiges Root-P1-Review und die gezielte native Nachprüfung sind bestanden. Der einmalige erforderliche Regressionslauf hat sechs bestätigte Baselinefehler; offizieller Gatestatus bleibt GATE_FAILED und Paketstatus REVIEW, nicht DONE.
- Ein Linux-Desktoplauf ist kein Windows-Nachweis. Windows-/EXE-/Packaging-Abnahme wurde nicht durchgeführt.
- Direkte unabhängige QC-API-Aufrufer dürfen den optionalen Katalogkontext weiterhin weglassen; der produktive Settings-Speicherweg darf das nicht.
- Die neue Einzelwert-Prozentkonfiguration wird erst in P2 in Analyse, Kurve und PDF verwendet. Alte QMMA-Schwellen, Analysen und historische PDFs bleiben fachlich unverändert.
- RiliBÄK-Anwendbarkeit wird durch diese technische Konfigurationsarbeit nicht normativ neu beurteilt.

Historischer nächster Schritt nach P1: Windows-Zielqualifikation beziehungsweise Entscheidung zu den Baselinebefunden. Die spätere Gesamtfreigabe autorisierte P2/P3/R1/P4 und den GitHub-Abschluss; die nachfolgenden Ergebnisse stehen im A1-Prüfbericht. Im P1-Paket erfolgten kein Git-Schreibzugriff und kein Build.
