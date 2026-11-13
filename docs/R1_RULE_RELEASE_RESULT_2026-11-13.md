# R1: PDF-Nachweis und bestätigte Regelfreigabe

Stand: 13.11.2026. Paketstatus: **ROOT-GO nach fokussiertem Rework 1**. Unabhängige native Prüfung und tatsächliche Create-/Update-/Abbruchbedienung sind bestanden. Den aktuellen integrierten Abschlussstand dokumentiert der [A1-Prüfbericht](A1_FINAL_VERIFICATION_2026-11-13.md); dieser Paketbericht behauptet keinen Windows-Build.

## Freigabe und Ausgangsstand

Der aktuelle Nutzerauftrag autorisiert das vereinbarte Gesamtpaket und den abschließenden GitHub-Upload. R1 folgt auf P3-ROOT-GO nach dessen engem UX-Rework. Die native P3-Nachprüfung bestand fünf Tests ohne Skips in 2,66 s; Manifestvergleich, tatsächlicher Abschluss-/Archiv-/Exportablauf und der externe Safety-Checkpoint `P3_before_R1` sind belegt. Der Writer hat das P3-Ergebnis um diese Root-Abnahme ergänzt.

Ein einziger Sol-Product-Writer, lesende Astra-Planung und unabhängige Root-Prüfung bleiben erhalten. Keine weiteren Agenten, keine Governanceänderung. Beobachtete Modell-/Effort-Telemetrie ist nicht verfügbar. Die materialisierte Arbeitskopie besitzt kein `.git`; der vom Root bestätigte Remote-Ausgangs-HEAD bleibt `489ffe2a06ab166992b8eeb754bb0fb6ba2ecbfa`. Keine Regel-JSON-/Runtime-/Patientendatenänderung, kein Build, kein Git-Schreibzugriff und kein vorzeitiger Versionsbump. Sämtliche Prüfdaten sind synthetisch.

## Ein Freigabeweg für denselben geladenen Entwurf

Der vorhandene Rule-Editor-Workspace enthält jetzt den gemeinsamen Freigabebereich mit Beispiel-/Problem-PDF, Update-Referenz, Struktur-/Beispiel-/Referenzstatus und Gesamtergebnis. **Mit PDFs prüfen** nutzt den tatsächlich geladenen Entwurf direkt über den vorhandenen RuleSuiteController; ein Feldwizard muss nicht erneut durchlaufen werden. Ergebnis zeigt Prüfzeit, PDF-Namen und geprüfte beziehungsweise verglichene Feldnamen. Neue Patientendatenlogs oder eine zweite Nachweisablage entstehen nicht.

Erfolg heißt **Prüfung erfolgreich – noch nicht aktiviert**. Reine Strukturprüfung und einzelne Extraktionsvorschau bleiben ausdrücklich technische Hilfen. Meta-/Feldänderungen, PDF-Auswahl, Draft-/Rootwechsel und externe Inputänderungen entwerten den Nachweis. Die UI prüft ihre aktuelle PDF-Auswahl zusätzlich gegen den gespeicherten Proof; ein Backend-Verify für PDF A kann nach Auswahl B nicht freigeben. Zurückwählen allein ersetzt keinen neuen Prüflauf. Effektive Assaynamen werden wie Backend und Splitter getrimmt verglichen; unveränderte Legacybytes werden nicht dafür umgeschrieben.

Generation, vollständiger UI-Kontext und eine getrennte aktive Prüfversuchskennung schützen die Workerpräsentation. Eine alte Completion kann weder einen neueren Lauf als fertig markieren noch dessen Busy-Zustand aufheben. `_proof_running` bleibt unabhängig von älteren allgemeinen Busy-Helfern geschützt. Bei Referenzfehlern wird nicht pauschal der gültige Beispielbericht als fehlgeschlagen bezeichnet. Häufige Sperrgründe erhalten eine kurze deutsche Erklärung und technische Details. Geschlossene Fenster verwerfen Completion. Die neue PDF-Prüfung verwendet nach Rework 1 den bereits vorhandenen TkTaskRunner: Worker schreiben ausschließlich in dessen threadsichere Queue; nur der auf dem Hauptthread geplante Poller spricht mit Tk.

Der bestehende Wizard bleibt Erstellung-/Feldhilfe. Sein PDF-Erfolg gibt höchstens einen geprüften Draft in denselben Editor zurück und aktiviert nichts. Alte automatische Aktivierungserwartungen wurden ausdrücklich durch Tests der getrennten Rückgabe ersetzt. Gespeicherte Feldschritte bleiben beim Abbruch als Draft erhalten.

