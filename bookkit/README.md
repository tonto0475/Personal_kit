# bookkit — 과제 파악 책 조립 키트

과제(README · uploads CSV)를 받으면 **v3 «과제 파악 책»** 과 같은 구조 · 품질의 책(HTML 한 파일 · A4 두 쪽 펼침 · 조작 블록 · 쪽 아래 각주)을 칸만 채워 찍어 낸다.
양식은 v3 의 장 구성 · 블록 순서 · 상자 · 그림 · 조작 블록을 그대로 떼어 낸 것이다 — **양식 + v3 내용 = v3 와 블록 169개가 같다**(`books/_selftest_v3` · 펼침 17장 픽셀까지 같다).
**병렬로 10분** — 받은 자료 스캔 A0 · 분석 셋(A1 · A2 · A3)이 계약 json 을 동시에 쓰고, 집필 여섯(W1~W6)이 장마다 다른 칸 파일을 동시에 쓰고, MAIN 이 합친다(`cards/README.md`).
⭐ 벤치마크 = `book_example/` 의 09(`task09/task09_kit.html` · 펼침 사진 `task09/Image/spread_*.png`) · 10(`task10_guide_v3.html` · 펼침 사진 `Image/spread_*.png`) — 같은 수준으로 만든다.
품질 기준은 `RULES.md`(점검표 5절 · 크기 6절). Codex 절차는 `.agents/skills/ontology/SKILL.md`(`$ontology` — 같은 분석 서브가 이어서 데이터 지도 `docs/ONTOLOGY.md` 도 채운다).

## 폴더

| 경로 | 무엇 |
|---|---|
| `engine/` | 책 엔진(과제 무관) — `build_book.py` 빌드 · `book/check_book.py` 헤드리스 검사 · `book/engine.py` 블록 API · `book/engine_live.py` 조작 블록 · `book/assets/` · `common.py`. 엔진 블록 설명은 `engine/book/README.md` |
| `template/` | **v3 구조 양식** — 장 파일 `pv`(한눈에) · `s1`~`s5` · `apx`(부록 A · B · C) · `shared.py`(그림 셋 · 재생기 셋) · `__init__.py`(META · 장 순서) = **구조만** · `kit.py`(분류 칩 · ◎ · 원본 줄 · 결함 표 · 칸 · 재생기 셋 · 추가 그림) · `figs.py`(그림) · `contract.py`(계약 → 칸 모양) |
| `template/content/` | **칸 파일** — 장마다 한 파일(`meta` · `pv` · `s1` · `s2` · `s3` · `s4_a` · `s4_b` · `s5` · `apx_a` · `apx_b` · `apx_c`) + `data.py`(계약 읽기 도우미) · `shared.py`(그림 · 재생기 = 계약에서) · `s4.py` · `apx.py`(두세 파일 합치기) |
| `contracts/` | 분석 결과 계약 형식(`README.md`) · 검사기 `check_contract.py` · 예시 `example/`(가짜 과제 + facts · reqs · steps) |
| `analysis/` | 과제 유형별 분석 틀 — `route_bundle.py`(경로 · 묶기) · `dispatch_sim.py`(배차 · 사건 시뮬레이션) · `schedule_assign.py`(일정 · 배정) · `coverage_place.py`(배치 · 덮기) · `stat_model.py`(측정 · 관리도 — 성분 분해 · 이상 잡기) · `_common.py`. `load()` 만 고치면 steps.json 이 나온다 |
| `cards/` | 역할 카드 — 분석 A1 · A2 · A3 · 집필 W1~W6 · 합치기 M · 나눠 주는 말(`README.md`) |
| `notes.py` | 책 스티커 — 유저 질문 목록 · 답 달기(아래 «책 스티커») |
| `new_book.py` | 새 책 시작 — template 을 `books/<이름>/` 로 복사(+ `contracts/` · `work/`) |
| `books/` | 만든 책들(공개 저장소에 올리지 않음 · .gitignore). `_selftest_v3` = 양식 + v3 내용을 계약으로 다시 담은 것(동일성 시험 · `v3calc/export.py` = v3 분석 → 계약) |
| `book_example/` | 벤치마크 — 09 `task09/task09_kit.html` + `task09/Image/spread_*.png`(20장) · 10 v3 `task10_guide_v3.html` + `Image/spread_01~17.png` · `task10v3_source/`(원본 패키지) · `template_examples.md`(양식 칸 예시). 공개 저장소에 올린다 · 동일성 시험 정본은 로컬 `books/_selftest_v3/gold/` |

