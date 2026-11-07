# -*- coding: utf-8 -*-
"""과제 파악 책(v3 양식) 공용 조각 — 분류 5색 칩 · 범례 · ◎ 항목 · 원본 줄 조각 · 결함 표 · 칸(빈 칸 알림) · 단계 재생기 셋

- 과제와 무관하다. 글 · 숫자 · 그림 데이터는 장 파일 머리의 fill() 과 shared.py 의 fill() 이 준다
- 장 파일끼리는 서로 부르지 않는다 — 여러 장이 함께 쓰는 것(분류 색 · 재생기)은 여기, 그림은 figs.py
- 이 파일은 고치지 않는다(빌드가 양식과 다르면 «구조 바뀜» 으로 알린다)
"""
import re

from book.engine import esc
from book import engine as _E

from . import figs

# 분류 이름 → CSS 이름 — 화면 · 시스템 · 알고리즘 · 파이프라인 · 문서(책 내내 같은 색 · v3 원칙 1)
CATS = {"화면": "ui", "시스템": "sys", "알고리즘": "alg", "파이프라인": "pipe", "문서": "doc"}

# 분류 칩 · ◎ 항목 · 원본 줄 조각 · 결함 표 · 범례의 CSS — 한눈에 첫 블록에 한 번 넣는다(v3 와 같다)
STYLE = """<style>
.cat{display:inline-block;font-size:.74em;font-weight:700;padding:0 .42em;border-radius:4px;border:1px solid;white-space:nowrap;line-height:1.55;vertical-align:.06em;margin-left:.25em}
.cat-ui{color:#15803d;background:#e9f7ee;border-color:#9ad4ae}
.cat-sys{color:#6d28d9;background:#f5f0ff;border-color:#c9b5f5}
.cat-alg{color:#1d4ed8;background:#eaf1ff;border-color:#a9c1f5}
.cat-pipe{color:#b45309;background:#fff7e6;border-color:#f0c98a}
.cat-doc{color:#0f766e;background:#eaf7f4;border-color:#9fd6cb}
td .cat{margin-left:0}
.qi{margin:.5em 0 .65em;padding:.45em .85em .55em;border:1px solid #d6dbe3;border-left:4px solid #94a3b8;border-radius:6px;background:#fff}
.qi.alg{border-left-color:#2563eb}.qi.ui{border-left-color:#16a34a}.qi.sys{border-left-color:#7c3aed}.qi.pipe{border-left-color:#b45309}.qi.doc{border-left-color:#0f766e}
.qi .qh{margin:0 0 .2em;font-weight:700;line-height:1.5}
.qi .qm{color:#2563eb;margin-right:.3em}
.qi dl{margin:0;display:grid;grid-template-columns:max-content 1fr;column-gap:.7em;row-gap:.12em;font-size:.92em;line-height:1.58}
.qi dt{font-weight:700;color:#4b5563;white-space:nowrap}
.qi dd{margin:0}
.mono{font-family:Consolas,"D2Coding","Noto Sans Mono",monospace;font-size:.88em;background:#f4f6f9;border:1px solid #e3e6eb;border-radius:4px;padding:0 .3em;white-space:pre-wrap;overflow-wrap:anywhere}
.mono.bad{background:#fdecec;border-color:#f5b5b5;color:#991b1b}
.mono.good{background:#e9f7ee;border-color:#a7dcb8;color:#15803d}
table.apxdef{table-layout:fixed;width:100%}
table.apxdef th:nth-child(1){width:30px}
table.apxdef th:nth-child(2){width:49%}
table.apxdef th:nth-child(3){width:29%}
.legend{font-size:.9em;line-height:1.7;margin:.3em 0 .6em}
.legend .cat{margin:0 .3em 0 0}
.legend span.ld{color:#4b5563;margin-right:.9em}
</style>"""


