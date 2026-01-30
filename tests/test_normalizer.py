from src.normalizer.api import normalize_lines

def test_normalize_preserves_line_count():
    inp = ["A   B", "  C\t\tD  ", ""]
    out = normalize_lines(inp)
    assert len(out) == len(inp)
    assert out[0] == "A B"
    assert out[1] == "C D"
