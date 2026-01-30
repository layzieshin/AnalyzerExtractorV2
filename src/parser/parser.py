from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

from .model import ParsedDocument, ParsedPage


LINE_Y_TOLERANCE: float = 2.0
MIN_X_GAP_FOR_SPACE: float = 1.5
MULTI_SPACE_GAP_STEP: float = 20.0
MIN_PRINTABLE_CHARS: int = 1


@dataclass(frozen=True)
class _Fragment:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2.0


class ParserError(RuntimeError):
    pass


class Parser:
    """Internal parser implementation (positional)."""

    def parse(self, pdf_path: str) -> ParsedDocument:
        try:
            pages = self._extract_pdf_pages_position_based(pdf_path)
        except Exception as e:
            raise ParserError(str(e)) from e

        parsed_pages = [ParsedPage(page_number=p.page_number, lines=p.lines) for p in pages]
        meta = {"page_count": len(parsed_pages), "engine": "pymupdf_positional"}
        return ParsedDocument(source_path=pdf_path, pages=parsed_pages, meta=meta)

    @dataclass(frozen=True)
    class _PdfPageText:
        page_number: int
        lines: List[str]

    def _extract_pdf_pages_position_based(self, pdf_path: str) -> List[_PdfPageText]:
        pages: List[Parser._PdfPageText] = []
        with fitz.open(pdf_path) as doc:
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                lines = self._extract_page_lines_position_based(page)
                pages.append(Parser._PdfPageText(page_number=page_index + 1, lines=lines))
        return pages

    def _extract_page_lines_position_based(self, page: fitz.Page) -> List[str]:
        fragments = self._extract_fragments(page)
        clusters = self._cluster_fragments_into_lines(fragments)
        lines: List[str] = []
        for cluster in clusters:
            line_text = self._join_line_fragments(cluster)
            if len(line_text.strip()) >= MIN_PRINTABLE_CHARS:
                lines.append(line_text)
        return lines

    def _extract_fragments(self, page: fitz.Page) -> List[_Fragment]:
        data = page.get_text("dict")
        fragments: List[_Fragment] = []
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "")
                    if not txt:
                        continue
                    x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                    fragments.append(_Fragment(text=txt, x0=x0, y0=y0, x1=x1, y1=y1))
        return fragments

    def _cluster_fragments_into_lines(self, fragments: List[_Fragment]) -> List[List[_Fragment]]:
        if not fragments:
            return []
        frags_sorted = sorted(fragments, key=lambda f: (f.y_center, f.x0))
        clusters: List[Tuple[float, List[_Fragment]]] = []
        for frag in frags_sorted:
            placed = False
            for idx, (y_ref, frags) in enumerate(clusters):
                if abs(frag.y_center - y_ref) <= LINE_Y_TOLERANCE:
                    frags.append(frag)
                    new_y_ref = (y_ref * (len(frags) - 1) + frag.y_center) / len(frags)
                    clusters[idx] = (new_y_ref, frags)
                    placed = True
                    break
            if not placed:
                clusters.append((frag.y_center, [frag]))
        clusters.sort(key=lambda c: c[0])
        return [sorted(frags, key=lambda f: f.x0) for _, frags in clusters]

    def _join_line_fragments(self, line_frags: List[_Fragment]) -> str:
        if not line_frags:
            return ""
        parts: List[str] = []
        prev_x1: Optional[float] = None
        for frag in line_frags:
            if prev_x1 is None:
                parts.append(frag.text)
                prev_x1 = frag.x1
                continue
            gap = frag.x0 - prev_x1
            if gap > MIN_X_GAP_FOR_SPACE:
                extra_spaces = int(gap // MULTI_SPACE_GAP_STEP) if MULTI_SPACE_GAP_STEP > 0 else 0
                parts.append(" " * (1 + max(0, extra_spaces)))
            parts.append(frag.text)
            prev_x1 = frag.x1
        return "".join(parts).strip()
