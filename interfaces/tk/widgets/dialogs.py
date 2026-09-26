from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from interfaces.tk.desktop_theme import COLOR_CARD


def show_error_dialog(parent: tk.Misc, title: str, message: str, *, details: str = "") -> None:
    if details:
        show_details_dialog(parent, title, message, details)
        return
    messagebox.showerror(title, message, parent=parent)


def show_info_dialog(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showinfo(title, message, parent=parent)


def show_confirm_dialog(parent: tk.Misc, title: str, message: str) -> bool:
    return bool(messagebox.askyesno(title, message, parent=parent))


def show_details_dialog(parent: tk.Misc, title: str, message: str, details: str) -> None:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.configure(background=COLOR_CARD)
    dialog.geometry("520x360")

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=message, wraplength=480).pack(anchor="w")
    text = tk.Text(frame, height=12, wrap="word")
    text.pack(fill="both", expand=True, pady=(8, 8))
    text.insert("1.0", details)
    text.configure(state="disabled")
    ttk.Button(frame, text="Schließen", command=dialog.destroy).pack(anchor="e")