# ════════════════════════════════════════════════════════════
# 글 조각
# ════════════════════════════════════════════════════════════
def chip(cat):
    """분류 칩 HTML — cat 은 CATS 의 이름 하나"""
    if cat not in CATS:
        raise ValueError(f"분류 «{cat}» 는 없다 — {', '.join(CATS)} 중 하나")
    return f'<span class="cat cat-{CATS[cat]}">{esc(cat)}</span>'


def mono(text, tone=""):
    """원본 데이터 조각 — 글자 그대로(빈 칸 · 공백이 보이게). tone = "" · "bad"(빨강) · "good"(초록)"""
    return f'<span class="mono{(" " + tone) if tone else ""}">{esc(text)}</span>'


def raw(*pairs):
    """원본 줄 비교 한 줄 — (글자, 색) … → HTML. 색 None = 그냥 글(설명), "" · "bad" · "good" = 원본 조각(mono)
    예: raw(("앞 절반", None), (정상 줄, "good"), ("· 블록", None), (잘못된 줄, "bad"))
    설명 글의 {F['이름']} · **굵게** · !!빨강!! 은 다른 글 칸처럼 채운다(계약 json 의 설명 글이 «{F[…]}» 글자 그대로 책에 나오지 않게)
    원본 조각은 글자 그대로(식 · 꾸밈을 풀지 않는다)"""
    return " ".join(mono(t, tone) if tone is not None else _note(t) for t, tone in pairs)


def _note(text):
    """원본 줄 사이 설명 글 → HTML — 식 · 꾸밈이 있을 때만 엔진 글 꾸밈(없으면 글자 그대로 — v3 와 같은 HTML)"""
    if not re.search(r"\{|\*\*|!!|\+\+", text):
        return esc(text)
    from book.engine import render_text
    from .content import data
    return render_text(text, data.env(), "원본 줄 설명 글")


def legend_html(desc):
    """분류 범례 한 줄 — desc = {분류: 이 과제에서 그 분류가 맡는 일}"""
    return '<p class="legend">' + "".join(f'{chip(c)}<span class="ld">{esc(d)}</span>' for c, d in desc.items()) + "</p>"


def no(row, n):
    """항목 번호 글 — 계약 항목 id(Q3 · H12 …)가 있으면 그 숫자, 없으면(손으로 쓴 칸) n"""
    rid = getattr(row, "id", None) or (row.get("id") if isinstance(row, dict) else None)
    m = re.search(r"(\d+)$", str(rid or ""))
    return m.group(1) if m else str(n)


def rid(row):
    """항목 id(계약에서 온 칸) — 없으면 None. 블록 ID 를 «장-id» 로 고정하는 데 쓴다"""
    return getattr(row, "id", None) or (row.get("id") if isinstance(row, dict) else None)


def span(rows, lo, hi):
    """표 머리 «a~b» — 첫 행 · 끝 행의 항목 번호(id 가 없으면 lo + 1 ~ hi)"""
    a, b = (no(rows[0], lo + 1), no(rows[-1], hi)) if rows else (str(lo + 1), str(hi))
    return a if a == b else f"{a}~{b}"


def qitem(w, title, cat, fields, fn=None, id=None, raw=(), key=None):
    """◎ 항목 — title · cat(분류 하나 또는 목록) · fields = [(이름, 꾸밈 글)]. raw = 꾸밈 글 대신 HTML 을 그대로 넣을 이름들
    key = 항목 id(Q1 · S2 …) — 주면 블록 ID 가 «장-id» 로 고정된다(판이 바뀌어도 스티커 자리 유지)"""
    if key:
        w.key(key)
    cats = cat if isinstance(cat, (list, tuple)) else [cat]
    head = f'<p class="qh"><span class="qm">◎</span>{w.t(title)}{"".join(chip(c) for c in cats)}</p>'
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{v if k in raw else w.t(v)}</dd>" for k, v in fields)
    h = f'<div class="qi {CATS[cats[0]]}">{head}<dl>{dl}</dl></div>'
    return w.html(h, fn=fn, id=id)


