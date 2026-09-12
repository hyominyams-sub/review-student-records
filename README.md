# 생기부 점검 · review-student-records

초·중·고 학교생활기록부와 종합일람표 PDF를 점검하는 Codex·Claude Code용 스킬입니다. **2026 교육부 기재요령을 바탕으로 작성한 공통·학교급별 기준이 포함되어 있어 기재요령 PDF를 매번 첨부하지 않아도 됩니다.**

## 결과물 두 종

1. **점검표시본.pdf** — 원본 내용을 유지하고 해당 문장에 형광펜과 주석을 추가합니다.
2. **오류보고서.pdf** — 원본 PDF 페이지 순서로 학생·영역·원문·문제·수정 제안·근거를 안내합니다. 같은 ID로 주석과 보고서를 찾을 수 있습니다.

빨강은 확인된 오류, 주황은 추가 확인, 노랑은 개선 권고입니다. 확인 필요나 권고를 확정 오류 건수로 집계하지 않습니다. 좌표를 확인하지 못한 항목도 보고서에 페이지와 사유를 남깁니다.

## 사용

```text
$review-student-records
이 종합일람표 PDF를 점검해줘.
2026학년도 중학교 3학년 자료야.
원본을 보존하고 형광펜·주석 PDF와 페이지별 오류 보고서 PDF를 만들어줘.
```

학교급·학년도·학년이 문서에서 확인되면 다시 묻지 않습니다. 임원 시작일 기본값은 **3월 1일**이며 학기 단위 선출·전입·재선출 등의 예외를 함께 확인합니다. 종료일은 학교 일정에 따릅니다. 반복 문구 검사는 기본 제외이며 요청하면 포함합니다.

자소서 교정이나 새로운 생기부 작성에는 사용하지 않습니다. Drive 업로드는 별도로 요청한 경우만 수행합니다.

## 설치

[최신 릴리스](https://github.com/hyominyams-sub/review-student-records/releases/latest)의 `review-student-records.zip`을 내려받아 압축을 풀고, 안의 `review-student-records` 폴더를 스킬 위치에 넣으세요.

| 환경 | 개인 스킬 폴더 예시 |
|---|---|
| Codex | `~/.codex/skills/review-student-records/` |
| Claude Code | `~/.claude/skills/review-student-records/` |
| Codex 프로젝트 전용 | `<프로젝트>/.agents/skills/review-student-records/` |

Windows의 `~`는 사용자 홈 폴더입니다. 설치 후 스킬 목록에서 확인하고 표시되지 않으면 앱을 다시 여세요. 기존 버전이 있으면 기존 폴더를 백업한 뒤 새 버전으로 교체하세요.

Python 3.10 이상과 한글 글꼴이 필요합니다. 스킬 폴더에서 실행합니다.

```sh
python -m pip install -r requirements.txt
```

Windows의 맑은 고딕, macOS의 AppleGothic, Linux의 NanumGothic 등 한글 TrueType 글꼴을 검색합니다. 글꼴을 찾지 못하면 보고서 생성기에 `--font /경로/한글글꼴.ttf`를 지정하세요. PDF 스킬이 있으면 함께 활용하지만 특정 플러그인이나 Google Drive 연결은 필수가 아닙니다.

## 포함 기준

- 공통: 관찰 근거, 기재 제한과 예외, 문체·표기, 임원 기간, 출결, 봉사, 학생·영역 대응.
- 초등: 통합 교과·창체, 진로희망 미입력 허용, 초등 수상·자격증 제한, 특수교육 기본 교육과정.
- 중등: 2026 학년별 창체 서식, 자유학기, 일반 학기와 자유학기 세특 차이, 독서 입력·중복 예외.
- 고등: 1·2/3학년 교육과정 구분, 수상·자격증 전용 칸, 세특 제한과 탐구 예외, 학교 밖 교육, 대입 미제공과 기재 금지의 차이.

[교육부 2026학년도 기재요령 안내](https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=316&boardSeq=105372&lev=0&searchType=null&statusYN=W&page=1&s=moe&m=0302&opType=N)를 바탕으로 독립 작성했습니다. [출처·적용범위](skills/review-student-records/references/sources.md)에 문서 버전·쪽수 기준과 한계를 적었습니다. 교육부 인증 도구가 아니며, 모든 학교 규정·성적 계산·학폭 조치의 적합성을 보증하지 않습니다. 이전 학년도와 근거 부족 항목은 확인 필요로 남깁니다.

## 처리 구조

모델이 원문과 기준을 읽고 판단하며, Python 스크립트는 추출·후보 탐지·주석·보고서·일치 검증을 담당합니다. 키워드 검색만으로 공식 규정 위반을 확정하지 않습니다.

```sh
cd skills/review-student-records
python scripts/extract_records.py input.pdf --outdir work
# 표선 없는 문서나 개인별 생기부는 페이지 모드로 원문 좌표를 확보합니다.
python scripts/extract_records.py input.pdf --layout pages --outdir work-pages
# 모델이 references/output-contract.md에 따라 issues.json과 meta.json을 작성합니다.
python scripts/build_marked_pdf.py input.pdf --issues work/issues.json --output input_점검표시본.pdf
python scripts/build_report_pdf.py --issues work/issues.json --meta work/meta.json --output input_오류보고서.pdf
python scripts/verify_review_outputs.py --source input.pdf --marked input_점검표시본.pdf --report input_오류보고서.pdf --issues-json work/issues.json
```

스크립트는 기존 결과 파일을 덮어쓰지 않습니다. 다시 실행할 때 새 출력 이름을 사용하세요. 스캔 PDF는 OCR과 원본 대응 확인이 추가로 필요하며, 인식할 수 없는 페이지를 점검 완료로 처리하지 않습니다.

## 검증

```sh
python skills/review-student-records/tests/regression.py
python skills/review-student-records/tests/standard_outputs.py
```

합성 PDF로 표기 후보, 회전 좌표, 기존 주석·원본 본문 보존, 보고서만 있는 항목, 오류 0건, 긴 문장·특수문자, 덮어쓰기 방지, ID·주석 내용 대응을 검사합니다. 실제 학교급별 모든 출력 양식과 모델의 규정 판단 정확성을 보증하는 테스트는 아닙니다. 결과 PDF의 페이지별 육안 확인을 병행하세요.

## 자료 취급

학생 원본·점검 결과·중간 추출물에는 개인정보가 들어갈 수 있으므로 공개 저장소에 올리지 않습니다. 이 저장소에는 원본 기재요령 PDF나 학생 자료가 포함되지 않습니다. 로컬 스크립트 실행과 모델에 전달되는 파일 내용은 구분해서 사용하세요.
