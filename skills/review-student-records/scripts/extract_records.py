#!/usr/bin/env python3
"""Extract per-student, per-field records from a 종합일람표 PDF.

The table structure is recovered from the drawn rules rather than guessed from
text positions, because the prose columns are packed edge to edge and give no
usable whitespace signal. Word-level coordinates are preserved so later steps
can anchor annotations on real evidence instead of re-searching the page.

Outputs (into --outdir):
  records.json  machine readable, keeps every word box
  records.txt   human readable, for eyeballing the extraction
  meta.json     document scope: pages, students, columns, field names

Usage:
  python extract_records.py "종합일람표.pdf" --outdir work
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

# A horizontal rule counts as a row boundary when it is nearly as long as the
# longest one on the page, i.e. it spans the whole table.
ROW_RATIO = 0.55
# A vertical rule counts as a column boundary when it crosses the header band
# almost completely. Measuring inside the header rather than over the whole
# page keeps the last page working, where the table body may be short and the
# outer border alone would otherwise dominate.
COLUMN_RATIO = 0.80
# Two rules within this distance are the same rule drawn in several pieces.
MERGE_TOLERANCE = 1.2


def rules(page) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Return (vertical, horizontal) rules as (position, start, end) triples.

    get_drawings() reports native (unrotated) coordinates, so on a /Rotate 90
    page the rules are laid out sideways. Everything is pushed through the
    rotation matrix here so that "vertical" really means a column divider as a
    reader sees it. visual_words() maps text the same way, keeping both in one
    frame. Skipping this silently swaps the two axes.
    """
    matrix = page.rotation_matrix
    vertical: list[tuple[float, float, float]] = []
    horizontal: list[tuple[float, float, float]] = []

    def add(a: pymupdf.Point, b: pymupdf.Point) -> None:
        a, b = a * matrix, b * matrix
        if abs(a.x - b.x) < 0.6:
            vertical.append((round(a.x, 1), min(a.y, b.y), max(a.y, b.y)))
        elif abs(a.y - b.y) < 0.6:
            horizontal.append((round(a.y, 1), min(a.x, b.x), max(a.x, b.x)))

    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                add(item[1], item[2])
            elif item[0] == "re":
                r = item[1]
                add(pymupdf.Point(r.x0, r.y0), pymupdf.Point(r.x1, r.y0))
                add(pymupdf.Point(r.x0, r.y1), pymupdf.Point(r.x1, r.y1))
                add(pymupdf.Point(r.x0, r.y0), pymupdf.Point(r.x0, r.y1))
                add(pymupdf.Point(r.x1, r.y0), pymupdf.Point(r.x1, r.y1))
    return vertical, horizontal


def merge_close(values: list[float], tolerance: float = MERGE_TOLERANCE) -> list[float]:
    """Collapse coordinates that describe the same rule."""
    out: list[float] = []
    for value in sorted(values):
        if out and value - out[-1] <= tolerance:
            out[-1] = (out[-1] + value) / 2
        else:
            out.append(value)
    return out


def total_length(segments: list[tuple[float, float, float]]) -> dict[float, float]:
    acc: dict[float, float] = defaultdict(float)
    for pos, start, end in segments:
        acc[pos] += end - start
    return acc


def row_bounds(horizontal: list[tuple[float, float, float]]) -> list[float]:
    acc = total_length(horizontal)
    if not acc:
        return []
    longest = max(acc.values())
    return merge_close([y for y, length in acc.items() if length >= longest * ROW_RATIO])


def column_bounds(vertical: list[tuple[float, float, float]],
                  top: float, bottom: float) -> list[float]:
    """Column rules are the vertical lines that cross the header band."""
    band = bottom - top
    if band <= 0:
        return []
    acc: dict[float, float] = defaultdict(float)
    for pos, start, end in vertical:
        overlap = min(end, bottom) - max(start, top)
        if overlap > 0:
            acc[pos] += overlap
    return merge_close([x for x, length in acc.items() if length >= band * COLUMN_RATIO])


