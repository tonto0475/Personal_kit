# 책 엔진 사용법 — `study_html\book\`

> **bookkit 에서 읽을 때** — 이 문서는 원래 엔진(study_html)의 설명서 사본이다. 블록 API(4~6절) · 조작 블록(11절)은 그대로 통한다.
> 다른 점: 책 폴더는 `bookkit/books/<이름>/`(경로를 인자로) · 출력은 그 책의 `dist/` · 빌드 끝에 «빈 칸 · 구조 바뀜» 도 알린다 · `--strict` ·
> check_book 은 브라우저가 없으면 SKIP · `--spreads all --spread-name`. 명령과 흐름은 `bookkit/README.md`, 양식 칸 규칙은 `bookkit/RULES.md`.
> 아래 «pandas 책 · 2~4부 집필 서브 · tests\» 이야기는 원래 엔진의 기록이다(bookkit 에는 tests 폴더가 없다).

학습용 «책»(A4 두 쪽 펼침 · 자동 쪽 나누기 · 각주 · ↩ 연결고리 · 예시 데이터 스위치 · 스티커 메모)을 만드는 범용 엔진.
흐름 규칙은 `C:\Users\sis99\.claude\policy\education.md`, 『Pandas — 표로 생각하기』 설계도는 `pandas\PLAN.md`.

## 1. 파일

| 파일 | 하는 일 |
|---|---|
| `engine.py` | 블록 API(Writer) · 글 꾸밈 · 표 · 그림 · 각주 · 차례 · 용어 찾아보기 · HTML 조립(Book). 과목과 무관 |
| `assets\book.css` · `assets\book.js` | 판형 · 쪽 나누기 · 보기 모드 · 목록 · ↩ 이동과 돌아가기 · 스위치 · 스티커. 빌드 때 HTML 에 인라인 |
| `engine_live.py` | 조작 블록(단계 재생기 · 조건 슬라이더 · 크게 열기) — 11절. 쓰는 책만 불러온다 |
| `check_book.py` | 헤드리스 검사(쪽 넘침 · 가로 넘침 · 각주 · 연결고리 · 장별 쪽 수) + 쪽 PNG |
| `tests\test_book_ui.py` | 화면 동작 대표 검사(넘김 · 목록 · ↩ · 돌아가기 · 스위치 · 모드 · 폰 · 스티커 가짜 API) |
| `tests\test_engine_integration.py` | 엔진 연결 검사(장 파일 추가 흉내 → 부 여는 쪽 · 차례 · 링크 · 찾아보기 자동 연결, 스티커 질문 상자, 꾸밈 글 안전장치) — 결과는 임시 폴더 |
| `tests\test_live.py` | 조작 블록 검사(단계 · 슬라이더 · 예측 · 넘김 제외 · 읽기 기록 · 폰) — 11절. 결과는 임시 폴더 |
| `..\build_book.py` | 빌드 명령 |
| `pandas\__init__.py` | 책 정보 META · 모듈 순서 ORDER |
| `pandas\data.py` | 공통 데이터(«어느 팹의 하루 기록») — 2~4부는 **읽기만** |
| `pandas\front.py` · `ch00.py` ~ `ch05.py` | 표지 · 읽는 법 · 차례 · 0장 · 1부(1~5장) |

## 2. 명령

```
py -3 build_book.py pandas                         전체 → dist\pandas_book.html
py -3 build_book.py pandas --only 6-10,case_a      일부 → dist\_partial\pandas_book__6-10_case_a.html
py -3 book\check_book.py dist\pandas_book.html     검사(PC 두 페이지 · 폰 한 페이지) — PASS 여야 한다
py -3 book\check_book.py <html> --shots 20,21 --spreads 10 --shot-dir <폴더>     쪽 · 펼침 PNG
py -3 book\tests\test_book_ui.py [html]            화면 동작 대표 검사
```

- `--only` : 숫자 · 범위는 장 번호(`6-10` → ch06 ~ ch10), 그 밖은 모듈 이름(`front` · `case_a` · `appendix`). 일부 빌드는 출력 이름이 달라 전체 판 · 다른 사람의 판을 덮어쓰지 않는다
- ORDER 에 있는데 파일이 없는 모듈은 건너뛴다. **장 파일 하나를 `book\pandas\` 에 만들면** 차례 · 목록 · 부 여는 쪽 질문 목록 · 용어 찾아보기에 자동으로 들어간다
- 일부 빌드에서 범위 밖 장을 가리키는 ↩ 링크는 회색 표식으로 남고 검사에서 «범위 밖 연결고리 N» 으로 따로 센다(실패 아님). 전체 빌드에서는 대상이 없으면 **빌드가 멈춘다**
- 빌드 끝의 «경고: 각주 없이 처음 나온 코드 이름» 은 일부 빌드에서는 앞 장 각주가 빠져서 생길 수 있다. 전체 빌드에서 남는 경고만 고친다

## 3. 장 파일 뼈대

```python
# -*- coding: utf-8 -*-
"""6장 열 단위 계산 — 흐름 한 줄 요약(쓰는 쪽 메모)"""
from book.engine import Svg, pair_svg      # 그림이 필요할 때만
from book.pandas import data               # data.speed() 처럼 빌드 때 잰 값이 필요할 때만


