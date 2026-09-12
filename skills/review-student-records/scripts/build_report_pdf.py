#!/usr/bin/env python3
"""Build a standalone page-ordered error report with complete findings."""
import argparse
import json
from pathlib import Path
from collections import Counter
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from review_common import LABELS, load_issues, ensure_new_output
FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\malgun.ttf", None),
    (r"C:\Windows\Fonts\gulim.ttc", 0),
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
    ("/Library/Fonts/AppleGothic.ttf", None),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", None),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", None),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0),
]

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


def build(issues, meta, output, font):
    st = {k: ParagraphStyle(k, fontName=font, fontSize=size, leading=lead,
          wordWrap='CJK', spaceAfter=6, keepWithNext=k in ['h1','h2','h3'])
          for k,size,lead in [('h1',18,25),('h2',13,19),('h3',10,15),('body',9,14)]}
    def p(text, style='body'):
        return Paragraph(escape(str(text)).replace('\n','<br/>'), st[style])
    counts = Counter(i.get('color','yellow') for i in issues)
    story = [p('생활기록부 페이지별 오류 보고서','h1'),
             p('원본 PDF 첫 장부터 센 페이지 번호를 사용합니다. 기재요령 근거 쪽수는 별도로 표시합니다.')]
    metadata = [
        ('원본 파일',meta.get('source','미확인')),
        ('범위',f"{meta.get('pages','미확인')}쪽 / 학생 {meta.get('student_count','미확인')}명"),
        ('학교급 / 기록 학년도 / 학년',f"{meta.get('school_level','미확인')} / {meta.get('academic_year','미확인')} / {meta.get('grade','미확인')}"),
        ('작성 기준일',meta.get('basis_date') or '미확인'),
        ('적용 기준',meta.get('guideline') or '일반 표기 검토; 공식 기준 미지정'),
        ('임원 기간',f"시작 {meta.get('officer_start') or '03.01. (기본값·예외 확인)'} / 종료 {meta.get('officer_end') or '학교 일정 확인 필요'}"),
        ('점검 항목',f"오류 {counts['red']} / 확인 필요 {counts['orange']} / 개선 권고 {counts['yellow']} / 기타 검토 {counts['purple']+counts['blue']} / 전체 {len(issues)}"),
        ('표시 상태',f"PDF 주석 {sum(not i.get('unmarked',False) for i in issues)} / 보고서만 {sum(bool(i.get('unmarked')) for i in issues)}"),
    ]
    rows = [[p(k),p(v)] for k,v in metadata]
    t=Table(rows,colWidths=[44*mm,130*mm]);t.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.35,colors.lightgrey),
        ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#F0F3F6'))]))
    story.extend([t,Spacer(1,6*mm),p('반복 문구 검사는 포함했습니다.' if meta.get('repeated_phrases') else '반복 문구 검사는 제외했습니다.')])
    if not issues:story.append(p('확인한 범위에서 보고할 항목이 없습니다. 미검토 범위는 아래를 확인하세요.'))
    current=None
    for i in sorted(issues,key=lambda x:(x['page'],x['id'])):
        if current!=i['page']:
            current=i['page'];story.append(p(f'원본 PDF {current}쪽','h2'))
        story.append(p(f"{i['id']} · {LABELS[i.get('color','yellow')]} · {i.get('student','학생 미확인')} · {i.get('field','영역 미확인')}",'h3'))
        if i.get('page_label'):story.append(p('문서 인쇄 쪽수: '+str(i['page_label'])))
        for label,key in [('원문','original'),('문제 / 확인할 내용','reason'),('수정 제안','suggestion'),('근거','basis')]:
            story.append(p(label+': '+str(i.get(key) or ('근거 확인 필요' if key=='basis' else '확인 필요'))))
        if i.get('rule_id'):story.append(p('기준 ID: '+i['rule_id']))
        if i.get('unmarked'):story.append(p('PDF 미표시 사유: '+i['unmarked_reason']))
        story.append(Spacer(1,3*mm))
    for title,key in [('추가 확인 사항','unmarked'),('검사 제외·미검토 범위','excluded')]:
        story.append(p(title,'h2'))
        for x in meta.get(key) or ['별도 항목 없음']:story.append(p(x))
    story.append(p('수정 제안은 원문과 실제 관찰·학교 자료를 대조한 뒤 반영합니다.'))
    doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=16*mm,bottomMargin=18*mm,title='생활기록부 페이지별 오류 보고서')
    def footer(c,d):
        c.setFont(font,8);c.drawRightString(192*mm,10*mm,f'보고서 {d.page}쪽')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)


def write_markdown(issues,meta,path):
    lines=['# 생활기록부 페이지별 오류 보고서','',json.dumps(meta,ensure_ascii=False),'']
    for i in sorted(issues,key=lambda x:(x['page'],x['id'])):
        lines += [f"## 원본 PDF {i['page']}쪽 · {i['id']}",'']
        lines += [f"- {key}: {i.get(key,'')}" for key in ['student','field','color','original','reason','suggestion','basis','rule_id']]
        if i.get('unmarked'):lines.append('- 미표시: '+i['unmarked_reason'])
        lines.append('')
    path.write_text('\n'.join(lines),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description='페이지별 오류 보고서 PDF')
    p.add_argument('--issues',type=Path,required=True);p.add_argument('--meta',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--markdown',type=Path);p.add_argument('--font',type=Path)
    a=p.parse_args()
    try:
        issues=load_issues(a.issues)
        meta=json.loads(a.meta.read_text(encoding='utf-8')) if a.meta else {}
        if type(meta.get('pages')) is int and any(i['page']>meta['pages'] for i in issues):raise ValueError('원본에 없는 페이지')
        ensure_new_output(a.output,a.issues,a.meta)
        if a.markdown:ensure_new_output(a.markdown,a.issues,a.meta,a.output)
        build(issues,meta,a.output,register_font(a.font))
        if a.markdown:write_markdown(issues,meta,a.markdown)
        print(f'보고서 생성: {a.output} ({len(issues)}항목)')
    except (ValueError,OSError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
