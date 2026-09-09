#!/usr/bin/env python3
"""Regression check for the review scripts.

Builds a small fixture PDF with deliberately planted defects, then asserts the
scripts still find exactly those. It uses a synthetic file on purpose: real
종합일람표 files contain student personal data and must never be committed.

Run:  python tests/regression.py
Exit: 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_report_pdf import register_font  # noqa: E402

# Two double spaces and one missing period before a subject label.
LINES = [
    "국어: 자기 생각을 또렷하게 말함. 토의에서 의견을 끝까지 듣고 요약함.",
    "설명하는 글의 구조를 알고  중심 내용을 정리함.",
    "인권 약속을 스스로 제안할 수 있음 사회: 우리 국토의 위치를 설명함.",
    "실험 결과를 표로  정리하여 규칙을 찾아냄.",
]
EXPECTED = {"double_space_candidate": 2, "missing_period_before_subject_candidate": 1}


def make_fixture(path: Path) -> None:
    from reportlab.pdfgen import canvas

    font = register_font(None)
    c = canvas.Canvas(str(path), pagesize=(1191, 842))
    c.setFont(font, 8)
    y = 700
    for line in LINES:
        c.drawString(100, y, line)
        y -= 20
    c.save()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", *args],
                          capture_output=True, text=True, encoding="utf-8")


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        fixture = work / "fixture.pdf"
        make_fixture(fixture)

        # 1. Typography scan finds exactly the planted defects.
        out = work / "typo.json"
        proc = run(str(ROOT / "scripts" / "scan_typography.py"), str(fixture),
                   "--output", str(out), "--column-range", "90:1100")
        if proc.returncode != 0:
            failures.append(f"scan_typography 실행 실패: {proc.stderr.strip()[:200]}")
        else:
            found = Counter(c["kind"] for c in
                            json.loads(out.read_text(encoding="utf-8"))["candidates"])
            for kind, want in EXPECTED.items():
                got = found.get(kind, 0)
                if got != want:
                    failures.append(f"{kind}: {want}건이어야 하는데 {got}건")
            extra = set(found) - set(EXPECTED)
            if extra:
                failures.append(f"예상에 없는 후보 유형: {sorted(extra)}")

        # 2. Marked copy carries one annotation per issue and verification passes.
        issues = [{"id": "R001", "page": 1, "color": "red",
                   "student": "01", "field": "교과학습발달상황",
                   "original": "있음 사회:", "suggestion": "있음. 사회:",
                   "reason": "교과 전환 전 온점 누락",
                   "bbox": [100, 130, 400, 145]}]
        issues_path = work / "issues.json"
        issues_path.write_text(json.dumps(issues, ensure_ascii=False), encoding="utf-8")
        marked = work / "marked.pdf"
        proc = run(str(ROOT / "scripts" / "build_marked_pdf.py"), str(fixture),
                   "--issues", str(issues_path), "--output", str(marked))
        if proc.returncode != 0:
            failures.append(f"build_marked_pdf 실행 실패: {proc.stderr.strip()[:200]}")

        report = work / "report.pdf"
        meta = work / "meta.json"
        meta.write_text(json.dumps({"source": "fixture.pdf", "pages": 1,
                                    "student_count": 1, "repeated_phrases": False},
                                   ensure_ascii=False), encoding="utf-8")
        proc = run(str(ROOT / "scripts" / "build_report_pdf.py"),
                   "--issues", str(issues_path), "--meta", str(meta),
                   "--output", str(report))
        if proc.returncode != 0:
            failures.append(f"build_report_pdf 실행 실패: {proc.stderr.strip()[:200]}")

        proc = run(str(ROOT / "scripts" / "verify_review_outputs.py"),
                   "--source", str(fixture), "--marked", str(marked),
                   "--report", str(report), "--issues-json", str(issues_path),
                   "--require-text", "반복 문구 검사는 제외")
        if proc.returncode != 0:
            failures.append(f"verify_review_outputs 실패: {proc.stdout.strip()[-300:]}")

    if failures:
        print("실패:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("모든 회귀 검사 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