`ReleaseMixin.on_activate` bleibt der einzige abschließende UI-Owner. Dirty-Zustand, Strukturfehler und fehlender/veralteter Nachweis blockieren vor jeder Aktivierungsbestätigung. Es gibt keinen generischen Struktur-Override für die Freigabe. Der aktuelle Backend-Diff bestimmt create/update, unabhängig von alten Inventarlisten. Genau ein finaler Ja/Nein-Dialog gehört zu jedem ausdrücklich gestarteten Versuch. Nein schreibt nichts; Ja ruft den bestehenden Controller und dessen erneuten Backendcheck auf. Saubere Drafts werden für Diff, Strukturansicht oder Aktivierung nicht neu serialisiert.

## Fokussiertes Rework 1: echte asynchrone Zustellung und sichtbarer Diff

Die erste tatsächliche Root-Bedienung fand einen Blocker, den der bisherige native
Test mit `ImmediateThread` verdeckte: Der Backend-Proof war bereits ready, während
die Oberfläche dauerhaft „Prüfung läuft“ zeigte. Root reproduzierte das am externen
Vor-Rework-Snapshot mit echtem Worker und laufender Hauptschleife deterministisch.
Der Worker-Aufruf `after(0, ...)` kehrte ohne Ausnahme zurück, sein Callback trat
aber nicht ein; andere Hauptthread-Timer liefen. Nach 2,4 s blieben Busy und
Prüfstatus gesetzt (`root_r1_dispatch_diagnostic.json`). Es wird keine beobachtete
RuntimeError-Ausnahme als Ursache behauptet.

Die Zustellung läuft jetzt über den bestehenden TkTaskRunner mit Hauptthread-
Polling. Die Proof-/Sicherheitsowner wurden dafür nicht geändert. Root bestätigte
unabhängig am gleichen echten Ablauf: Completion auf MainThread, Busy/running
false, aktive Versuchskennung leer, Status „Prüfung erfolgreich – noch nicht
aktiviert“ und null Worker-Tk-Aufrufe (`root_r1_dispatch_current.json`). Der
ursprüngliche native Freigabetest verwendet nun einen echten Worker und laufende
Tk-Hauptschleife. Zwei zusätzliche native Fälle prüfen Erfolg und fehlende
Update-Referenz einschließlich Threadidentitäten, Statuszustellung und fehlender
Aktivierung. Ein reiner Worker-Test verbietet jeden direkten Tk-Aufruf.

„Änderungen anzeigen“ hatte bisher nur in das versteckte Protokoll geschrieben.
Die bestehende Aktion öffnet jetzt sichtbar den vorhandenen Regeldetailsbereich
und scrollt zum Diff-Protokoll. Kein weiterer Editor oder Aktivierungsweg wurde
eingeführt. Der native Regressionstest prüft Sichtbarkeit im Viewport sowie
unveränderten sauberen Drafthash und weiterhin gültigen Proof. Fokusprüfung:
92 bestanden, neun bestehende Tk-Umgebungsskips in 2,16 s. Der funktionale
Rework-Freeze umfasst genau vier Python-Dateien; Backend und übrige R1-Dateien
sind gegen den ersten Freeze identisch. Die anschließende native Root-Nachprüfung
bestand 148 Fälle ohne Skips; die tatsächliche Dialogbedienung mit echtem Worker
bei 1024×768 und 1280×900 bestand ebenfalls. Details stehen im abschließenden
Root-Nachweis dieses Berichts.

## Exakte Nachweise und Veröffentlichung

Der vorhandene `authoring_readiness.py`-Owner erzeugt Proof-Version 2. Kurze Lifecycle→Draft-Sperren schützen Capture/Pending und Ready-Publikation. PDF-Arbeit hält keine 30-Sekunden-Draftsperre über den gesamten Lauf. Vor der Extraktion werden Draft, Originalindex, aktive Bindung und PDFs als exakte Bytes erfasst; die echte Parser-/Splitter-/Extractorstrecke verarbeitet private Kopien. Originalpfade, Hashes, Modus und geprüfte Feldnamen bleiben im Nachweis. Keine aktive Regel, kein Index und keine Historydatei wird durch einen erfolgreichen Proof geändert.

Die private Indexzeile des geprüften Assays wird ausdrücklich auf die private Active-Kopie umgebunden. Das ist nötig, weil der vorhandene Resolver absolute In-root-Bindungen und Symlink-Aliase akzeptiert. Originale Indexbytes und Originalbindungen bleiben unverändert eingefroren. Root hat einen Fehler des ersten Zwischenstands unter transienter Live-Mutation real reproduziert; nach dem privaten Binding-Fix lesen alle geprüften absoluten/Aliasfälle ausschließlich die eingefrorenen alten Werte. Ein bloßer Vorher-/Nachherhash ohne echte Bytekopie hätte diesen Fall nicht verhindert.

