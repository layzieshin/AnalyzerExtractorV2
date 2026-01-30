from __future__ import annotations

from typing import Dict, List

from .contentsplitter import ContentSplitter, split_by_assay_keys
from .model import AssayDescriptor


# TODO: deprecated – remove after migration to split_by_assay_name_and_key
def split_by_assay_keys(norm_text: str, assay_keys: List[str]) -> Dict[str, str]:
    """Legacy public API (temporary)."""
    return split_by_assay_keys(norm_text, assay_keys)


# TODO: deprecated – remove after migration to split_by_assay_name_and_key
def split_by_assay_name(norm_text: str, assay_names: List[str]) -> Dict[str, str]:
    """Legacy public API (temporary)."""
    return ContentSplitter().split_by_assay_name(norm_text, assay_names)


def split_by_assay_name_and_key(norm_text: str, assays: List[AssayDescriptor]) -> Dict[str, str]:
    """Public API (ContentSplitter) – NEW

    Contract (case-sensitive):
    - For each assay, find the FIRST occurrence of assay_name (case-sensitive).
    - Start is valid ONLY if assay_key occurs AFTER that start (case-sensitive).
    - Multi-assay: blocks are cut from each validated start to the next start (or EOF).
    - MUST-SPLIT: if any assay cannot be split into a non-empty block -> raise ContentSplitError("content_split_failed: ...").
    """
    return ContentSplitter().split_by_assay_name_and_key(norm_text, assays)
