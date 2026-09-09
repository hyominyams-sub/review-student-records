#!/usr/bin/env python3
"""Build the standalone A4 review summary (총평본) from confirmed issues.

The summary travels separately from the marked copy, so it repeats as little
student text as possible: quotes are trimmed to what is needed to recognise the
spot. It also states plainly what was NOT checked, because a reviewer who
cannot see the exclusions will read silence as "nothing wrong here".

Inputs:
  --issues  issues.json  (same file build_marked_pdf.py consumes)
  --meta    meta.json    (optional; extra keys below are read when present)

meta.json keys used here (all optional):
  source, pages, student_count      document scope
  basis_date                        문서 작성 기준일
  officer_start, officer_end        임원 임기. officer_end 가 없으면 "확인 필요"로 적는다
  repeated_phrases                  true 면 반복 문구를 검사했다는 뜻
  guideline                         적용한 기재요령·길라잡이
  excluded                          검사에서 제외한 범위 (문자열 목록)
  unmarked                          표시본에 표기하지 못한 항목 (문자열 목록)

Usage:
  python build_report_pdf.py --issues work/issues.json --meta work/meta.json \
      --output "종합일람표_반복문구제외_점검총평.pdf" --markdown 총평.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\malgun.ttf", None),
    (r"C:\Windows\Fonts\gulim.ttc", 0),
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
    ("/Library/Fonts/AppleGothic.ttf", None),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", None),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0),
]

ORDER = ["red", "orange", "yellow", "purple", "blue"]
LABELS = {
    "red": "반드시 수정",
    "orange": "확인 필요",
    "yellow": "다듬기 권장",
    "purple": "부정적 표현",
    "blue": "반복 문구",
}
SWATCH = {
    "red": colors.HexColor("#FF9E9E"),
    "orange": colors.HexColor("#FFCC73"),
    "yellow": colors.HexColor("#FFF259"),
    "purple": colors.HexColor("#D9B3FF"),
    "blue": colors.HexColor("#9ECCFF"),
}


def register_font(explicit: Path | None) -> str:
    """Find a Korean-capable TTF. Without one every glyph renders as a box."""
    candidates = ([(str(explicit), None)] if explicit else []) + FONT_CANDIDATES
    for path, index in candidates:
        if not Path(path).exists():
            continue
        try:
            font = (TTFont("KR", path, subfontIndex=index) if index is not None
                    else TTFont("KR", path))
            pdfmetrics.registerFont(font)
            return "KR"
        except Exception:
            continue
    raise SystemExit(
        "[오류] 한글 글꼴을 찾지 못했습니다. --font 로 TTF/TTC 경로를 지정하세요.\n"
        "  예: --font C:\\Windows\\Fonts\\malgun.ttf")


def clip(text: str, limit: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def styles(font: str) -> dict:
    return {
        "title": ParagraphStyle("t", fontName=font, fontSize=17, leading=23, spaceAfter=4),
        "sub": ParagraphStyle("s", fontName=font, fontSize=9, leading=14,
                              textColor=colors.HexColor("#555555"), spaceAfter=12),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=12.5, leading=18,
                             spaceBefore=14, spaceAfter=6,
                             textColor=colors.HexColor("#1A3D6D")),
        "h3": ParagraphStyle("h3", fontName=font, fontSize=10, leading=15,
                             spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("b", fontName=font, fontSize=9, leading=14),
        "cell": ParagraphStyle("c", fontName=font, fontSize=8, leading=11.5),
        "note": ParagraphStyle("n", fontName=font, fontSize=8.5, leading=13,
                               textColor=colors.HexColor("#A02020")),
    }


def table(rows, widths, font, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")))
    t.setStyle(TableStyle(style))
    return t


def overview(story, st, meta, issues, counts, font):
    repeated = bool(meta.get("repeated_phrases"))
    officer_end = meta.get("officer_end") or "종료일 확인 필요"
    rows = [
        ["항목", "내용"],
        ["대상 문서", clip(meta.get("source", "-"), 60)],
        ["쪽수 / 학생 수", f"{meta.get('pages', '-')}쪽 / {meta.get('student_count', '-')}명"],
        ["문서 작성 기준일", meta.get("basis_date") or "미확인"],
        ["적용 기준", clip(meta.get("guideline", "학교생활기록부 기재요령"), 60)],
        ["임원 시작일", meta.get("officer_start") or "03.01."],
        ["임원 종료일", officer_end],
        ["반복 문구 검사", "포함" if repeated else "제외"],
        ["확정 문제", f"{len(issues)}건"],
    ]
    story.append(table(rows, [38 * mm, 128 * mm], font))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("색상별 건수", st["h3"]))
    head = [["색", "구분", "건수"]]
    body = [["", LABELS[k], str(counts.get(k, 0))] for k in ORDER if counts.get(k)]
    if not body:
        body = [["", "확정된 문제 없음", "0"]]
    t = table(head + body, [12 * mm, 60 * mm, 20 * mm], font)
    for i, key in enumerate([k for k in ORDER if counts.get(k)], start=1):
        t.setStyle(TableStyle([("BACKGROUND", (0, i), (0, i), SWATCH[key])]))
    story.append(t)

    if not repeated:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph("※ 반복 문구 검사는 제외했습니다. "
                               "학생 간 동일·유사 문장은 오류로 집계하지 않았습니다.", st["note"]))


def issue_table(rows_src, st, font):
    head = [["ID", "학생", "영역", "쪽", "원문 → 제안", "사유"]]
    rows = [head[0]] + [[
        i.get("id", ""),
        Paragraph(clip(i.get("student", ""), 20), st["cell"]),
        Paragraph(clip(i.get("field", ""), 20), st["cell"]),
        str(i.get("page", "")),
        Paragraph(f"{clip(i.get('original', ''), 45)} → {clip(i.get('suggestion', ''), 45)}",
                  st["cell"]),
        Paragraph(clip(i.get("reason", ""), 60), st["cell"]),
    ] for i in rows_src]
    return table(rows, [14 * mm, 22 * mm, 26 * mm, 8 * mm, 56 * mm, 40 * mm], font)


def build(issues, meta, output: Path, font: str, st: dict) -> None:
    counts = Counter(i.get("color", "yellow") for i in issues)
    doc = SimpleDocTemplate(str(output), pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title="생활기록부 점검 총평")
    story = []
    story.append(Paragraph("생활기록부 점검 총평", st["title"]))
    story.append(Paragraph("종합일람표를 학생별·영역별로 점검한 결과입니다. "
                           "표시본 PDF와 함께 보십시오.", st["sub"]))
    overview(story, st, meta, issues, counts, font)

    for key in ORDER:
        group = [i for i in issues if i.get("color", "yellow") == key]
        if not group:
            continue
        story.append(PageBreak())
        story.append(Paragraph(f"{LABELS[key]} ({len(group)}건)", st["h2"]))
        story.append(issue_table(group, st, font))

    by_student = defaultdict(list)
    for i in issues:
        by_student[i.get("student") or "(학생 미지정)"].append(i)
    if by_student:
        story.append(PageBreak())
        story.append(Paragraph("학생별 상세", st["h2"]))
        for student in sorted(by_student):
            block = [Paragraph(f"{student} — {len(by_student[student])}건", st["h3"]),
                     issue_table(by_student[student], st, font),
                     Spacer(1, 3 * mm)]
            story.append(KeepTogether(block))

    unmarked = meta.get("unmarked") or []
    excluded = meta.get("excluded") or []
    if unmarked or excluded:
        story.append(PageBreak())
    if unmarked:
        story.append(Paragraph("별도 확인 사항 (표시본에 표기하지 못한 항목)", st["h2"]))
        for line in unmarked:
            story.append(Paragraph(f"• {line}", st["body"]))
    if excluded:
        story.append(Paragraph("검사 제외 범위", st["h2"]))
        for line in excluded:
            story.append(Paragraph(f"• {line}", st["body"]))

    doc.build(story)


def write_markdown(issues, meta, path: Path) -> None:
    counts = Counter(i.get("color", "yellow") for i in issues)
    repeated = bool(meta.get("repeated_phrases"))
    lines = ["# 생활기록부 점검 총평", "",
             f"- 대상: {meta.get('source', '-')} ({meta.get('pages', '-')}쪽, "
             f"학생 {meta.get('student_count', '-')}명)",
             f"- 문서 작성 기준일: {meta.get('basis_date') or '미확인'}",
             f"- 임원 시작일: {meta.get('officer_start') or '03.01.'} / "
             f"종료일: {meta.get('officer_end') or '종료일 확인 필요'}",
             f"- 반복 문구 검사: {'포함' if repeated else '제외'}",
             f"- 확정 문제: {len(issues)}건", ""]
    for key in ORDER:
        group = [i for i in issues if i.get("color", "yellow") == key]
        if not group:
            continue
        lines += [f"## {LABELS[key]} ({counts[key]}건)", "",
                  "| ID | 학생 | 영역 | 쪽 | 원문 → 제안 | 사유 |",
                  "|---|---|---|---:|---|---|"]
        for i in group:
            lines.append(
                f"| {i.get('id','')} | {clip(i.get('student',''),20)} | "
                f"{clip(i.get('field',''),20)} | {i.get('page','')} | "
                f"{clip(i.get('original',''),45)} → {clip(i.get('suggestion',''),45)} | "
                f"{clip(i.get('reason',''),60)} |")
        lines.append("")
    for title, key in (("별도 확인 사항", "unmarked"), ("검사 제외 범위", "excluded")):
        if meta.get(key):
            lines += [f"## {title}", ""] + [f"- {x}" for x in meta[key]] + [""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="확정된 문제로 A4 점검 총평본을 만든다")
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--meta", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, help="같은 내용을 Markdown 으로도 저장")
    parser.add_argument("--font", type=Path, help="한글 TTF/TTC 경로")
    args = parser.parse_args()

    if not args.issues.exists():
        print(f"[오류] 파일이 없습니다: {args.issues}", file=sys.stderr)
        return 1
    issues = json.loads(args.issues.read_text(encoding="utf-8"))
    if isinstance(issues, dict):
        issues = issues.get("issues", [])
    meta = json.loads(args.meta.read_text(encoding="utf-8")) if args.meta and args.meta.exists() else {}

    font = register_font(args.font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    build(issues, meta, args.output, font, styles(font))
    print(f"총평본 생성: {args.output}  (문제 {len(issues)}건)")
    if args.markdown:
        write_markdown(issues, meta, args.markdown)
        print(f"Markdown 사본: {args.markdown}")
    if not meta.get("officer_end"):
        print("[주의] 임원 종료일 근거가 없어 '종료일 확인 필요'로 적었습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
