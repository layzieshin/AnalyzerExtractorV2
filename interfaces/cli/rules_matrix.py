from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.assaychooser.api import detect_assays
from src.contentsplitter.api import AssayDescriptor, split_by_assay_name_and_key
from src.extractor.api import extract_record
from src.jobcontroller.api import submit
from src.normalizer.api import normalize_lines
from src.parser.api import parse
from src.ruleresolver.api import resolve_ruleset, validate_rules_integrity


DEFAULT_SAMPLE_PDFS = ("input/sample_single.pdf", "input/sample_multi.pdf")
STATUS_ORDER = {"green": 0, "yellow": 1, "red": 2}


def run_matrix(
    project_root: str | Path,
    pdfs: list[str | Path] | None = None,
    mode: str = "preview",
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project_root)
    if mode not in {"preview", "e2e"}:
        raise ValueError("mode must be preview or e2e")

    pdf_paths = [Path(p) for p in (pdfs or [root / rel for rel in DEFAULT_SAMPLE_PDFS])]
    pdf_paths = [p if p.is_absolute() else root / p for p in pdf_paths]
    index_path = root / "rules" / "index.json"
    rules_dir = root / "rules"

    assays = _load_index(index_path)
    integrity = validate_rules_integrity(str(rules_dir), str(index_path))
    rows: dict[str, dict[str, Any]] = {
        row["assay_key"]: {
            "assay_key": row["assay_key"],
            "ruleset_file": row["ruleset_file"],
            "assay_name": None,
            "status": "red",
            "issues": [],
            "dedupe_policy": "unknown",
            "pdf_results": [],
        }
        for row in assays
    }

    for pdf in pdf_paths:
        pdf_report = _analyze_pdf(root, pdf, mode)
        for result in pdf_report["assay_results"]:
            key = result["assay_key"]
            if key not in rows:
                continue
            rows[key]["pdf_results"].append(result)
            rows[key]["assay_name"] = rows[key]["assay_name"] or result.get("assay_name")
            if result.get("dedupe_policy") != "unknown":
                rows[key]["dedupe_policy"] = result["dedupe_policy"]

    for key, row in rows.items():
        detected_results = [r for r in row["pdf_results"] if r.get("detected")]
        if not detected_results:
            row["status"] = "red"
            row["issues"].append("not_detected_in_selected_pdfs")
            continue

        status = "green"
        issues: list[str] = []
        for result in detected_results:
            status = _worse(status, result["status"])
            issues.extend(result.get("issues", []))
        row["status"] = status
        row["issues"] = sorted(set(issues))

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(root),
        "mode": mode,
        "pdfs": [str(p) for p in pdf_paths],
        "rules_integrity_ok": not any(bool(value) for value in integrity.values()),
        "rules_integrity": integrity,
        "summary": _summarize(rows.values()),
        "assays": list(rows.values()),
    }

    if write_report:
        out_dir = root / "output" / "verification"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = out_dir / f"rule_matrix_{stamp}.json"
        md_path = out_dir / f"rule_matrix_{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(_render_markdown(report), encoding="utf-8")
        report["report_paths"] = {"json": str(json_path), "md": str(md_path)}

    return report


