from __future__ import annotations

import argparse
import json
from pathlib import Path

from pypdf import PdfReader


def annotation_count(reader: PdfReader) -> int:
    return sum(len(page.get("/Annots", [])) for page in reader.pages)


def load_issues(path: Path | None) -> list[dict] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return payload["issues"]
    raise ValueError("issues JSON은 배열이거나 issues 배열을 포함한 객체여야 합니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="생기부 점검 표시본·총평본을 검증합니다.")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--marked", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--issues-json", type=Path)
    parser.add_argument("--require-text", action="append", default=[])
    args = parser.parse_args()

    for path in [args.source, args.marked, args.report, args.issues_json]:
        if path is not None and not path.is_file():
            parser.error(f"파일을 찾을 수 없습니다: {path}")

    marked = PdfReader(str(args.marked))
    report = PdfReader(str(args.report))
    source = PdfReader(str(args.source)) if args.source else None
    issues = load_issues(args.issues_json)

    marked_annotations = annotation_count(marked)
    source_annotations = annotation_count(source) if source else 0
    added_annotations = marked_annotations - source_annotations
    report_text = "\n".join(page.extract_text() or "" for page in report.pages)
    errors: list[str] = []

    if source and len(source.pages) != len(marked.pages):
        errors.append("원본과 표시본의 페이지 수가 다릅니다.")
    if not report.pages:
        errors.append("총평본에 페이지가 없습니다.")
    if added_annotations < 0:
        errors.append("표시본의 주석 수가 원본보다 적습니다.")
    if issues is not None:
        ids = [issue.get("id") for issue in issues if issue.get("id") is not None]
        if len(ids) != len(set(ids)):
            errors.append("issues JSON의 문제 ID가 중복됩니다.")
        if added_annotations != len(issues):
            errors.append(
                f"추가 주석 수({added_annotations})와 문제 수({len(issues)})가 다릅니다."
            )
    for required in args.require_text:
        if required not in report_text:
            errors.append(f"총평본에 필수 문구가 없습니다: {required}")

    result = {
        "status": "ok" if not errors else "failed",
        "source_pages": len(source.pages) if source else None,
        "marked_pages": len(marked.pages),
        "report_pages": len(report.pages),
        "source_annotations": source_annotations if source else None,
        "marked_annotations": marked_annotations,
        "added_annotations": added_annotations,
        "issue_count": len(issues) if issues is not None else None,
        "marked_bytes": args.marked.stat().st_size,
        "report_bytes": args.report.stat().st_size,
        "required_text": {text: text in report_text for text in args.require_text},
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
