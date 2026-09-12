#!/usr/bin/env python3
"""Verify preservation, issue-to-page mapping, note contents and report IDs."""
import argparse
import json
from collections import Counter
from pathlib import Path
import pymupdf
from review_common import COLORS, load_issues
from build_marked_pdf import annotation_text


def annotation_count(doc):
    return sum(len(list(p.annots() or [])) for p in doc)


def verify(source,marked,report,issues,required):
    errors=[]
    with pymupdf.open(marked) as m, pymupdf.open(report) as r:
        added=annotation_count(m)
        if source:
            with pymupdf.open(source) as s:
                added-=annotation_count(s)
                if len(s)!=len(m):errors.append('원본과 표시본 페이지 수 불일치')
                for n,(sp,mp) in enumerate(zip(s,m),1):
                    if sp.get_text()!=mp.get_text():errors.append(f'{n}쪽: 원본 텍스트 변경')
                    if sp.rotation!=mp.rotation or sp.mediabox!=mp.mediabox or sp.cropbox!=mp.cropbox:
                        errors.append(f'{n}쪽: 회전/페이지 크기 변경')
                    # PDF content streams preserve text, image placement and table drawing.
                    if sp.read_contents()!=mp.read_contents():errors.append(f'{n}쪽: 본문 스트림 변경')
        rt='\n'.join(p.get_text() for p in r)
        for t in required:
            if t not in rt:errors.append('보고서 문구 누락: '+t)
        if issues is not None:
            expected=[i for i in issues if not i.get('unmarked')]
            if added!=len(expected):errors.append(f'추가 주석 {added} / 예상 {len(expected)} 불일치')
            for i in issues:
                if i['page']>len(m):errors.append(i['id']+': 존재하지 않는 페이지');continue
                if i['id'] not in rt:errors.append(i['id']+': 보고서 누락')
                if f"원본 PDF {i['page']}쪽" not in rt:errors.append(i['id']+': 보고서 원본 페이지 누락')
                if i.get('unmarked'):continue
                page=m[i['page']-1]
                matches=[a for a in page.annots() or [] if a.info.get('subject')==i['id']]
                if len(matches)!=1:errors.append(i['id']+': 해당 페이지 주석 ID 불일치');continue
                a=matches[0]
                if a.type[1]!='Highlight':errors.append(i['id']+': 형광펜이 아님')
                if a.info.get('content')!=annotation_text(i):errors.append(i['id']+': 주석 내용 불일치')
                actual=a.colors.get('stroke') or ()
                want=COLORS[i.get('color','yellow')]
                if len(actual)!=3 or any(abs(x-y)>.01 for x,y in zip(actual,want)):errors.append(i['id']+': 색상 불일치')
                bounds=page.rect*page.derotation_matrix
                if not all(bounds.contains(pymupdf.Point(v)) for v in a.vertices or []):errors.append(i['id']+': 주석 좌표 이탈')
        return {'status':'failed' if errors else 'ok','marked_pages':len(m),'report_pages':len(r),
                'added_annotations':added,'issue_count':len(issues) if issues is not None else None,'errors':errors}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path)
    p.add_argument('--marked',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--issues-json',type=Path);p.add_argument('--require-text',action='append',default=[])
    a=p.parse_args()
    try:
        issues=load_issues(a.issues_json) if a.issues_json else None
        result=verify(a.source,a.marked,a.report,issues,a.require_text)
    except (ValueError,OSError) as e:p.exit(1,str(e)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(1 if result['errors'] else 0)
if __name__=='__main__':main()
