"""Hilfetexte, Step-by-Step-Guide und Farbpalette des Rule Editors."""
from __future__ import annotations

HELP_TEXTS: dict[str, str] = {
    "search_pattern": (
        "Die Erkennungsregel (Regex) legt fest, welcher Teil des Berichttexts als Wert übernommen wird. "
        "Markieren Sie am besten zuerst den gewünschten Wert im PDF-Testbericht."
    ),
    "required_field": (
        "Ist diese Option aktiv, muss das Feld im Bericht gefunden werden. "
        "Fehlt es, wird die Auswertung als fehlerhaft behandelt."
    ),
    "search_from": (
        "Der Suchbereich begrenzt die Suche auf einen späteren Bereich des Berichts. "
        "Das ist hilfreich, wenn derselbe Begriff mehrfach vorkommt."
    ),
    "pattern_from_selection": (
        "Muster aus Markierung erstellt aus dem markierten Beispieltext einen Vorschlag für die Erkennungsregel. "
        "Prüfen Sie den Vorschlag anschließend mit 'Regex testen'."
    ),
    "draft_control": (
        "Im Inventar wählen Sie eine bestehende Regel. "
        "'Regel aus PDF erstellen oder prüfen …' startet immer neutral. "
        "'Neue Regel aus PDF …' startet denselben Ablauf für eine Neuanlage, weiterhin mit PDF zuerst."
    ),
    "pdf_block": (
        "Wählen Sie eine Test-PDF und klicken Sie auf 'PDF-Text laden'. "
        "Markieren Sie Text im Bericht, lassen Sie eine Erkennungsregel vorschlagen und legen Sie Felder an."
    ),
    "fields": (
        "Hier legen Sie fest, welche Werte aus der PDF gelesen werden. "
        "Ein Feld besteht aus Feldschlüssel, Erkennungsregel (Regex) und dem Suchbereich."
    ),
    "meta_actions": (
        "Unter Regeldetails pflegen Sie Assay-Name, Los-/Chargenkennung und die Exportdateinamen. "
        "Die Excel-Spaltenzuordnung entsteht im Feldeditor. Danach speichern, strukturell prüfen, "
        "die Extraktion mit PDF testen und erst dann den Entwurf aktivieren."
    ),
    "validation": (
        "Die Strukturprüfung prüft, ob die Regeldatei technisch sauber ist. "
        "Typische Fehler: leere Erkennungsregel, falscher Suchbereich oder eine Excel-Spalte ohne Feld."
    ),
    "preview": (
        "Extraktion mit PDF testen prüft den Entwurf mit einer echten PDF, ohne produktive Dateien zu überschreiben."
    ),
    "activate": (
        "Entwurf aktivieren übernimmt den Entwurf in die produktiven Regeln. "
        "Bei bestehendem Assay wird die alte Regel ersetzt, bei neuem Assay wird ein neuer Eintrag angelegt."
    ),
    "diff": (
        "Änderungen anzeigen zeigt, was sich gegenüber der aktiven Regel geändert hat. "
        "Prüfen Sie vor der Aktivierung vor allem Felder, Los-/Chargenkennung und die Excel-Spaltenzuordnung."
    ),
    "batch_regex": (
        "Alle Felder testen prüft jede Erkennungsregel in einem Lauf. "
        "Sie sehen pro Feld: Treffer, kein Treffer oder Fehler."
    ),
    "undo_redo": (
        "Mit Rückgängig und Wiederholen machen Sie Änderungen zurück oder stellen sie wieder her. "
        "Shortcuts: Strg+Z und Strg+Y."
    ),
    "autosave": (
        "Automatisch speichern sichert den Entwurf alle 45 Sekunden, wenn es neue Änderungen gibt. "
        "Der Zeitpunkt der letzten automatischen Speicherung wird daneben angezeigt."
    ),
}

STEP_BY_STEP_GUIDE: list[dict[str, str]] = [
    {
        "title": "1) Regel aus PDF erstellen oder prüfen",
        "text": (
            "Die Schaltfläche in der Kopfzeile startet immer neutral. "
            "Wählen Sie dort ausdrücklich eine neue Regel aus einer PDF oder einen vorhandenen Entwurf.\n\n"
            "'Neue Regel aus PDF …' im Inventar startet denselben Ablauf direkt für eine Neuanlage, weiterhin mit PDF zuerst."
        ),
    },
    {
        "title": "2) Test-PDF laden",
        "text": (
            "Im Bereich 'PDF-Testbericht' eine Test-PDF wählen und 'PDF-Text laden' klicken.\n\n"
            "Text markieren, eine Erkennungsregel vorschlagen lassen und Felder direkt bearbeiten."
        ),
    },
    {
        "title": "3) Felder pflegen",
        "text": (
            "In der Feldliste ein Feld wählen und rechts Feldschlüssel und Erkennungsregel pflegen.\n\n"
            "Mit 'Regex testen' prüfen Sie ein Feld sofort. 'Alle Felder testen' liegt unter Regeldetails."
        ),
    },
    {
        "title": "4) Regeldetails",
        "text": (
            "Unter Regeldetails Assay-Name, Los-/Chargenkennung und Exportdateinamen pflegen.\n\n"
            "Die Excel-Spaltenzuordnung wird im Feldeditor gesetzt und dort nur angezeigt. "
            "Speichern Sie danach den Entwurf."
        ),
    },
    {
        "title": "5) Strukturprüfung und Extraktionstest",
        "text": (
            "Klicken Sie 'Entwurf strukturell prüfen'. Beheben Sie Fehler aus der Liste.\n\n"
            "Danach 'Extraktion mit PDF testen', um mit echter PDF zu prüfen, "
            "ob die erwarteten Werte extrahiert werden."
        ),
    },
    {
        "title": "6) Änderungen prüfen und aktivieren",
        "text": (
            "Mit 'Änderungen anzeigen' kontrollieren Sie die Unterschiede zur aktiven Regel.\n\n"
            "Erst wenn alles passt: 'Entwurf aktivieren'. Bestehende Regeln werden dabei ersetzt, "
            "neue Assays werden neu angelegt."
        ),
    },
]

FIELD_MARKING_COLORS = [
    "#cce5ff",
    "#d4edda",
    "#fff3cd",
    "#f8d7da",
    "#e2d5f1",
    "#d1ecf1",
    "#fde2e4",
    "#e7f5ff",
    "#fff0f6",
    "#e9ecef",
]
