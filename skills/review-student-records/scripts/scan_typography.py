from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pdfplumber


SUBJECTS = "국어|도덕|사회|수학|과학|실과|체육|음악|미술|영어"


def group_lines(words: list[dict], tolerance: float = 2.0) -> list[list[dict]]:
    lines: dict[float, list[dict]] = defaultdict(list)
    for word in words:
        key = round(float(word["top"]) / tolerance) * tolerance
        lines[key].append(word)
    return [sorted(line, key=lambda item: item["x0"]) for _, line in sorted(lines.items())]


def split_columns(line: list[dict], break_gap: float) -> list[list[dict]]:
    if not line:
        return []
    groups = [[line[0]]]
    for left, right in zip(line, line[1:]):
        if float(right["x0"]) - float(left["x1"]) >= break_gap:
            groups.append([])
        groups[-1].append(right)
    return [group for group in groups if group]


def bbox(words: Iterable[dict]) -> list[float]:
    items = list(words)
    return [
        round(min(float(item["x0"]) for item in items), 2),
        round(min(float(item["top"]) for item in items), 2),
        round(max(float(item["x1"]) for item in items), 2),
        round(max(float(item["bottom"]) for item in items), 2),
    ]


def line_text(line: list[dict]) -> str:
    return " ".join(str(item["text"]) for item in line)


def parse_column_ranges(values: list[str] | None) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for value in values or []:
        try:
            left_text, right_text = value.split(":", 1)
            left, right = float(left_text), float(right_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"열 범위는 x0:x1 형식이어야 합니다: {value}"
            ) from exc
        if left < 0 or right <= left:
            raise argparse.ArgumentTypeError(f"잘못된 열 범위입니다: {value}")
        ranges.append((left, right))
    return ranges


def add_candidate(candidates: list[dict], seen: set[tuple], candidate: dict) -> None:
    box = tuple(round(float(value), 1) for value in candidate["bbox"])
    key = (candidate["kind"], candidate["page"], box, candidate["text"])
    if key not in seen:
        seen.add(key)
        candidates.append(candidate)


