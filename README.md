# review-student-records

초등학교 학교생활기록부 종합일람표 PDF를 점검하는 AI 에이전트 스킬입니다. 기재요령과 사용자 기준을 대조하고, 원본 위에 색상별 형광펜 주석을 넣은 표시본과 별도 총평 PDF를 생성·검증합니다. **Codex와 Claude Code 양쪽에서 씁니다.**

이 저장소에는 학생 PDF나 개인정보가 포함되어 있지 않습니다.

## 주요 기능

- 학생별·영역별 PDF 텍스트와 좌표 추출 (연속 페이지에 걸친 기록을 한 학생으로 연결)
- 맞춤법, 띄어쓰기, 이중 공백, 온점, 숫자·날짜 표기 점검
- 학급 반장·임원 시작일 `03.01.` 확인과 학교별 종료일 확인
- 반복 문구 검사 기본 제외
- 색상별 형광펜 표시본 생성 (원본 재조판 없이 주석만 추가)
- 별도 점검 총평 PDF·Markdown과 문제 목록 생성
- 페이지 수, 주석 수, 총평 집계, 렌더링 교차검증
- 요청 시 Google Drive 업로드 후 메타데이터 재확인

## 색상 범례

색은 심각도가 아니라 **다음에 할 행동**을 뜻합니다.

| 색 | 뜻 |
|---|---|
| 🔴 빨강 | 반드시 수정 (명백한 오류·기재 제한 위반) |
| 🟠 주황 | 확인 필요 (근거를 찾아야 판단 가능) |
| 🟡 노랑 | 다듬기 권장 |
| 🟣 보라 | 부정적 표현 |
| 🔵 파랑 | 반복 문구 (검사를 켠 경우에만) |

## 설치

### 의존성

```powershell
python -m pip install -r skills/review-student-records/requirements.txt
```

`pymupdf`, `pdfplumber`, `pypdf`, `reportlab` 이 필요합니다. 총평본 조판에는 한글 TTF/TTC가 있어야 하며, Windows(맑은 고딕·굴림)·macOS·나눔고딕/Noto를 자동으로 찾습니다. 없으면 `--font` 로 지정합니다.

### Codex

```powershell
git clone https://github.com/hyominyams-sub/review-student-records.git
Copy-Item -Recurse -Force `
  .\review-student-records\skills\review-student-records `
  "$HOME\.codex\skills\review-student-records"
```

### Claude Code

```powershell
git clone https://github.com/hyominyams-sub/review-student-records.git
Copy-Item -Recurse -Force `
  .\review-student-records\skills\review-student-records `
  "$HOME\.claude\skills\review-student-records"
```

프로젝트 안에서만 쓰려면 `$HOME\.claude` 대신 그 프로젝트의 `.claude` 폴더에 넣습니다.

## 사용

Codex:

```text
Use $review-student-records to 이 종합일람표 PDF를 점검하고 표시본과 총평본을 만들어 줘.
```

Claude Code에서는 `생기부 점검해 줘`, `종합일람표 검토해 줘`처럼 요청하면 스킬이 자동으로 걸립니다.

스크립트만 따로 쓸 수도 있습니다.

```powershell
cd skills/review-student-records

# 1. 학생별·영역별 추출
python scripts/extract_records.py "종합일람표.pdf" --outdir work

# 2. 이중 띄어쓰기·온점 후보
python scripts/scan_typography.py "종합일람표.pdf" --output work/typo.json `
  --min-gap auto --column-range 92:455 --column-range 455:719 --column-range 849:977

# 3. (사람이 확인해 work/issues.json 확정)

# 4~5. 표시본과 총평본
python scripts/build_marked_pdf.py "종합일람표.pdf" --issues work/issues.json `
  --output "종합일람표_반복문구제외_점검표시본.pdf"
python scripts/build_report_pdf.py --issues work/issues.json --meta work/meta.json `
  --output "종합일람표_반복문구제외_점검총평.pdf"