def build(w):
    # 부의 첫 장이면 맨 앞에 부 여는 쪽(쪽 전체). 질문 목록은 이 부의 장 question 으로 자동으로 채워진다
    w.part(2, "한 표 안에서", "1부에서 표를 손에 쥐었다. 2부는 … (앞 부와의 연결 한 줄)", extra=w.svg_item(그림))

    w.chapter(6, "열 단위 계산", "단위를 바꾼 열을 만들려면?",              # 장 머리(E1): 번호 · 제목 · 이 장의 질문
              link="5장에서 … (앞 장과의 연결 한 줄)")
    w.section("두께를 mm 로 바꾼다")                                      # 절 번호 6.1 은 자동 — 단계 번호 쓰지 않기
    w.src("insp_m")                                                        # 다음 블록의 «예시 데이터 만든 과정» 에 공통 표 코드
    w.run(['mm = insp_m.assign(두께_mm=insp_m["두께"] / 1000)'])            # 실행 + 다음 블록 스위치에 코드
    w.p("두께 {len(mm)}행 … **굵게** · !!틀림!! · ++맞음++", fn={"assign": "(설명) 새 열을 붙인 표를 돌려준다"})
    w.fig(w.T("insp_m", caption="전", max_rows=5), w.arrow("mm 로", code='insp_m.assign(…)'), w.T("mm", caption="후", max_rows=5))
    w.back(4, "rule", "4장에서 «같은 행 라벨이면 같은 행» 을 살펴보았다. 거기서는 …였지만 지금은 …다")   # ↩ 연결고리(L) — 장마다 2개 이상
    w.rule("**~이면 ~다** — 조건이 든 한 줄")
    w.guess("결과는 몇 행일까?", "**18행**이다. …")                        # 먼저 맞혀 보기 — 답은 가림
    w.faq("질문?", "답 …")
    w.think("정답 없이 생각할 거리")
    w.summary(["핵심 1", "핵심 2", "핵심 3"])
    w.practice([("연습 1?", "답 1"), ("연습 2?", "답 2")])
    w.task("열린 과제 …")
    w.next_q("다음 장의 첫 질문 …", to=7)                                  # 대상 장이 빌드에 없으면 링크만 빠진다
