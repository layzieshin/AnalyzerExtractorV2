import pytest

from src.contentsplitter.api import split_by_assay_name_and_key
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
