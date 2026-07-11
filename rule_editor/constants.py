"""Hilfetexte, Step-by-Step-Guide und Farbpalette des Rule Editors."""
from __future__ import annotations

HELP_TEXTS: dict[str, str] = {
    "draft_control": (
        "Hier starten Sie immer. "
        "Bestehendes Regelset bearbeiten: Assay auswaehlen und 'Draft aus aktivem Assay' klicken. "
        "Neues Regelset anlegen: neuen assay_key + assay_name eintragen und 'Neues Draft mit Headern' "
        "oder 'Aus aktivem ableiten' verwenden."
    ),
    "pdf_block": (
        "Waehlen Sie hier eine Test-PDF und klicken Sie auf 'Text laden'. "
        "Markieren Sie Text im Assay-Block, lassen sich Regex vorschlagen und legen Felder "
        "neu an oder passen bestehende direkt im Markierungs-Panel an."
    ),
    "fields": (
        "Hier legen Sie fest, welche Werte aus der PDF gelesen werden sollen. "
        "Ein Feld besteht aus Name (key), Suchmuster (regex) und optionalen Einstellungen "
        "wie 'required' oder 'search_from'."
    ),
    "meta_actions": (
        "Hier pflegen Sie Assay-Name, Lot-Regel, Dedupe-Felder und Spalten-Mapping fuer Excel. "
        "Danach speichern, validieren, Preview ausfuehren und erst dann aktivieren."
    ),
    "validation": (
        "Die Validierung prueft, ob Ihr Regelset technisch sauber ist. "
        "Typische Fehler: leere regex, falsche search_from-Werte oder Mapping auf nicht vorhandene Felder."
    ),
    "preview": (
        "Preview testet Ihr Draft mit einer echten PDF, ohne produktive Dateien zu ueberschreiben. "
        "So sehen Sie vorab, ob die richtigen Werte extrahiert werden."
    ),
    "activate": (
        "Aktivieren uebernimmt den Draft in die produktiven Regeln. "
        "Bei bestehendem Assay wird die alte Regel ersetzt, bei neuem Assay wird ein neuer Eintrag angelegt."
    ),
    "diff": (
        "Diff zeigt, was sich gegenueber der aktiven Regel geaendert hat. "
        "Pruefen Sie vor Aktivierung vor allem Felder, lot_rule und column_mapping."
    ),
    "batch_regex": (
        "Batch-Regex-Check prueft alle Felder in einem Lauf. "
        "Sie sehen pro Feld: Treffer, kein Treffer oder Fehler."
    ),
    "undo_redo": (
        "Mit Undo/Redo koennen Sie Aenderungen schnell rueckgaengig machen oder wiederherstellen. "
        "Shortcuts: Ctrl+Z und Ctrl+Y."
    ),
    "autosave": (
        "Auto-Save speichert Ihren Draft automatisch alle 45 Sekunden, wenn es neue Aenderungen gibt. "
        "Die Uhrzeit der letzten automatischen Speicherung wird rechts angezeigt."
    ),
}

STEP_BY_STEP_GUIDE: list[dict[str, str]] = [
    {
        "title": "1) Start: Draft anlegen oder laden",
        "text": (
            "Wenn Sie ein bestehendes Regelset bearbeiten wollen: Assay auswaehlen und "
            "'Draft aus aktivem Assay' klicken.\n\n"
            "Wenn Sie ein neues Regelset brauchen: assay_key + assay_name eintragen und "
            "'Neues Draft mit Headern' oder 'Aus aktivem ableiten' nutzen."
        ),
    },
    {
        "title": "2) Test-PDF laden",
        "text": (
            "Im Tab 'PDF / Assay-Text' eine Test-PDF waehlen und 'Text laden' klicken.\n\n"
            "Text markieren, Regex vorschlagen lassen und Felder direkt im Markierungs-Panel "
            "neu anlegen oder bestehende anpassen."
        ),
    },
    {
        "title": "3) Felder pflegen",
        "text": (
            "Im Bereich 'Felder' key + regex setzen. Optional: required und search_from.\n\n"
            "Mit 'Regex testen' pruefen Sie ein Feld sofort. Mit 'Batch-Regex-Check' testen Sie alle Felder auf einmal."
        ),
    },
    {
        "title": "4) Meta und Mapping pflegen",
        "text": (
            "Im Bereich 'Meta / Excel / Aktionen' assay_name, lot_rule.regex, dedupe_fields und "
            "column_mapping pflegen.\n\n"
            "Speichern Sie danach den Draft."
        ),
    },
    {
        "title": "5) Validieren und Preview",
        "text": (
            "Klicken Sie 'Draft validieren'. Beheben Sie Fehler aus der Liste.\n\n"
            "Danach 'Preview (extract)' starten, um mit echter PDF zu pruefen, "
            "ob die erwarteten Werte extrahiert werden."
        ),
    },
    {
        "title": "6) Diff pruefen und aktivieren",
        "text": (
            "Mit 'Diff anzeigen' kontrollieren Sie die Unterschiede zur aktiven Regel.\n\n"
            "Erst wenn alles passt: 'Aktivieren'. Bestehende Regeln werden dabei ersetzt, "
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
