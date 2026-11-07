# skeleton — 뼈대: 문제 파악 직후 명세 없이도 깔 수 있는 틀

> 과제를 받자마자(1-1 의 A 카드와 함께) 서브에게 맡겨 **어느 과제에나 들어가는 틀**을 먼저 깐다. 담당자 답 · 유저 결정이 오기 전에도 만들 수 있는 것만. 업무 판단이 필요한 자리는 **설정 칸으로 비워 둔다**.

## 1. 흐름
1. 과제 README · 자료 파일을 받는다(bookkit A 카드와 같은 때)
2. **K0 · K3 · K5 는 바로 서브에게** — 카드(cards/)와 키트 README 만으로 된다(유저 확인 없음)
3. 계획표 초안: `python3 skeleton/plan.py --task <과제 폴더> [--book bookkit/books/<이름>]` → `skeleton/out/plan.json · plan.md`(묶음 · 파일 · 함수 이름 · 비워 둘 설정 칸 · 근거). 이름 칸 «다듬을 칸» 은 서브가 다듬는다
4. **K1 · K2 · K4 는 hand_off 의 파일 · 함수 표를 유저가 확인한 뒤** — 계획표(파일 · 함수 이름)를 hand_off 작업 개요의 «뼈대 파일 · 함수 표» 에 옮기고 유저가 이름을 고쳐 확인 → 확인된 줄만 서브가 구현(유저가 고친 이름 우선 · CODE_RULE 9-1). flowtree 는 2차판 시점에 쉬운 것만 초안($graph 준비판 · 이 계획표가 재료) → 논의 뒤 보강할 때 `skeleton/to_flowtree.py`(완료 노드로 붙이기)로 뼈대 결과를 완료 노드로 붙인다
5. 부품 복사: `python3 skeleton/copy_parts.py K0`(묶음 이름 또는 lib 경로) — src · tests · 루트로 복사 · `from lib.` 을 복사한 자리로 · WORKLOG 한 줄
6. 끝 확인: `python3 skeleton/check.py --task <과제 폴더>` — 새 DB → 자료 적용 → 기본 계산 → 앱 기동 · 주요 경로 → 종료 · 단계마다 통과 · 실패 · 건너뜀 한 줄

## 2. 묶음
| 묶음 | 무엇 | 확인 없이 시작 | 카드 |
|---|---|---|---|
| K0 | 실행 · 배포(run.sh · Dockerfile · compose · /health · .env.example · 로그 · 설정) | 예 | cards/K0.md |
| K1 | 입력 파이프라인(자료 파일마다 읽기 함수 + 검사 리포트 — 보고만) | 아니오 | cards/K1.md |
| K2 | 저장 · 적용(SQLite · 판 번호 · 검사 통과 → 한 번에 적용 · 같은 요청 두 번) | 아니오 | cards/K2.md |
| K3 | 화면 틀(앱 껍데기 · 업로드 → 미리보기 → 검사 결과 · 결과 표 · 지도 · 시간표 자리 · 역할별 화면 자리) | 예 | cards/K3.md |
| K4 | 계산 자리(core 에 «정리된 표 → 결과» 함수 하나 + 기본 규칙) | 아니오 | cards/K4.md |
| K5 | 시험 틀(conftest · 같은 요청 두 번 · 경계값 · 냉시동) | 예 | cards/K5.md |

## 3. 진입점 — check.py 가 부르는 함수
- 계획표 `entry` 칸이 «모듈:함수» 를 정한다. 유저가 이름을 바꾸면 그 칸도 같이 바꾼다(또는 `check.py --entry K1=src.core.입력:전부_읽기`)

| 묶음 | 받는 것 → 돌려주는 것 |
|---|---|
| K1 | 과제 폴더 경로 → `{"tables": {표 이름: 행 목록 · DataFrame}, "report": [{"file", "line", "kind", "raw"}]}` |
| K2 | (DB 경로, K1 의 tables) → `{"version": 판 번호, "rows": {표 이름: 행 수}}` — 같은 자료를 두 번 넣어도 행 수가 같아야 한다 |
| K4 | K1 의 tables → 결과(비어 있지 않은 dict · 목록) |
| K0 · K3 | `python3 -m <앱 모듈>` 을 PORT · DB_PATH 환경변수로 띄워 `/health` 와 계획표 `pages` 를 부른다 |

## 4. 만들지 않는 것(설정 칸으로만 비워 둠)
- 업무 기준값(정원 · 시각 · 임계값 · 단가) — `config/config.yaml` 에 이름만 · 값은 «?» 주석
- 함정 처리 결정(결측 · 중복 · 형식 오류를 고칠지 · 버릴지) — K1 은 **보고만**, 처리 칸은 비움
- 최적화 목표(무엇을 최소로 · 최대로) — K4 는 기본 규칙 하나 · 목표 칸은 비움
- 화면 세부(문구 · 배치 · 색 세부) — K3 는 자리만 · «데이터 없음» 빈 상태
- 묶음마다 끝 신호는 **시험 명령 통과**(카드 «끝 신호»)

## 5. 파일
| 파일 | 무엇 |
|---|---|
| plan.py | 과제 폴더 + bookkit 분석 결과(있으면) → 계획표 초안(out/plan.json · plan.md) |
| to_flowtree.py | 뼈대로 만든 결과 → flowtree 완료 노드로 붙이기(논의 뒤 보강할 때) — `--bundles K0 K3 …` · `--section <값>` · `--map K1=<값> …` · `--graph hand_off\|task` · `--dry`(미리 보기) · `--plan` · `--tree` · 이미 있는 제목은 건너뜀. 값이 섹션 번호 0~8 · 틀 작업 id(`s2-t3` = 그 칸부터) = 새 노드 없이 빈 틀 작업 칸을 위에서부터 fill → start → done(칸이 모자라면 다음 섹션 · 섹션 8 까지 없으면 실패로 남은 묶음 보고) · 값이 그 밖의 노드 id = Main 방식 — 그 밑에 add → start → done · 값이 없으면 «뼈대(skeleton)» 노드를 만들어 그 밑에 |
| copy_parts.py | lib 부품 → src · tests · 루트 복사(이미 있으면 안 덮음) · import 바꿈 · WORKLOG 덧붙이기 |
| check.py | 냉시동 한 바퀴 판정 |
| out/ | 계획표 출력(커밋 안 함) |
- 시험: `python3 -m pytest -q skeleton`