def tab(w, header, rows, caption, raw_cols=(), extra="", **kw):
    """표 블록 — 칸 글을 꾸밈 글(w.t)로. raw_cols 의 칸은 HTML 그대로. extra = 표에 더할 클래스(apxdef = 결함 표 열 너비)"""
    out = [[c if i in raw_cols else w.t(str(c)) for i, c in enumerate(r)] for r in rows]
    return w.table(header=header, rows=out, caption=caption, cls="wr lf" + (" " + extra if extra else ""), html_cols=list(range(len(header))), small=True, **kw)


def deftab(w, rows, start, caption, fn=None):
    """결함 표 — # · 무엇(굵게) + 처리(그 아래 줄) · 잘못된 예 · 정상 예. rows = [(무엇, 잘못된 예 HTML, 정상 예 HTML, 처리)]"""
    out = [[no(r, start + i + 1), f"{r[0]}\n**처리** {r[3]}", r[1], r[2]] for i, r in enumerate(rows)]
    return tab(w, ["#", "무엇 · 처리", "잘못된 예", "정상 예"], out, caption, raw_cols=(2, 3), extra="apxdef", fn=fn)


def sec_text(x):
    """초 → 읽기 쉬운 시간 글(0.08초 · 9.1초 · 약 12분 · 약 3시간 · 약 38일)"""
    if x < 1:
        return f"{x:.2f}초"
    if x < 90:
        return f"{x:.1f}초" if x < 10 else f"{x:.0f}초"
    if x < 7200:
        return f"약 {x / 60:.0f}분"
    if x < 172800:
        return f"약 {x / 3600:.0f}시간"
    return f"약 {x / 86400:.0f}일"


# 셈 낱말 — 1 → «한» … 10 → «열»(«세 가지» 처럼 절 제목에)
_NUM_KR = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉", 10: "열"}


def num_kr(n):
    """정수 → 셈 낱말(10 넘으면 숫자 그대로)"""
    return _NUM_KR.get(n, str(n))


