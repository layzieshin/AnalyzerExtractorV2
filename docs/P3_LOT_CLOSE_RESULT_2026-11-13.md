# P3: Nutzungsnachweis, Abschlussvorschau und Archiv

Stand: 13.11.2026. Paketstatus: **ROOT-GO nach fokussiertem UX-Rework 1**. Unabhängige native Prüfung, tatsächlicher App-/Archiv-/Exportablauf und enge Nachprüfung der Zustandsbereinigung nach Reload sind bestanden. Ein integriertes Vollsuite-Ergebnis wird nicht behauptet.

## Auftrag und gesicherter Ausgangsstand

Die aktuelle ausdrückliche Nutzerfreigabe umfasst die vereinbarten Pakete und den abschließenden GitHub-Upload. P3 folgt auf das unabhängige P2-ROOT-GO. Ein Product-Writer, lesende Astra-Planung und unabhängige Root-Prüfung bleiben erhalten; keine weiteren Agenten oder Product-Writer wurden gestartet. Beobachtete Modell-/Effort-Telemetrie ist nicht verfügbar. Die aktuellen Rollen und die Gesamtfreigabe haben Vorrang vor älteren Rollen-/Einzelfreigabevorgaben; Governance-Dateien wurden dafür nicht geändert.

Remote-Ausgangs-HEAD bleibt `489ffe2a06ab166992b8eeb754bb0fb6ba2ecbfa`. Die materialisierte Arbeitskopie besitzt kein `.git`; ein lokal beobachteter HEAD wird nicht behauptet. Root hat den vollständigen externen P2-Checkpoint `P2_before_P3` und sein P2-GO gesichert. Der Writer hat die tatsächliche native P2-Abnahme (72 bestanden, keine Skips, tatsächliche Voll-App-/PDF-Sichtprüfung) im P2-Ergebnisdokument nachgetragen.

Umsetzung ausschließlich in den vorhandenen QC-, Application- und Tk-Ownern; keine weitere Persistenz, Migration, Shell, View oder Controller. Keine Regel-JSON-/Governance-/Runtime-/Patientendatenänderung, kein Build, keine Git-Schreibaktion. Sämtliche Testdaten sind synthetisch.

## Ein gemeinsamer Nutzungsnachweis

`get_lot_chronology(store_spec, profile_version_id=...)` in `qualitycontrol/sources.py` liefert `QCUsageSnapshot`, unveränderliches kanonisches JSON mit SHA-256. Der Snapshot bindet den expliziten Store, Geräte-/Assay-ID, Profilfassung und -köpfe, zeitliche Zuordnungen, Inventar, Chargenbindungen sowie alle projizierten Ergebnisse ohne UI-Limit. Jeder Lauf trägt Revisions-/Auswahlkennungen, Quellhash, effektiven Validierungsstand, exakte mögliche Chargenidentitäten, Datum-/Zeitrohwerte, Intervallpräzision und Klärungsgründe.

Chronologie und statistische Eignung bleiben unabhängig. Ein unvalidierter oder numerisch ungeeigneter späterer Lauf belegt die Nutzung seiner Charge, ohne in deren QMMA oder Westgard einzugehen. Die bestehenden `included`-/`excluded`-Populationen wurden nicht gelockert.

Die Intervalle sind halboffen. Datum allein bedeutet den ganzen Tag; fehlende oder ungültige separate Uhrzeit lässt bei gültigem Datum höchstens Tagespräzision zu. Nur zusammenhängend explizite Stunde → Minute → Sekunde verfeinert die Zeit. Bei einem akzeptierten ungewöhnlichen Format mit Sekunden ohne Stunde oder Stunde/Sekunde ohne Minute werden die fehlenden höheren Komponenten nicht als gemessen behandelt; die Unterkante wird auf Tages- beziehungsweise Stundenpräzision abgerundet. Nutzungsanzeige, Quellenliste, Punktinfos, Tooltips und Datumachsen zeigen keine künstliche Mitternacht an.

Eine spätere B-Nutzung ist ein Nachweis für den Abschluss von A, wenn sie sicher nach sämtlichen möglichen letzten Nutzungen von A liegt. Ein späterer Beginn von B ist nicht mehr erforderlich. Beispiel A02/03 gegen B01/04: A erhält ein Angebot. A03 gegen B04/C04: A erhält ein Angebot, B/C werden untereinander nicht künstlich geordnet. Identische Zeitstempel, gemeinsame Tage ohne Uhrzeit und überlappende Intervalle erhalten keinen Tie-Breaker über Importzeit oder Lauf-ID. Eine dritte Charge mit unbekanntem Datum verhindert nicht automatisch den bereits bewiesenen Paarvergleich; es wird keine global neueste Charge behauptet. Unbekannte Zielnutzung bleibt ein Klärungsbedarf.

