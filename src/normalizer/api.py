from __future__ import annotations

from typing import List

from .normalizer import Normalizer


def normalize_lines(lines: List[str]) -> List[str]:
    """Public API (Normalizer)

    Contract:
    - Reduce whitespace within each line.
    - Preserve line breaks (line count unchanged).
    """
    return Normalizer().normalize_lines(lines)