# ════════════════════════════════════════════════════════════
# 칸 — 장 파일 머리의 fill() 이 돌려준 dict. 빈 칸은 책에 빨간 표시 + 빌드 끝 «빈 칸: 장 · 칸»
# ════════════════════════════════════════════════════════════
class Slots:
    """칸 묶음. 비었다 = None · "" · 빈 목록 · 빈 dict · 칸 이름이 없음
    - 1차판(빌드 --stage 1)에서는 빈 칸이 빨간 «빈 칸» 대신 회색 «2차판에서 채워짐» 이고 빈 칸으로 세지 않는다(book.later 에 모은다)
    - 칸을 읽을 때마다 w.at(칸 이름) — 블록 ID 가 «장-칸 이름» 으로 고정된다
    - K["이름"] — 글 칸. 비었으면 «⟦빈 칸 — 장 · 이름⟧» 빨간 글을 돌려주고 빈 칸으로 센다
    - K.tf("이름") — 글 + 각주: 칸 값이 "글" 또는 ("글", {"용어": "설명"}) → (글, 각주 | None)
    - K.need("이름") — 그림 · 표 · 목록 칸. 비었으면 그 자리에 빈 칸 블록을 넣고 False
    - K.opt("이름") — 선택 칸(각주 등). 비어도 세지 않는다 → 값 | None"""

    def __init__(self, w, ch, values):
        self.w, self.ch, self.v = w, ch, dict(values or {})

    def empty(self, key):
        """칸이 비었나"""
        v = self.v.get(key)
        return v is None or (isinstance(v, (str, list, tuple, dict, set)) and len(v) == 0)

    def _mark(self, key):
        """빈 칸 기록 — 빌드 끝에 «빈 칸: 장 · 칸» 으로 나온다(1차판은 «2차판 대기» 목록으로)"""
        name = "later" if _E.STAGE == 1 else "blanks"
        lst = getattr(self.w.book, name, None)
        if lst is not None:
            lst.append(f"{self.ch} · {key}")

    def mark(self, key):
        """빈 칸 표시 글 — 빨간 굵은 글(꾸밈 글) · 1차판은 회색 «2차판에서 채워짐»"""
        self._mark(key)
        if _E.STAGE == 1:
            return f"⟪2차판에서 채워짐 — {self.ch} · {key}⟫"
        return f"!!⟦빈 칸 — {self.ch} · {key}⟧!!"

    def _at(self, key):
        """블록 ID 바탕 = 이 칸 이름"""
        if hasattr(self.w, "at"):
            self.w.at(key)

    def __getitem__(self, key):
        self._at(key)
        if self.empty(key):
            return self.mark(key)
        v = self.v[key]
        if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], dict):
            return v[0]  # 각주를 붙일 수 없는 자리(제목 등) — 글만
        return v

    def tf(self, key):
        """글 칸 → (글, 각주). 비었으면 (빈 칸 표시, None)"""
        self._at(key)
        if self.empty(key):
            return self.mark(key), None
        v = self.v[key]
        if isinstance(v, tuple) and len(v) == 2 and (v[1] is None or isinstance(v[1], dict)):
            return v[0], (v[1] or None)
        return v, None

    def need(self, key):
        """그림 · 표 · 목록 칸이 채워졌나 — 비었으면 그 자리에 빈 칸 블록을 넣고 False"""
        self._at(key)
        if hasattr(self.w, "key"):
            self.w.key(key)  # 다음 블록(그림 · 표 · 빈 칸 자리) ID = «장-이 칸» — 뒤따르는 캡션 칸을 읽어도 바뀌지 않게
        if self.empty(key):
            self.w.p(self.mark(key))
            return False
        return True

    def opt(self, key):
        """선택 칸 — 값 또는 None(비어도 빈 칸으로 세지 않는다)"""
        self._at(key)
        return None if self.empty(key) else self.v[key]

    def get(self, key, default=None):
        """칸 값 그대로(비었으면 default) — 빈 칸으로 세지 않는다"""
        self._at(key)
        return default if self.empty(key) else self.v[key]


def slots(w, ch, values):
    """장 파일의 fill() 결과 → 칸 묶음(Slots)"""
    return Slots(w, ch, values)


def blank(w, where):
    """칸 밖의 빈 곳(META 등)을 빈 칸으로 센다 — where = «META · title» 처럼"""
    blanks = getattr(w.book, "blanks", None)
    if blanks is not None:
        blanks.append(where)


# ════════════════════════════════════════════════════════════
# 단계 재생기 공통 — 오른쪽 목록(차마다 한 줄)
# ════════════════════════════════════════════════════════════
def vehicle_lines(state, marks, P):
    """차마다 오른쪽 목록 한 줄 — P["words"] = {"line": "{mark}차 {k}  {fill}/{cap}\\n{stops}", "empty": "차 {k}  —\\n"}
    줄 글에 쓸 수 있는 이름: mark(«▶ » 또는 «») · k(차 번호 1부터) · fill(인원 합) · cap(P["cap"]) · km(P["measure"](경로)) · stops(«베이1 27→베이2 18»)
    words["stop"](선택) = 들른 곳 하나의 글 형식(short = 짧은 이름 · n = 수) — 없으면 «{short}{n}»(베이1 27)
    marks = 강조할 차 번호 모음(0부터)"""
    Wd = P["words"]
    short = P["map"].get("short", {})
    colors = P["map"].get("colors", figs.COLORS)
    out = []
    for b, stops in enumerate(state):
        if not stops:
            out.append((Wd["empty"].format(k=b + 1), "#9aa3ad"))
            continue
        fill = sum(c for _, c in stops)
        km = P["measure"](stops) if P.get("measure") else 0
        st = "→".join(Wd.get("stop", "{short}{n}").format(short=short.get(n, n), n=c) for n, c in stops)
        out.append((Wd["line"].format(mark="▶ " if b in marks else "", k=b + 1, fill=fill, cap=P.get("cap", ""), km=km, stops=st),
                    colors[b % len(colors)]))
    return out


