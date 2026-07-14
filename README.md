# review-student-records

초등학교 학교생활기록부 종합일람표 PDF를 점검하는 Codex 스킬입니다. 기재요령과 사용자 기준을 대조하고, 원본 위에 색상별 형광펜 주석을 넣은 표시본과 별도 총평 PDF를 생성·검증합니다.

이 저장소에는 학생 PDF나 개인정보가 포함되어 있지 않습니다.

## 주요 기능

- 학생별·영역별 PDF 텍스트와 좌표 추출
- 맞춤법, 띄어쓰기, 이중 공백, 온점, 숫자·날짜 표기 점검
- 학급 반장·임원 시작일 `03.01.` 확인과 학교별 종료일 확인
- 반복 문구 검사 기본 제외
- 빨강·주황·노랑 형광펜 표시본 생성
- 별도 점검 총평 PDF와 문제 목록 생성
- 페이지 수, 주석 수, 총평 집계, 렌더링 교차검증
- 요청 시 Google Drive 업로드 후 메타데이터 재확인

## 검증 범위

포함된 PDF 분석 로직은 22쪽·21명 종합일람표를 대상으로 회귀 시험했습니다.

- 이중 띄어쓰기 후보 8건 재현
- 교과 전환 전 온점 누락 후보 1건 재현
- 확정 문제 159건과 추가 PDF 주석 159개 일치 확인
- 표시본 22쪽과 총평본 13쪽 렌더링 확인

좌표와 간격 임계값은 양식이 다른 PDF에 그대로 적용하지 않습니다. 현재 문서의 표 열을 먼저 측정하고 자동 탐지 결과를 원본 렌더링에서 확인하도록 스킬에 명시되어 있습니다.

## 설치

저장소를 복제한 뒤 `skills/review-student-records` 폴더를 Codex 개인 스킬 폴더에 복사합니다.

Windows PowerShell 예시:

```powershell
git clone https://github.com/hyominyams-sub/review-student-records.git
Copy-Item -Recurse -Force `
  .\review-student-records\skills\review-student-records `
  "$HOME\.codex\skills\review-student-records"
```

## 사용

Codex에서 다음처럼 요청합니다.

```text
Use $review-student-records to 이 종합일람표 PDF를 점검하고 표시본과 총평본을 만들어 줘.
```

또는 `생기부 점검해 줘`, `종합일람표 분석해 줘`처럼 요청할 수 있습니다.

## 저장소 구조

```text
skills/review-student-records/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── review-criteria.md
│   └── validated-pdf-workflow.md
└── scripts/
    ├── scan_typography.py
    └── verify_review_outputs.py
```

## 개인정보 주의

- 학생 원본 PDF와 생성한 점검 결과는 저장소에 커밋하지 마세요.
- 공개 저장소에는 학교 내부 일정, 학생 이름, 로컬 파일 경로를 포함하지 마세요.
- Drive 공유 권한은 사용자가 명시적으로 요청할 때만 변경하세요.