def scan_page(page, page_number: int, args) -> list[dict]:
    words = [
        word
        for word in page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
        if page.height * args.top_margin <= float(word["top"])
        <= page.height * (1 - args.bottom_margin)
    ]
    if args.parsed_column_ranges:
        column_word_sets = [
            [word for word in words if left <= float(word["x0"]) < right]
            for left, right in args.parsed_column_ranges
        ]
    else:
        column_word_sets = [words]
    column_segments = [
        [
            group
            for line in group_lines(column_words, args.line_tolerance)
            for group in split_columns(line, args.column_break_gap)
            if len(group) >= 1
        ]
        for column_words in column_word_sets
    ]
    segments = [segment for column in column_segments for segment in column]

    ordinary_gaps: list[float] = []
    for segment in segments:
        for left, right in zip(segment, segment[1:]):
            gap = float(right["x0"]) - float(left["x1"])
            if 1.0 <= gap <= args.baseline_max_gap:
                ordinary_gaps.append(gap)
    page_baseline = statistics.median(ordinary_gaps) if ordinary_gaps else 0.0

    candidates: list[dict] = []
    seen: set[tuple] = set()
    for segment in segments:
        text = line_text(segment)
        gaps = [
            float(right["x0"]) - float(left["x1"])
            for left, right in zip(segment, segment[1:])
        ]
        local = [gap for gap in gaps if 1.0 <= gap <= args.baseline_max_gap]
        # Use the line/column segment itself as the primary spacing baseline.
        # A page-wide baseline over-flags justified Korean text whose normal
        # inter-word spacing differs by line. Fall back only for punctuation-
        # only segments that have no ordinary gap at all.
        baseline = statistics.median(local) if local else page_baseline
        # A fixed point threshold is font-size dependent: in 8pt Gulim a real
        # double space is only ~4.4pt wide, so a 6.8pt floor silently drops
        # every one of them. In "auto" mode the ratio test does the work and
        # this is just a noise floor.
        min_gap = args.auto_gap_floor if args.min_gap_auto else args.min_gap
        for index, gap in enumerate(gaps):
            ratio = gap / baseline if baseline else 0.0
            if (
                gap >= min_gap
                and gap <= args.max_candidate_gap
                and ratio >= args.min_ratio
            ):
                pair = segment[index : index + 2]
                add_candidate(
                    candidates,
                    seen,
                    {
                        "kind": "double_space_candidate",
                        "page": page_number,
                        "bbox": bbox(pair),
                        "text": f"{pair[0]['text']}  {pair[1]['text']}",
                        "context": text,
                        "severity": "red",
                        "note": f"단어 간격 {gap:.2f}, 기준 대비 {ratio:.2f}배; 표 정렬 여부를 육안 확인",
                    },
                )

        if re.search(r"\s+[.!?,;:]", text):
            add_candidate(
                candidates,
                seen,
                {
                    "kind": "space_before_punctuation_candidate",
                    "page": page_number,
                    "bbox": bbox(segment),
                    "text": text,
                    "context": text,
                    "severity": "red",
                    "note": "문장부호 앞 공백 또는 분리된 문장부호인지 확인",
                },
            )
        if re.search(r"\.{2,}|[!?]{2,}", text):
            add_candidate(
                candidates,
                seen,
                {
                    "kind": "duplicate_punctuation_candidate",
                    "page": page_number,
                    "bbox": bbox(segment),
                    "text": text,
                    "context": text,
                    "severity": "red",
                    "note": "중복 문장부호가 의도된 표기인지 확인",
                },
            )
        if re.search(rf"[가-힣]\s+({SUBJECTS}):", text):
            match = re.search(rf"[가-힣]\s+({SUBJECTS}):", text)
            prefix = text[: match.start(1)].rstrip() if match else text
            if prefix and prefix[-1] not in ".?!)]}”’":
                add_candidate(
                    candidates,
                    seen,
                    {
                        "kind": "missing_period_before_subject_candidate",
                        "page": page_number,
                        "bbox": bbox(segment),
                        "text": text,
                        "context": text,
                        "severity": "red",
                        "note": "다음 교과명 앞에서 이전 문장의 온점이 누락되었는지 확인",
                    },
                )
        if any(re.search(r"[가-힣A-Za-z]\.[가-힣A-Za-z]", str(word["text"])) for word in segment):
            add_candidate(
                candidates,
                seen,
                {
                    "kind": "missing_space_after_period_candidate",
                    "page": page_number,
                    "bbox": bbox(segment),
                    "text": text,
                    "context": text,
                    "severity": "red",
                    "note": "온점 뒤 띄어쓰기 누락인지 약어·고유명사인지 확인",
                },
            )

    # Subject headings commonly start on a new visual line. Check the previous
    # line in the same table column so `있음` + next-line `사회:` is not missed.
    for column in column_segments:
        for previous, current in zip(column, column[1:]):
            previous_text = line_text(previous).rstrip()
            current_text = line_text(current).lstrip()
            if not re.match(rf"^({SUBJECTS}):", current_text):
                continue
            if not previous_text or previous_text[-1] in ".?!)]}”’":
                continue
            vertical_gap = float(current[0]["top"]) - float(previous[0]["top"])
            if vertical_gap <= 0 or vertical_gap > args.max_subject_line_gap:
                continue
            pair = [previous[-1], current[0]]
            add_candidate(
                candidates,
                seen,
                {
                    "kind": "missing_period_before_subject_candidate",
                    "page": page_number,
                    "bbox": bbox(pair),
                    "text": f"{previous[-1]['text']} {current[0]['text']}",
                    "context": f"{previous_text} / {current_text}",
                    "severity": "red",
                    "note": "다음 줄 교과명 앞에서 이전 문장의 온점이 누락되었는지 확인",
                },
            )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="생기부 PDF의 이중 띄어쓰기·온점 후보를 추출합니다.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--min-gap",
        default="auto",
        help="이중 띄어쓰기로 볼 최소 간격(pt). 'auto'(기본)면 --min-ratio 로만 판정하고 "
             "--auto-gap-floor 를 잡음 하한으로 쓴다. 글자 크기가 작은 문서에서 "
             "고정값을 쓰면 실제 이중 공백을 통째로 놓친다.",
    )
    parser.add_argument("--auto-gap-floor", type=float, default=2.0,
                        help="auto 모드에서 무시할 최소 간격(pt). 기본 2.0")
    parser.add_argument("--min-ratio", type=float, default=1.65)
    parser.add_argument("--max-candidate-gap", type=float, default=18.0)
    parser.add_argument("--baseline-max-gap", type=float, default=15.0)
    parser.add_argument("--column-break-gap", type=float, default=30.0)
    parser.add_argument(
        "--column-range",
        action="append",
        help="검사할 본문 열의 x0:x1 좌표. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument("--line-tolerance", type=float, default=2.0)
    parser.add_argument("--max-subject-line-gap", type=float, default=28.0)
    parser.add_argument("--top-margin", type=float, default=0.08)
    parser.add_argument("--bottom-margin", type=float, default=0.05)
    args = parser.parse_args()

    args.min_gap_auto = str(args.min_gap).strip().lower() == "auto"
    if not args.min_gap_auto:
        try:
            args.min_gap = float(args.min_gap)
        except ValueError:
            parser.error("--min-gap 은 숫자이거나 'auto' 여야 합니다.")

    try:
        args.parsed_column_ranges = parse_column_ranges(args.column_range)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if not args.input.is_file():
        parser.error(f"입력 PDF를 찾을 수 없습니다: {args.input}")

    candidates: list[dict] = []
    with pdfplumber.open(args.input) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            candidates.extend(scan_page(page, page_number, args))
        page_count = len(pdf.pages)

    for index, candidate in enumerate(candidates, 1):
        candidate["id"] = f"T{index:04d}"
    payload = {
        "input": str(args.input.resolve()),
        "page_count": page_count,
        "candidate_count": len(candidates),
        "min_gap_mode": "auto" if args.min_gap_auto else args.min_gap,
        "warning": "모든 항목은 후보입니다. 원문 렌더링에서 확인한 뒤 확정하십시오.",
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pages": page_count, "candidates": len(candidates), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