Offene Ergebniskandidaten mit unveränderter Charge und Zeit lassen Nutzung bestimmen, bleiben aber statistisch ausgeschlossen. Geänderte Zeit oder Charge bewahrt sämtliche möglichen betroffenen Identitäten und lässt keinen Kandidaten als bestätigten Nutzungszeugen zu. Unlesbare Revisionshistorie kann eine unbekannte Kandidatenidentität verdecken und verlangt deshalb gruppenweite Klärung. Widersprüchliche zeitliche Profilinterpretationen bleiben sichtbar. Mehrere passende Profile werden nicht still gewählt; bestehende Bindung oder ausdrückliche Profilwahl liefert den Kontext.

## Vorschau und alleinige Abschlussautorität

Der bestehende ResultsController ergänzt `prepare_qc_lot_close(detail) -> QCLotClosePreview`. Vorbereitung liest die aktuellen Quellen und Nutzung, erzeugt das eingefrorene P2-Modell und die echte geprüfte PDF im bestehenden begrenzten Renderprozess und prüft den Kontext danach erneut. Sie schreibt weder offene Charge noch Evidenz oder SD-Referenz. Auswahl-/Profil-/Storewechsel und Vorbereitungsabbruch verwerfen spätere Callbacks. „Später“ hinterlässt keine Chargenrevision.

Die bestehende StatisticsView zeigt Angebote in der Chargenliste und genau einen Knopf „Abschluss prüfen“. Derselbe Dialog zeigt Gerät, Assay-ID/-Name, exakte Charge, letzte und belegte spätere Nutzung, weitere Unklarheiten, Profil-/Feldzuordnungen, Quellen-/Ausschlusszahlen, alle Level und deren eingefrorene QMMA-/Grenz-/Westgard-/SD-Verfügbarkeit sowie die vorbereiteten Modell-/PDF-Hashes. Nicht auswertbare Level werden ausdrücklich dargestellt. Fußzeilenaktionen bleiben bei kleiner Fenstergröße und vielen Leveln erreichbar.

`close_qc_lot(preview, ...)` veröffentlicht genau die vorbereiteten PDF-Bytes. Es erzeugt nach der finalen Bestätigung keine neue PDF. Während der endgültigen Schreibaktion sind Speichern, Abbrechen, Escape und Dialog-Fensterschließen gesperrt; der bestehende App-Schließschutz wartet auf laufende Worker. Ein persistentes Statusfeld zeigt auch nach gerenderter Vorschau einen veralteten Auswahl-/Storezustand an; es wird kein zerstörtes Widget angesprochen. Doppelte Klicks starten keinen zweiten Schreibauftrag.

`qualitycontrol/store.py:close_lot` bleibt alleinige Abschlussautorität. Unter `BEGIN IMMEDIATE` prüft es erwarteten Kopf oder erwartete Abwesenheit, Quellen-/Profil-/Inventarstand, vollständigen Chronologietoken und konkreten späteren Nutzungszeugen, Modell-/PDF-Hashes und SD-Bindung. Die bestehende gemeinsame `_require_sources`-Prüfung erzwingt weiterhin mindestens einen geeigneten Zielchargenwert. Dieser Schutz gilt auch für direkte API-Aufrufe oder einen manipulierten Controller-Sperrtext. Ein rein chronologisches Angebot und eine erläuternde Vorschau sind bei vollständig ungeklärten Zielwerten möglich, die Veröffentlichung bleibt gesperrt. Der Nutzungszeuge braucht keine statistisch geeigneten Werte.

`expected_version_id=0` plus ausdrücklicher Profilfassung erlaubt die erste direkt abgeschlossene Revision mit leeren gespeicherten SD-Referenzen. Es gibt keine beiläufige offene Revision oder Referenzbestätigung. Bestehende offene Chargen behalten Profil und Referenzen; eine lediglich ausgewählte ungespeicherte Profiländerung muss zuvor ausdrücklich gespeichert werden. Abschluss und Evidenz entstehen gemeinsam in den vorhandenen fünf Tabellen. Fehler rollen beide zurück. Request-/Intent-Prüfung und genaue Wiederholbarkeit bleiben erhalten. Die neue `successor_witness`-Fassung friert den vollständigen versionierten Nutzungsnachweis ein, ohne eine globale Reihenfolge zu behaupten.

## Archiv und Wiederöffnung

Neue Quellen zu einer geschlossenen Charge ändern deren Zustand und archivierte Modell-/PDF-Bytes nicht. Ein eigenes Live-Änderungsfeld bleibt neben der Archivzusammenfassung sichtbar. Statistik lädt weiterhin ausschließlich das gespeicherte Modell. Die vorhandene begründete Wiederöffnung erzeugt ausdrücklich eine neue Revision; alte Berichte bleiben auswählbar und bytegenau exportierbar. Gegenwärtige Nutzung und bereits abgeschlossener Zustand sind getrennte Eigenschaften.

## Funktionsnachweise und Grenzen

