#!/usr/bin/env python3
"""Add ID-matched highlights with notes; preserve source content and rotation."""
import argparse
from collections import Counter
from pathlib import Path
import math
import pymupdf
from review_common import COLORS, LABELS, load_issues, ensure_new_output


def annotation_text(issue):
    return '\n'.join(str(x) for x in [
        f"ID: {issue['id']} / 원본 PDF {issue['page']}쪽",
        ' · '.join(filter(None, [issue.get('student'), issue.get('field')])),
        '원문: ' + issue.get('original', ''),
        '제안: ' + issue.get('suggestion', '확인 필요'),
        '사유: ' + issue.get('reason', ''),
        '근거: ' + issue.get('basis', '일반 표기 검토'),
    ] if x)


def issue_rects(issue):
    boxes = issue.get('bboxes', [issue['bbox']] if 'bbox' in issue else [])
    if not isinstance(boxes, list) or not boxes:
        raise ValueError(issue['id'] + ': 좌표 없음. 미표시는 unmarked와 사유를 지정하세요.')
    rects = []
    for b in boxes:
        if len(b) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in b):
            raise ValueError(issue['id'] + ': 유효하지 않은 좌표')
        r = pymupdf.Rect(b)
        if r.is_empty or r.is_infinite:
            raise ValueError(issue['id'] + ': 빈 좌표')
        rects.append(r)
    return rects


def build(source, issues, output, popup=True):
    ensure_new_output(output, source)
    with pymupdf.open(source) as doc:
        planned = []
        for i in issues:
            if not 1 <= i['page'] <= len(doc):
                raise ValueError(i['id'] + ': 원본에 없는 페이지')
            if i.get('unmarked'):
                continue
            page = doc[i['page'] - 1]
            # Text and annotations use native coordinates, NOT rotated page.rect.
            bounds = page.rect * page.derotation_matrix
            rects = issue_rects(i)
            if any(not bounds.contains(r) for r in rects):
                raise ValueError(i['id'] + ': 일부 또는 전체 좌표가 페이지 밖입니다.')
            planned.append((i, rects))
        counts = Counter()
        for i, rects in planned:
            page = doc[i['page'] - 1]
            color = i.get('color', 'yellow')
            a = page.add_highlight_annot(rects)
            a.set_colors(stroke=COLORS[color])
            a.set_opacity(.35)
            a.set_info(title=f"[{LABELS[color]}] {i['id']}", content=annotation_text(i), subject=i['id'])
            if popup:
                bounds = page.rect * page.derotation_matrix
                x = max(bounds.x0, min(rects[0].x1 + 4, bounds.x1 - 210))
                y = max(bounds.y0, min(rects[0].y0, bounds.y1 - 95))
                a.set_popup(pymupdf.Rect(x, y, min(x+210,bounds.x1), min(y+95,bounds.y1)))
            a.update()
            counts[color] += 1
        doc.save(output, garbage=3, deflate=True)
    return len(planned), counts


def main():
    p = argparse.ArgumentParser(description='원본 보존 형광펜·주석 PDF')
    p.add_argument('input', type=Path)
    p.add_argument('--issues', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--no-popup', action='store_true')
    a = p.parse_args()
    try:
        issues = load_issues(a.issues)
        n, _ = build(a.input, issues, a.output, not a.no_popup)
        print(f'전체 {len(issues)}항목 / 표시 {n} / 보고서에만 기재 {len(issues)-n}: {a.output}')
    except (ValueError, OSError) as e:
        p.exit(1, str(e)+'\n')

if __name__ == '__main__':
    main()
