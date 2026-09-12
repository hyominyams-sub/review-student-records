#!/usr/bin/env python3
"""Synthetic roundtrips: rotated pages, report-only findings, long text, no findings."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import pymupdf
from reportlab.pdfgen import canvas
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from build_report_pdf import register_font, build as report
from build_marked_pdf import build as mark
from review_common import load_issues
from verify_review_outputs import verify
from extract_records import extract_pages


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    font=register_font(None)
    base=out/'base.pdf';c=canvas.Canvas(str(base),pagesize=(595,842));c.setFont(font,11)
    c.drawString(55,100,'가상 학생의 기록: 확인할수 있음.');c.showPage();c.setFont(font,11)
    c.drawString(55,760,'독서: 제목(저자) / 기관명은 도서 제목의 일부임.');c.save()
    source=out/'synthetic.pdf'
    with pymupdf.open(base) as doc:
        doc[0].set_rotation(90);doc[1].add_text_annot((40,40),'기존 주석 유지');doc.save(source)
    with pymupdf.open(source) as doc:
        box=list(doc[0].search_for('확인할수')[0])
    issues=[{'id':'R001','page':1,'color':'red','student':'1번','field':'교과',
             'original':'확인할수','reason':'의존 명사 띄어쓰기','suggestion':'확인할 수','basis':'일반 표기 검토','bbox':box},
            {'id':'R002','page':2,'color':'orange','original':'<b>문서 일부 & 조건</b>',
             'reason':'학교 일정 확인 필요','unmarked':True,'unmarked_reason':'문장 좌표 미확정',
             'suggestion':'학교 자료와 대조','basis':'C06'}]
    ip=out/'issues.json';ip.write_text(json.dumps(issues,ensure_ascii=False));load_issues(ip)
    marked=out/'synthetic_점검표시본.pdf';rp=out/'synthetic_오류보고서.pdf'
    mark(source,issues,marked);report(issues,{'source':source.name,'pages':2,'school_level':'초등학교','academic_year':2026,'grade':5,'guideline':'2026 내장 기준','excluded':['가상 시험 문서']},rp,font)
    result=verify(source,marked,rp,issues,['R001','R002','PDF 미표시 사유'])
    assert not result['errors'],result
    assert result['added_annotations']==1
    assert extract_pages(source)['meta']['pages']==2
    # Existing output and source overwrite must fail without changing bytes.
    old=source.read_bytes()
    for dest in [source,marked]:
        try:mark(source,issues,dest);raise AssertionError('overwrite allowed')
        except ValueError:pass
    assert source.read_bytes()==old
    # Partial multi-line bounds must not silently drop one line.
    bad=[dict(issues[0],bboxes=[box,[0,0,9000,9010]])]
    try:mark(source,bad,out/'bad.pdf');raise AssertionError('bad coordinates accepted')
    except ValueError:pass
    assert not (out/'bad.pdf').exists()
    # Missing IDs and duplicate IDs are rejected.
    for payload in [[dict(issues[0],id='')],[issues[0],issues[0]]]:
        badp=out/'invalid.json';badp.write_text(json.dumps(payload))
        try:load_issues(badp);raise AssertionError('invalid schema accepted')
        except ValueError:pass
    # No findings still produces both outputs.
    mark(source,[],out/'zero_marked.pdf');report([],{'source':source.name,'pages':2},out/'zero_report.pdf',font)
    assert not verify(source,out/'zero_marked.pdf',out/'zero_report.pdf',[],[])['errors']
    # Long entries and literal XML-like strings must survive PDF layout and extraction.
    long=dict(issues[1],id='LONG001',reason=('확인할 사항 <기관명> & 예외 조건. '*150)+'ENDLONG')
    report([long],{'source':source.name,'pages':2},out/'long_report.pdf',font)
    with pymupdf.open(out/'long_report.pdf') as d:
        text=''.join(p.get_text() for p in d)
        assert 'ENDLONG' in text and '<기관명>' in text
    # Report content tampering must be detected even if annotation counts match.
    tampered=[dict(issues[0],reason='다른 사유'),issues[1]]
    assert verify(source,marked,rp,tampered,[])['errors']
    print(json.dumps({'status':'ok','tests':['rotation','existing annotations','report-only','page extraction','no overwrite','partial bounds','IDs','zero findings','long escaped text','note tampering'],'output':str(out)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--outdir',type=Path);a=p.parse_args()
    if a.outdir:run(a.outdir)
    else:
        with tempfile.TemporaryDirectory() as t:run(Path(t))
