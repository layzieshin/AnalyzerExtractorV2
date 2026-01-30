from __future__ import annotations

from pathlib import Path

from src.jobcontroller.api import submit


def main() -> None:
    project_root = str(Path(__file__).resolve().parent)
    input_dir = Path(project_root) / "input"
    pdfs = [input_dir / "sample_single.pdf", input_dir / "sample_multi.pdf"]

    for pdf in pdfs:
        print("=" * 50)
        print(f"JOB: {pdf.name}")
        print("=" * 50)
        res = submit(str(pdf), project_root)
        print(f"status: {res.status}")
        print(f"job_id: {res.job_id}")
        print(f"pdf_path: {res.pdf_path}")
        if res.details:
            for k, v in res.details.items():
                print(f"{k}: {v}")
        print()

if __name__ == "__main__":
    main()