```

## 4. 블록 API (`w` = Writer)

### 구획

| 메서드 | 하는 일 |
|---|---|
| `w.part(no, title, intro, questions=None, extra=None)` | 부 여는 쪽(쪽 전체). `questions` 를 비우면 이 부의 장 질문으로 채운다. 앵커 `part{no}` |
| `w.chapter(no, title, question, link=None, key=None, sub=None)` | 장 머리 — 새 쪽에서 시작. `no` 정수 → «N장» · 앵커 `c{no}`. «사례 A» · «부록 1» 같은 글자는 META `labels` 의 앵커(`case-a` …)를 쓴다. `sub` = 제목 옆 작은 글(«Series») |
| `w.matter(title, key, lead=None, toc=True)` | 번호 없는 앞 · 뒤 구획(읽는 법 · 차례) |
| `w.section(title, num=None, id=None)` | 절 제목(h2) — 번호 `장.n` 자동 · 앵커 `c{no}-{n}` · 다음 블록과 같은 쪽 |
| `w.sub(title)` | 작은 제목(h3) — 다음 블록과 같은 쪽 |
| `w.cover(title, subtitle, *items, foot=)` · `w.toc()` | 표지 · 차례 자리(앞부분 전용) |

### 글 · 연결

| 메서드 | 하는 일 |
|---|---|
| `w.p(text, fn=None, cls=None, id=None)` | 문단 |
| `w.ul(items, ordered=False)` | 목록 |
| `w.back(ch, sec, text, tag=None)` | ↩ 연결고리 문단 — «↩ N장 · N.k» 표식 + 그 자리 링크(누르면 이동 · 돌아가기 칩). `sec`: 절 번호(정수) · 블록 `id` 이름(글자) · `None`(장 머리) |
| `w.next_q(text, to=7)` | 다음 질문(F9) — 장 마지막 문단 |
| `w.more(text)` | «더 읽기 — Pandas 검증 NN장» 한 줄 |

### 표 · 그림

| 메서드 | 하는 일 |
|---|---|
| `w.table(src, caption=, **표옵션)` | 표 블록(가운데). `src` = 식 글자(`"insp.head(6)"` — 빌드 때 실행, 스위치에 식이 붙는다) · DataFrame · Series · 또는 `header=` + `rows=` |
| `w.fig(*조각, caption=, gap=, align=)` | 가로 그림 — 조각을 나란히 |
| 조각 `w.T(src, **표옵션)` | 표 조각 |
| 조각 `w.arrow(label, code=None, tone="acc"|"ng"|"ok"|"gray", down=False)` | 화살표 + 동작 이름 + 연산 이름표(코드 한 줄) |
| 조각 `w.plus()` · `w.note(text, tone="big"|"bad"|"good")` · `w.col(*조각)` | 더하기 기호 · 작은 글 · 세로 묶음 |
| 조각 `w.code(lines, title=, out=)` | 짧은 코드(+ 출력). 본문 코드는 연산 이름표 수준까지만 |
| 조각 `w.textfile(lines, title=, marks={줄: "hl"|"bad"|"good"}, notes={줄: "← 설명"})` | 글자 파일 보기(메모장 · CSV). 줄 안 `==강조==` · `!!빨강!!` |
| `w.svg(markup, caption=, width=)` · 조각 `w.svg_item(markup)` | SVG 그림. `Svg(w, h)` 도우미(box · text · line · arrow · path) · `pair_svg(왼쪽, 오른쪽, pairs)` 짝짓기 선 그림 |

**표 옵션**: `hl_rows` · `bad_rows` · `good_rows`(표시 순서 0부터) · `hl_cells` · `bad_cells` · `good_cells`(`(행, 열 이름)`) · `hl_cols` ·
`notes={행: "← 설명"}` 또는 `("글", "bad"|"muted"|"good"|"acc")`(주석 화살표 E8) · `col_notes={열: "↓ 설명"}` · `max_rows`(넘으면 «… 총 N행») ·
`dtype=True`(맨 아래 자료형 줄) · `index=False` · `index_name=` · `value_name=`(Series) · `fmt={열: ".1%"}` · `tfmt="%H:%M"`(시각) · `na=""` ·
`small=True` · `cls="wr"`(칸 줄바꿈) · `cls="lf"`(왼쪽 정렬) · `nw_cols=[열]`(그 열만 줄바꿈 안 함) · `code_cols=[열]` · `html_cols=[열]`(칸에 `w.t("꾸밈 글")`)

### 상자

| 메서드 | 상자 |
|---|---|
| `w.rule(text)` | 규칙(F6) — 파랑 |
| `w.name(*내용)` | 이름 붙이기(F3) — 보라 |
| `w.ng(*내용, title=)` | 깨지는 곳 · 주의 — 빨강 |
| `w.faq(q, *a)` | 자주 하는 질문(E4) |
| `w.think(*내용)` | 생각해 보기(E5) |
| `w.guess(q, a)` | 먼저 맞혀 보기(F8 · E6) — 답은 가림(자리를 미리 잡아 쪽이 밀리지 않는다) |
| `w.summary(points)` · `w.practice([(q, a)])` · `w.task(*내용)` | 장 끝 정리 · 연습 문제(답 가림 · 문제마다 블록 하나) · 열린 과제(E9) |
| `w.box(kind, *내용, title=)` | 그 밖(`info` 등). 내용 = 꾸밈 글 · 조각 · 글 목록(리스트) |
| `w.html(raw)` | 날 HTML(마지막 수단) |

### 묶음 · 쪽

- 블록은 **쪼개지지 않는다.** 쪽(내용 높이 약 990px · 폭 664px)보다 큰 블록은 검사에서 «쪽보다 큰 블록» 실패 — 표는 `max_rows`, 긴 그림은 나눈다
- `with w.keep(): …` 안의 블록들은 같은 쪽에. `w.newpage()` 는 다음 블록을 새 쪽에서
- 절 · 작은 제목은 자동으로 다음 블록과 같은 쪽. 장 머리는 새 쪽, 부 여는 쪽 · 표지는 쪽 전체

## 5. 글 꾸밈 · 숫자 · 각주

- `**굵게**` · `!!빨강(틀림)!!` · `++초록(맞음)++` · `` `코드` `` · 줄바꿈 `\n`
- **숫자는 손으로 적지 않는다.** `{식}` · `{식:형식}` 은 그 장의 실행 환경에서 계산해 채운다 — `{len(insp)}행` · `{rate:.1%}` · `{cnt['ETCH-01']}건`. 글자 `{`·`}` 는 `{{` `}}`
- 🔴 `` `코드` `` 안의 `{식}` 은 계산하지 않는다(빌드가 멈추고 알려 준다). 코드 안에 값을 넣으려면 파이썬 f-글자로 먼저 채운다: `` w.guess(f"`loc[{top}]` 은?", …) ``
- 파이썬 지역 변수는 실행 환경에 없다 — 글에서 쓰려면 `w.env["top"] = top` 또는 `w.env.update(…)`
- 각주: `fn={"용어": "(전체 이름) 설명"}` — 그 블록 글에서 용어가 **처음 나온 자리 바로 뒤**에 번호가 붙고, 설명은 그 쪽 아래에 놓인다. 약어는 괄호에 전체 이름 → «dtype(data type) — …». 용어가 블록 글에 없으면 빌드가 멈춘다. 표 · 그림 · 상자 · 조각에도 `fn=` 를 줄 수 있다
- 각주는 «용어 찾아보기»(부록 3)에 자동으로 모인다(용어마다 처음 나온 곳). 이미 앞 장에서 단 용어는 다시 달지 않는다

## 6. 실행 환경 · 예시 데이터 스위치

| 메서드 | 하는 일 |
|---|---|
| `w.run(lines, show=True)` | 코드 실행. `show=True` 면 **다음 블록**의 «예시 데이터 만든 과정» 에 붙는다. 실행 중 난 경고 이름은 `w.last_warnings` |
| `w.src("insp_m", …)` | 공통 표를 만든 코드(data.py)를 다음 블록 스위치에 붙인다(다시 실행하지 않는다) |
| `w.val(expr)` | 식의 값(파이썬 객체) — 표 · 문장을 조립할 때 |
| `w.try_run(expr)` | (값, 에러 문구, 경고 이름) — 에러를 보여 줄 때. 오타 계열(NameError 등)은 빌드를 멈춘다 |
| `w.t(text)` | 꾸밈 글 → HTML(표 칸 `html_cols` 등에) |

- 장마다 **새 실행 환경**(`data.env()`)이다. 장 안에서 표를 바꿔도 다른 장에 번지지 않는다. 장 파일끼리 import 하지 않는다 — 앞 장 숫자가 필요하면 data.py 표로 다시 계산한다
- 빌드 때 재는 값(속도 · 메모리)은 `data.speed()` · `data.memory_probe()` — 한 번 빌드 안에서는 같은 값을 여러 장이 나눠 쓴다

## 7. 연결고리 앵커 — 다른 장에서 ↩ 로 가리킬 수 있는 자리

| 앵커 | 가리키는 곳 | `w.back(…)` |
|---|---|---|
| `c{N}` | N장 머리 | `w.back(N, None, …)` |
| `c{N}-{k}` | N장 k번째 절(N.k) | `w.back(N, k, …)` |
| `c{N}-{이름}` | `id="이름"` 을 준 블록 | `w.back(N, "이름", …)` |
| `case-a` · `case-b` · `case-c` · `app-1` · `app-2` | 사례 · 부록 머리(META labels) | `w.back("사례 A", None, …)` |

1부가 만들어 둔 이름 붙은 앵커(2~4부에서 «규칙 문장» 을 다시 걸 때 쓴다):
`c1-rule`(행 하나 = 관측 하나 · 열 하나 = 같은 종류 값) · `c2-rule`(반복 작업은 열 전체 대상 코드로) · `c3-rule`(자료형이 계산을 정한다) ·
`c4-rule`(같은 행 라벨 = 같은 행) · `c5-rule`(계산 전에 행 수 · 자료형 · 빈 칸 수) · `c0-silent`(0장 «조용히 틀린다» — 18행이 36행) · `howto-data`(공통 데이터 지도)

자기 장의 규칙 블록에도 `id="rule"` 을 붙여 두면 뒤 장이 `w.back(N, "rule", …)` 로 건다.

## 8. 스티커 메모

- 화면 오른쪽 아래 노란 메모 버튼 → 쪽을 누르면 포스트잇 → «접수» 하면 서버 `api/notes` 에 저장(사이트 로그인 쿠키). doc 이름 = META `doc`(`pandas_book`)
- 위치는 **가장 가까운 블록 ID** 기준(x = 쪽 폭 대비, y = 블록 위 끝에서 쪽 폭 대비 거리) — 기기마다 쪽 나누기가 달라도 같은 자리에 붙는다. 맥락(ctx) = «쪽 | 장 | 절 | «블록 글 앞부분» | b=블록ID»
- 블록 ID = 장 키 + 순번(`c6-014`). 장 안에서 블록 순서를 크게 바꾸면 이미 붙은 스티커가 다른 블록 옆으로 갈 수 있다
- **답이 달린 스티커는 화면에서 빠지고 책 아래 «질문 줄»로 간다** — «예시 데이터 만든 과정» 과 같은 모양의 접이식 패널(두 페이지 `#spQa` · 한 페이지는 쪽마다 `.qa1`). 행 = 지금 펼친 쪽 질문만 «Q1. 제목»(제목 = notes.json `title` · 없으면 질문 앞부분) · 그 쪽에 없으면 패널을 숨긴다. 답 없는 스티커는 그대로 화면에 남는다
  - 행을 누르면 원 질문 · 답 · 꼬리 질문이 펼쳐지고, 그 안 «꼬리 질문» 칸 + 🪄 → `POST api/notes/<id>/thread {q}` → `POST api/notes/<id>/thread/<꼬리 id>/magic`(2ND). 답(`notes.py answer <id> --thread <꼬리 id>`)은 같은 행 안에 쌓인다(행 수는 그대로)
  - 답 대기(원 질문 · 꼬리)가 있으면 4초마다 `api/notes` 를 다시 읽어 답이 달리는 순간 옮긴다(꼬리 질문 칸에 쓰는 중이면 다음 차례로 미룸)
  - 주소 `#note=<스티커 id>`(꼬리면 `&t=<꼬리 id>`) — 그 블록 쪽으로 넘기고 그 행을 펼쳐 보인다(꼬리면 그 꼬리까지 스크롤) · 열린 책에서 hash 만 바뀌어도 같다
