from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from src.assaycandidate.api import canonical_assay_key, find_assay_candidates

from .model import AssayDescriptor, AssaySection


class ContentSplitError(RuntimeError):
    pass


def split_assay_sections(norm_text: str, *, known_keys: Iterable[str] = ()) -> List[AssaySection]:
    """Resolve anchored document identity and boundaries once for proof/import.

    Display names in a ruleset are not document locators. A title and its Test
    path are one occurrence; every anchored header (also unknown IDs) bounds the
    previous section. Ambiguous identities are never silently merged.
    """
    lines = norm_text.split("\n")
    configured_keys = {canonical_assay_key(key) for key in known_keys}
    def is_key(raw: str) -> bool:
        return bool(re.fullmatch(r"\([0-9a-fA-F]{4}\)", raw)) or canonical_assay_key(raw) in configured_keys
    headers: list[dict] = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        test = next((row for row in find_assay_candidates(line) if row.get("reason") == "test_line"), None)
        if test is not None:
            headers.append({"start": index, "name": str(test["assay_name_hint"]),
                            "key": canonical_assay_key(str(test["raw_assay_key"])),
                            "raw_key": str(test["raw_assay_key"]), "test": True})
            continue
        header = re.fullmatch(r"(.+?)\s+(\([^()\s]+\))", line)
        if header and ":" not in header.group(1) and is_key(header.group(2)):
            headers.append({"start": index, "name": header.group(1), "key": canonical_assay_key(header.group(2)),
                            "raw_key": header.group(2), "test": False})
        elif re.fullmatch(r"\([^()\s]+\)", line) and is_key(line) and index and lines[index - 1].strip():
            headers.append({"start": index - 1, "name": lines[index - 1].strip(), "key": canonical_assay_key(line),
                            "raw_key": line, "test": False})
    consumed: set[int] = set()
    previous_test = -1
    for test in (row for row in headers if row["test"]):
        end = test["start"]
        corroborating = [row for row in headers if not row["test"] and previous_test < row["start"] < end
                          and row["name"] == test["name"]]
        if any(row["key"] != test["key"] for row in corroborating):
            raise ContentSplitError("content_split_failed: assay_header_ambiguous")
        titles = [index for index in range(previous_test + 1, end) if lines[index].strip() == test["name"]]
        if len(corroborating) > 1 or len(titles) > 1:
            raise ContentSplitError("content_split_failed: assay_header_ambiguous")
        if corroborating:
            test["start"] = corroborating[0]["start"]
            consumed.add(id(corroborating[0]))
        elif titles:
            test["start"] = titles[0]
        if any(test["start"] < row["start"] < end and row is not test and id(row) not in consumed for row in headers):
            raise ContentSplitError("content_split_failed: assay_header_ambiguous")
        previous_test = end
    headers = sorted((row for row in headers if id(row) not in consumed), key=lambda row: row["start"])
    if len({row["start"] for row in headers}) != len(headers) or len({row["key"] for row in headers}) != len(headers):
        raise ContentSplitError("content_split_failed: assay_header_ambiguous")
    offsets, cursor = [], 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1
    sections = []
    for index, header in enumerate(headers):
        start = offsets[header["start"]]
        end = offsets[headers[index + 1]["start"]] if index + 1 < len(headers) else len(norm_text)
        raw = norm_text[start:end]
        start += len(raw) - len(raw.lstrip())
        block = raw.strip()
        if not block:
            raise ContentSplitError("content_split_failed: assay_block_empty")
        sections.append(AssaySection(header["key"], header["name"], header["raw_key"], start, start + len(block), block))
    return sections


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
