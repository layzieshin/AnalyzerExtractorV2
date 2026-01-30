from src.contentsplitter.api import split_by_assay_keys
import pytest

def test_split_blocks():
    text = "aaa (1111) block1 xxx (2222) block2 yyy"
    blocks = split_by_assay_keys(text, ["(1111)", "(2222)"])
    assert "block1" in blocks["(1111)"]
    assert "block2" in blocks["(2222)"]

def test_split_fail_missing_key():
    with pytest.raises(Exception):
        split_by_assay_keys("aaa (1111)", ["(1111)", "(2222)"])
