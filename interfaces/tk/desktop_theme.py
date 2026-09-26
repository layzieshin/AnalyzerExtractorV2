from __future__ import annotations

import tkinter as tk
from tkinter import ttk

APP_TITLE = "Analyzer Result Extractor"
APP_SUBTITLE = "EUROIMMUN Ergebnisverarbeitung"

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 10
FONT_SIZE_TITLE = 14
FONT_SIZE_SECTION = 11

COLOR_BG = "#f0f2f5"
COLOR_CARD = "#ffffff"
COLOR_BORDER = "#d8dde6"
COLOR_TEXT = "#1f2933"
COLOR_TEXT_MUTED = "#5c6b7a"
COLOR_PRIMARY = "#2563eb"
COLOR_PRIMARY_HOVER = "#1d4ed8"
COLOR_SUCCESS = "#15803d"
COLOR_WARNING = "#b45309"
COLOR_ERROR = "#b91c1c"
COLOR_NAV_ACTIVE = "#e8eef9"
COLOR_NAV_HOVER = "#f5f7fa"

MIN_WIDTH = 960
MIN_HEIGHT = 620
DEFAULT_WIDTH = 1180
DEFAULT_HEIGHT = 760

NAV_WIDTH = 200


def configure_desktop_theme(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(background=COLOR_BG)

    style.configure(".", font=(FONT_FAMILY, FONT_SIZE), background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("TFrame", background=COLOR_BG)
    style.configure("Card.TFrame", background=COLOR_CARD, relief="flat")
    style.configure("CardInner.TFrame", background=COLOR_CARD)
    style.configure("Header.TFrame", background=COLOR_BG)
    style.configure("Nav.TFrame", background=COLOR_CARD)
    style.configure("Content.TFrame", background=COLOR_BG)

    style.configure(
        "SectionTitle.TLabel",
        font=(FONT_FAMILY, FONT_SIZE_SECTION, "bold"),
        background=COLOR_CARD,
        foreground=COLOR_TEXT,
    )
    style.configure(
        "Muted.TLabel",
        font=(FONT_FAMILY, FONT_SIZE),
        foreground=COLOR_TEXT_MUTED,
        background=COLOR_CARD,
    )
    style.configure(
        "AppTitle.TLabel",
        font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"),
        foreground=COLOR_TEXT,
        background=COLOR_BG,
    )
    style.configure(
        "AppSubtitle.TLabel",
        font=(FONT_FAMILY, FONT_SIZE),
        foreground=COLOR_TEXT_MUTED,
        background=COLOR_BG,
    )
    style.configure(
        "Nav.TButton",
        font=(FONT_FAMILY, FONT_SIZE),
        padding=(12, 8),
        anchor="w",
    )
    style.configure(
        "NavActive.TButton",
        font=(FONT_FAMILY, FONT_SIZE),
        padding=(12, 8),
        anchor="w",
        background=COLOR_NAV_ACTIVE,
    )
    style.configure(
        "Primary.TButton",
        font=(FONT_FAMILY, FONT_SIZE),
        padding=(10, 6),
    )
    style.configure("Treeview", rowheight=24, font=(FONT_FAMILY, FONT_SIZE))
    style.configure("Treeview.Heading", font=(FONT_FAMILY, FONT_SIZE, "bold"))
    return style


def status_color(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized in {"success", "ok", "done", "fertig"}:
        return COLOR_SUCCESS
    if normalized in {"warning", "warn", "pending", "wait"}:
        return COLOR_WARNING
    if normalized in {"error", "failed", "danger"}:
        return COLOR_ERROR
    return COLOR_TEXT_MUTED
