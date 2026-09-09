#!/usr/bin/env python3
"""Lay confirmed issues onto the original PDF as highlight annotations.

The original page content is never redrawn. Re-typesetting would change line
breaks and make the marked copy impossible to compare against the record the
school actually holds, so this only adds transparent annotations on top.

Input: issues.json, a list of objects following the schema in SKILL.md step 3.
  Required: id, page, color, and either "bbox" (4 numbers) or "bboxes"
            (list of 4-number boxes, for a phrase that wraps across lines).
  Optional: student, field, original, suggestion, reason.
  Coordinates are native (unrotated) PDF points, exactly what
  extract_records.py writes and what PyMuPDF annotations expect.

Usage:
  python build_marked_pdf.py "종합일람표.pdf" --issues work/issues.json \
      --output "종합일람표_반복문구제외_점검표시본.pdf"
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pymupdf

# Legend from references/review-criteria.md. The colour says what to do next,
# not how severe the problem is.
COLORS = {
    "red": (1.00, 0.62, 0.62),
    "orange": (1.00, 0.80, 0.45),
    "yellow": (1.00, 0.95, 0.35),
    "purple": (0.85, 0.70, 1.00),
    "blue": (0.62, 0.80, 1.00),
}
LABELS = {
    "red": "반드시 수정",
    "orange": "확인 필요",
    "yellow": "다듬기 권장",
    "purple": "부정적 표현",
    "blue": "반복 문구",
}


def issue_rects(issue: dict) -> list[pymupdf.Rect]:
    if "bboxes" in issue:
        return [pymupdf.Rect(b) for b in issue["bboxes"]]
    if "bbox" in issue:
        return [pymupdf.Rect(issue["bbox"])]
    return []


def annotation_text(issue: dict) -> str:
    lines = []
    who = " · ".join(x for x in (issue.get("student"), issue.get("field")) if x)
    if who:
        lines.append(who)
    original, suggestion = issue.get("original"), issue.get("suggestion")
    if original and suggestion:
        lines.append(f"{original} → {suggestion}")
    elif original:
        lines.append(f"원문: {original}")
    if issue.get("reason"):
        lines.append(f"사유: {issue['reason']}")
    return "\n".join(lines)


def build(source: Path, issues: list[dict], output: Path, popup: bool) -> tuple[int, Counter]:
    doc = pymupdf.open(source)
    counts: Counter = Counter()
    added = 0

    for issue in issues:
        page_no = int(issue["page"])
        if not 1 <= page_no <= doc.page_count:
            print(f"[건너뜀] {issue.get('id')}: {page_no}쪽은 문서에 없음", file=sys.stderr)
            continue
        rects = issue_rects(issue)
        if not rects:
            print(f"[건너뜀] {issue.get('id')}: 좌표 없음", file=sys.stderr)
            continue

        page = doc[page_no - 1]
        clipped = [r for r in rects if r.intersects(page.rect) and not r.is_empty]
        if not clipped:
            print(f"[건너뜀] {issue.get('id')}: 좌표가 쪽 밖에 있음", file=sys.stderr)
            continue

        color_key = issue.get("color", "yellow")
        annot = page.add_highlight_annot(clipped)
        annot.set_colors(stroke=COLORS.get(color_key, COLORS["yellow"]))
        annot.set_info(
            title=f"[{LABELS.get(color_key, color_key)}] {issue.get('id', '')}".strip(),
            content=annotation_text(issue),
        )
        if popup:
            first = clipped[0]
            annot.set_popup(pymupdf.Rect(first.x1 + 4, first.y0,
                                         first.x1 + 210, first.y0 + 95))
        annot.update()
        added += 1
        counts[color_key] += 1

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output, garbage=3, deflate=True)
    doc.close()
    return added, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="확정된 문제를 원본 PDF 위에 형광펜 주석으로 얹는다")
    parser.add_argument("input", type=Path)
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-popup", action="store_true",
                        help="팝업 메모 상자를 만들지 않는다(주석 목록에는 그대로 보임)")
    args = parser.parse_args()

    for path in (args.input, args.issues):
        if not path.exists():
            print(f"[오류] 파일이 없습니다: {path}", file=sys.stderr)
            return 1

    issues = json.loads(args.issues.read_text(encoding="utf-8"))
    if isinstance(issues, dict):
        issues = issues.get("issues", [])

    ids = [i.get("id") for i in issues]
    duplicates = [i for i, n in Counter(ids).items() if n > 1]
    if duplicates:
        print(f"[오류] 중복된 문제 ID: {', '.join(map(str, duplicates))}", file=sys.stderr)
        return 1

    added, counts = build(args.input, issues, args.output, not args.no_popup)

    print(f"문제 {len(issues)}건 중 {added}건을 표시했습니다 -> {args.output}")
    for key in ("red", "orange", "yellow", "purple", "blue"):
        if counts.get(key):
            print(f"  {LABELS[key]}({key}): {counts[key]}건")
    if added != len(issues):
        print(f"[경고] 표시하지 못한 문제가 {len(issues) - added}건 있습니다. "
              f"총평의 '별도 확인 사항'에 남기세요.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
