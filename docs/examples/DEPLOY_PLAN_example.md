# 배포 계획서 — 설비 점검 기록 앱 (예시)

> 🔴 이 파일은 **예시**다. 가상 과제(설비 점검 기록 — 점검 입력 · 목록 · 불량 집계)로 채웠다. 줄 번호 · 시각 · 출력 · 해시는 가짜다.
> 양식 원본은 docs/DEPLOY_PLAN.md — 칸 이름(굵은 글씨)을 그대로 쓴다.

## 0. 이 기계 ($ready-start 세션)
- **docker**: C6 DOCKER 없음(명령 없음) → 컨테이너 빌드 · 실행 확인 불가 · run.sh 로 같은 명령 · 포트를 확인
- **확인 시각**: 19:12 · bash scripts/envcheck/envcheck.sh --no-install

## 1. 과제가 요구한 배포 방식 (근거 = 과제 문서 원문)
- **README 원문**: 41행 «The application must be runnable as a container.» · 43행 «Fill in HOW_TO_RUN.md so that reviewers can start the app.» ($ready-start grep) · 52행 «Reviewers will use the same commands for every submission.»(MAIN 이 더함)
- **컨테이너 요구**: 필요
- **제출 문서 양식**: HOW_TO_RUN.md · AI_COLLABORATION.md(둘 다 유저가 직접 쓴다)
- **빌드 위치**: <루트> — README 에 위치 말이 없음 → 저장소 루트에서 docker build . 로 본다

## 2. 실행 형태 (MAIN · 구현하며 고친다)
- **로컬 실행**: bash run.sh
- **컨테이너**: docker build -t app . · docker run --rm -p 3000:3000 -v app-data:/app/data app
- **포트**: 3000 · 0.0.0.0
- **데이터 · DB 위치**: SQLite 파일 data/app.db(환경변수 DB_PATH) · 컨테이너는 /app/data 볼륨 · 켜질 때 표가 없으면 만든다
- **설정(환경변수)**: PORT = 3000 · DB_PATH = data/app.db · DEFECT_LIMIT = 3(연속 불량 알람 기준) — 바꾸는 곳: 로컬은 명령 앞에, 컨테이너는 -e
- **시험 계정**: inspector / inspect123 — 켜질 때 없으면 만든다(비밀번호는 환경변수 TEST_PASSWORD 로 바꿈)
- **기본 데이터**: 켜질 때 설비 3대 · 점검 기록 20건(고정 시드 42) — 매번 같은 목록
- **/health**: DB 열림 · 표 3개 존재 → 하나라도 실패면 503
- **주요 API**: GET /api/inspections · POST /api/inspections · GET /api/summary

## 3. 확인 방법 (무엇을 무엇으로)

| 무엇 | 무엇으로 | 기대 |
|---|---|---|
| 기동 | 유저 터미널 탭에서 bash run.sh | «Uvicorn running on http://0.0.0.0:3000» |
| /health | curl -s -w " %{http_code}" http://127.0.0.1:3000/health | 200 |
| 주요 API | curl GET /api/summary · POST /api/inspections | 200 · 201 + 본문 |
| 화면 핵심 흐름 | 유저가 Browser 도구 — 로그인 → 점검 추가 → 목록에 1줄 | 목록 21건 |
| 시험 | python3 -m pytest -q tests | 실패 0 |

- **막히면 대안**: docker 불가(0절) → run.sh 로 같은 포트 · 같은 환경변수로 확인하고 WORKLOG 에 «이 환경에서 컨테이너를 실행하지 못함» 한 줄(유저가 실행 문서에 반영) · Dockerfile 은 정적 점검(ready_end.py R8)만

## 4. 결과 ($ready-end 1-1 이 채움 — 명령과 실제 출력)

### ① 준비
- **만든 · 고친 파일**: Dockerfile · .dockerignore(lib/deploy 양식 · 포트 그대로)
- **계획과 달라진 칸**: 주요 API · GET /api/stats → GET /api/summary · 담당자 용어에 맞춤

### ② 구동
- **명령**: bash run.sh (유저 터미널 탭 · docker 불가라 대안)
- **실제 출력**: «NiceGUI ready to go on http://0.0.0.0:3000» · «시드 적재 — 설비 3 · 점검 20»

### ③ 정상 동작 확인

| 무엇 | 명령 | 실제 출력 · 상태 코드 | 판정 |
|---|---|---|---|
| /health | curl -s -w " %{http_code}" http://127.0.0.1:3000/health | {"ok": true, "db": true} 200 | 🟢 |
| 주요 API | curl -s http://127.0.0.1:3000/api/summary | {"total": 20, "defect": 4} 200 | 🟢 |
| 화면 핵심 흐름 | 유저가 Browser 도구로 로그인 → 점검 추가 | 목록 21건 · 유저 확인 | 🟢 |
| 시험 | python3 -m pytest -q tests | 31 passed | 🟢 |

- **못 한 것 · 이유**: docker build · run — 대회 기계에 docker 없음(0절) · Dockerfile 은 R8 통과
