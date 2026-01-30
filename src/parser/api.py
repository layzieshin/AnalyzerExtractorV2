from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .model import ParsedDocument, ParsedPage
from .parser import Parser

def parse(pdf_path: str) -> ParsedDocument:
    """Public API (Parser)

    Contract:
    - Positional / line-based PDF extraction using PyMuPDF.
    - Deterministic.
    - No normalization.
    """
    return Parser().parse(pdf_path)