- 로컬(file://)에서는 API 가 없어 조용히 넘어간다. 검사는 `tests\test_book_ui.py` 의 가짜 라우팅으로 한다 · 질문 줄은 `tests\test_note_rows_ui.py`(devview 페이지 서버 · 헤드리스)
- 스티커 질문의 답은 `study_html\qa\pandas_book.json`(META `qa`)에 적는다. 빌드가 그 블록 **바로 뒤**에 «자주 하는 질문» 상자로 넣는다 — 장 파일을 고치지 않아도 된다

```json
[{"id": "s001", "block": "c12-034",          // 또는 "anchor": "c12-5" — 대상 블록(스티커 ctx 의 b=… 값)
  "q": "오른쪽 표의 키 순서가 뒤죽박죽이면?",
  "a": "결과는 왼쪽 표 순서를 따른다 … {len(insp)}행",   // 꾸밈 글 · {식} 가능(새 실행 환경)
  "cards": [{"title": "left — k=1 이 3행", "code": ["left = pd.DataFrame({…})", "left"], "hl": [0, 1, 2]}]}]
```
  카드마다 코드를 실행해 마지막 줄의 결과를 표로 보인다(답을 글로만 쓰지 않는다 — web_ppt 정책 6절). 대상 블록이 빌드에 없으면 경고만 남기고 건너뛴다. 절 제목 블록보다는 내용 블록 뒤를 대상으로 한다

## 9. 2~4부 집필 서브가 알아야 할 것

1. `engine.py` · `assets\` · `data.py` · `front.py` · `ch00` ~ `ch05` 는 고치지 않는다. 엔진 기능이 더 필요하면 자기 장 파일 안에서 해결(`w.html` · `Svg`)하거나 보고에 «엔진 요청» 으로 적는다
2. 부 여는 쪽은 **그 부의 첫 장 파일 맨 앞**에서 `w.part(...)` (2부 = ch06 · 3부 = ch11 · 4부 = ch15)
3. 사례 · 부록 장: `w.chapter("사례 A", "한 표로 보고서", question, link=…)` — 앵커는 META labels(`case-a`)가 정한다. 절 번호가 필요하면 `w.section(title, num="A.1")`
4. 쪽 폭은 664px 이다. 표 두 개 + 화살표를 나란히 놓으면 넘치기 쉽다 — `small=True`, 짧은 열 이름, `notes` 글을 짧게. 검사의 «쪽 가로 넘침» 이 0 이어야 한다
5. 본문 표는 12행 이하 권장, 20행 초과 금지(`max_rows`). 숫자는 전부 `{식}` · `w.val`
6. 함수 이름을 본문 `` `코드` `` 로 쓰면 그 자리(또는 그보다 앞)에 각주가 있어야 한다 — 빌드 경고가 알려 준다
7. 일부 빌드 결과(`dist\_partial\…`)로 검사 · PNG 확인을 하고, 전체 빌드는 메인이 한다
8. 커밋 · 배포 하지 않는다

## 10. API 책 블록 — 요청 · 응답 · 서버 코드 · 순서도 · 타임라인 · 책 사이 연결고리

`engine_api.py`(2026-10-22 추가). 이 블록을 쓰는 책만 불러온다 — 판다스 책은 그대로다. 요청은 **빌드 때 실제로 보낸 결과**다(FastAPI 0.139 · httpx 0.28 · starlette 1.3).

### 10.1 META 옵션

| 키 | 뜻 | 없으면 |
|---|---|---|
| `display_host` | 해부도 · `ex.url` 에 보일 주소(`"https://fab.example"`). 요청 `host` 헤더도 `fab.example` 로 보인다. ASGI 앱으로 만든 TestClient 의 base_url 도 `http://fab.example` | `testserver` |
| `default_app` | `w.call` 의 `app=` 을 비웠을 때 쓸 실행 환경 이름 | `"client"` |

### 10.2 블록 API

| 메서드 | 하는 일 |
|---|---|
| `w.call(method, path, *, app=None, params=, json=, data=, content=, headers=, cookies=, follow_redirects=False, base=None, name=None, jar=True, show_host=None)` → Exchange | 요청을 **실제로** 보낸다(블록은 안 만든다). `app` = 실행 환경 안의 이름 — TestClient(그대로 씀) 또는 ASGI 앱(TestClient 를 만들어 장 안에서 캐시). `base="http://127.0.0.1:포트"` 면 로컬 실서버에 httpx 로. 리다이렉트는 기본으로 안 따라간다(302 를 보이려고). `name=` 이면 `w.env[name]` 에 넣는다 → 문장 `{ex.status}`. 같은 장 안에서는 앱 상태 · 쿠키가 이어진다(POST 뒤 GET 에 반영). `jar=False` = 쿠키 상자를 비운 채 보냄(처음 온 브라우저 — 이 응답의 Set-Cookie 도 담지 않음). `show_host` = 이 요청만 표시 주소를 바꿈 |
| `w.exchange(req, res, source, name=None)` → Exchange | **녹화 예시**(외부 서비스 — 빌드 때 보내지 않는다). `req` · `res` = 원문 글자(`"POST /v1/messages HTTP/1.1\nhost: api.anthropic.com\n…\n\n{…}"`) 또는 dict(`req`: method · url 또는 path · headers · json 또는 body / `res`: status · reason(생략 = 표준 사유) · headers · json 또는 body). `source`(공식 문서 주소) 필수 — 해부도에 «녹화 — 실행 아님» 표식 + 출처 각주가 자동으로 붙는다(용어 찾아보기에는 안 들어감) |
| `w.http(ex, part="both"\|"req"\|"res", notes=None, marks=None, hide=None, body_lines=12, title=None, wrap=None, pretty=True, fn=, id=)` | **HTTP 메시지 해부도** — 시작줄(요청) · 상태줄(응답) · 헤더 · 빈 줄 · 본문을 원문 모양으로, 영역마다 왼쪽 괄호 이름표. 요청 위 · 응답 아래로 쌓는다 |
| `w.listing(lines, title=None, run=True, marks=None, notes=None, start=1, fn=, id=)` | **서버 코드 묶음** — 줄 번호 · 칠하기(글자 · 주석 · 키워드 · 데코레이터) · 줄 주석 칸. `run=True` 면 그 장 실행 환경에서 실행 → 정의한 앱을 바로 `w.call(…, app="app")`. 실행 에러는 **화면 줄 번호**와 함께 빌드를 멈춘다 |
| `w.seq(lanes, steps, title=None, caption=None, fn=, id=)` | **순서도** — 주체마다 세로 줄, 위에서 아래로 번호 붙은 화살표. steps 원소 = `(보내는 쪽, 받는 쪽, 글)` · `(…, tone)` · `(…, tone, 점선)` 또는 dict(`frm` · `to` · `text` · `tone`="acc"\|"ok"\|"ng"\|"gray" · `dashed`=응답 · `note`=화살표 밑 작은 글). 보내는 쪽 = 받는 쪽이면 자기 처리 상자 |
| `w.gantt(tracks, unit="초", title=None, caption=None, fn=, id=)` | **타임라인** — `tracks=[(이름, [(시작, 끝, tone, 글)])]`. 축 눈금 자동(1 · 2 · 2.5 · 5 단위), 막대 안 글(넘치면 오른쪽 밖) |
| `w.back_x(book_doc, anchor, label, text, fn=, id=)` | **책 사이 연결고리** — «↗ label» 표식(청록) + `/{book_doc}#{anchor}` 링크(같은 창). 책 안 ↩ 와 따로 센다(빌드 · 검사 출력 «책 사이 연결고리 N»). 대상 책에 앵커가 있는지는 검사하지 않는다 — 앵커 이름은 그 책 README 7절 표에서 고른다 |

**Exchange 속성**(문장 `{…}` · `w.val` 에서): `status` · `reason` · `json`(JSON 이면 파이썬 값, 아니면 None) · `body`(글자) · `size`(본문 바이트) · `headers["location"]`(대소문자 무관, `.get` · `.all`) · `method` · `path` · `query` · `target`(경로+쿼리) · `url`(표시 주소) · `http_version`(요청) · `res_version`(응답) · `req_headers` · `req_body` · `req_json` · `recorded` · `source` · `history`(follow_redirects=True 일 때 앞 단계들)

```python
w.listing(['from fastapi import FastAPI',
           'app = FastAPI()',
           '',
           '@app.get("/equipment/{equipment_id}")',
           'def get_equipment(equipment_id: str):',
           '    return {"id": equipment_id}'],
          title="app.py", marks={4: "hl"}, notes={4: "← 경로의 `{equipment_id}` 칸"})
ex = w.call("GET", "/equipment/ETCH-01", app="app", name="ex")
w.http(ex, notes={"req": {"start": "← 메서드 · 경로 · 버전"}, "res": {"content-type": "← 본문 형식", "body": "← 함수의 반환값"}})
w.p("상태 코드는 {ex.status}, 본문의 id 는 {ex.json['id']} 다.")
w.seq(["클라이언트", "서버"], [("클라이언트", "서버", "GET /equipment/ETCH-01"),
                               ("서버", "서버", "get_equipment 호출"),
                               ("서버", "클라이언트", "200 + JSON", "ok", True)])
w.back_x("pandas_book", "c12", "Pandas 책 12장", "판다스 책 12장에서는 두 표를 로트 값이 같은 행끼리 이었다. …")
```

### 10.3 해부도 줄 주석 · 표시의 열쇠

`notes` · `marks` = `{"req": {열쇠: …}, "res": {열쇠: …}}` — 열쇠는 `"start"`(시작줄 · 상태줄) · **헤더 이름**(`"content-type"`, 대소문자 무관) · `"blank"`(빈 줄) · `"body"`(본문 첫 줄) · `"body:N"`(본문 N번째 줄, 0부터 — 들여쓴 JSON 기준) · 정수(표시 줄 위치, 시작줄 = 0). 값은 꾸밈 글(`"← 설명"`) 또는 `("글", "muted"|"good"|"acc"|"ink")`(기본 빨강). marks 값 = `"hl"` · `"bad"` · `"good"`.
대상 줄이 없으면(숨긴 헤더 · 본문 줄 수 밖) **빌드가 멈춘다.** 코드 묶음의 `marks` · `notes` 열쇠는 **화면 줄 번호**(`start` 부터).

### 10.4 API 책 집필 서브가 알아야 할 것

1. **상태 코드 · 헤더 · 본문을 손으로 적지 않는다.** `w.call` 로 보내고 `w.http` 로 그린다. 문장 숫자도 `{ex.status}` · `{ex.json["total"]}` — 지역 변수 ex 는 실행 환경에 없으니 `name="ex"` 로 넣는다
2. **잡음 헤더는 기본으로 숨는다** — 요청 `user-agent` · `accept-encoding` · `connection` · `accept`, 응답 `date`. `hide=[…]` 를 주면 기본값을 **대신**한다(`hide=[]` = 전부 보임 — `accept` 를 보여 줘야 하는 장 등)
3. **JSON 본문은 2칸 들여쓰기로 보인다**(읽기용). `content-length` 는 실제로 보낸(들여쓰지 않은) 바이트 수라 화면 글자 수와 다르다 — 그 차이를 짚어야 하는 장은 `pretty=False`(보낸 글자 그대로)
4. 본문이 `body_lines`(기본 12, HTML 은 8) 보다 길면 «… 총 N줄» 로 줄인다. 줄이 표시 폭(기본 80칸 · 줄 주석이 있으면 58칸, 한글 2칸)을 넘으면 꺾고 ↵ 를 단다(`wrap=`). 줄 주석은 짧게 — 오른쪽 칸은 쪽 폭의 44% 까지
5. **녹화**(OKX · Claude API · ntfy)는 `w.exchange(…, source=공식 문서 URL)` 만. 문서로 확인한 칸만 적고, 키 · 서명은 누가 봐도 가짜(`test-key-0000` · `sk-ant-test-…`)
6. **로컬 실서버**(`base=`): 표시 주소는 기본으로 포트를 뺀 `http://127.0.0.1` — 실물 주소로 보이려면 `show_host="https://notes.…"`. 응답 `date` 는 숨지만 `server` 헤더(파이썬 판 번호)는 보인다. 서버 기동 · 종료는 장 파일(또는 data.py 도우미)이 맡는다 — 엔진은 보내기만 한다
7. ASGI 앱으로 만든 TestClient 는 서버 예외를 **500 응답으로** 돌려받는다(500 을 보여 줘야 하는 장이 있어서). 의도하지 않은 5xx 는 빌드 경고 «… → 500» 으로 알린다 — 전체 빌드 경고가 0 이어야 한다
8. 같은 장 안에서 앱 · 쿠키 상태가 이어진다(장마다 새 실행 환경). 같은 이름에 앱을 다시 만들면(3부처럼 장 안에서 앱을 고쳐 나갈 때) 새 앱용 TestClient 를 새로 만든다
9. 해부도 · 코드 묶음 본문은 «각주 없이 처음 나온 코드 이름» 경고 대상이 아니다(제목 · 줄 주석의 `` `코드` `` 만 걸린다). 개념 · 함수 이름의 각주는 본문 문단에서 단다
10. 순서도는 단계 12개 안팎, 화살표 글은 짧게(주체 간격을 넘으면 옆 주체 위로 겹친다). 블록 하나가 쪽보다 크면 검사 «쪽보다 큰 블록» 실패 — 둘로 나눈다
11. 다른 책 주소 `/{doc}#{앵커}` 로 열면 그 책이 쪽 나누기 뒤 그 쪽을 연다(두 페이지 · 한 페이지 모두, 앵커 · 블록 ID · `b-블록ID` 모두). 책 사이 ↗ 는 장마다 책 안 ↩ 2개와 **따로** 센다 — ↗ 를 걸어도 건 내용을 한 문장으로 다시 적는다

## 11. 조작 블록 — 단계 재생기 · 조건 슬라이더 · 크게 열기 · 읽기 기록

`engine_live.py`(2026-11-02 추가, 명세 `LIVE_SPEC.md`). 이 블록을 쓰는 책만 불러온다 — 판다스 · API 책의 블록 마크업은 그대로다(런타임 JS · CSS 만 늘었다).
원칙: **안 만져도 읽히는 책 + 확인용 조작.** 첫 화면(0단계 · 기본 조합)이 정적 HTML 로 이미 그려져 있어 조작하지 않아도 본문이 이해돼야 한다. 숫자 · 그림 · 표시 글자는 **빌드 때 파이썬이 미리 계산해 심는다** — 브라우저는 골라서 보여 주기만 한다(본문 숫자와 조작 결과가 어긋나지 않는다).

### 11.1 블록 API

| 메서드 | 하는 일 |
|---|---|
| `w.stepper(steps, title=None, caption=None, table=None, task=None, auto_ms=900, fn=None, id=None, start=0)` | **단계 재생기** — `steps` = `[{"svg": SVG 글자, "text": 꾸밈 글, "row": 표 행 번호 또는 None}]`. `table` = `{"header": [...], "rows": [[...]], "small": True}`(선택 — 지금 단계의 `row` 행 강조 · 아직 안 온 행은 흐리게). 단추 처음 · 이전 · 다음 · 자동(`auto_ms` 간격, 마지막에서 멈춤) · «3 / 12». 블록에 포커스가 있으면 ← → 가 단계를 움직인다 |
| `w.slider(params, frames, render="svg", metrics=None, task=None, predict=None, title=None, caption=None, fn=None, id=None)` | **조건 슬라이더** — `params` = `[{"key", "label", "values", "default", "unit"}]`(슬라이더는 values 칸에만 멈춘다 · 2~3개 권장). `frames` = `{"30\|1.5": {"svg", "metrics": {지표: 값}, "note": 꾸밈 글}}`. `metrics` = `[{"key", "fmt": ".1f", "unit": "배", "bad_above": 2.0}]`(기준을 **넘으면** 빨강 · 기본 조합 대비 차이 «▲ +3» · 같으면 «기준»). `predict` = `{"q", "at": {key: 값}, "metric"}`(숫자 입력 + «확인» → 슬라이더를 그 조건으로 옮기고 «실제 · 입력 · 차이») |
| `w.open_full(path, label, note=None, id=None)` | **크게 열기** — 쪽에 안 들어가는 큰 조작 화면(HTML 한 파일)으로 가는 새 탭 단추. 빌드가 `path` 를 출력 옆 `<doc>__<파일이름>` 으로 복사한다(`path` 는 절대 경로 또는 `study_html\` · `book\` 기준). 빌드 끝에 «함께 배포할 파일» 목록이 나온다 — **배포할 때 같이 올린다** |

- **열쇠**: `frames` 의 열쇠는 `params` 순서대로 **값의 파이썬 글자(`str(값)`)를 `|` 로 이은 것** — `f"{cap}|{det}"` 와 같다(2.0 은 «2.0»). 튜플 `(30, 1.5)` 로 줘도 된다. 조건 조합이 아닌 열쇠 · 기본 조합 frame 없음 · predict 의 지표 없음은 **빌드가 멈춘다**. 빠진 조합은 허용 — 화면에 «계산 안 함»
- **크기 고정**: 단계 · frame 의 그림은 **같은 `Svg(w, h)` 크기**여야 한다(viewBox 가 다르면 빌드가 멈춘다). 모든 단계의 글은 한 칸에 겹쳐 두고 하나만 보이므로 가장 긴 글이 높이를 정한다 → 단계 · 조건이 바뀌어도 블록 높이가 변하지 않아 쪽 나누기가 흔들리지 않는다
- 그림은 **SVG 만**(`render="canvas"` 는 거부 — 오른쪽 축소판이 쪽을 복제하면 canvas 는 빈칸이 된다). 블록 하나는 쪽 안에(폭 664px · 높이 약 990px) — 넘으면 검사 «쪽보다 큰 블록». 블록 데이터(JSON) 500KB 넘으면 빌드 경고
- `task=` 한 줄은 블록 위 노란 띠 «해 보기» — **무엇을 놓고 무엇을 볼지**(«차당 건수를 30 으로 놓아 봐 → 차가 몇 대 늘어나나?»). 안내 없는 자유 조작은 초보에게 시간만 먹는다
- 바깥 상자 `live` 클래스: 두 페이지의 좌우 20% 넘김 · ← → 키 넘김에서 **제외**된다(블록 안 클릭 · 포커스 · 끌기는 넘김이 아니다 — 슬라이더를 끌다 블록 밖에서 놓아도). 블록 밖 20% 구역은 그대로 넘어간다
- 데이터는 블록 안 `<script type="application/json" class="lvdata">` — book.js 가 쪽 나누기가 끝난 뒤 블록마다 한 번 초기화한다. 오른쪽 축소판은 **그 순간의 DOM 복제**라 조작한 상태가 그대로 보인다(복제본은 `inert`)
- 스티커 · 각주(`fn=` 은 보이는 HTML 의 첫 등장에 붙는다 — 제목 · 띠 · 캡션에 용어를 두는 게 안전) · `id=` · ↩ 앵커는 다른 블록과 같다
- 좌표가 필요한 조작을 새로 만들면 SVG 기준 좌표로 바꾼다(`getScreenCTM` — 판이 `transform: scale(--k)` 로 줄어 있다). 지금 있는 세 블록은 좌표 조작이 없다

```python
import math
from book.engine import Svg


def oht_svg(n):                     # 같은 크기(664 × 120)의 그림을 단계 · 조합마다 만든다
    s = Svg(664, 120)
    for k in range(n):
        s.box(20 + k * 60, 40, 50, 40, f"V{k + 1}", tone="ok")
    return s.render("OHT")


def build(w):
    w.chapter(7, "차당 건수와 차 대수", "한 대가 맡는 건수를 바꾸면 차는 몇 대 필요한가?")
    steps = [{"svg": oht_svg(i + 1), "text": f"{i + 1}대째에 맡긴다.", "row": i} for i in range(3)]
    w.stepper(steps, title="차례로 맡긴다", table={"header": ["대", "맡은 건수"], "rows": [[1, 30], [2, 60], [3, 90]], "small": True},
              task="다음을 눌러 보며 → 표에서 지금 채우는 행을 찾아 봐", id="fill")
    frames = {f"{c}|{d}": {"svg": oht_svg(math.ceil(100 / c)), "metrics": {"필요 차 대수": math.ceil(100 / c), "최악 대기 배율": d}}
              for c in (30, 45, 60) for d in (1.5, 2.0)}
    w.slider([{"key": "cap", "label": "차당 건수", "values": [30, 45, 60], "default": 45, "unit": "건"},
              {"key": "det", "label": "대기 허용", "values": [1.5, 2.0], "default": 1.5, "unit": "배"}], frames,
             metrics=[{"key": "필요 차 대수", "unit": "대"}, {"key": "최악 대기 배율", "fmt": ".1f", "unit": "배", "bad_above": 1.8}],
             task="차당 건수를 30 으로 놓아 봐 → 차가 몇 대 늘어나나?",
             predict={"q": "차당 30 건이면 차는 몇 대?", "at": {"cap": 30}, "metric": "필요 차 대수"}, id="cap")
    w.open_full("whatif.html", "크게 열기 — 배차 시뮬레이터", note="쪽에 안 들어가는 큰 화면이다.")
```

### 11.2 읽기 기록 — META `"reading_log": True` 인 책만

- 쪽마다 **화면에 보인 시간**을 localStorage(`bk:<doc>:log`)에 누적한다. 두 페이지는 보이는 두 쪽에 각각 쌓인다(합계 `total` 은 한 번만 센다). 탭이 숨겨져 있거나(`visibilityState`) **60초 넘게 입력(마우스 · 키 · 스크롤 · 터치)이 없으면** 세지 않는다. 쪽은 «쪽의 첫 블록 ID» 로 저장해 쪽 나누기가 바뀌어도 이어진다
- 조작 블록 사용 횟수를 블록 ID 별로 센다 — 단계가 **실제로 바뀐** 넘김 · 자동 재생 시작 · 슬라이더 값이 **실제로 바뀐** 이동 · 예측 «확인» · 크게 열기 누름(제자리 누름 · 같은 값은 안 센다)
- 오른쪽 아래 버튼 줄에 «기록» 버튼(시계) → 쪽별 시간 표(장 이름 · 쪽 · 초 · «긴 순으로 / 쪽 순서로» 전환) + 조작 블록 사용 표 + «복사»(JSON) · «초기화»(두 번 눌러야 지운다 — 확인창은 쓰지 않는다)
- 서버로 보내지 않는다(로컬 저장만). `reading_log` 가 없는 책에는 버튼 · 창 · 저장이 전혀 없다 — 판다스 · API 책은 그대로다

### 11.3 시험

`py -3 book\tests\test_live.py` — 최소 책(조작 블록 3종 · 각 블록이 자기 쪽)을 **임시 폴더**에 빌드해 헤드리스로 확인한다. 쪽 번호(`window.__book.cur`) · 단계 표시 글자 · 지표 값 글자 · localStorage 를 단언한다. 항목: 빌드 안전장치 7종 · 단계 넘김 · 표 행 강조 · 자동 재생 · ← → 키 · 넘김 제외(블록 안 20% 구역 클릭 · 끌기 / 블록 밖 20% 구역) · 슬라이더 이동 · 빨강 기준 · 빠진 조합 · 예측 확인 · 블록 높이 고정 · 축소판 SVG · 읽기 기록(Playwright `page.clock` 으로 60초 입력 없음 · 숨김 · 정렬 · 복사 · 초기화 · 새로고침) · 한 페이지 · 폰 412 · 기록을 안 켠 책.