## 내용이 들어가는 길

```
과제 원본 ─ A1 ─→ contracts/facts.json ─┐
          ─ A2 ─→ contracts/reqs.json  ─┼→ content/data.py 도우미 ─→ content/<장>.py 의 fill() ─→ 장 파일 build()(구조) ─→ html
          ─ A3 ─→ contracts/steps.json ─┘        (목록 · 그림 · 재생기 · 표는 자동)      (W1~W6 은 글 칸만)
```

- 장 파일(`s1.py` …) = 머리 import 한 줄(`from .content.s1 import fill`) + `# ══ 구조` 아래 `build()` — **고치지 않는다**(빌드가 «구조 바뀜: 파일 — 몇째 줄» 로 알린다)
- 칸 파일(`content/s1.py` …) = `fill()` 하나 — 칸 이름 · 주석(«무엇을 넣나 · 분량»)은 옛 장 머리 그대로 · 예시는 «예: book_example/template_examples.md · 칸 이름»(v3 문구). 한 사람이 자기 칸 파일만 고친다 → 동시에 써도 충돌 없음
- 칸이 비면 책에 빨간 «⟦빈 칸 — 장 · 이름⟧» 이 보이고 빌드 끝에 목록이 나온다
- 빌드는 계약 json 만 읽는다(계산을 다시 돌리지 않는다) — `_selftest_v3` 기준 빌드 0.1초(전 2.1초) · 명령 전체 0.8초(전 3.0초)

## 명령(키트 폴더에서 · 리눅스 python3 3.10 이상 · 윈도우는 py -3)

```
python3 bookkit/new_book.py <이름>                                     새 책 — 과제 폴더 = 키트 루트 task_copy/(지급 자료 복사본 · 없으면 안내 후 멈춤 — 원본을 위로 올라가며 찾지 않는다)
python3 bookkit/new_book.py <이름> --task <과제 폴더>                   다른 폴더를 줄 때(연습 · 시험)
python3 bookkit/contracts/check_contract.py bookkit/books/<이름>/contracts [--task <과제 폴더>] [--render]    계약 검사 → PASS / FAIL
python3 bookkit/analysis/<틀>.py --demo --out /tmp/steps.json           분석 틀을 가짜 데이터로 돌려 보기
python3 bookkit/engine/build_book.py bookkit/books/<이름>                빌드 → bookkit/books/<이름>/dist/<이름>__v<N>_<판 이름>.html(새 판 = 새 파일) + <이름>.html(최신 복사본) · versions.json(판 목록) · 빈 칸 · 구조 바뀜 · 각주 · 표 경고 목록
python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 2 --label 정원우선   방향을 바꾼 판 → dist/<이름>__v<N>_정원우선.html(판은 덮어쓰지 않는다 — 앞 판 html 은 그대로 남는다)
python3 bookkit/engine/build_book.py bookkit/books/<이름> --strict       완성 확인 — 빈 칸 · 구조 바뀜이 하나라도 있으면 종료 코드 1
python3 bookkit/engine/build_book.py bookkit/books/<이름> --only pv,s1   일부만 → dist/_partial/(집필 카드가 자기 장 확인용)
python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 1 --strict   1차판 — 1장 · 3장 · 5장(나머지 장 · 빈 칸은 회색 «2차판에서 채워짐» · strict 는 구조 바뀜만)
python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 1 --chapters s1,s3,s5,s4 --label 4장까지 --strict   중간판 — 끝난 장까지 싣는다(나머지 장 · 빈 칸은 회색 · strict 는 구조 바뀜만 · 앞 판 대비 «새로») → dist/<이름>__v<N>_4장까지.html
python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 2 --strict   2차판 — 전부 · 빈 칸 0 · 1차판 뒤 새로 생기거나 바뀐 블록에 «새로» 띠
python3 bookkit/contracts/check_contract.py <폴더> --add-ids                  항목 id 가 빠진 곳만 채운다(R1 · H1 · S1 · Q1 · B1 · T1 · D1 · F1 · P1 · C1)
python3 bookkit/notes.py list | answer <id> "답"                             책 스티커 — 아래 «책 스티커»
python3 bookkit/engine/book/check_book.py <html>                         검사(PC 두 페이지 · 폰 한 페이지 — 쪽 넘침 · 가로 넘침 · 각주 · 연결고리) → PASS / FAIL
python3 bookkit/engine/book/check_book.py <html> --spreads all --spread-name "spread_{:02d}.png" --shot-dir <폴더>    두 쪽 펼침마다 PNG
```