def visual_words(page) -> list[tuple]:
    """Words in display space, carrying their native rect for annotation use.

    get_text() and get_drawings() both report native (unrotated) coordinates,
    and annotations are placed in native coordinates too. Reasoning about rows
    and columns is far easier in display space, so words are mapped forward for
    the logic and their native rect is kept at index 8 for output.
    """
    matrix = page.rotation_matrix
    out = []
    for w in page.get_text("words"):
        native = pymupdf.Rect(w[:4])
        r = native * matrix
        out.append((r.x0, r.y0, r.x1, r.y1, w[4], w[5], w[6], w[7], native))
    return out


def words_in(words: list[tuple], x0: float, x1: float, y0: float, y1: float) -> list[tuple]:
    """Words whose centre falls inside the box. Centres avoid double counting
    glyphs that straddle a rule by a fraction of a point."""
    out = []
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            out.append(w)
    return out


def cell_text(cell_words: list[tuple]) -> str:
    """Join words back into lines, preserving reading order."""
    if not cell_words:
        return ""
    lines: dict[int, list[tuple]] = defaultdict(list)
    for w in cell_words:
        lines[round(w[1] / 2)].append(w)
    parts = []
    for key in sorted(lines):
        row = sorted(lines[key], key=lambda w: w[0])
        parts.append(" ".join(w[4] for w in row))
    return "\n".join(parts)


def header_labels(page, columns: list[float], label_top: float, bottom: float) -> list[str]:
    """Read column labels from the lower header row.

    The header has two rows: group titles (창의적 체험활동, 출결 상황) on top and
    the per-column labels below. Reading the whole band would prefix every
    grouped column with its group title, so start below the group rule when
    one exists.
    """
    words = visual_words(page)
    labels = []
    for i in range(len(columns) - 1):
        cell = words_in(words, columns[i], columns[i + 1], label_top, bottom)
        text = re.sub(r"\s+", " ", cell_text(cell).replace("\n", " ")).strip()
        labels.append(text or f"열{i + 1}")
    return labels


def extract(pdf: Path, number_column: int, name_column: int, header_line: int) -> dict:
    doc = pymupdf.open(pdf)
    first_columns: list[float] = []
    labels: list[str] = []
    students: list[dict] = []
    current: dict | None = None
    warnings: list[str] = []

    for pno, page in enumerate(doc, start=1):
        vertical, horizontal = rules(page)
        rows = row_bounds(horizontal)
        # The header's middle rule only spans the merged groups, so it is not a
        # full-width row boundary. The first full-width rule below the table top
        # is therefore the header bottom.
        if len(rows) <= header_line:
            warnings.append(f"{pno}쪽: 표 가로선을 찾지 못해 건너뜀")
            continue
        table_top, header_bottom = rows[0], rows[header_line]
        # Group dividers (창의적 체험활동, 출결 상황) only start at the group rule,
        # so measure column coverage over the lower header row where every
        # divider is present.
        inner = [y for y, _s, _e in horizontal if table_top + 0.5 < y < header_bottom - 0.5]
        label_top = max(inner) if inner else table_top
        columns = column_bounds(vertical, label_top, header_bottom)
        if len(columns) < 3:
            warnings.append(f"{pno}쪽: 표 세로선을 찾지 못해 건너뜀")
            continue

        if not first_columns:
            first_columns = columns
            labels = header_labels(page, columns, label_top, header_bottom)
        elif len(columns) != len(first_columns):
            warnings.append(
                f"{pno}쪽: 열 개수가 {len(columns) - 1}개로 1쪽({len(first_columns) - 1}개)과 다름")

        words = visual_words(page)
        bounds = [header_bottom] + [y for y in rows if y > header_bottom + 0.5]
        for row_top, row_bottom in zip(bounds, bounds[1:]):
            row_words = words_in(words, columns[0], columns[-1], row_top, row_bottom)
            if not row_words:
                continue
            number_cell = words_in(row_words, columns[number_column],
                                   columns[number_column + 1], row_top, row_bottom)
            starts_student = any(w[4].strip().isdigit() for w in number_cell)

            if starts_student or current is None:
                name_cell = words_in(row_words, columns[name_column],
                                     columns[name_column + 1], row_top, row_bottom)
                current = {
                    "index": len(students) + 1,
                    "number": " ".join(w[4] for w in number_cell).strip(),
                    "name": " ".join(w[4] for w in name_cell).strip(),
                    "pages": [],
                    "fields": {},
                }
                students.append(current)

            if pno not in current["pages"]:
                current["pages"].append(pno)

            for ci in range(len(columns) - 1):
                label = labels[ci] if ci < len(labels) else f"열{ci + 1}"
                cell = words_in(row_words, columns[ci], columns[ci + 1], row_top, row_bottom)
                if not cell:
                    continue
                field = current["fields"].setdefault(label, {"text": "", "words": []})
                chunk = cell_text(cell)
                field["text"] = f"{field['text']}\n{chunk}".strip() if field["text"] else chunk
                field["words"].extend(
                    {"page": pno, "bbox": [round(v, 2) for v in w[8]], "text": w[4]}
                    for w in sorted(cell, key=lambda w: (round(w[1] / 2), w[0]))
                )

    meta = {
        "source": pdf.name,
        "pages": doc.page_count,
        "page_size": [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)],
        "rotation": doc[0].rotation,
        "columns": [round(c, 1) for c in first_columns],
        "field_names": labels,
        "student_count": len(students),
        "warnings": warnings,
    }
    doc.close()
    return {"meta": meta, "students": students}


