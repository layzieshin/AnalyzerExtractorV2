from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_app_root(module_file: str | Path | None = None) -> Path:
    """Return the writable runtime root for source and PyInstaller runs."""
    home = os.getenv("ARE_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    if module_file is not None:
        return Path(module_file).resolve().parent

    return Path.cwd().resolve()
