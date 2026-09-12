"""Shared validation for review findings (no automatic policy decisions)."""
import json
from pathlib import Path

COLORS = {'red': (1, .62, .62), 'orange': (1, .80, .45), 'yellow': (1, .95, .35),
          'purple': (.85, .70, 1), 'blue': (.62, .80, 1)}
LABELS = {'red': '오류', 'orange': '확인 필요', 'yellow': '개선 권고',
          'purple': '부정적 표현 검토', 'blue': '반복 문구 검토'}


def load_issues(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    issues = value if isinstance(value, list) else value.get('issues')
    if not isinstance(issues, list):
        raise ValueError('issues는 배열이어야 합니다.')
    ids = set()
    for i in issues:
        if not isinstance(i, dict) or not isinstance(i.get('id'), str) or not i['id'].strip():
            raise ValueError('각 항목에 비어 있지 않은 문자열 ID가 필요합니다.')
        if i['id'] in ids:
            raise ValueError('중복 ID: ' + i['id'])
        ids.add(i['id'])
        if type(i.get('page')) is not int or i['page'] < 1:
            raise ValueError(i['id'] + ': page는 1부터 시작하는 정수입니다.')
        if i.get('color', 'yellow') not in COLORS:
            raise ValueError(i['id'] + ': 알 수 없는 색상')
        for field in ('original', 'reason'):
            if not isinstance(i.get(field), str) or not i[field].strip():
                raise ValueError(i['id'] + ': ' + field + ' 필요')
        if i.get('unmarked') and not i.get('unmarked_reason'):
            raise ValueError(i['id'] + ': 미표시 사유 필요')
    return issues


def ensure_new_output(path, *inputs):
    p = Path(path)
    if any(p.resolve() == Path(x).resolve() for x in inputs if x):
        raise ValueError('출력 경로가 입력과 같습니다: ' + str(p))
    if p.exists():
        raise ValueError('기존 파일을 덮어쓰지 않습니다: ' + str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
