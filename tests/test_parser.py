from pathlib import Path

import fitz

from src.parser.api import parse


def test_parser_extracts_inserted_lines(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Anti-TPO IgG")
    page.insert_text((72, 90), "(5f03)")
    doc.save(str(pdf))
    doc.close()

    parsed = parse(str(pdf))
    lines = [ln for p in parsed.pages for ln in p.lines]
    joined = "\n".join(lines)

    assert parsed.meta.get("page_count") == 1
    assert "Anti-TPO IgG" in joined
    assert "(5f03)" in joined