def write_text_dump(data: dict, path: Path) -> None:
    lines = [f"# {data['meta']['source']} 추출 결과",
             f"# 쪽수 {data['meta']['pages']} / 학생 {data['meta']['student_count']}명", ""]
    for student in data["students"]:
        pages = ", ".join(str(p) for p in student["pages"])
        lines.append("=" * 78)
        lines.append(f"[{student['index']}] 번호 {student['number'] or '-'} "
                     f"성명 {student['name'] or '-'}  (쪽: {pages})")
        lines.append("=" * 78)
        for label, field in student["fields"].items():
            body = field["text"].strip()
            if not body:
                continue
            lines.append(f"--- {label} ---")
            lines.append(body)
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="종합일람표 PDF에서 학생별·영역별 기록을 추출한다")
    parser.add_argument("input", type=Path)
    parser.add_argument("--outdir", type=Path, default=Path("work"))
    parser.add_argument("--number-column", type=int, default=0,
                        help="번호가 들어 있는 열 번호(0부터). 기본 0")
    parser.add_argument("--name-column", type=int, default=1,
                        help="성명이 들어 있는 열 번호(0부터). 기본 1")
    parser.add_argument("--header-line", type=int, default=1,
                        help="머리글 하단에 해당하는 가로 구조선 번호(0부터). 기본 1")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"[오류] 파일이 없습니다: {args.input}", file=sys.stderr)
        return 1

    data = extract(args.input, args.number_column, args.name_column, args.header_line)
    args.outdir.mkdir(parents=True, exist_ok=True)

    (args.outdir / "records.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.outdir / "meta.json").write_text(
        json.dumps(data["meta"], ensure_ascii=False, indent=2), encoding="utf-8")
    write_text_dump(data, args.outdir / "records.txt")

    meta = data["meta"]
    print(f"쪽수 {meta['pages']} / 회전 {meta['rotation']}도 / 열 {len(meta['columns']) - 1}개")
    print(f"학생 {meta['student_count']}명")
    print("열 이름: " + " | ".join(meta["field_names"]))
    for warning in meta["warnings"]:
        print(f"[주의] {warning}")
    print(f"저장: {args.outdir / 'records.json'}, records.txt, meta.json")
    print("→ 열 이름과 학생 수가 눈으로 본 것과 맞는지 반드시 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