# ════════════════════════════════════════════════════════════
# 단계 재생기 1 — 채우기: 정해 둔 규칙이 사람(물건)을 차에 차례로 담는 과정(v3 방안 A 거리순)
# ════════════════════════════════════════════════════════════
def stepper_fill(w, id, P, note=True):
    """P = shared.py «재생기_채우기» 칸
        title · task(해 보기 한 줄) · caption · fn(각주 — note=True 인 첫 자리에만) · auto_ms
        map(figs.route_map 의 지도 칸) · frame_title(지도 위 제목) · right_title(오른쪽 목록 제목) · words · cap
        steps = [{"state": [[(곳, 수) …] 차마다], "cur": 지금 차(0부터), "text": 단계 글(동작 + 결과 숫자), "row": 표 행 | None}]
        table = {"header", "rows", "small": True, "bad_cells": [(행, 열)]} | None
    P["kind"] = "quiver" 이면 지도 대신 측정 화살표(figs.quiver_map — 분석 틀 stat_model · steps = [{"dx", "dy", "head", "lines", "text", "row"}])"""
    if P.get("kind") == "quiver":
        out = [{"svg": figs.quiver_map(P, st), "text": st["text"], "row": st.get("row")} for st in P["steps"]]
        return w.stepper(out, title=P["title"], table=P.get("table"), task=P["task"], auto_ms=P.get("auto_ms", 1100), id=id,
                         caption=P.get("caption"), fn=P.get("fn") if note else None)
    out = []
    for st in P["steps"]:
        lines = vehicle_lines(st["state"], {st["cur"]}, P)
        svg = figs.route_map(P["map"], st["state"], st.get("head", P["frame_title"]), P["right_title"], lines, cur=st["cur"], style="fill")
        out.append({"svg": svg, "text": st["text"], "row": st.get("row")})
    return w.stepper(out, title=P["title"], table=P.get("table"), task=P["task"], auto_ms=P.get("auto_ms", 1100), id=id,
                     caption=P.get("caption"), fn=P.get("fn") if note else None)


# ════════════════════════════════════════════════════════════
# 단계 재생기 2 — 한 곳씩 고치기: 계획에서 한 번에 한 곳만 바꿔 보고 줄면 받아들이는 과정(v3 국소 탐색)
# ════════════════════════════════════════════════════════════
def stepper_fix(w, id, P):
    """P = shared.py «재생기_고치기» 칸
        title · task · caption · auto_ms · map · right_title · words · measure(경로 → 길이 숫자 · 줄 글의 {km})
        steps = [{"state", "hl": [바뀐 차], "gone": [(차, 곳)](빨간 ×), "head": 지도 위 제목, "text", "row"}]
        table = {"header", "rows", "small": True}
    P["kind"] = "quiver" 이면 지도 대신 측정 화살표(figs.quiver_map — 잔차 지도 · 단계 "limit" 보다 긴 화살표 빨강)"""
    if P.get("kind") == "quiver":
        out = [{"svg": figs.quiver_map(P, st), "text": st["text"], "row": st.get("row")} for st in P["steps"]]
        return w.stepper(out, title=P["title"], table=P.get("table"), task=P["task"], auto_ms=P.get("auto_ms", 1300), id=id,
                         caption=P.get("caption"))
    out = []
    for st in P["steps"]:
        hl = set(st.get("hl", ()))
        lines = vehicle_lines(st["state"], hl, P)
        svg = figs.route_map(P["map"], st["state"], st["head"], P["right_title"], lines, hl=hl, gone=st.get("gone", ()), style="fix")
        out.append({"svg": svg, "text": st["text"], "row": st.get("row")})
    return w.stepper(out, title=P["title"], table=P.get("table"), task=P["task"], auto_ms=P.get("auto_ms", 1300), id=id,
                     caption=P.get("caption"))


