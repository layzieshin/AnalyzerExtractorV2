from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.rulesuite.api import activate_draft, create_draft, list_fields, preview_extract, set_field_regex


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule authoring and preview suite")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-draft", help="Create draft ruleset from active assay ruleset")
    p_create.add_argument("--assay-key", required=True)

    p_fields = sub.add_parser("list-fields", help="List extract field keys for assay")
    p_fields.add_argument("--assay-key", required=True)

    p_set = sub.add_parser("set-regex", help="Set regex of one extract field in draft")
    p_set.add_argument("--draft-path", required=True)
    p_set.add_argument("--field-key", required=True)
    p_set.add_argument("--regex", required=True)

    p_preview = sub.add_parser("preview", help="Run extraction preview against test PDF")
    p_preview.add_argument("--pdf", required=True)
    p_preview.add_argument("--assay-key", required=True)
    p_preview.add_argument("--draft-path")

    p_activate = sub.add_parser("activate-draft", help="Promote draft to active ruleset")
    p_activate.add_argument("--assay-key", required=True)
    p_activate.add_argument("--draft-path", required=True)

    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]

    if args.cmd == "create-draft":
        print(create_draft(str(root), args.assay_key))
        return
    if args.cmd == "list-fields":
        print(json.dumps(list_fields(str(root), args.assay_key), indent=2, ensure_ascii=False))
        return
    if args.cmd == "set-regex":
        print(set_field_regex(args.draft_path, args.field_key, args.regex))
        return
    if args.cmd == "preview":
        out = preview_extract(str(root), args.pdf, args.assay_key, draft_path=args.draft_path)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    if args.cmd == "activate-draft":
        print(activate_draft(str(root), args.assay_key, args.draft_path))
