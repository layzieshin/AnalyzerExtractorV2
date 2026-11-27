from __future__ import annotations

import tkinter as tk
from tkinter import ttk

APP_TITLE = "Analyzer Result Extractor"
APP_SUBTITLE = "EUROIMMUN Ergebnisverarbeitung"

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 10
FONT_SIZE_TITLE = 14
FONT_SIZE_SECTION = 12

COLOR_BG = "#f3f6fa"
COLOR_CARD = "#ffffff"
COLOR_BORDER = "#dbe4ed"
COLOR_TEXT = "#16293c"
COLOR_TEXT_MUTED = "#53677a"
COLOR_PRIMARY = "#175ba4"
COLOR_PRIMARY_HOVER = "#134a83"
COLOR_SUCCESS = "#186252"
COLOR_WARNING = "#7c4b08"
COLOR_ERROR = "#a63231"
COLOR_NAV_ACTIVE = "#eaf3fd"
COLOR_NAV_HOVER = "#f3f7fc"
COLOR_HERO = "#eef6ff"

MIN_WIDTH = 960
MIN_HEIGHT = 620
DEFAULT_WIDTH = 1180
DEFAULT_HEIGHT = 760

NAV_WIDTH = 222


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
    style.configure("Header.TFrame", background=COLOR_CARD)
    style.configure("Nav.TFrame", background=COLOR_CARD)
    style.configure("Content.TFrame", background=COLOR_BG)
    style.configure("Hero.TFrame", background=COLOR_HERO)
    style.configure("TLabel", background=COLOR_CARD, foreground=COLOR_TEXT)

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
    for name, size, weight, background, foreground in (
        ("PageTitle.TLabel", 25, "bold", COLOR_BG, COLOR_TEXT),
        ("PageSubtitle.TLabel", 10, "normal", COLOR_BG, COLOR_TEXT_MUTED),
        ("Eyebrow.TLabel", 8, "bold", COLOR_BG, COLOR_PRIMARY_HOVER),
        ("HeroTitle.TLabel", 18, "bold", COLOR_HERO, COLOR_TEXT),
        ("HeroMuted.TLabel", 10, "normal", COLOR_HERO, COLOR_TEXT_MUTED),
        ("HeroIcon.TLabel", 19, "normal", COLOR_NAV_ACTIVE, COLOR_PRIMARY),
        ("NavBrand.TLabel", 14, "bold", COLOR_CARD, COLOR_TEXT),
        ("NavBrandDetail.TLabel", 8, "normal", COLOR_CARD, COLOR_TEXT_MUTED),
        ("NavGroup.TLabel", 8, "bold", COLOR_CARD, COLOR_TEXT_MUTED),
        ("HeaderPath.TLabel", 10, "normal", COLOR_CARD, COLOR_TEXT_MUTED),
        ("HeaderSection.TLabel", 10, "bold", COLOR_CARD, COLOR_TEXT),
        ("HeaderDevice.TLabel", 9, "normal", COLOR_CARD, COLOR_TEXT_MUTED),
        ("Metric.TLabel", 21, "bold", COLOR_CARD, COLOR_TEXT),
        ("Device.TLabel", 12, "bold", COLOR_CARD, COLOR_TEXT),
    ):
        style.configure(name, font=(FONT_FAMILY, size, weight), background=background, foreground=foreground)
    style.configure(
        "TButton",
        font=(FONT_FAMILY, FONT_SIZE),
        padding=(10, 6),
        background=COLOR_CARD,
        foreground=COLOR_TEXT,
        bordercolor=COLOR_BORDER,
        lightcolor=COLOR_CARD,
        darkcolor=COLOR_CARD,
        relief="flat",
    )
    style.map("TButton", background=[("active", COLOR_NAV_HOVER)], foreground=[("disabled", COLOR_TEXT_MUTED)])
    style.configure(
        "Nav.TButton",
        font=(FONT_FAMILY, FONT_SIZE),
        padding=(10, 10),
        anchor="w",
        background=COLOR_CARD,
        foreground="#335069",
        borderwidth=0,
        relief="flat",
    )
    style.map("Nav.TButton", background=[("active", COLOR_NAV_HOVER)], foreground=[("active", COLOR_PRIMARY_HOVER)])
    style.configure(
        "NavActive.TButton",
        font=(FONT_FAMILY, FONT_SIZE),
        padding=(10, 10),
        anchor="w",
        background=COLOR_NAV_ACTIVE,
        foreground=COLOR_PRIMARY_HOVER,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "NavActive.TButton",
        background=[("active", COLOR_NAV_ACTIVE)],
        foreground=[("active", COLOR_PRIMARY_HOVER)],
    )
    style.configure(
        "Primary.TButton",
        font=(FONT_FAMILY, FONT_SIZE, "bold"),
        padding=(12, 8),
        background=COLOR_PRIMARY,
        foreground=COLOR_CARD,
        bordercolor=COLOR_PRIMARY,
        lightcolor=COLOR_PRIMARY,
        darkcolor=COLOR_PRIMARY,
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", COLOR_BORDER), ("active", COLOR_PRIMARY_HOVER)],
        foreground=[("disabled", COLOR_TEXT_MUTED), ("!disabled", COLOR_CARD)],
        bordercolor=[("active", COLOR_PRIMARY_HOVER)],
        lightcolor=[("active", COLOR_PRIMARY_HOVER)],
        darkcolor=[("active", COLOR_PRIMARY_HOVER)],
    )
    style.configure(
        "Treeview", rowheight=30, font=(FONT_FAMILY, FONT_SIZE),
        background=COLOR_CARD, fieldbackground=COLOR_CARD, bordercolor=COLOR_BORDER,
    )
    style.map("Treeview", background=[("selected", COLOR_NAV_ACTIVE)], foreground=[("selected", COLOR_TEXT)])
    style.configure(
        "Treeview.Heading", font=(FONT_FAMILY, 9, "bold"),
        background="#f1f5fa", foreground="#456078", padding=(8, 7), relief="flat",
    )
    for orientation in ("Vertical", "Horizontal"):
        style.layout(f"Slim.{orientation}.TScrollbar", [
            (f"{orientation}.Scrollbar.trough", {"sticky": "nswe", "children": [
                (f"{orientation}.Scrollbar.thumb", {"sticky": "nswe", "expand": "1"}),
            ]}),
        ])
        style.configure(f"Slim.{orientation}.TScrollbar", background="#bac8d7", troughcolor=COLOR_BG,
                        borderwidth=0, relief="flat", width=8, arrowsize=0)
        style.map(f"Slim.{orientation}.TScrollbar", background=[("active", "#91a9c1")])
    style.configure("Recent.Treeview", rowheight=36, font=(FONT_FAMILY, FONT_SIZE), borderwidth=0)
    style.configure("Toolbar.TButton", font=(FONT_FAMILY, 9), padding=(6, 3))
    style.configure("Compact.Primary.TButton", font=(FONT_FAMILY, 9, "bold"), padding=(10, 5))
    style.configure("Toolbar.TLabel", font=(FONT_FAMILY, 9), background=COLOR_CARD, foreground=COLOR_TEXT)
    style.configure("ToolbarTitle.TLabel", font=(FONT_FAMILY, 9, "bold"), background=COLOR_CARD, foreground=COLOR_TEXT)
    style.configure("CompactPageTitle.TLabel", font=(FONT_FAMILY, 17, "bold"), background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("Compact.TMenubutton", font=(FONT_FAMILY, 9), padding=(4, 3), background=COLOR_CARD)
    style.configure("CompactMuted.TLabel", font=(FONT_FAMILY, 9), background=COLOR_CARD, foreground=COLOR_TEXT_MUTED)
    style.configure("CompactValues.Treeview", rowheight=28, font=(FONT_FAMILY, 9))
    style.configure("CompactValues.Treeview.Heading", font=(FONT_FAMILY, 9, "bold"), padding=(6, 2))
    style.configure("Compact.TNotebook.Tab", font=(FONT_FAMILY, 9), padding=(7, 2))
    style.layout("Recent.Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
        ("Treeitem.image", {"side": "left", "sticky": ""}),
        ("Treeitem.text", {"side": "left", "sticky": ""}),
    ]})])
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
