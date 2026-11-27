import pytest

from src.contentsplitter.api import split_by_assay_name_and_key
from src.contentsplitter.api import split_assay_sections
from src.contentsplitter.contentsplitter import ContentSplitError
from src.contentsplitter.model import AssayDescriptor


def test_split_by_assay_name_and_key_happy_path():
    text = "Header\nAssay A\n(1111)\nblock-a\nAssay B\n(2222)\nblock-b"
    assays = [
        AssayDescriptor(assay_key="(1111)", assay_name="Assay A"),
        AssayDescriptor(assay_key="(2222)", assay_name="Assay B"),
    ]
    blocks = split_by_assay_name_and_key(text, assays)
    assert "block-a" in blocks["(1111)"]
    assert "block-b" in blocks["(2222)"]


def test_split_by_assay_name_and_key_requires_key_after_name():
    text = "Assay A\nblock-a\n(1111)"
    assays = [AssayDescriptor(assay_key="(2222)", assay_name="Assay A")]
    with pytest.raises(ContentSplitError):
        split_by_assay_name_and_key(text, assays)


def test_anchored_sections_keep_manufacturer_block_units_and_exact_offsets():
    text = "\n".join(["Earlier reference to Instrument Alpha", "Instrument Alpha", "Plate: P1", "Lot: L1",
                      r"Test: C:\Assays\Instrument Alpha.asy (1C9E)", "Referenzwerte (U/mL)", "Einheit (IU)",
                      "Value: 106.4", "Unknown assay (FADE)", "Value: 999"])
    sections = split_assay_sections(text)
    assert [row.assay_key for row in sections] == ["(1c9e)", "(fade)"]
    target = sections[0]
    assert target.raw_assay_key == "(1C9E)" and target.assay_name == "Instrument Alpha"
    assert target.text.startswith("Instrument Alpha\nPlate: P1\nLot: L1\nTest:")
    assert "Value: 106.4" in target.text and "Value: 999" not in target.text
    assert "Referenzwerte (U/mL)" in target.text and "Einheit (IU)" in target.text
    for section in sections:
        assert text[section.start:section.end] == section.text


@pytest.mark.parametrize("text", ["Assay A (1111)\nValue: 1\nAssay A (1111)\nValue: 2",
                                 "Instrument Alpha (1111)\nTest: C:\\Assays\\Instrument Alpha.asy (2222)"])
def test_anchored_sections_reject_duplicate_or_conflicting_identity(text):
    with pytest.raises(ContentSplitError, match="assay_header_ambiguous"):
        split_assay_sections(text)


def test_anchored_sections_accept_special_keys_only_from_explicit_configuration():
    text = "Custom assay (custom-key)\nValue: 7\nUnknown assay (FADE)\nValue: 99"
    assert [row.assay_key for row in split_assay_sections(text)] == ["(fade)"]
    result = split_assay_sections(text, known_keys=("(custom-key)",))
    assert [row.assay_key for row in result] == ["(custom-key)", "(fade)"]
    assert "Value: 99" not in result[0].text
