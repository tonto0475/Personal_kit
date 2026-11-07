# 분석 결과 계약 — facts.json · reqs.json · steps.json

분석(A1 · A2 · A3)과 집필(W1~W6)이 **동시에** 일하게 하는 경계다. 분석은 계약 json 만 쓰고, 집필은 계약만 읽는다(분석 스크립트를 다시 돌리지 않는다). 빌드도 계약만 읽는다 — 계산을 다시 돌리지 않아 빌드가 1초 안쪽이다.

- 자리: `bookkit/books/<이름>/contracts/` — 파일 하나 = 분석 카드 하나(A1 → facts · A2 → reqs · A3 → steps). 서로 다른 파일이라 동시에 써도 충돌하지 않는다
- 검사: `python3 bookkit/contracts/check_contract.py bookkit/books/<이름>/contracts [--task <과제 폴더>] [--render]` — PASS 가 «분석 끝» 신호
- 예시: `contracts/example/`(가짜 과제 «부품 순회 운반» — `example/task/` 에 README · uploads 까지) · v3 전체: `books/_selftest_v3/contracts/`(공개 저장소에는 없을 수 있다)
- 책이 읽는 길: 장 content 파일 → `content/data.py` 의 도우미(`D.facts()` · `D.trap_cards()` · `D.player("채우기")` …) → 계약. 목록 칸(함정 · 질문 · 숨은 요구 · 결함 …)은 도우미가 칸 모양으로 바꿔 넣으므로 집필은 글 칸만 쓴다

## 공통 규칙