- 검사 · 캡처는 playwright + Chromium 이 있어야 한다. 없으면 **«SKIP — … (PASS 아님)»** 을 찍고 종료 코드 0 — 그때는 `RULES.md` 6절 크기 기준으로 미리 지킨다
- 빌드 · 계약 검사 · 분석 틀은 표준 라이브러리만으로 돈다(분석 스크립트 work/a1.py 등은 pandas · numpy 를 써도 된다 — 키트 requirements.txt). 3.10 ~ 3.14

## 판 · 블록 ID

- **두 번 내보내기**: 1차판(`--stage 1`) = 1장(요구 · 숨은 요구) · 3장(README 에서 나온 질문) · 5장(시스템) — A2 · W1 · W6 · W2(3장)만 끝나면 낸다. 2차판(`--stage 2`) = 전부. 순서 · 카드는 `cards/README.md` «두 번 내보내기»
- **중간판**(`--stage 1 --chapters <실을 장 전체> --label <이름>`): 장이 끝날 때마다 지휘가 낸다 — META `stage1` 대신 이 장 목록을 싣고 나머지는 1차판처럼 회색(`--strict` 는 구조 바뀜만) · 판 이름 = `--label`(없으면 «중간판») · versions.json 에 `chapters` 로 남는다
- 판 표시: 첫 블록 위 «1차판 · 알고리즘 · 함정 준비 중» / «2차판» · 쪽 머리글(META `editions`)
- «새로» 띠: 판을 줄 때마다 빌드가 `dist/<이름>.blocks.json`(블록 ID → 내용 해시)를 남기고, 다음 판에서 새로 생기거나 바뀐 블록 왼쪽에 빨간 세로 막대를 단다(글자표는 본문을 가려서 없다 · 판 목록의 «새로» 수는 그대로 · 사람 · AI 가 표시하지 않는다)
- 블록 ID = «장-칸 이름»(s1-무엇을) · 계약 항목은 «장-항목 id»(s3-Q1 · s1-S2 · aA-F3) — 판이 바뀌어 블록 수가 달라져도 읽던 위치 · 스티커 자리가 그대로. 책의 번호(«질문 3» · 표 «#»)도 항목 id 숫자
- 4장 머리 «자료 정리 전 · 2차판 갱신»: steps.json `"data": "raw"`(A3 이 A1 자료 정리 전에 계산)
- v3 동일성: `python3 bookkit/engine/same_v3.py [--png <폴더>]` — `_selftest_v3` 를 `--stage 2 --strict --v3-compat`(옛 블록 ID · 판 표시 · «새로» 끔)로 빌드해 v3 정본과 블록 169 바이트 · 펼침 17장 픽셀 비교 · 판 시험 `python3 bookkit/engine/test_stage.py` · 서식 시험 `python3 bookkit/engine/test_format.py`(모델이 칸을 v3 와 다르게 채우기 쉬운 곳 — 양식이 v3 모양으로 그리고 · 빌드 «서식:» · 계약 검사 «v3 한도» 가 잡는지)
- 서식 점검: 빌드 끝 «서식 경고 N개 — 서식: …»(v3 보다 긴 문단 · ◎ · 표 행 · 절 제목 번호 · 굵게 빠짐 · 2차판의 ⟪⟫) · «식 글자 남음»(책에 «{F[…]}» 가 글자 그대로 = `--strict` 실패) · 한도는 RULES.md 6절 «칸 길이표»

## 책 스티커(유저 질문 → 2ND 서브가 답)

책 html 을 devview 페이지 서버(포트 = devview + 100 · 주소 `/bookkit/books/<이름>/dist/<이름>.html`)로 열면 오른쪽 아래 메모 버튼으로 스티커(질문)를 붙일 수 있다. 답은 2ND 의 서브가 아래 명령(**bookkit 스티커 명령 = `bookkit/notes.py`**)으로 달고, 답이 달리면 그 스티커는 화면에서 빠지고 책 아래 «질문 줄» 행(«Q1. 짧은 제목» — 지금 펼친 쪽 것만)으로 간다. 행을 누르면 질문 · 답 · 꼬리 질문(행 안 🪄)이 펼쳐진다.

```
python3 bookkit/notes.py list                          답 없는 스티커(모든 책) — [id] 시각 · 책 · 블록 ID · 자리(쪽 · 장 · 절 · 블록 글) · 질문
python3 bookkit/notes.py list --all [--book <이름>]     답한 것까지 · 그 책만
python3 bookkit/notes.py answer <id> "답" --title "짧은 제목"   답 달기(다시 하면 바꿈 · 줄 바꿈은 \n · 제목 = 질문 줄 행 이름 · 40자)
python3 bookkit/notes.py answer <id> --file <답.md>      긴 답은 파일에서
python3 bookkit/notes.py answer <id> --thread <꼬리 id> "답"   꼬리 질문 답(list 에 «꼬리 [t1] … 답 대기» 로 나온다)
python3 bookkit/notes.py list --flowtree <tree.json>   (선택 · 기본 끔) 답 없는 스티커를 flowtree 질문 노드로도(한 번만)
```

- 저장 위치: 책 폴더의 `notes.json`(`bookkit/books/<이름>/notes.json` — 작업 폴더 안 · 커밋하지 않는 폴더). devview 페이지 서버가 책 html 옆 상대 경로 `api/notes`(GET · POST · PATCH · DELETE)로 쓴다 — 페이지 서버의 다른 경로는 읽기 전용 그대로
- 항목: `{id, ts, doc, slide, x, y, w, h, ctx, text}` + 답 `answer` · `answer_ts` · `title` · 마법봉 `magic_rid` + 꼬리 질문 `thread: [{id(t1 …), q, ts, magic_rid, a, a_ts}]`(옛 항목 = title · thread 없음 그대로 읽힘). 꼬리 경로 = `POST …/api/notes/<id>/thread {q}` · `POST …/api/notes/<id>/thread/<꼬리 id>/magic`(409 = 그 꼬리가 답 대기 중 · 원 질문 재요청과 따로 판정) · 책 주소 `#note=<id>&t=<꼬리 id>` = 그 쪽 · 그 행 펼침. 자리 = `ctx` 의 `b=<블록 ID>` — 블록 ID 가 고정이라 1차판에 붙인 스티커가 2차판에도 같은 블록에 붙는다
- 답은 그 칸 · 계약을 읽고 쓴다. 책 내용을 고쳐야 하는 질문이면 답에 무엇을 고칠지 적고 그 칸 담당(카드)에게 넘긴다 — 고친 뒤 다시 빌드하면 바뀐 블록에 «새로» 가 붙는다
- 스티커 🪄(접수된 스티커 «수정» 왼쪽): 페이지 서버 `POST …/api/notes/<id>/magic` → 2ND 마법봉(답 자리 note) → 2ND 가 블록 맥락을 읽고 `magic.py answer-note` 로 답(같은 notes.py) · 2ND 미연결이면 «2ND 미연결» · 새 단추는 책을 다시 빌드해야 생긴다
- 시험: `python3 bookkit/engine/test_notes.py`(빈 포트에 devview · 헤드리스 — 책 열기 → 스티커 → notes.json → answer → 2차판 새로고침 뒤 답)

## 흐름

1. **새 책** — `new_book.py`
2. **A0 뒤 분석 동시 → 1차판** — A0 가 끝나면 A2 README → reqs · A1 자료 함정 → facts(파일 4개 이상이면 둘로) · A3 분석 틀 → steps 를 같이 시작(카드 `cards/A1~A3.md`) · A2 PASS 뒤 W1 · W6 · W2(3장) → `--stage 1`(유저에게 경로) · 끝 신호 = 계약 검사 PASS · PASS 뒤 같은 A 서브가 «이어서 지도»(데이터 지도 — 각 카드 맨 아래 절)
3. **집필** — 계약 없이 쓸 칸 전부 먼저 → 계약별로 PASS 되는 대로 숫자 칸만(steps → W4 · W5 · facts → W2 · W3 · 카드 `cards/W1~W6.md`) · 끝 신호 = `--only` 빌드에서 자기 칸 빈 칸 0 · 장이 끝날 때마다 지휘가 중간판(`--chapters`)
4. **합치기 → 2차판** — 계약 셋 교차 검사 → `--stage 2 --strict` · check_book · 결과 경로(카드 `cards/M.md`)
5. **읽기** — 결과 html 을 devview 로 연다. 스티커 질문은 2ND 서브가 `notes.py` 로 답한다(위 «책 스티커»)

혼자 할 때는 같은 카드를 위에서 아래로 차례로 한다.