Updates verlangen eine andere Datei mit anderem PDF-Inhalt. Auf der Referenz müssen sämtliche bisherigen `data`-Felder und `lot_id` gleich bleiben. Jedes konfigurierte Feld braucht weiterhin einen nichtleeren echten Extraktionswert, unabhängig vom `required`-Flag. Eine direkte Prüfung ersetzt nicht die fachliche Vollständigkeit durch einen schwächeren Acht-Headercheck.

Vor Ready werden aktuelle Inputhashes, create/update-Modus, Index und aktive Zielbindung erneut geprüft. Jeder neue Versuch entwertet zunächst den alten Proof. Die Versuchskennung wird bei Ready unter kurzer Sperre erneut kontrolliert; ein älterer langsamer Erfolg kann einen jüngeren pending/failed Versuch nicht überschreiben. Fehlgeschlagene oder unvollständige Nachweise bleiben fail-closed. Proof-Version 1 verlangt eine neue Prüfung; dies berührt keine archivierten QC-Modelle oder PDFs.

Die bestehenden unteren Aktivierungs-APIs bleiben mit optionalem `require_authoring_proof=False` kompatibel. Der Produktcontroller setzt die Pflicht immer auf true. Der fachliche Aktivierungsowner prüft innerhalb der bestehenden Lifecycle→Draft-Sperren erneut, bindet genau den tatsächlich publizierten Draftsnapshot und lädt danach keine ungeprüften Draftbytes nach. Proofpflichtige Neuanlage weist ein abweichendes, ungetestetes Namensargument ab. Aktualisierung erhält den bytegenauen alten Historysnapshot; Neuanlage erzeugt keinen solchen Snapshot.

## Sechs Baselinebefunde nach Ursache behandelt

| Bisheriger Befund | Behandlung und Nachweis |
|---|---|
| Settings-Casevariante von Watch/Backup | Im Test ausdrücklich Windows-Casevergleich mit nativen Separatoren simuliert; Host-Produktnormcase bleibt unverändert. |
| Ingestion-Casevariante vor Parent/Child-/Dateifällen | Casevergleich eng im Test simuliert; weitere native Parent/Child-/Dateifälle bleiben erhalten. |
| UNC-Direktverbindung unter POSIX nicht erreicht | Nur der genaue synthetische UNC-Pfad und seine auf diesem Host aufgelöste Form gelten im Mock als vorhanden; kein globales `is_file=True`. |
| UNC-`query_only`-Beobachtung unter POSIX nicht erreicht | Derselbe portable Mockfix; zusätzlich echte lokale SQLite-Verbindung mit `PRAGMA query_only=1` und abgewiesenem Schreibversuch. |
| Echter Phase-6-Layoutfehler | PDF-Pfad/Dateiauswahl und schmale Werkzeuge gestaffelt, Headergruppen in überschaubare Zeilen, rechte Feldeinstellungen scrollbar. Sashes werden beim ersten tatsächlich sichtbaren Workspace initialisiert und überschreiben späteres Benutzerziehen nicht. Mindestgröße unverändert. |
| Echter Draftnamen-/Assaykey-Härtungsbedarf | Zentraler Owner verwirft beide Separatoren, Traversal, Laufwerk-/UNC-/Rootsyntax und NUL hostunabhängig statt stiller Umbenennung. Zusätzlich resolved-Enthaltenheit gegen Symlinks erhalten; legitime technische Keyabbildung bleibt bestehen. |

Die ersten vier sind Testkontextkorrekturen, die letzten zwei Produktkorrekturen. Keine willkürlichen Skips und kein globales Casefold der Produktion. Reine Netzwerkpfadklassifikation ist als synthetischer Branchtest bezeichnet; sie behauptet keine echte UNC-/Netzlaufwerksintegration. Vorhandene Regel-JSONs wurden nicht umgeschrieben.

## Prüfstand

Umgebung: Python 3.12.14, externe Testabhängigkeiten über `PYTHONPATH`, Plugin-Autoload und Bytecode ausgeschaltet; Cache und temporäre Dateien außerhalb des Produkts. Die CLI erreicht den Desktop-X-Namespace nicht; unveränderte bestehende Tk-Umgebungsskips werden durch Root nativ ausgeführt.

