# 두 결과물의 데이터 계약

중간 파일은 작업 디렉터리에 두고 사용자에게 기본 전달하는 결과는 표시본 PDF와 오류보고서 PDF 두 종이다. 사용자 요청 시에만 Markdown 사본 등을 추가한다.

## issues.json

모델이 원문과 기준을 대조하여 확정한 **보고할 항목**의 배열. 확인 필요·권고도 포함하지만 확정 오류와 구분한다. 자동 탐지 스크립트만으로 이 배열을 완성했다고 주장하지 않는다.

```json
[
  {
    "id": "R001",
    "page": 2,
    "page_label": "1 / 2",
    "student": "2번",
    "field": "교과학습발달상황",
    "color": "red",
    "original": "확인할수 있음.",
    "suggestion": "확인할 수 있음.",
    "reason": "의존 명사 띄어쓰기",
    "rule_id": "C12",
    "basis": "일반 표기 검토: 의존 명사 수",
    "bbox": [100, 210, 180, 223]
  }
]
```

- `id`는 비어 있지 않은 유일한 문자열, `page`는 원본 PDF 첫 장부터 센 1-based 정수다.
- `original`, `reason`은 필수다. 신규 항목에는 `student`, `field`, `suggestion`, `rule_id`, `basis`도 적는다.
- 공식 규정의 근거 예: `2026 초등 기재요령 본문 p.81 / PDF p.87, C06·E06; 학기 선출 예외 확인`.
- `bbox`는 PyMuPDF 회전 전 네이티브 좌표. 여러 줄은 `bboxes` 배열로 줄별 상자를 지정한다. 보여지는 회전 후 좌표를 그대로 넣지 않는다.
- 위치를 확정 못한 항목은 `unmarked: true`, `unmarked_reason`을 넣고 좌표를 생략한다. 보고서에는 원본 페이지와 사유가 남는다. 페이지 자체가 불명확한 전역 문제는 `meta.unmarked`에 적고 페이지를 지어내지 않는다.
- 정상 원문을 예시로 표시하지 않는다. 동일 문장·동일 사유는 한 항목으로 만든다.
- 공식 기재요령의 규정 ID는 `references/*-2026.md`/`review-criteria.md`와 연결한다.

## meta.json

추출기의 meta에 아래 항목을 추가한다. 입력 파일에는 없지만 있을 것으로 추정한 값을 넣지 않는다.

```json
{
  "source": "가상종합일람표.pdf",
  "pages": 2,
  "student_count": 2,
  "school_level": "초등학교",
  "academic_year": 2026,
  "grade": "5학년",
  "basis_date": "2026.07.14.",
  "officer_start": "2026.03.01. (기본값, 예외 별도 검토)",
  "officer_end": null,
  "repeated_phrases": false,
  "guideline": "2026 초등학교 기재요령 기반 내장 점검 기준 2026.1",
  "excluded": ["학교 내부 증빙자료의 사실 검증", "이전 학년도 규정 판단"],
  "unmarked": []
}
```

`school_level`·학년도·학년의 미확정 상태도 보고서에 그대로 적는다. 빈 이슈 배열이어도 검토 범위와 미검토 범위를 구분한다. 중간 추출 결과에 경고가 있으면 누락 페이지·영역을 해소하거나 `excluded`에 남긴다.