def _analyze_pdf(root: Path, pdf: Path, mode: str) -> dict[str, Any]:
    index_path = root / "rules" / "index.json"
    rules_dir = root / "rules"
    assays = _load_index(index_path)
    results = [_empty_pdf_result(row, pdf) for row in assays]
    by_key = {row["assay_key"]: row for row in results}

    if not pdf.exists():
        for row in results:
            row["status"] = "red"
            row["issues"].append("pdf_not_found")
        return {"pdf": str(pdf), "assay_results": results, "e2e_result": None}

    try:
        doc = parse(str(pdf))
        raw_lines = [line for page in doc.pages for line in page.lines]
        norm_text = "\n".join(normalize_lines(raw_lines))
        detected = detect_assays(norm_text, str(index_path))
        detected_keys = [match.assay_key for match in detected]
    except Exception as exc:
        for row in results:
            row["status"] = "red"
            row["issues"].append(f"pre_split_failed:{exc}")
        return {"pdf": str(pdf), "assay_results": results, "e2e_result": None}

    descriptors: list[AssayDescriptor] = []
    rulesets: dict[str, Any] = {}
    for key in detected_keys:
        if key not in by_key:
            continue
        by_key[key]["detected"] = True
        by_key[key]["criteria"]["detected"] = "green"
        try:
            ruleset = resolve_ruleset(key, str(rules_dir), str(index_path))
            rulesets[key] = ruleset
            assay_name = str(ruleset.data.get("assay_name", "")).strip()
            by_key[key]["assay_name"] = assay_name
            by_key[key]["dedupe_policy"] = _dedupe_policy(ruleset.data)
            descriptors.append(AssayDescriptor(assay_key=key, assay_name=assay_name))
        except Exception as exc:
            by_key[key]["status"] = "red"
            by_key[key]["issues"].append(f"resolve_failed:{exc}")

    blocks: dict[str, str] = {}
    if descriptors:
        try:
            blocks = split_by_assay_name_and_key(norm_text, descriptors)
        except Exception as exc:
            for descriptor in descriptors:
                row = by_key[descriptor.assay_key]
                row["criteria"]["block"] = "red"
                row["status"] = "red"
                row["issues"].append(f"split_failed:{exc}")

    for key, block in blocks.items():
        row = by_key[key]
        row["criteria"]["block"] = "green" if block.strip() else "red"
        if not block.strip():
            row["status"] = "red"
            row["issues"].append("empty_block")
            continue
        try:
            record = extract_record(block, rulesets[key])
            row["criteria"]["lot_id"] = "green" if record.lot_id else "red"
            row["criteria"]["required_fields"] = _required_status(rulesets[key].data, record.data)
            row["dedupe_policy"] = _dedupe_policy_from_record(record)
            row["criteria"]["dedupe"] = "green"
            row["lot_id"] = record.lot_id
            row["dedupe_key"] = record.dedupe_key
            row["dedupe_basis"] = record.dedupe_basis
            optional_missing = _optional_missing(rulesets[key].data, record.data)
            if optional_missing:
                row["optional_missing"] = optional_missing
                row["issues"].append("optional_fields_missing")
            row["status"] = _preview_row_status(row["criteria"], row["issues"])
        except Exception as exc:
            msg = str(exc)
            row["status"] = "red"
            if "lot_id not found" in msg:
                row["criteria"]["lot_id"] = "red"
            elif "required field not found" in msg:
                row["criteria"]["required_fields"] = "red"
            elif "dedupe basis missing" in msg:
                row["criteria"]["dedupe"] = "red"
                row["dedupe_policy"] = "missing"
                for field in _missing_dedupe_basis_fields(msg):
                    row["issues"].append(f"dedupe_basis_missing:{field}")
            elif "dedupe fields empty" in msg:
                row["criteria"]["dedupe"] = "red"
                row["dedupe_policy"] = "missing"
            row["issues"].append(f"extract_failed:{msg}")

    e2e_result = None
    if mode == "e2e":
        e2e_result = _run_e2e(root, pdf, by_key)

    return {"pdf": str(pdf), "assay_results": results, "e2e_result": e2e_result}


