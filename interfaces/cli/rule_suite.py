from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.rulesuite.api import (
    activate_draft,
    activate_new_draft,
    check_authoring_readiness,
    check_required_fields,
    create_draft,
    get_assay_text,
    list_fields,
    locate_fields,
    load_draft,
    preview_extract,
    set_field_regex,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_assay_text(args: argparse.Namespace, root: Path) -> str | None:
    if getattr(args, "assay_text", None):
        return str(args.assay_text)
    pdf = getattr(args, "pdf", None)
    assay_key = getattr(args, "assay_key", None)
    if not pdf or not assay_key:
        return None
    assay_name = getattr(args, "assay_name", None)
    if not assay_name and getattr(args, "draft_path", None):
        data = load_draft(args.draft_path)
        assay_name = str(data.get("assay_name", "")).strip()
    if not assay_name:
        raise SystemExit("--assay-name erforderlich wenn --pdf ohne Draft mit assay_name")
    draft_path = getattr(args, "draft_path", None)
    block = get_assay_text(
        str(root),
        pdf,
        assay_key,
        assay_name,
        draft_path=draft_path,
    )
    return str(block.get("assay_block", ""))


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

    p_activate = sub.add_parser("activate-draft", help="Promote draft to existing active ruleset")
    p_activate.add_argument("--assay-key", required=True)
    p_activate.add_argument("--draft-path", required=True)

    p_activate_new = sub.add_parser("activate-new-draft", help="Promote draft to new ruleset + index entry")
    p_activate_new.add_argument("--assay-key", required=True)
    p_activate_new.add_argument("--assay-name", required=True)
    p_activate_new.add_argument("--draft-path", required=True)

    for name, help_text in (
        ("readiness", "Structural + optional required-field readiness check"),
        ("check-required", "Required header fields against assay text (alias for focused check)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--draft-path", required=True)
        p.add_argument("--assay-text")
        p.add_argument("--pdf")
        p.add_argument("--assay-key")
        p.add_argument("--assay-name")

    p_locate = sub.add_parser("locate-field", help="Locate field regex matches in assay text")
    p_locate.add_argument("--draft-path", required=True)
    p_locate.add_argument("--assay-text")
    p_locate.add_argument("--pdf")
    p_locate.add_argument("--assay-key")
    p_locate.add_argument("--assay-name")
    p_locate.add_argument("--field-key", help="Optional single field key to filter")

    args = parser.parse_args()
    root = _project_root()

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
        try:
            out = preview_extract(str(root), args.pdf, args.assay_key, draft_path=args.draft_path)
        except Exception as e:
            print(json.dumps({"error": str(e)}, indent=2, ensure_ascii=False), file=sys.stderr)
            raise SystemExit(1) from e
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    if args.cmd == "activate-draft":
        print(activate_draft(str(root), args.assay_key, args.draft_path))
        return
    if args.cmd == "activate-new-draft":
        print(activate_new_draft(str(root), args.assay_key, args.assay_name, args.draft_path))
        return
    if args.cmd == "readiness":
        text = _resolve_assay_text(args, root)
        out = check_authoring_readiness(args.draft_path, text)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if not out.get("ok"):
            raise SystemExit(1)
        return
    if args.cmd == "check-required":
        text = _resolve_assay_text(args, root)
        if not (text or "").strip():
            print(
                json.dumps(
                    {"error": "assay_text_required: --assay-text oder --pdf mit --assay-key/--assay-name"},
                    indent=2,
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            raise SystemExit(1)
        out = check_required_fields(args.draft_path, text)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if not out.get("all_confirmed"):
            raise SystemExit(1)
        return
    if args.cmd == "locate-field":
        text = _resolve_assay_text(args, root)
        if not (text or "").strip():
            print(
                json.dumps(
                    {"error": "assay_text_required: --assay-text oder --pdf mit --assay-key/--assay-name"},
                    indent=2,
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            raise SystemExit(1)
        out = locate_fields(args.draft_path, text)
        if args.field_key:
            key = args.field_key.strip()
            out = {
                **out,
                "results": [r for r in out.get("results", []) if r.get("key") == key],
            }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