# 6. 검증
python scripts/verify_review_outputs.py --source "종합일람표.pdf" `
  --marked "종합일람표_반복문구제외_점검표시본.pdf" `
  --report "종합일람표_반복문구제외_점검총평.pdf" `
  --issues-json work/issues.json --require-text "반복 문구 검사는 제외"
```

## 검증 범위

PDF 분석 로직은 실제 종합일람표(A3 가로, `/Rotate 90`, 20쪽·22명)와 같은 형식으로 재현한 회전 없는 문서, 그리고 결함을 심어 둔 합성 시험지에서 확인했습니다.

- 표 선에서 13개 열 경계를 두 문서 모두 동일하게 검출
- 학생 1~22번을 순서대로 인식하고, 쪽을 넘어 이어지는 기록을 한 학생으로 연결
- 합성 시험지에서 이중 띄어쓰기 2건·온점 누락 1건을 정확히 재현 (오탐 0)
- 확정 문제 수와 추가된 주석 수의 일치 검증

좌표와 간격 임계값은 양식이 다른 PDF에 그대로 적용하지 않습니다. 현재 문서의 표 열을 먼저 측정하고, 자동 탐지 결과를 원본 렌더링에서 확인하도록 스킬에 명시되어 있습니다.

### 알려진 함정

`skills/review-student-records/references/validated-pdf-workflow.md` 9절에 실측 근거와 함께 정리되어 있습니다. 특히:

- **좌표계** — PyMuPDF는 텍스트·도형·주석 모두 회전 **전** 좌표를 씁니다. `page.rect`만 회전 후입니다.
- **이중 띄어쓰기 임계값** — 고정 pt 값은 글자 크기에 딸려 갑니다. 8pt 본문에서 두 칸 공백은 약 4.4pt라, 예전 기본값 `6.8pt`로는 실제 문서에서 **한 건도 잡히지 않았습니다.** 지금은 `--min-gap auto`가 기본이며 줄·열의 중앙값 대비 비율로 판정합니다.
- **명사형 종결** — `습니다`만 찾으면 `뛰어납니다` 같은 `ㅂ니다` 활용을 전부 놓칩니다. `니다.`로 찾습니다.
- **주석 수 세기** — 메모 달린 하이라이트는 `/Popup`을 하나 더 만들어, 그냥 세면 문제 수의 두 배가 나옵니다.

## 회귀 검사

```powershell
python skills/review-student-records/tests/regression.py
```

합성 시험지를 만들어 탐지·표시·총평·검증을 한 번에 돌립니다. 실제 학생 파일은 쓰지 않습니다.

## 저장소 구조

```text
skills/review-student-records/
├── SKILL.md
├── requirements.txt
├── agents/openai.yaml
├── references/
│   ├── review-criteria.md            점검 항목과 색상 범례
│   └── validated-pdf-workflow.md     검증된 PDF 분석 로직과 알려진 함정
├── scripts/
│   ├── extract_records.py            1단계 학생별·영역별 추출
│   ├── scan_typography.py            2단계 이중 띄어쓰기·온점 후보
│   ├── build_marked_pdf.py           4단계 표시본 생성
│   ├── build_report_pdf.py           5단계 총평본 생성
│   └── verify_review_outputs.py      6단계 산출물 재검증
└── tests/
    └── regression.py                 합성 시험지 기반 회귀 검사
```

## 개인정보 주의

- 학생 원본 PDF와 생성한 점검 결과는 저장소에 커밋하지 마세요.
- 중간 산출물(`records.json`, `records.txt`, `issues.json`)에는 실명이 들어갑니다. 작업이 끝나면 지우거나 원본과 같은 보안 수준으로 관리하세요.
- 공개 저장소에는 학교 내부 일정, 학생 이름, 로컬 파일 경로를 포함하지 마세요.
- Drive 공유 권한은 사용자가 명시적으로 요청할 때만 변경하세요.
