from __future__ import annotations

from typing import Dict, List, Tuple

from .model import AssayDescriptor


class ContentSplitError(RuntimeError):
    pass


def split_by_assay_keys(norm_text: str, assay_keys: List[str]) -> Dict[str, str]:
    if not assay_keys:
        raise ContentSplitError("content_split_failed: no assay_keys provided")

    occ: List[Tuple[int, str]] = []
    for key in assay_keys:
        pos = norm_text.find(key)
        if pos == -1:
            raise ContentSplitError(f"content_split_failed: key not found: {key}")
        occ.append((pos, key))

    occ.sort(key=lambda x: x[0])
    blocks: Dict[str, str] = {}
    for i, (pos, key) in enumerate(occ):
        start = pos
        end = occ[i + 1][0] if i + 1 < len(occ) else len(norm_text)
        block = norm_text[start:end].strip()
        if not block:
            raise ContentSplitError(f"content_split_failed: empty block for {key}")
        blocks[key] = block

    if set(blocks.keys()) != set(assay_keys):
        raise ContentSplitError("content_split_failed: mismatch keys vs blocks")
    return blocks


class ContentSplitter:

    # Legacy (temporary)
    def split_by_assay_name(self, norm_text: str, assay_names: List[str]) -> Dict[str, str]:
        if not assay_names:
            raise ContentSplitError("content_split_failed: no assay_names provided")

        occ: List[Tuple[int, str]] = []
        for name in assay_names:
            pos = norm_text.find(name)
            if pos == -1:
                raise ContentSplitError(f"content_split_failed: assay_name not found: {name}")
            occ.append((pos, name))

        occ.sort(key=lambda x: x[0])
        blocks: Dict[str, str] = {}
        for i, (pos, name) in enumerate(occ):
            start = pos
            end = occ[i + 1][0] if i + 1 < len(occ) else len(norm_text)
            block = norm_text[start:end].strip()
            if not block:
                raise ContentSplitError(f"content_split_failed: empty block for assay_name {name}")
            blocks[name] = block

        if set(blocks.keys()) != set(assay_names):
            raise ContentSplitError("content_split_failed: mismatch assay names vs blocks")
        return blocks

    # NEW (final mechanism)
    def split_by_assay_name_and_key(self, norm_text: str, assays: List[AssayDescriptor]) -> Dict[str, str]:
        if not assays:
            raise ContentSplitError("content_split_failed: no assays provided")

        # Determine validated starts (case-sensitive)
        starts: List[Tuple[int, AssayDescriptor]] = []
        for a in assays:
            if not a.assay_name or not a.assay_key:
                raise ContentSplitError("content_split_failed: assay descriptor missing assay_name/assay_key")

            start = norm_text.find(a.assay_name)  # case-sensitive
            if start == -1:
                raise ContentSplitError(f"content_split_failed: assay_name not found: {a.assay_name}")

            # Validation: key must occur after start
            if norm_text.find(a.assay_key, start) == -1:
                raise ContentSplitError(
                    f"content_split_failed: assay_key {a.assay_key} not found after assay_name {a.assay_name}"
                )

            starts.append((start, a))

        # Multi-assay: sort by start positions and cut blocks
        starts.sort(key=lambda x: x[0])

        blocks: Dict[str, str] = {}
        for i, (start, a) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(norm_text)
            block = norm_text[start:end].strip()
            if not block:
                raise ContentSplitError(f"content_split_failed: empty block for assay_key {a.assay_key}")
            blocks[a.assay_key] = block

        # Ensure 1:1 mapping by assay_key
        if set(blocks.keys()) != {a.assay_key for a in assays}:
            raise ContentSplitError("content_split_failed: mismatch assay_keys vs blocks")
        return blocks