| Gezielte Prüfung | Beobachtetes Ergebnis |
|---|---|
| Erste vorhandene Proof-/manipulierte-Key-Fälle | 5 bestanden |
| Portable Baselinekontexte, ResultStore und RulesController | 48 bestanden |
| RuleSuite/Controller einschließlich echter Proofs und zusätzlicher Integritätsrennen | 163 bestanden in 1,36 s |
| Editor-Routing/Wizard/Dirty-Semantik nach Entkopplung | 80 bestanden, 9 bestehende Tk-Skips |
| UI-Kontext, Busy-/Late-/Referenzfehlerfälle, Feld-/Markierungs-/Architekturprüfung | 147 bestanden, 16 bestehende Tk-Skips in 2,21 s |
| Gesamte fokussierte R1-Auswahl einschließlich aller betroffenen Editor-/RuleSuite-/Controller-/Baseline-/Architekturdateien | 403 bestanden, 21 bestehende Tk-Skips in 3,64 s |
| Unabhängige native Root-Auswahl vor Rework 1 | 424 bestanden, 0 Skips in 5,91 s |
| Fokussierte Rework-1-Prüfung | 92 bestanden, 9 bestehende Tk-Skips in 2,16 s |
| Syntax und nachgestellte Leerzeichen aller 26 geänderten Python-Dateien | geprüft |

Integritätsfälle enthalten sechs echte Verify-to-use-Rennen (Draft/Index/Active nach Controller- oder gesperrtem Verify), fünf Inputänderungen während echter PDF-Prüfung, einen deterministisch langsameren alten Versuch gegen einen neueren Fehler, Modus-/Namens-/Bindungsänderungen, absolute/Alias-Referenzauflösung unter transienter Live-Mutation, Hashstabilität sauberer Diffansichten und fail-closed UI-PDF-/Dirtykontext. Frühere Controller-Snapshottests mit bloßem `verify=True` verwenden nun echte PDF-Proofs.

Root hat vorab unabhängig echte synthetische PDF-/Backendfälle geprüft: create/update Proof-only ohne aktive/index/history Änderung, anschließende Aktivierung mit exakten alten Historybytes, gleiche Referenzbytes unter anderem Namen, ungetestetes Namensargument, Moduswechsel, neue aktive Bindung bei unveränderten alten Bytes und leeres optional konfiguriertes Feld. Ergebnisdatei `test_runs/root_r1_real_proof_check.json`. Der zusätzlich reproduzierte absolute Live-Bindingfehler ist im externen Zwischenstand gesichert; der Fix bestand danach alle vier echten Fälle absolute/Alias × gute/abweichende Referenz in 0,53 s. Alle Active-Previews verwendeten private Kopien und den ursprünglichen Wert BASE; Beleg `test_runs/root_r1_private_binding_check.json`.

Die unabhängige native R1-Gesamtauswahl bestand **424 Tests, 0 Skips in 5,91 s**. Nach Rework 1 bestand die unabhängige native Auswahl weitere **148 Tests, 0 Skips**; sämtliche Hashes aus `tmp/R1_rework1_freeze.json` stimmen. Root prüfte echte Create-/Update-Klickwege bei **1024×768 und 1280×900** mit realen PDF-Dateien, echtem Worker und echten abschließenden Dialogen. Proof-only änderte keine aktiven Regeln, Index- oder Historydateien. Abbruch mit „Nein“ publizierte nichts; die eine abschließende Zustimmung aktivierte den exakten geprüften Draft. Das Update erhielt die alten Active-Bytes in genau einem Historyeintrag. Fehlende Referenz, dieselben Referenzbytes unter anderem Namen und inhaltlich abweichende Referenz blockierten; eine passende Referenz ergab „bereit, noch nicht aktiviert“. Die sichtbare Diffansicht bleibt sauber und beweisgebunden. Der unabhängige Real-Worker-Vergleich bestätigte MainThread-Completion, gelöschten Busy-Zustand und null Worker-Tk-Aufrufe.

Root erteilte **R1-GO**. Externe Gesamtevidenz: `test_runs/root_r1_review_final.json`; Safety-Checkpoint `R1_before_P4`. Die echten Backend-/Integritätsnachweise und die ursprünglichen 424 nativen Tests bleiben gültig. Native Windows-/EXE-/Packaging-Qualifikation wird durch Linux-Tk und synthetische PDF-Nachweise nicht ersetzt. Die spätere P4-Abnahme und der integrierte Gesamtlauf sind bestanden; aktueller Quellfreigabestand: [A1-Prüfbericht](A1_FINAL_VERIFICATION_2026-11-13.md).

Status: **ROOT-GO**. Historischer Paketübergang: P4-Layout nach Nutzerbild. Den nachfolgenden integrierten Abschluss und autorisierten GitHub-Upload dokumentiert der A1-Prüfbericht.
