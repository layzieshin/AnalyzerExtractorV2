from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from .errors import PathOpenError

PathOpener = Callable[[str], None]


def default_path_opener(path: str) -> None:
    target = Path(path)
    if not target.exists():
        raise PathOpenError(f"path_not_found: {path}")
    if sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    if target.is_dir():
        subprocess.Popen(["xdg-open", str(target)])
        return
    subprocess.Popen(["xdg-open", str(target)])


def open_path(path: str, *, opener: PathOpener | None = None) -> None:
    text = str(path or "").strip()
    if not text:
        raise PathOpenError("path_empty")
    resolved = Path(text)
    if not resolved.exists():
        raise PathOpenError(f"path_not_found: {text}")
    open_impl = opener or default_path_opener
    try:
        open_impl(str(resolved))
    except PathOpenError:
        raise
    except Exception as exc:
        raise PathOpenError(f"path_open_failed: {exc}") from exc