# ════════════════════════════════════════════════════════════
# 단계 재생기 3 — 이어 붙이기: 일(트립 · 운반)을 시작 시각 순서로 차에 하나씩 붙이는 과정(v3 트립 이어 붙이기)
# ════════════════════════════════════════════════════════════
def stepper_chain(w, id, P):
    """P = shared.py «재생기_이어붙이기» 칸
        title · task · caption · auto_ms · timetable(figs.timetable 의 시간표 칸 — steps 포함)
        heads = [단계마다 그림 위 제목] + [정리 그림 제목] · texts = [단계마다 글] + [정리 글]  (둘 다 길이 = 단계 수 + 1)
    P["kind"] = "chart" 이면 시간표 대신 관리도(P["chart"] = figs.control_chart 칸 — 분석 틀 stat_model)"""
    if P.get("kind") == "chart":
        Ch = P["chart"]
        n = len(Ch["steps"])
        if len(P["heads"]) != n + 1 or len(P["texts"]) != n + 1:
            raise ValueError(f"관리도 재생기: heads · texts 는 단계 수 + 1 = {n + 1}개여야 한다(지금 {len(P['heads'])} · {len(P['texts'])})")
        out = [{"svg": figs.control_chart(Ch, k, P["heads"][k]), "text": P["texts"][k], "row": None} for k in range(n + 1)]
        return w.stepper(out, title=P["title"], task=P["task"], auto_ms=P.get("auto_ms", 1300), id=id, caption=P.get("caption"))
    T = P["timetable"]
    n = len(T["steps"])
    if len(P["heads"]) != n + 1 or len(P["texts"]) != n + 1:
        raise ValueError(f"이어 붙이기 재생기: heads · texts 는 단계 수 + 1 = {n + 1}개여야 한다(지금 {len(P['heads'])} · {len(P['texts'])})")
    out = [{"svg": figs.timetable(T, k, P["heads"][k]), "text": P["texts"][k], "row": None} for k in range(n + 1)]
    return w.stepper(out, title=P["title"], task=P["task"], auto_ms=P.get("auto_ms", 1300), id=id, caption=P.get("caption"))


# ════════════════════════════════════════════════════════════
# 추가 그림 — 양식에 자리가 따로 없는 그림(상태 전이 · 시각별 막대 + 임계선 · 같은 번호 두 줄 비교)
# 2장(함정 카드 뒤) · 4장(조건별 표 뒤) · 5장(주의 카드 뒤)의 «추가_그림» 칸 — 비우면 블록을 하나도 넣지 않는다(v3 와 같은 책)
# ════════════════════════════════════════════════════════════
# 추가 그림 종류 → figs 함수 이름
EXTRA = {"상태전이": "states", "시각막대": "time_bars", "두줄비교": "pair_rows"}


def extra_figs(w, items):
    """items = [{"fig": 상태전이 | 시각막대 | 두줄비교, "P": 그림 칸, "caption": 한 줄, "fn": 각주 | None}] → 그림 블록(그림마다 하나)"""
    for it in items or ():
        if it.get("fig") not in EXTRA:
            raise ValueError(f"추가 그림 «{it.get('fig')}» 는 없다 — {', '.join(EXTRA)} 중 하나")
        if not it.get("P"):
            w.p(f"!!⟦빈 칸 — 추가 그림 · {it['fig']}⟧!!")
            blank(w, f"추가 그림 · {it['fig']}")
            continue
        w.svg(getattr(figs, EXTRA[it["fig"]])(it["P"]), caption=it.get("caption"), fn=it.get("fn"))