def _run_e2e(root: Path, pdf: Path, by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    res = submit(str(pdf), str(root))
    out = {
        "status": res.status,
        "job_id": res.job_id,
        "details": res.details,
    }
    writes = res.details.get("writes", []) if isinstance(res.details, dict) else []
    writes_by_key = {
        str(item.get("assay_key")): item
        for item in writes
        if isinstance(item, dict) and item.get("assay_key")
    }
    for key, row in by_key.items():
        if not row.get("detected"):
            continue
        if res.status == "DONE":
            write_item = writes_by_key.get(key)
            if not write_item:
                row["criteria"]["write"] = "red"
                row["status"] = "red"
                row["issues"].append("write_missing")
                continue
            statuses = [
                str(output.get("status", ""))
                for output in write_item.get("outputs", [])
                if isinstance(output, dict)
            ]
            if any(status == "failed" for status in statuses):
                row["criteria"]["write"] = "red"
                row["status"] = "red"
                row["issues"].append("write_failed")
            elif any(status == "skipped" for status in statuses):
                row["criteria"]["write"] = "yellow"
                row["status"] = _worse(row["status"], "yellow")
                row["issues"].append("write_skipped_dedupe")
            else:
                row["criteria"]["write"] = "green"
        elif res.status == "SKIPPED":
            row["criteria"]["write"] = "yellow"
            row["status"] = _worse(row["status"], "yellow")
            row["issues"].append(f"submit_skipped:{res.details.get('reason')}")
        else:
            row["criteria"]["write"] = "red"
            row["status"] = "red"
            row["issues"].append(f"submit_failed:{res.details.get('error')}")
    return out


def _empty_pdf_result(index_row: dict[str, str], pdf: Path) -> dict[str, Any]:
    return {
        "pdf": str(pdf),
        "assay_key": index_row["assay_key"],
        "ruleset_file": index_row["ruleset_file"],
        "assay_name": None,
        "detected": False,
        "status": "red",
        "criteria": {
            "detected": "red",
            "block": "not_run",
            "lot_id": "not_run",
            "required_fields": "not_run",
            "dedupe": "not_run",
            "write": "not_run",
        },
        "dedupe_policy": "unknown",
        "issues": [],
    }


def _load_index(index_path: Path) -> list[dict[str, str]]:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    assays = data.get("assays", [])
    if not isinstance(assays, list):
        raise ValueError("index.assays must be a list")
    out: list[dict[str, str]] = []
    for row in assays:
        if not isinstance(row, dict):
            continue
        key = str(row.get("assay_key", "")).strip()
        file_name = str(row.get("ruleset_file", "")).strip()
        if key and file_name:
            out.append({"assay_key": key, "ruleset_file": file_name})
    return out


def _dedupe_policy(ruleset_data: dict[str, Any]) -> str:
    dedupe = ruleset_data.get("extract_rules", {}).get("dedupe_fields")
    return "explicit_legacy" if isinstance(dedupe, list) and bool(dedupe) else "v2_default"


def _dedupe_policy_from_record(record: Any) -> str:
    version = str(getattr(record, "dedupe_version", "") or "")
    if version == "explicit_legacy":
        return "explicit_legacy"
    if version == "v2":
        return "v2_default"
    return "unknown"


def _missing_dedupe_basis_fields(message: str) -> list[str]:
    marker = "dedupe basis missing:"
    if marker not in message:
        return []
    raw = message.split(marker, 1)[1]
    return [field.strip() for field in raw.split(",") if field.strip()]


def _required_status(ruleset_data: dict[str, Any], data: dict[str, Any]) -> str:
    fields = ruleset_data.get("extract_rules", {}).get("fields", [])
    missing = []
    for field in fields:
        if not isinstance(field, dict) or not field.get("required"):
            continue
        key = str(field.get("key", "")).strip()
        value = data.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
    return "red" if missing else "green"


def _optional_missing(ruleset_data: dict[str, Any], data: dict[str, Any]) -> list[str]:
    fields = ruleset_data.get("extract_rules", {}).get("fields", [])
    missing = []
    for field in fields:
        if not isinstance(field, dict) or field.get("required"):
            continue
        key = str(field.get("key", "")).strip()
        value = data.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
    return missing


def _criteria_status(criteria: dict[str, str]) -> str:
    status = "green"
    for value in criteria.values():
        if value in {"not_run"}:
            continue
        status = _worse(status, value)
    return status


def _preview_row_status(criteria: dict[str, str], issues: list[str]) -> str:
    status = _criteria_status(criteria)
    if status == "green" and "optional_fields_missing" in issues:
        return "yellow"
    return status


def _worse(left: str, right: str) -> str:
    return left if STATUS_ORDER.get(left, 2) >= STATUS_ORDER.get(right, 2) else right


def _summarize(rows: Any) -> dict[str, int]:
    summary = {"green": 0, "yellow": 0, "red": 0}
    for row in rows:
        summary[row["status"]] += 1
    return summary


def _render_console(report: dict[str, Any]) -> str:
    lines = [
        f"Rule matrix ({report['mode']})",
        f"root: {report['project_root']}",
        f"summary: green={report['summary']['green']} yellow={report['summary']['yellow']} red={report['summary']['red']}",
        "",
        f"{'STATUS':<7} {'ASSAY':<8} {'DEDUPE':<8} ISSUES",
        "-" * 78,
    ]
    for row in report["assays"]:
        issues = ", ".join(row.get("issues", []))
        lines.append(f"{row['status']:<7} {row['assay_key']:<8} {row['dedupe_policy']:<8} {issues}")
    if report.get("report_paths"):
        lines.append("")
        lines.append(f"json: {report['report_paths']['json']}")
        lines.append(f"md:   {report['report_paths']['md']}")
    return "\n".join(lines)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Rule Pipeline Verification Matrix",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Rules integrity OK: `{report['rules_integrity_ok']}`",
        f"- Summary: green={report['summary']['green']}, yellow={report['summary']['yellow']}, red={report['summary']['red']}",
        "",
        "| Status | Assay | Ruleset | Dedupe | Issues |",
        "|---|---|---|---|---|",
    ]
    for row in report["assays"]:
        issues = "<br>".join(row.get("issues", []))
        lines.append(
            f"| {row['status']} | `{row['assay_key']}` | `{row['ruleset_file']}` | "
            f"{row['dedupe_policy']} | {issues} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify active rules against sample PDFs")
    parser.add_argument("--mode", choices=["preview", "e2e"], default="preview")
    parser.add_argument("--pdf", action="append", help="PDF path; may be repeated. Defaults to sample PDFs.")
    parser.add_argument("--no-write-report", action="store_true", help="Print only; do not write output/verification files.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    report = run_matrix(root, pdfs=args.pdf, mode=args.mode, write_report=not args.no_write_report)
    print(_render_console(report))
    if report["summary"]["red"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