| 규칙 | 내용 |
|---|---|
| 머리 | `"contract": "facts" \| "reqs" \| "steps"` · `"version": 1` · `"task": 과제 이름` |
| 항목 id | 목록 항목마다 `"id"` = 접두 + 번호 — readme `R` · hidden `H` · silent `S` · questions `Q`(main = true) / `B`(부록 B) · traps `T` · defects `D` · facts `F` · report `P` · conditions `C`. 책의 번호(«질문 3» · 표 «#» · «사실 2»)가 id 숫자 그대로 · 블록 ID = «장-id»(s3-Q3) · flowtree `import-analysis` 의 출처 열쇠. 빠짐 · 겹침 · 접두 틀림 = FAIL · `--add-ids` 가 빈 곳만 채운다 · 다시 쓸 때 남은 id 는 바꾸지 않는다 |
| 숫자 | 글에 쓸 실측 값은 `numbers` 에 이름을 붙여 둔다(facts · steps 둘 다 가능 — 이름이 겹치면 steps 가 이긴다 · 검사기가 경고). 글 칸에서는 `{F['이름']}` — 빌드가 계산해 채운다. **손으로 적은 숫자 금지** |
| 분류 | `cat` = 화면 · 시스템 · 알고리즘 · 파이프라인 · 문서 중 하나 |
| 꾸밈 글 | 글 칸은 `**굵게**` · `!!빨강!!` · `++초록++` 를 쓸 수 있다 |
| 각주 | `"fn": {"용어": "(영문 전체 이름) 설명"}` — 용어는 **그 카드 글 안에 글자 그대로** 있어야 한다(없으면 빌드 실패). 본문에 ¹ 같은 표식을 손으로 넣지 않는다(이중 표식) |
| 원본 줄 조각 | `"raw": [[글, 색], …]` — 색 `null` = 설명 글(`{F['이름']}` · `**굵게**` 를 쓸 수 있다), `""` · `"bad"` · `"good"` = 원본 조각(글자 그대로 · 식을 쓰면 FAIL · `--task` 로 대조) |
| json 이 못 담는 것 | 짝 `(a, b)` → 목록 `[a, b]`(4개 이하 글자 · 숫자 목록은 빌드가 짝으로 되살린다) · 함수 칸은 표로(아래 steps 의 `measure` · `deadhead` · `place`) |

## facts.json — A1 자료 함정

```json
{"contract": "facts", "version": 1, "task": "…",
 "files":   [{"name": "orders.csv", "desc": "주문", "rows": 10}],
 "numbers": {"qty_total": 40, "qty_total_naive": 35},
 "traps":   [{"id": "T1", "file": "orders.csv", "lines": [4, 4], "what": "제목 한 줄", "cat": "파이프라인",
              "raw": [["정상", null], ["O02,P2,6,06:00", "good"], ["· 섞인 줄", null], ["O03,p3,5,06:00", "bad"]],
              "measured": {"정리한 값": 40, "그냥 읽은 값": 35},
              "naive": "그냥 하면 — 실측 틀린 숫자 !!빨강!! 1~2문장", "fix": "이렇게 — 처리 + 리포트에 남길 것 1~2문장",
              "big": true, "fn": {"짝": "…"}}],
 "defects": [{"file": "orders.csv", "what": "**무엇**(개수)", "bad": "원본 칸 그대로 · 둘째 원본 칸", "good": [["주문마다 한 줄", null]], "fix": "처리 두 문장", "fn": null}],
 "facts":   [{"title": "…", "cat": "알고리즘", "raw": [["orders.csv", null], ["O01,P1,4,06:00", ""]], "effect": "계획에 주는 영향(숫자)", "do": "이렇게"}],
 "report":  [{"file": "orders.csv", "line": 4, "kind": "작업장 번호 소문자", "raw": "p3", "action": "고쳐서 적용"}],
 "figures": {"그림_자료띠": {…figs.file_band 칸…}, "C_적용_그림": {…figs.txn 칸…}}}
```

| 칸 | 책 자리 | 개수(권장) |
|---|---|---|
| `traps`(big = true) | 2장 함정 ◎ 카드(실제 데이터 · 그냥 하면 · 이렇게) | 5~8 — 계획을 크게 바꾸는 것만 |
| `defects` | 부록 A 파일별 결함 표(파일 순서대로 묶고 표 하나 6행까지 — 넘으면 자동으로 나눈다) · 파일 순서 = 가장 큰 함정의 파일부터(함정이 가장 큰 파일 → 그다음 파일) · `bad` · `good` = 글자(« · » 로 나눈 조각마다 원본 칩 하나 — 원본에 글자 그대로 있는 값만) 또는 `[[글, 색]]`(색 `null` = 칩 없는 설명 글 — «키마다 한 줄» · «A 또는 B» 처럼 원본에 없는 말은 이쪽 · v3 와 같은 모양) | 전부 |
| `facts` | 부록 A 사실 ◎ | 8~12 |
| `report` | 부록 C 검증 리포트 예(이 자료의 실제 줄 · 줄 번호) | 6~8 |
| `figures.그림_자료띠` | 한눈에 · 2장 — 가장 큰 함정의 줄 구간 + 정리 전후 막대 | 1 |
| `figures.C_적용_그림` | 부록 C 전부 아니면 전무 실험 — `analysis/_common.py` 의 `txn_fig({파일: 행 수}, 실패 위치)` 가 sqlite 메모리 DB 로 실제로 넣어 본다 | 1 |

## reqs.json — A2 README 요구 · 질문

```json
{"contract": "reqs", "version": 1, "task": "…",
 "readme":    [{"group": "만들 것", "text": "README 원문 요지", "cat": "알고리즘", "make": "만들 것"}],
 "readme_fn": {"만들 것": {"트랜잭션": "(transaction) …"}},
 "hidden":    [{"text": "숨은 요구 한 줄", "where": "어디서 드러나나(파일 · {F['숫자']})", "cat": "파이프라인", "make": "만들 것"}],
 "silent":    [{"title": "README 가 말하지 않은 곳", "cat": "알고리즘", "why": "왜 문제인가(이 자료의 숫자 2~3문장)", "default": "기본 가정 1문장"}],
 "questions": [{"q": "예 · 아니오로 답이 나오는 질문", "cat": "알고리즘", "why": "이유", "rec": "추천(= 답이 없을 때 기본 가정)", "opp": "반대면 무엇이 바뀌나", "main": true}]}
```

| 칸 | 책 자리 | 개수(권장) |
|---|---|---|
| `readme` | 1장 README 원문 요구 — 같은 `group` 이 이어지는 줄이 한 표(묶음 4개 안팎 · 묶음마다 8행 안쪽). README 문장을 **빠짐없이**(제출 · 실행 환경 포함) | 전부 |
| `hidden` | 1장 숨은 요구 표(알고리즘 표 / 나머지 표 자동) | 8~12 |
| `silent` | 1장 말하지 않은 곳 ◎ | 7~10 |
| `questions` main = true | 3장 질문 ◎ — 번호 순서를 4장 선택표가 «질문 N» 으로 쓴다 | 5~8 |
| `questions` main = false | 부록 B 질문 ◎ | 6~10 |

A2 는 A1 · A3 와 동시에 일한다 — 숫자가 필요하면 `{F['이름']}` 자리만 두고 이름을 A1 · A3 와 맞춘다(검사기가 없는 이름을 알린다). 이름이 아직 없으면 문장에서 숫자를 빼고 집필에게 넘긴다.

## steps.json — A3 알고리즘 그림 · 재생기

```json
{"contract": "steps", "version": 1, "type": "route | dispatch | schedule | other", "task": "…", "data": "clean | raw",
 "numbers": {"A_len": 61.7, "B_len": 24.9},
 "players": {"채우기": {…}, "고치기": {…}, "이어붙이기": {…}},
 "figures": {"그림_큰흐름": {…}, "순서_지도": {…}, "C_화면_그림": {…}, "상태전이": {…}, "시각막대": {…}, "두줄비교": {…}},
 "tables":  {"순서_표": {…}, "전부세기_표": {…}, "조건별_표": {…}},
 "conditions": [{"name": "정원", "value": "12명", "result": {"차 수": 4}}]}
```

`data` = `"raw"` 면 자료 정리(A1 facts) 전에 계산한 값 — 4장 머리에 회색 «자료 정리 전 · 2차판 갱신»(없거나 `"clean"` 이면 표시 없음).

분석 틀(`bookkit/analysis/`)이 이 모양 전체를 낸다 — 경로 · 묶기형 `route_bundle.py` · 배차 · 사건 시뮬레이션형 `dispatch_sim.py` · 일정 · 배정형 `schedule_assign.py` · 배치 · 덮기형 `coverage_place.py`(`type` = `other`) · 측정 · 관리도형 `stat_model.py`(`type` = `other` · 재생기 칸에 `kind` — 아래 표 끝 세 줄). 틀을 `<책>/work/a3.py` 로 복사해 `load()`(입력 연결 칸)만 고친다.

| 칸 | 모양(양식 함수 설명이 정본) | 책 자리 |
|---|---|---|
| `players.채우기` | `kit.stepper_fill` 칸 — `title · task · caption · map · frame_title · right_title · words · cap · steps[{state, cur, text, row}] · table` | 한눈에 · 4장 방안 A |
| `players.고치기` | `kit.stepper_fix` 칸 + **`measure`: `{"곳a→곳b→곳c": 길이}`** — 단계마다 차 경로 전부의 길이(줄 글에 `{km}` 를 쓰면 필수) | 한눈에 · 4장 방안 B |
| `players.이어붙이기` | `kit.stepper_chain` 칸 — `timetable` 안 **`deadhead`: `{곳 a: {곳 b: 분}}`**(일에 나오는 곳 전부 × 전부) · **`place`: `{곳: 보일 이름}`** · `hm` 은 빼도 된다(«07:30» 기본) · `rows`(줄 수 · 10 넘으면 그림이 아래로 늘어난다 · 16 까지) · `heads` · `texts` = 단계 수 + 1 | 한눈에 · 4장 공통 단계 |
| `figures.그림_큰흐름` | `figs.overview` 칸 — 위 흐름 상자 글 + 아래 묶음 막대(열 4~12 · 열 아래 글 5자 안팎) | 한눈에 · 1장 |
| `figures.순서_지도` | `figs.orders_map` 칸 | 4장 첫 절 |
| `figures.C_화면_그림` | `figs.screens` 칸(계획에서 읽은 실제 값) | 부록 C |
| `figures.상태전이` · `시각막대` · `두줄비교` | `figs.states` · `figs.time_bars` · `figs.pair_rows` 칸 — 2 · 4 · 5장의 «추가_그림» 칸이 쓴다(선택) | 2 · 4 · 5장 |
| `players.채우기` · `고치기` 에 `"kind": "quiver"` | 지도 · 오른쪽 목록 대신 측정 화살표(`figs.quiver_map`) — `title · task · caption · plate{x, y, radius, scale, bar, unit} · right_title · frame_title · steps[{dx, dy, head, lines: [[글, 색]], limit, text, row}] · table` · 단계마다 dx · dy 개수 = 칸 수 · `limit` 보다 긴 화살표 빨강 | 4장 방안 A · B |
| `players.이어붙이기` 에 `"kind": "chart"` | 시간표 대신 관리도(`figs.control_chart`) — `title · task · caption · chart{points: [[x, 값, 줄 번호, 한계 밖?]], series, steps: [[점 번호 …]], center, ucl, lcl, unit, axis, ticks, words} · heads · texts`(= 단계 수 + 1) | 4장 공통 단계 |
| `figures.순서_지도` 에 `"kind": "arrows"` | 작은 지도 대신 화살표 두 판(`figs.arrows_pair`) — `x · y · radius · scale · unit · good{dx, dy, label} · bad{dx, dy, label}` | 4장 첫 절 |
| `tables.순서_표` · `전부세기_표` · `조건별_표` | 표 칸 `{"header", "rows", "bad_cells": [[행, 열 이름]], "good_rows", "bad_rows", "notes": {"행": [글, 색]}, "small": true, "caption"}` — 전부 세기 시간은 **실제로 잰 값**(분석 틀 `brute_table`) | 4장 |

재생기 크기 기준(RULES.md 6절): 재생기 표 8행 이하 · 단계 글 150자 이하 · 오른쪽 목록 8대 이하 · 지도 이름표는 점 위(아래는 `below`).

## 검사기가 보는 것

- 모양: 꼭 있어야 하는 칸 · 분류 이름 · 원본 조각 `[글, 색]` 짝 · 표의 `bad_cells` 열 이름 · 행 번호 범위 · 재생기 단계의 `row` · 경로 길이 표가 단계마다 경로를 다 담았나 · 빈 차 이동 표가 곳 전부 × 전부인가 · `heads` · `texts` 개수
- 숫자 자리: 글 안 `{F['이름']}` 의 이름이 `numbers` 에 있나(facts · steps 를 함께 검사할 때 없으면 FAIL)
- `--task`: 원본 조각 · 결함 «잘못된 예» · 리포트 줄이 원본 파일에 글자 그대로 있나(경고) · 줄 번호가 파일 줄 수 안인가
- `--render`: 그림 · 재생기 단계를 양식 함수로 실제로 그려 본다(실패하면 FAIL — 어느 칸인지 알린다)
- 항목 id: 빠짐 · 접두 + 번호 형식 · 겹침(`--add-ids` = 빈 곳만 채워 파일에 쓴다)
- 경고만(PASS 를 막지 않음): 개수가 권장 범위 밖 · 숫자 이름 겹침 · 쓴 차가 시간표 줄 수보다 많음
- 서식(경고 · v3 정본 계약의 칸 최대 + 약간 — 넘으면 책 모양이 v3 와 갈린다 · RULES.md 6절 «칸 길이표»): 칸 글자 수(hidden.text 28 · where 55 · readme.text 40 · silent.title 24 · traps.what 48 · naive 150 · fix 100 · ◎ 카드 전체 360 · facts.title 32 · effect 120 · defects.what 55 …) · 너무 짧은 이유 · 반대면(questions.why 25 · opp 20 · silent.why 35 이상) · README 묶음(5개 이하 · 묶음마다 3행 이상) · 지도(짧은 이름 5자 이하 · 그리는 점이 범위 한쪽에 몰림) · `--task` 면 결함 «정상 예» 초록 칩이 원본에 없을 때(설명 글이면 `[[글, null]]`)
- FAIL: 원본 조각(색 `""` · bad · good) · 결함 칩 글자에 `{식}` — 원본은 글자 그대로라 계산되지 않는다