Umgebung wie P2: Python 3.12.14, externe Testabhängigkeiten über `PYTHONPATH`, Plugin-Autoload und Bytecode ausgeschaltet, pytest-Cache deaktiviert, temporäre Dateien außerhalb des Produkts. Die CLI besitzt keinen Zugriff auf den Desktop-X-Namespace; bestehende native Tk-Skips wurden nicht verändert oder neu eingeführt. Root führt diese Fälle nativ aus.

| Prüfung | Beobachtetes Ergebnis |
|---|---|
| Bestehende und neue Profil-/Quellen-/Store-/Chronologiefälle | 111 bestanden in 3,23 s |
| Neue echte Vorschau-/Direktabschluss-/Empty-Target-/Hashfälle und 18 einzelne Vorbereitungs-/Publikationsrennen | 21 bestanden in 8,27 s |
| Fokussierter Application-/Profil-/Quellen-/Store-/Echt-PDF-/Architekturlauf | 222 bestanden, 21 bestehende Tk-Umgebungsskips in 39,89 s |
| Zwei zusätzliche explizite Profil-/Konfigurationsbindungsfälle | 2 bestanden in 1,02 s |
| Unabhängige native Root-Auswahl: Application/Profil/Quellen/Store/Echt-PDF/Architektur | 246 bestanden, 0 Skips in 44,08 s |
| Syntax und nachgestellte Leerzeichen aller zwölf geänderten Python-Dateien | geprüft |

Die Rennen behandeln getrennt Zielwert, Zielvalidierung, neue Zielnutzung, neue Zeugennutzung, neue Drittchargennutzung, Profilkopf, Inventar, Chargenkopf und Storewechsel, jeweils während Vorbereitung und vor Veröffentlichung. Keiner dieser veralteten Vorschläge veröffentlicht Abschluss oder Evidenz. Echte PDF-Fehler, unverfügbare Zielstatistik und manipulierte PDF-Bytes hinterlassen keinen Abschluss. Bestehende Transaktions-Rollback-, Archiv-/Wiederöffnungs- und echte P2-Altarchivtests bleiben enthalten. Ein direkter negativer QC-API-Test verwendet ein wirklich gerendertes Empty-Target-Modell/PDF.

Native neue Abnahmefälle prüfen alle Level einschließlich nicht verfügbarer Statistik, kleine Vorschaufenster, gesperrten Abbruch beim Schreiben, tatsächlichen Shell-Stale-Submit nach gerenderter Vorschau, veraltete Vorbereitungscallbacks und erhaltene Archivänderungshinweise. Root hat den tatsächlichen vollständigen App-Ablauf mit A02/03, B01/04 (B04 unvalidiert und numerisch ungeeignet), C mit unbekanntem Datum, zwei Leveln und noch unkonfigurierter A geprüft. Angebot und Vorschau sind korrekt. „Später“ erhält Datenbankbytes und mtime und hinterlässt null Chargen-/Evidenzzeilen. Ein finaler Klick erzeugt genau eine erste abgeschlossene Revision mit Vorgänger 0 plus Evidenz. Das Archiv öffnet; der tatsächliche UI-PDF-Export ist byteidentisch zum gespeicherten PDF. Alle Python-Hashes waren beim unabhängigen Lauf unverändert.

Fokussiertes Rework 1: Nach dem Abschluss/Reload ohne Auswahl wurde fälschlich eine fehlende Profilkonfiguration behauptet und alte Level-/Punktdetails blieben sichtbar. Der vorhandene Auswahlpfad zeigt nun „Charge auswählen“, leert deaktivierte Profil-/Level-/Nachweisauswahl sowie Punkt-/Diagrammzustand und zeigt den Profilfehler ausschließlich bei tatsächlich ausgewählter Charge ohne Profil. Ein nativer Post-Abschluss-/Refresh-Regressionsfall prüft genau diesen Zustand und den weiterhin berechtigten Profilfehler. Keine andere Produktlogik wurde für das Rework geändert. Die erneute unabhängige native Root-Auswahl bestand **5 Tests, 0 Skips in 2,66 s**: neuer Post-Refresh-Fall, Archivhinweis/Datumpräzision, veralteter Submit, P2-Frozen-Linien und Diagramminteraktionen. Sämtliche Freeze-Hashes stimmen. Root erteilte P3-GO; externer Nachweis `test_runs/root_p3_review_final.json`, Safety-Checkpoint `P3_before_R1`. Eine integrierte Vollsuite, Build und Windows-Zielqualifikation werden nicht aus den fokussierten Linux-Nachweisen abgeleitet.

Phasengleiche öffentliche Verträge wurden in `docs/ARCHITECTURE.md`, `docs/EMBEDDING.md` und `docs/TESTBASELINE.md` aktualisiert. Keine zweite Workflowengine, keine Chronologieberechnung im Controller oder UI und keine Persistenzänderung außerhalb der vorhandenen JSON-Snapshots.

Status: **ROOT-GO**. Der damalige Paketübergang und die folgenden Arbeitspakete sind historisch; den aktuellen integrierten Abschluss dokumentiert der [A1-Prüfbericht](A1_FINAL_VERIFICATION_2026-11-13.md).
