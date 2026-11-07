# -*- coding: utf-8 -*-
r"""범용 책 엔진 — 블록 API · 실행 환경 · HTML 렌더 (과목과 무관한 코드만 둔다)

구조
- 책 한 권 = 책 폴더 book\<이름>\ 의 __init__.py(META · ORDER) + 모듈들(front · ch00 … · appendix)
- 모듈마다 build(w) 함수 하나. w(Writer) 의 메서드를 차례로 부르면 블록이 쌓인다
- 글 안의 {식} 은 그 모듈의 실행 환경(META["env"]() 가 만든 dict)에서 계산해 채운다 — 손으로 적은 숫자 금지
- 쪽 나누기 · 각주 번호 · 쪽 번호 · 목록은 브라우저(assets\book.js)가 한다. 여기서는 블록 HTML · 각주 · 연결고리 · 예시 코드만 만든다

사용법은 book\README.md
"""
import hashlib
import html as _html
import json
import re
import sys
import warnings
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))  # study_html — 공용 모듈 common.py 위치

from common import esc, hl_code  # noqa: E402  공용 모듈(수정 금지) — 이스케이프 · 코드 칠하기
from common import fmt as _common_fmt  # noqa: E402  표 칸 값 표시(NaN · 실수 30.0 · 앞뒤 공백 repr)


class BuildError(Exception):
    """빌드를 멈추는 오류 — 각주 용어 없음 · 연결고리 대상 없음 · 식 실행 실패"""


# ════════════════════════════════════════════════════════════
# 값 표시
# ════════════════════════════════════════════════════════════
def _is_frame(o):
    return hasattr(o, "columns") and hasattr(o, "itertuples")


def _is_series(o):
    return (not _is_frame(o)) and hasattr(o, "index") and hasattr(o, "items") and hasattr(o, "dtype")


def _scalar(v):
    """numpy 스칼라 → 파이썬 값"""
    if hasattr(v, "item") and not isinstance(v, (str, bytes)) and getattr(v, "ndim", 1) == 0:
        try:
            return v.item()
        except (ValueError, AttributeError):
            return v
    return v


def fmt_val(v):
    """글 안에 넣는 값 — 정수는 천 단위 쉼표, 실수는 유효숫자 6자리, 그 밖은 str"""
    v = _scalar(v)
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        if v != v:
            return "NaN"
        return f"{v:g}"
    return str(v)


def cell_text(v, spec=None, tfmt=None, na="NaN"):
    """표 칸 하나의 글자"""
    if callable(spec):
        return str(spec(v))
    if spec and not (isinstance(v, float) and v != v):
        try:
            return format(_scalar(v), spec)
        except (TypeError, ValueError):
            pass
    if tfmt and hasattr(v, "strftime") and v == v:
        return v.strftime(tfmt)
    t = _common_fmt(v)
    if t in ("NaN", "<NA>", "None", "NaT"):
        return na if t in ("NaN", "NaT") else t
    return t


# ════════════════════════════════════════════════════════════
# 글 꾸밈 — **굵게** · !!빨강!! · ++초록++ · `코드` · {식} · {식:형식} · 줄바꿈 \n
# ════════════════════════════════════════════════════════════
_PH_OPEN, _PH_CLOSE = "", ""
_MARKS = [(re.compile(r"\*\*(.+?)\*\*", re.S), r'<b>\1</b>'),
          (re.compile(r"!!(.+?)!!", re.S), r'<b class="bad">\1</b>'),
          (re.compile(r"\+\+(.+?)\+\+", re.S), r'<b class="good">\1</b>'),
          (re.compile(r"⟪(.+?)⟫", re.S), r'<b class="later">\1</b>')]  # 회색 «2차판에서 채워짐» 자리(단계별 배포)

# 지금 빌드의 판(단계별 배포) — None = 판 없음(옛 빌드) · 1 = 1차판 · 2 = 2차판. build_book.py 가 책을 불러오기 전에 넣는다(책의 data.py 가 읽는다)
STAGE = None


def _top_colon(expr):
    """형식 지정 «:» 위치 — 괄호 · 따옴표 밖의 첫 콜론(형식 안의 콜론 «%H:%M» 을 살린다). 없으면 -1"""
    depth, q, pos = 0, None, -1
    for i, ch in enumerate(expr):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            return i
    return pos


def _eval_expr(expr, env, where):
    k = _top_colon(expr)
    body, spec = (expr[:k], expr[k + 1:]) if k >= 0 else (expr, None)
    try:
        val = eval(body, env)
    except Exception as e:
        raise BuildError(f"{where}: 글 안의 식 {{{expr}}} 실행 실패 — {type(e).__name__}: {e}") from None
    if spec:
        return format(_scalar(val), spec)
    return fmt_val(val)


def _fill(text, env, where):
    """{식} 을 값으로 바꾸고 자리표시로 감싼 글 + 값 목록. {{ }} 는 글자 그대로"""
    out, vals, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            if text[i + 1:i + 2] == "{":
                out.append("{")
                i += 2
                continue
            depth, j, q = 1, i + 1, None
            while j < n and depth:
                ch = text[j]
                if q:
                    if ch == q:
                        q = None
                elif ch in "\"'":
                    q = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                j += 1
            if depth:
                raise BuildError(f"{where}: 닫히지 않은 {{ — {text[:60]}")
            vals.append(_eval_expr(text[i + 1:j - 1], env, where))
            out.append(f"{_PH_OPEN}{len(vals) - 1}{_PH_CLOSE}")
            i = j
            continue
        if c == "}":
            if text[i + 1:i + 2] == "}":
                out.append("}")
                i += 2
                continue
            raise BuildError(f"{where}: 짝 없는 }} — {text[:60]}")
        out.append(c)
        i += 1
    return "".join(out), vals


def render_text(text, env, where="글"):
    """꾸밈 글 → HTML. `코드` 안은 꾸밈 · 식 계산을 하지 않는다"""
    if text is None:
        return ""
    parts = re.split(r"(`[^`\n]+`)", str(text))
    out = []
    for part in parts:
        if len(part) >= 2 and part[0] == "`" and part[-1] == "`":
            m = re.search(r"\{([A-Za-z_]\w*)", part)
            if m and m.group(1) in env:  # `코드` 안의 {식} 은 계산되지 않는다 — 조용히 글자로 남는 실수를 막는다
                raise BuildError(f"{where}: `코드` 안의 {{{m.group(1)}…}} 는 계산되지 않는다 — 파이썬 f-글자로 값을 먼저 넣을 것: {part}")
            out.append(f"<code>{esc(part[1:-1])}</code>")
            continue
        filled, vals = _fill(part, env, where)
        h = esc(filled)
        for rx, rep in _MARKS:
            h = rx.sub(rep, h)
        h = h.replace("\n", "<br>")
        h = re.sub(f"{_PH_OPEN}(\\d+){_PH_CLOSE}", lambda m: esc(vals[int(m.group(1))]), h)
        h = _MARKS[3][0].sub(_MARKS[3][1], h)  # 값으로 들어온 «⟪2차판⟫»(1차판의 아직 없는 숫자)도 회색으로
        out.append(h)
    return "".join(out)


def _insert_marker(h, term, fid):
    """HTML 안 첫 «term» 바로 뒤에 각주 표식을 넣는다. <code> 안이면 </code> 뒤에. 못 찾으면 None"""
    needle = esc(term)
    toks = re.split(r"(<[^>]+>)", h)
    in_code = 0
    for i, t in enumerate(toks):
        if t.startswith("<"):
            tag = t.lower()
            if tag.startswith("<code"):
                in_code += 1
            elif tag.startswith("</code"):
                in_code = max(0, in_code - 1)
            continue
        k = t.find(needle)
        if k < 0:
            continue
        mark = f'<sup class="fm" data-f="{fid}"></sup>'
        if in_code:
            depth = in_code
            for j in range(i + 1, len(toks)):
                tj = toks[j].lower()
                if tj.startswith("<code"):
                    depth += 1
                elif tj.startswith("</code"):
                    depth -= 1
                    if depth == 0:
                        # 이미 붙은 표식(</code> 바로 뒤 sup) 뒤로 — 표식 순서 = 각주 단 순서
                        k2 = j + 1  # 토큰: </code> · "" · <sup …> · "" · </sup> · 다음 글 — 표식 하나 = 4토큰 건너뛰기
                        while k2 + 3 < len(toks) and toks[k2] == "" and toks[k2 + 1].startswith('<sup class="fm'):
                            k2 += 4
                        if k2 > j + 1:  # 바로 앞에 표식이 붙어 있음 — 쉼표로 구분(fm2)
                            mark = f'<sup class="fm fm2" data-f="{fid}"></sup>'
                        toks.insert(k2, mark)
                        return "".join(toks)
            return None
        toks[i] = t[:k + len(needle)] + mark + t[k + len(needle):]
        return "".join(toks)
    return None


# ════════════════════════════════════════════════════════════
# 표 HTML
# ════════════════════════════════════════════════════════════
# 표 경고 — 표시할 행 밖을 가리킨 칸 · 행 · 주석(조용히 무시되던 것). build_book.py 가 빌드 끝 «경고» 로 알리고 비운다
TABLE_WARN = []


def _norm_note(v, default="bad"):
    if isinstance(v, (tuple, list)):
        return v[0], v[1]
    return v, default


def table_html(obj=None, *, header=None, rows=None, caption_html="", index=None, hl_rows=(), bad_rows=(),
               good_rows=(), hl_cells=(), bad_cells=(), good_cells=(), hl_cols=(), notes=None, col_notes=None,
               max_rows=None, fmt=None, tfmt=None, dtype=False, small=False, na="NaN", index_name=None,
               value_name=None, cls="", note_head=None, code_cols=(), html_cols=(), nw_cols=()):
    """DataFrame · Series(덕 타이핑) 또는 header + rows → <table>. 행 위치는 표시 순서(0부터)

    hl_rows · bad_rows · good_rows : 강조 · 틀림(빨강) · 맞음(초록) 행
    hl_cells · bad_cells · good_cells : (행 위치, 열 이름 또는 열 위치) — 열 위치는 인덱스 열을 빼고 센다
    hl_cols : 강조 열(이름 또는 위치)
    notes : {행 위치: "← 설명"} — 표 오른쪽 주석(주석 화살표). ("글", "muted"|"good"|"bad") 로 색 지정
    col_notes : {열 이름: "↓ 설명"} — 머리 위 주석
    max_rows : 넘으면 앞 max_rows 행만 + «… 총 N행» 줄
    dtype : True 면 맨 아래에 자료형 줄(Series 는 한 칸, DataFrame 은 열마다)
    """
    fmt = fmt or {}
    total = None
    dtypes = None
    if obj is not None and _is_frame(obj):
        cols = [str(c) for c in obj.columns]
        show_ix = True if index is None else index
        ixname = index_name if index_name is not None else (str(obj.index.name) if obj.index.name is not None else "")
        total = len(obj)
        view = obj.iloc[:max_rows] if max_rows and total > max_rows else obj
        body = [(ix, list(r)) for ix, r in zip(view.index, view.itertuples(index=False))]
        if dtype:
            dtypes = [str(t) for t in obj.dtypes]
    elif obj is not None and _is_series(obj):
        vname = value_name if value_name is not None else (str(obj.name) if obj.name is not None else "값")
        cols = [vname]
        show_ix = True if index is None else index
        ixname = index_name if index_name is not None else (str(obj.index.name) if obj.index.name is not None else "")
        total = len(obj)
        view = obj.iloc[:max_rows] if max_rows and total > max_rows else obj
        body = [(ix, [v]) for ix, v in view.items()]
        if dtype:
            dtypes = [str(obj.dtype)]
    else:
        if header is None or rows is None:
            raise BuildError("표: DataFrame · Series 또는 header + rows 가 필요하다")
        cols = [str(c) for c in header]
        show_ix = bool(index)
        ixname = index_name or ""
        total = len(rows)
        view_rows = rows[:max_rows] if max_rows and total > max_rows else rows
        body = [(i, list(r)) for i, r in enumerate(view_rows)]

    def col_pos(c):
        if isinstance(c, int):
            return c
        try:
            return cols.index(str(c))
        except ValueError:
            raise BuildError(f"표: 열 «{c}» 가 없다 (열: {cols})") from None

    cellset = {}
    for name, cells in (("hl", hl_cells), ("bad", bad_cells), ("good", good_cells)):
        for r, c in cells:
            cellset[(r, col_pos(c))] = name
    colset = {col_pos(c) for c in hl_cols}
    codeset = {col_pos(c) for c in code_cols}
    htmlset = {col_pos(c) for c in html_cols}  # 칸 글을 HTML 그대로(장 파일이 w.t() 로 꾸민 글)
    nwset = {col_pos(c) for c in nw_cols}  # 줄바꿈하지 않는 열(wr 표 안에서)
    notes = {k: _norm_note(v) for k, v in (notes or {}).items()}
    # 행 밖 검사 — 열 이름이 틀리면 위에서 멈추지만, 행 번호가 표보다 크면 아무 표시 없이 지나갔다
    nrow = len(body)
    head_txt = caption_html[:30] if caption_html else " · ".join(cols[:3])
    for what, rs in (("bad_cells · good_cells · hl_cells", [r for r, _ in cellset]), ("bad_rows · good_rows · hl_rows", list(bad_rows) + list(good_rows) + list(hl_rows)),
                     ("notes", list(notes))):
        out_of = sorted({r for r in rs if not (isinstance(r, int) and 0 <= r < nrow)}, key=str)
        if out_of:
            TABLE_WARN.append(f"표 «{head_txt}»: {what} 의 행 {out_of} 이 표({nrow}행) 밖이라 표시되지 않는다")
    has_notes = bool(notes) or bool(note_head)
    out = [f'<table class="t{" sm" if small else ""}{(" " + cls) if cls else ""}">']
    if caption_html:
        out.append(f"<caption>{caption_html}</caption>")
    out.append("<thead>")
    if col_notes:
        cn = {col_pos(k): v for k, v in col_notes.items()}
        out.append('<tr class="cn">' + ('<th class="nb"></th>' if show_ix else ""))
        for i in range(len(cols)):
            out.append(f'<th class="nb">{esc(cn[i]) if i in cn else ""}</th>')
        out.append(('<th class="nb"></th>' if has_notes else "") + "</tr>")
    out.append("<tr>" + (f'<th class="ix">{esc(ixname)}</th>' if show_ix else ""))
    for i, c in enumerate(cols):
        hcl = " ".join(x for x, on in (("hc", i in colset), ("nw", i in nwset)) if on)
        out.append(f'<th{f" class={chr(34)}{hcl}{chr(34)}" if hcl else ""}>{esc(c)}</th>')
    if has_notes:
        out.append(f'<th class="nb nt">{esc(note_head or "")}</th>')
    out.append("</tr></thead><tbody>")
    for r, (ix, vals) in enumerate(body):
        rc = "bad" if r in set(bad_rows) else "good" if r in set(good_rows) else "hl" if r in set(hl_rows) else ""
        out.append(f'<tr{f" class={rc}" if rc else ""}>')
        if show_ix:
            out.append(f'<td class="ix">{esc(cell_text(ix, fmt.get("#"), tfmt, na))}</td>')
        for i, v in enumerate(vals):
            t = cell_text(v, fmt.get(cols[i]), tfmt, na)
            cl = []
            if t == na or t in ("<NA>", "None"):
                cl.append("na")
            if i in colset:
                cl.append("hc")
            if i in nwset:
                cl.append("nw")
            if (r, i) in cellset:
                cl.append("c-" + cellset[(r, i)])
            inner = str(v) if i in htmlset else (f"<code>{esc(t)}</code>" if i in codeset else esc(t))
            out.append(f'<td{(" class=" + chr(34) + " ".join(cl) + chr(34)) if cl else ""}>{inner}</td>')
        if has_notes:
            if r in notes:
                txt, tone = notes[r]
                out.append(f'<td class="nr {tone}">{esc(txt)}</td>')
            else:
                out.append('<td class="nb"></td>')
        out.append("</tr>")
    span = len(cols) + (1 if show_ix else 0)
    if max_rows and total > max_rows:
        out.append(f'<tr class="more"><td colspan="{span}">… 총 {total:,}행</td>' + ('<td class="nb"></td>' if has_notes else "") + "</tr>")
    if dtypes:
        out.append('<tr class="dt">' + ('<td class="ix">자료형</td>' if show_ix else ""))
        for t in dtypes:
            out.append(f"<td>{esc(t)}</td>")
        out.append(('<td class="nb"></td>' if has_notes else "") + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ════════════════════════════════════════════════════════════
# 그림 도우미 — SVG (좌표는 viewBox 기준, 글꼴은 쪽 글꼴)
# ════════════════════════════════════════════════════════════
TONE = {"acc": ("#2563eb", "#eaf1ff"), "ng": ("#dc2626", "#fdecec"), "ok": ("#16a34a", "#e9f7ee"),
        "pur": ("#7c3aed", "#f3eeff"), "gray": ("#4b5563", "#f1f3f6"), "amber": ("#b45309", "#fff4e0"),
        "teal": ("#0f766e", "#e6f6f4"), "ink": ("#1f2328", "#ffffff"), "mute": ("#9aa3ad", "#f6f7f9")}


def _tone(t):
    return TONE.get(t, (t, "#ffffff"))


class Svg:
    """간단한 SVG 그림. 메서드를 부른 순서대로 그린다(뒤에 부른 것이 위)"""

    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def _txt(self, x, y, text, size, color, anchor, weight, lh=1.25, italic=False, halo=False):
        lines = str(text).split("\n")
        y0 = y - (len(lines) - 1) * size * lh / 2
        st = ' font-style="italic"' if italic else ""
        if halo:  # 선 위에 얹는 글자 — 바탕색 테두리로 선을 가린다
            st += ' stroke="#fffdf8" stroke-width="4" stroke-linejoin="round" paint-order="stroke"'
        sp = "".join(f'<tspan x="{x:g}" y="{y0 + i * size * lh:g}">{esc(ln)}</tspan>' for i, ln in enumerate(lines))
        return (f'<text text-anchor="{anchor}" dominant-baseline="central" font-size="{size:g}" '
                f'fill="{color}" font-weight="{weight}"{st}>{sp}</text>')

    def text(self, x, y, text, size=12, tone="gray", anchor="middle", bold=False, italic=False, halo=False):
        self.parts.append(self._txt(x, y, text, size, _tone(tone)[0], anchor, 700 if bold else 400, italic=italic, halo=halo))
        return self

    def box(self, x, y, w, h, text="", tone="gray", size=12, bold=False, rx=6, fill=None, stroke=None,
            dash=False, sw=1.5, text_tone=None, anchor="middle"):
        col, bg = _tone(tone)
        d = ' stroke-dasharray="5 4"' if dash else ""
        self.parts.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" '
                          f'fill="{fill or bg}" stroke="{stroke or col}" stroke-width="{sw:g}"{d}/>')
        if text != "":
            tx = x + w / 2 if anchor == "middle" else x + 8
            self.parts.append(self._txt(tx, y + h / 2, text, size, _tone(text_tone)[0] if text_tone else col,
                                        anchor, 700 if bold else 400))
        return self

    def line(self, x1, y1, x2, y2, tone="gray", sw=1.5, dash=False):
        d = ' stroke-dasharray="5 4"' if dash else ""
        self.parts.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{_tone(tone)[0]}" stroke-width="{sw:g}"{d}/>')
        return self

    def arrow(self, x1, y1, x2, y2, tone="acc", sw=2, label=None, size=11, head=8, dash=False, lx=None, ly=None,
              bold=True):
        col = _tone(tone)[0]
        dx, dy = x2 - x1, y2 - y1
        ln = (dx * dx + dy * dy) ** 0.5 or 1
        ux, uy = dx / ln, dy / ln
        bx, by = x2 - ux * head, y2 - uy * head
        d = ' stroke-dasharray="5 4"' if dash else ""
        self.parts.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{bx:g}" y2="{by:g}" stroke="{col}" stroke-width="{sw:g}"{d}/>')
        px, py = -uy * head * 0.55, ux * head * 0.55
        self.parts.append(f'<path d="M{x2:g} {y2:g} L{bx + px:g} {by + py:g} L{bx - px:g} {by - py:g} Z" fill="{col}"/>')
        if label:
            mx = lx if lx is not None else (x1 + x2) / 2
            my = ly if ly is not None else (y1 + y2) / 2 - size * 0.9
            self.parts.append(self._txt(mx, my, label, size, col, "middle", 700 if bold else 400, halo=True))
        return self

    def path(self, d, tone="gray", sw=1.5, fill="none", dash=False):
        da = ' stroke-dasharray="5 4"' if dash else ""
        self.parts.append(f'<path d="{d}" stroke="{_tone(tone)[0]}" stroke-width="{sw:g}" fill="{fill}"{da}/>')
        return self

    def raw(self, markup):
        self.parts.append(markup)
        return self

    def render(self, label=""):
        return (f'<svg class="svgfig" viewBox="0 0 {self.w:g} {self.h:g}" role="img" aria-label="{esc(label)}" '
                f'xmlns="http://www.w3.org/2000/svg">{"".join(self.parts)}</svg>')


def pair_svg(left, right, pairs, left_title="", right_title="", tones=None, bad=(), box_w=86, gap=170, row_h=30,
             size=12):
    """짝짓기 그림 — 왼쪽 항목 · 오른쪽 항목을 선으로 잇는다. pairs = [(왼쪽 위치, 오른쪽 위치)], bad = 빨간 선으로 칠할 쌍"""
    tones = tones or {}
    n = max(len(left), len(right))
    top = 26 if (left_title or right_title) else 6
    H = top + n * row_h + 6
    W = box_w * 2 + gap + 12
    s = Svg(W, H)
    lx, rx = 6, 6 + box_w + gap
    ly = lambda i: top + i * row_h + (row_h - 22) / 2  # noqa: E731
    roff = (n - len(right)) * row_h / 2
    loff = (n - len(left)) * row_h / 2
    if left_title:
        s.text(lx + box_w / 2, 11, left_title, size=11, bold=True)
    if right_title:
        s.text(rx + box_w / 2, 11, right_title, size=11, bold=True)
    for a, b in pairs:
        t = "ng" if (a, b) in set(bad) else tones.get(("l", a), tones.get(("r", b), "acc"))
        s.line(lx + box_w, loff + ly(a) + 11, rx, roff + ly(b) + 11, tone=t, sw=2)
    for i, t in enumerate(left):
        s.box(lx, loff + ly(i), box_w, 22, t, tone=tones.get(("l", i), "gray"), size=size, bold=True, rx=4)
    for i, t in enumerate(right):
        s.box(rx, roff + ly(i), box_w, 22, t, tone=tones.get(("r", i), "gray"), size=size, bold=True, rx=4)
    return s.render(f"{left_title} ↔ {right_title}")


# ════════════════════════════════════════════════════════════
# 조각(Item) · 블록(Block)
# ════════════════════════════════════════════════════════════
class Item:
    """그림 · 상자 안에 넣는 조각(표 · 화살표 · 글). 혼자서는 블록이 아니다"""

    def __init__(self, html, make=None, fids=None, cap=""):
        self.html = html
        self.make = list(make or [])
        self.fids = list(fids or [])
        self.cap = cap


class Block:
    __slots__ = ("id", "kind", "html", "ch", "chl", "anchors", "fids", "make", "flags", "group", "links", "cap",
                 "module", "toc", "tail")

    def __init__(self, kind, html):
        self.kind, self.html = kind, html
        self.id = ""
        self.ch = ""
        self.chl = ""
        self.anchors = []
        self.fids = []
        self.make = []
        self.flags = set()  # np(새 쪽) · fp(쪽 전체) · kn(다음 블록과 같은 쪽)
        self.group = None
        self.links = []
        self.cap = ""
        self.module = ""
        self.toc = None
        self.tail = ""


def slug_of(no, labels=None):
    """장 번호 · 이름 → 연결고리 앵커 이름(ASCII). 정수 3 → c3, «사례 A» → META labels 표의 값"""
    if isinstance(no, int):
        return f"c{no}"
    s = str(no)
    if labels and s in labels:
        return labels[s]
    if re.fullmatch(r"[A-Za-z0-9_\-]+", s):
        return s
    return "x" + hashlib.md5(s.encode("utf-8")).hexdigest()[:6]


def label_of(no):
    return f"{no}장" if isinstance(no, int) else str(no)


def plain(t):
    """꾸밈 글의 기호(** · !! · ++ · `)만 지운 맨 글 — 차례 · 머리글 · 목록용"""
    return re.sub(r"\*\*|!!|\+\+|`", "", str(t))


# ════════════════════════════════════════════════════════════
# Writer — 모듈 하나를 쓰는 도구. build(w) 안에서 쓴다
# ════════════════════════════════════════════════════════════
class Writer:
    def __init__(self, book, module, env):
        self.book = book
        self.module = module
        self.env = env
        self.blocks = []
        self.ch = None  # 지금 장 기록(dict)
        self.chkey = module  # 장이 없을 때(앞부분)의 묶음 이름
        self.chl = ""  # 머리글에 쓸 장 이름
        self.sec_no = 0
        self.pending = []  # 다음 블록에 붙일 «예시 데이터 만든 과정» 코드
        self._group = None
        self._np_next = False
        self.bseq = 0  # 장 안 블록 순번(옛 블록 ID · 위치 알림)
        self.last_warnings = []
        # 고정 블록 ID 의 바탕 이름 — 마지막으로 읽은 칸 이름(kit.Slots 가 at() 으로 넣는다)
        self.slot = ""
        # 다음 블록 하나에만 쓸 고정 이름(항목 id — Q1 · H3 …) — key() 로 넣는다
        self.next_key = None
        # 바탕 ID → 지금까지 나온 수(같은 칸에서 블록이 여럿이면 -2 · -3)
        self.keycount = {}

    # ── 실행 환경 ───────────────────────────────────────
    def run(self, lines, show=True):
        """코드 줄을 실행 환경에서 실행한다. show=True 면 다음 블록의 «예시 데이터 만든 과정» 에 붙는다"""
        if isinstance(lines, str):
            lines = [lines]
        with warnings.catch_warnings(record=True) as wl:
            warnings.simplefilter("always")
            try:
                exec("\n".join(lines), self.env)
            except Exception as e:
                raise BuildError(f"{self._where()}: 코드 실행 실패 — {type(e).__name__}: {e}\n" + "\n".join(lines)) from None
        self.last_warnings = list(dict.fromkeys(type(x.message).__name__ for x in wl))  # 경고 이름(본문에 보일 때)
        if show:
            self.pending.extend(lines)
        return self

    def val(self, expr):
        """식의 값(파이썬 객체) — 장 파일에서 문장 · 표를 만들 때"""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return eval(expr, self.env)
        except Exception as e:
            raise BuildError(f"{self._where()}: 식 {expr} 실행 실패 — {type(e).__name__}: {e}") from None

    def try_run(self, expr):
        """에러가 나는지 보여 줄 때 — (값, 에러 문구) 를 돌려준다. 오타 계열 에러는 빌드를 멈춘다"""
        with warnings.catch_warnings(record=True) as wl:
            warnings.simplefilter("always")
            try:
                v = eval(expr, self.env)
                return v, None, [type(x.message).__name__ for x in wl]
            except (SyntaxError, NameError, AttributeError) as e:
                raise BuildError(f"{self._where()}: {expr} — {type(e).__name__}: {e}") from None
            except Exception as e:
                return None, f"{type(e).__name__}: {str(e).splitlines()[0]}", [type(x.message).__name__ for x in wl]

    def src(self, *names):
        """공통 데이터 표를 만든 코드(META["code"][이름])를 다음 블록의 «예시 데이터 만든 과정» 에 붙인다(다시 실행하지 않는다)"""
        code = self.book.meta.get("code", {})
        for n in names:
            if n not in code:
                raise BuildError(f"{self._where()}: 공통 데이터 코드 «{n}» 가 없다")
            self.pending.extend(code[n])
        return self

    def t(self, text):
        """꾸밈 글 → HTML (장 파일에서 직접 HTML 을 조립할 때)"""
        return render_text(text, self.env, self._where())

    def _where(self):
        return f"{self.module}" + (f" · {self.ch['label']}" if self.ch else "") + f" · 블록 {self.bseq}"

    # ── 각주 ─────────────────────────────────────────────
    def _fn(self, h, fn):
        """fn={"용어": "설명"} — 용어의 첫 등장 뒤에 표식. 설명이 «(전체 이름) …» 로 시작하면 용어 옆에 붙인다"""
        fids = []
        for term, desc in (fn or {}).items():
            fid = self.book.add_fn(term, desc, self)
            nh = _insert_marker(h, term, fid)
            if nh is None:
                raise BuildError(f"{self._where()}: 각주 용어 «{term}» 가 그 블록 글에 없다")
            h = nh
            fids.append(fid)
        return h, fids

    # ── 블록 추가 ────────────────────────────────────────
    def at(self, name):
        """고정 블록 ID 의 바탕 칸 이름을 바꾼다 — 이 뒤 블록들의 ID = «장-칸 이름»(-2 · -3)"""
        self.slot = re.sub(r"\s+", "_", str(name))

    def key(self, name):
        """다음 블록 하나의 고정 이름(항목 id) — ID = «장-이름»"""
        self.next_key = re.sub(r"\s+", "_", str(name))

    def _bid(self, kind):
        """블록 ID — 옛 방식(legacy_ids) = «장-순번 3자리», 기본 = «장-칸 이름»(판이 바뀌어 블록 수가 달라져도 같은 칸은 같은 ID)"""
        if self.book.legacy_ids:
            return f"{self.chkey}-{self.bseq:03d}"
        if kind in ("chapter", "matter", "part", "cover"):
            base = self.chkey
        elif self.next_key:
            base = f"{self.chkey}-{self.next_key}"
        else:
            base = f"{self.chkey}-{self.slot or '본문'}"
        self.next_key = None
        n = self.keycount[base] = self.keycount.get(base, 0) + 1
        bid = base if n == 1 else f"{base}-{n}"
        while bid in self.book.ids:  # 다른 모듈 · 장에서 이미 쓴 ID(드묾) — 뒤에 ~ 를 붙인다
            bid += "~"
        self.book.ids.add(bid)
        return bid

    def _add(self, kind, h, fids=(), make=None, flags=(), anchors=(), cap="", items=(), id=None, links=(), toc=None):
        self.bseq += 1
        b = Block(kind, h)
        b.module = self.module
        b.ch = self.chkey
        b.chl = self.chl
        b.id = self._bid(kind)
        b.fids = list(fids)
        for it in items:
            b.fids.extend(it.fids)
        mk = list(self.pending)
        self.pending = []
        for it in items:
            mk.extend(it.make)
        if make:
            mk.extend(make)
        b.make = mk
        b.flags = set(flags)
        if self._np_next:
            b.flags.add("np")
            self._np_next = False
        b.group = self._group
        b.anchors = list(anchors)
        if id:
            b.anchors.append(f"{self.chkey}-{id}")
        b.cap = cap
        b.links = list(links)
        b.toc = toc
        for f in b.fids:
            self.book.fns[f]["block"] = b.id
        self.blocks.append(b)
        return b

    @contextmanager
    def keep(self):
        """with w.keep(): … — 안에서 만든 블록들을 한 쪽에 둔다"""
        self.book.gseq += 1
        old, self._group = self._group, self.book.gseq
        try:
            yield
        finally:
            self._group = old

    def newpage(self):
        """다음 블록을 새 쪽에서 시작"""
        self._np_next = True

    # ── 구획 ─────────────────────────────────────────────
    def cover(self, title, subtitle="", *items, foot=""):
        """표지 — 쪽 전체"""
        body = "".join(it.html if isinstance(it, Item) else f"<p>{self.t(it)}</p>" for it in items)
        h = (f'<div class="cover"><p class="cvk">{self.t(self.book.meta.get("kicker", ""))}</p>'
             f'<h1>{self.t(title)}</h1><p class="cvs">{self.t(subtitle)}</p><div class="cvb">{body}</div>'
             f'<p class="cvf">{self.t(foot)}</p></div>')
        self.chkey, self.chl = "cover", ""
        b = self._add("cover", h, flags={"fp"}, anchors=["cover"], items=[i for i in items if isinstance(i, Item)])
        self.book.chapters.append({"kind": "cover", "key": "cover", "label": "", "title": "표지", "sections": [], "block": b.id})
        return b

    def matter(self, title, key, lead=None, toc=True):
        """번호 없는 앞 · 뒤 구획(이 책을 읽는 법 · 차례 …) — 새 쪽에서 시작, 머리글 = 제목"""
        self.ch = None
        self.chkey, self.chl = key, title
        self.sec_no = 0
        h = (f'<header class="chead mat"><h1>{self.t(title)}</h1>'
             + (f'<p class="lead">{self.t(lead)}</p>' if lead else "") + "</header>")
        rec = {"kind": "matter", "key": key, "label": "", "title": title, "sections": [], "module": self.module}
        b = self._add("matter", h, flags={"np", "kn"}, anchors=[key], toc=rec if toc else None)
        rec["block"] = b.id
        self.book.chapters.append(rec)
        return b

    def part(self, no, title, intro, questions=None, extra=None):
        """부 여는 쪽 — 쪽 전체. questions 를 비우면 이 부의 장 질문(chapter 의 question)을 빌드 때 모아 채운다"""
        self.ch = None
        self.chkey, self.chl = f"part{no}", f"{no}부 {title}"
        rec = {"kind": "part", "no": no, "key": f"part{no}", "title": title, "questions": questions,
               "module": self.module, "chapters": []}
        extra_html = ""
        items = []
        if extra is not None:
            ex = extra if isinstance(extra, (list, tuple)) else [extra]
            for it in ex:
                if isinstance(it, Item):
                    extra_html += it.html
                    items.append(it)
                else:
                    extra_html += f"<p>{self.t(it)}</p>"
        h = (f'<div class="partpg"><p class="pno">{no}부</p><h1>{self.t(title)}</h1>'
             f'<p class="pintro">{self.t(intro)}</p><div class="pq"><p class="pqh">이 부에서 답할 질문들</p>'
             f'<!--PARTQ:{no}--></div><div class="pex">{extra_html}</div></div>')
        b = self._add("part", h, flags={"fp"}, anchors=[f"part{no}"], toc=rec, items=items)
        rec["block"] = b.id
        self.book.chapters.append(rec)
        self.book.cur_part = rec
        return b

    def chapter(self, no, title, question, link=None, key=None, sub=None):
        """장 머리(E1) — 장 번호 · 제목 · 이 장의 질문 · 앞 장과의 연결 한 줄. 새 쪽에서 시작"""
        labels = self.book.meta.get("labels", {})
        slug = key or slug_of(no, labels)
        self.chkey = slug
        self.chl = f"{label_of(no)} · {plain(title)}"
        self.sec_no = 0
        self.bseq = 0  # 장 안 블록 순번(옛 블록 ID)
        self.slot = ""  # 고정 블록 ID 바탕 — 장마다 새로
        rec = {"kind": "chapter", "no": no, "key": slug, "label": label_of(no), "title": title,
               "question": question, "sections": [], "module": self.module}
        self.ch = rec
        h = (f'<header class="chead"><p class="cno">{esc(label_of(no))}</p><h1>{self.t(title)}'
             + (f' <span class="sub">{self.t(sub)}</span>' if sub else "") + "</h1>"
             + f'<p class="cq"><span>이 장의 질문</span>{self.t(question)}</p>'
             + (f'<p class="lead">{self.t(link)}</p>' if link else "") + "</header>")
        b = self._add("chapter", h, flags={"np", "kn"}, anchors=[slug], toc=rec)
        rec["block"] = b.id
        self.book.chapters.append(rec)
        if self.book.cur_part is not None:
            self.book.cur_part["chapters"].append(rec)
        return b

    def section(self, title, num=None, id=None):
        """절 제목(h2) — 자동 번호 «장.n». 다음 블록과 같은 쪽에 둔다"""
        self.sec_no += 1
        if num is None and self.ch is not None and isinstance(self.ch["no"], int):
            num = f"{self.ch['no']}.{self.sec_no}"
        anchor = f"{self.chkey}-{self.sec_no}"
        h = f'<h2 class="sec">{f"<b>{esc(num)}</b>" if num else ""}{self.t(title)}</h2>'
        b = self._add("section", h, flags={"kn"}, anchors=[anchor], id=id)
        rec = {"num": num, "title": title, "anchor": anchor, "block": b.id}
        if self.ch is not None:
            self.ch["sections"].append(rec)
        else:
            for c in reversed(self.book.chapters):
                if c.get("key") == self.chkey:
                    c["sections"].append(rec)
                    break
        return b

    def sub(self, title, id=None):
        """작은 제목(h3) — 다음 블록과 같은 쪽"""
        return self._add("sub", f'<h3 class="subh">{self.t(title)}</h3>', flags={"kn"}, id=id)

    # ── 글 ───────────────────────────────────────────────
    def p(self, text, fn=None, cls=None, id=None, make=None):
        """문단. fn={"용어": "설명"} 은 각주"""
        h, fids = self._fn(self.t(text), fn)
        return self._add("p", f'<p{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{h}</p>', fids, make=make, id=id)

    def ul(self, items, fn=None, ordered=False, cls=None, id=None):
        """목록 — 항목은 꾸밈 글"""
        tag = "ol" if ordered else "ul"
        h = f'<{tag}{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>' + "".join(f"<li>{self.t(x)}</li>" for x in items) + f"</{tag}>"
        h, fids = self._fn(h, fn)
        return self._add("list", h, fids, id=id)

    def back(self, ch, sec, text, fn=None, id=None, tag=None):
        """연결고리(L) — «↩ N장» 표식 + 그 장 · 절로 가는 링크
        ch: 장 번호(정수) · 장 이름(«사례 A») · 앞부분 키(«howto»). sec: 절 번호(정수) · 블록 id 이름(글자) · None(장 머리)
        tag: 표식 글자를 바꿀 때(앞부분 구획 등)"""
        labels = self.book.meta.get("labels", {})
        slug = slug_of(ch, labels)
        if sec is None:
            target, t = slug, label_of(ch)
        elif isinstance(sec, int):
            target = f"{slug}-{sec}"
            t = f"{label_of(ch)} · {ch}.{sec}" if isinstance(ch, int) else f"{label_of(ch)} · {sec}"
        else:
            target, t = f"{slug}-{sec}", label_of(ch)
        tag = tag or t
        body, fids = self._fn(self.t(text), fn)
        h = (f'<p class="backp"><a class="back" href="#{esc(target)}" data-to="{esc(target)}">↩ {esc(tag)}</a>'
             f'{body}</p>')
        return self._add("back", h, fids, links=[target], id=id)

    def next_q(self, text, to=None, fn=None):
        """다음 질문(F9) — 마지막 문단. to = 다음 장 번호(링크)"""
        body, fids = self._fn(self.t(text), fn)
        link = ""
        links = []
        if to is not None:
            slug = slug_of(to, self.book.meta.get("labels", {}))
            link = f' <a class="fwd" href="#{slug}" data-to="{slug}">→ {esc(label_of(to))}</a>'
            links.append(slug)
        h = f'<p class="nextq"><span>다음 질문</span>{body}{link}</p>'
        b = self._add("next", h, fids)
        b.tail = ",".join(links)  # 앞으로 가는 링크 — 대상이 빌드에 없으면 글만 남긴다
        return b

    def more(self, text, fn=None):
        """더 읽기 — 함정 깊이 읽기 안내 한 줄"""
        body, fids = self._fn(self.t(text), fn)
        return self._add("more", f'<p class="more"><span>더 읽기</span>{body}</p>', fids)

    # ── 조각(Item) ───────────────────────────────────────
    def T(self, src=None, caption=None, fn=None, make=None, **opts):
        """표 조각. src = 식(글자) · DataFrame · Series 또는 header= · rows= 로 직접"""
        mk = []
        obj = None
        if isinstance(src, str):
            obj = self.val(src)
            mk.append(src)
        elif src is not None:
            obj = src
        cap = self.t(caption) if caption else ""
        h = table_html(obj, caption_html=cap, **opts)
        fids = []
        if fn:
            h, fids = self._fn(h, fn)
        if make:
            mk.extend(make)
        return Item(h, mk, fids, cap=re.sub("<[^>]+>", "", cap))

    def arrow(self, label="", code=None, tone="acc", down=False, fn=None, width=None):
        """화살표 조각 — 위에 동작 이름, 아래에 연산 이름표(코드 한 줄)"""
        lab = self.t(label) if label else ""
        cd = f'<span class="opw"><code class="op">{esc(code)}</code></span>' if code else ""  # 각주 표식이 코드 바로 옆에 붙도록 감싼다
        svg = ('<svg viewBox="0 0 24 60" class="dn"><line x1="12" y1="2" x2="12" y2="46" stroke="currentColor" stroke-width="3"/>'
               '<path d="M4 44 L12 58 L20 44 Z" fill="currentColor"/></svg>') if down else (
              '<svg viewBox="0 0 100 24"><line x1="2" y1="12" x2="86" y2="12" stroke="currentColor" stroke-width="3"/>'
              '<path d="M84 4 L98 12 L84 20 Z" fill="currentColor"/></svg>')
        st = f' style="width:{width}"' if width else ""
        h = f'<div class="arrow {tone}{" down" if down else ""}"{st}><span>{lab}</span>{svg}{cd}</div>'
        fids = []
        if fn:
            h, fids = self._fn(h, fn)
        return Item(h, [], fids)

    def plus(self, sym="+"):
        return Item(f'<span class="plus">{esc(sym)}</span>')

    def note(self, text, fn=None, tone=""):
        """작은 글 조각"""
        h, fids = self._fn(self.t(text), fn)
        return Item(f'<div class="inote {tone}">{h}</div>', [], fids)

    def col(self, *items, cls=""):
        """세로로 쌓는 조각 묶음"""
        its = [i if isinstance(i, Item) else self.note(i) for i in items]
        return Item(f'<div class="vcol {cls}">' + "".join(i.html for i in its) + "</div>",
                    [m for i in its for m in i.make], [f for i in its for f in i.fids])

    def code(self, lines, title=None, fn=None, out=None):
        """짧은 코드 조각(본문은 연산 이름표 수준까지만). out = 출력 줄(콘솔 모양)"""
        if isinstance(lines, str):
            lines = [lines]
        body = "\n".join(hl_code(ln) for ln in lines)
        o = ""
        if out is not None:
            o = f'<pre class="cdo">{esc(out)}</pre>'
        h = (f'<div class="cdw">{f"<p class=cdt>{self.t(title)}</p>" if title else ""}'
             f'<pre class="cd"><code>{body}</code></pre>{o}</div>')
        fids = []
        if fn:
            h, fids = self._fn(h, fn)
        return Item(h, [], fids)

    def textfile(self, lines, title="", marks=None, notes=None, fn=None, numbers=True):
        """글자 파일 보기(메모장 · CSV) — marks={줄 위치: "hl"|"bad"|"good"}, notes={줄 위치: "← 설명"}"""
        marks = marks or {}
        notes = {k: _norm_note(v) for k, v in (notes or {}).items()}
        rows = []
        for i, ln in enumerate(lines):
            m = marks.get(i, "")
            nt = ""
            if i in notes:
                txt, tone = notes[i]
                nt = f'<span class="tfn {tone}">{esc(txt)}</span>'
            num = f'<span class="tfi">{i + 1}</span>' if numbers else ""
            rows.append(f'<div class="tfl {m}">{num}<span class="tft">{_mark_spans(ln)}</span>{nt}</div>')
        h = (f'<div class="tf">{f"<div class=tfh>{esc(title)}</div>" if title else ""}'
             f'<div class="tfb">{"".join(rows)}</div></div>')
        fids = []
        if fn:
            h, fids = self._fn(h, fn)
        return Item(h, [], fids)

    def svg_item(self, markup, width=None, caption=None):
        st = f' style="width:{width}"' if width else ""
        cap = f'<p class="cap">{self.t(caption)}</p>' if caption else ""
        return Item(f'<div class="svgw"{st}>{markup}</div>{cap}')

    def html_item(self, raw):
        return Item(raw)

    # ── 그림 · 표 블록 ───────────────────────────────────
    def table(self, src=None, caption=None, fn=None, make=None, id=None, center=True, **opts):
        """표 블록(가운데 정렬)"""
        it = self.T(src, caption=caption, fn=None, make=make, **opts)
        h = f'<div class="fig{"" if center else " left"}">{it.html}</div>'
        fids = []
        if fn:
            h, fids = self._fn(h, fn)
        return self._add("table", h, fids, items=[it], cap=it.cap, id=id)

    def fig(self, *items, caption=None, fn=None, make=None, id=None, gap=None, align="center", wrap=False):
        """가로 그림 — 조각(표 · 화살표 · 글 · 세로 묶음)을 나란히. 캡션은 아래"""
        its = [i if isinstance(i, Item) else self.note(i) for i in items]
        st = []
        if gap:
            st.append(f"gap:{gap}")
        if align != "center":
            st.append(f"align-items:{align}")
        style = f' style="{";".join(st)}"' if st else ""
        cap = f'<p class="cap">{self.t(caption)}</p>' if caption else ""
        h = f'<div class="fig{" wrap" if wrap else ""}"{style}>{"".join(i.html for i in its)}</div>{cap}'
        fids = []
        if fn:
            h, fids = self._fn(h, fn)
        return self._add("fig", h, fids, items=its, make=make, id=id,
                         cap=re.sub("<[^>]+>", "", cap) or next((i.cap for i in its if i.cap), ""))

    def svg(self, markup, caption=None, fn=None, make=None, width=None, id=None):
        """SVG 그림 블록 — markup 은 Svg(...).render() 나 pair_svg(...) 결과"""
        st = f' style="width:{width}"' if width else ""
        cap = f'<p class="cap">{self.t(caption)}</p>' if caption else ""
        h = f'<div class="svgw"{st}>{markup}</div>{cap}'
        fids = []
        if fn:
            h, fids = self._fn(h, fn)
        return self._add("svg", h, fids, make=make, id=id, cap=re.sub("<[^>]+>", "", cap))

    def html(self, raw, fn=None, make=None, id=None, kind="html", items=()):
        """날 HTML 블록(마지막 수단)"""
        h, fids = self._fn(raw, fn)
        return self._add(kind, h, fids, make=make, id=id, items=items)

    # ── 상자 ─────────────────────────────────────────────
    def _content(self, content):
        out, items = [], []
        for c in content:
            if isinstance(c, Item):
                out.append(c.html)
                items.append(c)
            elif isinstance(c, (list, tuple)):
                out.append("<ul>" + "".join(f"<li>{self.t(x)}</li>" for x in c) + "</ul>")
            else:
                out.append(f"<p>{self.t(c)}</p>")
        return "".join(out), items

    def box(self, kind, *content, title=None, fn=None, id=None, inline_title=False):
        """상자 — kind: rule(규칙) · name(이름) · ng(깨지는 곳) · faq · think · guess · sum · prac · task · info"""
        body, items = self._content(content)
        if title and inline_title and body.startswith("<p>"):
            body = f"<p><b class='bt'>{self.t(title)}</b> — " + body[3:]
            head = ""
        else:
            head = f'<p class="bh">{self.t(title)}</p>' if title else ""
        h = f'<div class="box {kind}">{head}{body}</div>'
        h, fids = self._fn(h, fn)
        return self._add("box-" + kind, h, fids, items=items, id=id)

    def rule(self, text, fn=None, id=None):
        """규칙 상자(F6) — 조건문 한 줄"""
        return self.box("rule", text, title="규칙", fn=fn, id=id, inline_title=True)

    def name(self, *content, fn=None, id=None):
        """이름 상자(F3) — 동작을 먼저 말한 뒤 이름을 붙이는 자리"""
        return self.box("name", *content, fn=fn, id=id)

    def ng(self, *content, title=None, fn=None, id=None):
        """깨지는 곳 · 주의 상자(빨강)"""
        return self.box("ng", *content, title=title, fn=fn, id=id)

    def faq(self, q, *a, fn=None, id=None):
        """자주 하는 질문(E4)"""
        body, items = self._content(a)
        h = (f'<div class="box faq"><p class="bh">자주 하는 질문</p><p class="q">{self.t(q)}</p>{body}</div>')
        h, fids = self._fn(h, fn)
        return self._add("box-faq", h, fids, items=items, id=id)

    def think(self, *content, fn=None, id=None):
        """생각해 보기(E5) — 정답 없이 생각만 시키는 질문"""
        return self.box("think", *content, title="생각해 보기", fn=fn, id=id)

    def _ans(self, a):
        body, items = self._content(a if isinstance(a, (list, tuple)) and not isinstance(a, str) else [a])
        return (f'<div class="ans"><div class="ai">{body}</div>'
                f'<button type="button" class="cov" aria-label="답 보기">답 보기</button></div>'), items

    def guess(self, q, a, fn=None, id=None, title="먼저 맞혀 보기"):
        """먼저 맞혀 보기(F8 · E6) — 답은 가려 두고 누르면 보인다(자리를 미리 잡아 쪽이 밀리지 않는다)"""
        qb, qitems = self._content([q] if not isinstance(q, (list, tuple)) else q)
        ab, aitems = self._ans(a)
        h = f'<div class="box guess"><p class="bh">{esc(title)}</p>{qb}{ab}</div>'
        h, fids = self._fn(h, fn)
        return self._add("box-guess", h, fids, items=qitems + aitems, id=id)

    def summary(self, points, fn=None, id=None, title="이 장의 정리"):
        """장 끝 정리(E9) — 핵심 3~6줄"""
        h = (f'<div class="box sum"><p class="bh">{esc(title)}</p><ul>'
             + "".join(f"<li>{self.t(x)}</li>" for x in points) + "</ul></div>")
        h, fids = self._fn(h, fn)
        return self._add("box-sum", h, fids, id=id)

    def practice(self, items, fn=None, title="연습 문제"):
        """연습 문제(E9) — [(질문, 답)] · 질문마다 블록 하나(쪽이 나뉠 수 있게), 답은 가림"""
        out = []
        for i, (q, a) in enumerate(items):
            qb, qitems = self._content([q] if not isinstance(q, (list, tuple)) else q)
            ab, aitems = self._ans(a)
            head = f'<p class="bh">{esc(title)}</p>' if i == 0 else ""
            h = (f'<div class="box prac{" first" if i == 0 else ""}">{head}<div class="pq1"><span class="pn1">{i + 1}</span>'
                 f'<div>{qb}{ab}</div></div></div>')
            h, fids = self._fn(h, fn if i == 0 else None)
            out.append(self._add("box-prac", h, fids, items=qitems + aitems))
        return out

    def task(self, *content, fn=None, title="열린 과제"):
        """열린 과제(E9) — 정답 없이 직접 해 볼 일"""
        return self.box("task", *content, title=title, fn=fn)

    def toc(self):
        """차례 자리 — 빌드 끝에 모든 장 · 절로 채운다"""
        return self._add("toc", "<!--TOC-->")

    # ── API 책 블록(engine_api.py — 쓰는 책만 불러온다) ───────────
    def call(self, method, path, **kw):
        """요청을 실제로 보내고 Exchange 를 돌려준다 — app="이름"(TestClient · ASGI 앱) 또는 base="http://127.0.0.1:포트" """
        from .engine_api import call
        return call(self, method, path, **kw)

    def exchange(self, req, res, source, name=None):
        """녹화 예시(외부 서비스 — 실행 아님) → Exchange"""
        from .engine_api import exchange
        return exchange(self, req, res, source, name=name)

    def http(self, ex, part="both", **kw):
        """HTTP 메시지 해부도 블록"""
        from .engine_api import http
        return http(self, ex, part, **kw)

    def listing(self, lines, **kw):
        """서버 코드 묶음 블록(run=True 면 실행)"""
        from .engine_api import listing
        return listing(self, lines, **kw)

    def seq(self, lanes, steps, **kw):
        """순서도 블록"""
        from .engine_api import seq
        return seq(self, lanes, steps, **kw)

    def gantt(self, tracks, **kw):
        """타임라인 블록"""
        from .engine_api import gantt
        return gantt(self, tracks, **kw)

    def back_x(self, book_doc, anchor, label, text, **kw):
        """책 사이 연결고리 «↗ 다른 책» — /{book_doc}#{anchor}"""
        from .engine_api import back_x
        return back_x(self, book_doc, anchor, label, text, **kw)

    # ── 조작 블록(engine_live.py — 쓰는 책만 불러온다) ───────────
    def stepper(self, steps, **kw):
        """단계 재생기 블록 — steps = [{"svg", "text", "row"}] · 처음 · 이전 · 다음 · 자동 재생"""
        from .engine_live import stepper
        return stepper(self, steps, **kw)

    def slider(self, params, frames, **kw):
        """조건 슬라이더 블록 — 조건 조합마다 미리 계산한 그림 · 지표를 골라 보인다"""
        from .engine_live import slider
        return slider(self, params, frames, **kw)

    def open_full(self, path, label, note=None, id=None):
        """크게 열기 블록 — 큰 조작 화면(HTML 한 파일)으로 가는 단추. 파일은 빌드가 출력 옆에 복사한다"""
        from .engine_live import open_full
        return open_full(self, path, label, note=note, id=id)


# ════════════════════════════════════════════════════════════
# Book — 모듈을 모아 HTML 한 파일로
# ════════════════════════════════════════════════════════════
class Book:
    def __init__(self, meta):
        self.meta = meta
        self.blocks = []
        self.fns = {}  # fid → dict(term, label, text, ch, block)
        self.fn_order = []
        self.chapters = []  # 앞뒤 구획 · 부 · 장 기록(나온 순서)
        self.gseq = 0
        self.cur_part = None
        self.modules = []
        self.warnings = []
        self._cur_writer = None
        self.x_links = []  # 책 사이 연결고리(back_x) — (블록 ID, 주소)
        self.ids = set()  # 이미 쓴 블록 ID(고정 ID 겹침 막기)
        self.legacy_ids = False  # True = 옛 블록 ID «장-순번»(v3 호환 빌드 — 바이트 비교용)
        self.edition = ""  # 판 표시 글(«1차판 · …» · «2차판») — 비우면 표시 없음
        self.prev = None  # 앞 판의 {블록 ID: 내용 해시} — 주면 새로 생기거나 바뀐 블록에 «새로» 띠
        self.extra_files = {}  # 함께 배포할 파일(open_full) — {출력 옆 이름: 원본 경로}

    def add_fn(self, term, desc, w, index=True):
        """각주 등록 → fid. index=False 면 용어 찾아보기에 넣지 않는다(녹화 출처처럼 용어가 아닌 것)"""
        fid = f"f{len(self.fns) + 1}"
        d = str(desc)
        label = term
        m = re.match(r"^\(([^)]*)\)\s*(.*)$", d, re.S)
        if m:
            label, d = f"{term}({m.group(1)})", m.group(2)
        self.fns[fid] = {"id": fid, "term": term, "label": label, "text": render_text(d, w.env, w._where()),
                         "ch": w.chkey, "chl": (w.ch["label"] if w.ch else w.chl), "block": ""}
        if not index:
            self.fns[fid]["noindex"] = True
        self.fn_order.append(fid)
        return fid

    def attach_qa(self, path):
        """스티커 질문 · 답(qa\\<doc>.json)을 «자주 하는 질문» 상자로 그 블록 바로 뒤에 넣는다(빌드 때)
        항목: {"id", "block": "c12-034" 또는 "anchor": "c12-5", "q": 질문, "a": 답(꾸밈 글),
               "cards": [{"title", "code": [줄 …, 마지막 줄 = 보여 줄 식], "hl": [행 위치]}]}  — 카드는 실행 결과 표로 보인다"""
        p = Path(path)
        if not p.exists():
            return 0
        from common import run_block  # 공용 모듈 — 마지막 줄을 식으로 평가
        items = json.loads(p.read_text(encoding="utf-8"))
        n = 0
        for it in items:
            pos = None
            for i, b in enumerate(self.blocks):
                if (it.get("block") and b.id == it["block"]) or (it.get("anchor") and it["anchor"] in b.anchors):
                    pos = i
            if pos is None:
                self.warnings.append(f"qa {it.get('id')}: 대상 블록 {it.get('block') or it.get('anchor')} 이 이 빌드에 없어 넣지 않았다")
                continue
            target = self.blocks[pos]
            env = self.meta["env"]()
            where = f"qa {it.get('id')}"
            new = []
            head = Block("box-faq", f'<div class="box faq"><p class="bh">자주 하는 질문</p><p class="q">{render_text(it["q"], env, where)}</p>'
                                    f'<p>{render_text(it.get("a", ""), env, where)}</p></div>')
            new.append(head)
            for k, c in enumerate(it.get("cards", [])):
                val, err, _ = run_block(env, list(c.get("code", [])))
                if err and err.split(":")[0] in ("SyntaxError", "NameError", "AttributeError"):
                    raise BuildError(f"{where}: 카드 «{c.get('title')}» 코드 오류 — {err}")
                cap = render_text(c.get("title", ""), env, where)
                if err:
                    inner = f'<p class="cap" style="text-align:left">{cap}</p><pre class="cdo">{esc(err)}</pre>'
                elif _is_frame(val) or _is_series(val):
                    inner = table_html(val, caption_html=cap, hl_rows=c.get("hl", ()), max_rows=c.get("max_rows", 14), small=True)
                else:
                    inner = f'<p class="cap" style="text-align:left">{cap}</p><pre class="cdo">{esc(fmt_val(val))}</pre>'
                make = list(c.get("code", []))
                b = Block("box-faq", f'<div class="box faq cont"><div class="fig left">{inner}</div></div>')
                b.make = make
                b.cap = re.sub("<[^>]+>", "", cap)
                new.append(b)
            for k, b in enumerate(new):
                b.id = f"{target.id}-qa{it.get('id', n)}-{k}"
                b.ch, b.chl, b.module = target.ch, target.chl, target.module
                b.group = None
            self.blocks[pos + 1:pos + 1] = new
            n += 1
        return n

    def run_module(self, name, build, env):
        w = Writer(self, name, env)
        self._cur_writer = w
        try:
            build(w)
        finally:
            for c in getattr(w, "_clients", {}).values():  # w.call 이 만든 클라이언트 — 장이 끝나면 닫는다
                try:
                    c.close()
                except Exception:
                    pass
        if w.pending:
            self.warnings.append(f"{name}: 붙일 블록 없이 남은 «예시 데이터 만든 과정» 코드 {len(w.pending)}줄")
        self.blocks.extend(w.blocks)
        self.modules.append(name)

    def lint(self):
        """각주 점검(경고만) — 본문 `코드` 속 함수 · 속성 이름이 책에서 처음 나온 블록까지 각주가 없으면 알린다"""
        skip = set(self.meta.get("no_fn", []))
        try:
            skip |= {k for k in self.meta["env"]().keys()}  # 데이터 변수 이름(alarm · insp …)은 빼고
        except Exception:
            pass
        pos = {b.id: i for i, b in enumerate(self.blocks)}
        fn_at = {}
        for fid in self.fn_order:
            f = self.fns[fid]
            fn_at.setdefault(f["term"], pos.get(f["block"], 10 ** 9))
        seen, out = set(), []
        for i, b in enumerate(self.blocks):
            # 표의 code_cols 칸(<td><code>값</code></td>)은 데이터 값이라 빼고 본다 — 해부도 · 코드 묶음 본문은 <code> 를 쓰지 않아 제목 · 줄 주석만 걸린다
            html_ = re.sub(r"<td[^>]*><code>.*?</code></td>", "", b.html, flags=re.S)
            for code in re.findall(r"<code[^>]*>(.*?)</code>", html_, re.S):
                code = _html.unescape(re.sub(r"<[^>]+>", "", code))
                names = re.findall(r"\.?([A-Za-z_][A-Za-z0-9_]*)\s*\(", code)
                names += re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)", code)
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", code.strip()):
                    names.append(code.strip())
                for nm in names:
                    if nm in skip or nm in seen:
                        continue
                    seen.add(nm)
                    hit = [t for t in fn_at if re.search(rf"(^|[^A-Za-z0-9_]){re.escape(nm)}($|[^A-Za-z0-9_])", t)]
                    if not hit or min(fn_at[t] for t in hit) > i:
                        out.append(f"각주 없이 처음 나온 코드 이름 «{nm}» — 블록 {b.id}")
        return out

    # ── 빌드 끝 처리 ─────────────────────────────────────
    def _toc_blocks(self):
        out = []
        for c in self.chapters:
            if c["kind"] == "part":
                h = (f'<div class="toc-part"><a href="#{c["key"]}" data-to="{c["key"]}">'
                     f'<span class="tl">{c["no"]}부 {esc(plain(c["title"]))}</span><span class="ld"></span>'
                     f'<span class="pg" data-to="{c["key"]}"></span></a></div>')
                b = Block("toc-part", h)
                b.flags = {"kn"}
                out.append(b)
                continue
            if c["kind"] == "matter" and c.get("key") == "toc":
                continue
            if c["kind"] == "cover":
                continue
            lab = c.get("label", "")
            tn = f'<span class="tn">{esc(lab)}</span>' if lab else ""
            rows = [f'<a class="toc-ch" href="#{c["key"]}" data-to="{c["key"]}">{tn}'
                    f'<span class="tl">{esc(plain(c["title"]))}</span><span class="ld"></span>'
                    f'<span class="pg" data-to="{c["key"]}"></span></a>']
            for s in c.get("sections", []):
                rows.append(f'<a class="toc-sec" href="#{s["anchor"]}" data-to="{s["anchor"]}"><span class="tn">{esc(s["num"] or "")}</span>'
                            f'<span class="tl">{esc(plain(s["title"]))}</span><span class="ld"></span>'
                            f'<span class="pg" data-to="{s["anchor"]}"></span></a>')
            out.append(Block("toc-ch", f'<div class="toc-blk">{"".join(rows)}</div>'))
        return out

    def _index_blocks(self):
        """용어 찾아보기 — 각주에서 자동. 용어마다 처음 나온 곳 하나(장 · 쪽)"""
        seen, entries = set(), []
        for fid in self.fn_order:
            f = self.fns[fid]
            if f["term"] in seen or f.get("noindex"):
                continue
            seen.add(f["term"])
            entries.append(f)

        def key(f):
            t = f["term"].lstrip("._")
            hangul = bool(re.match(r"[가-힣]", t))
            return (0 if hangul else 1, t.lower())

        entries.sort(key=key)
        title = self.meta.get("index_title", "용어 찾아보기")
        key_ = self.meta.get("index_key", "index")
        rec = {"kind": "matter", "key": key_, "label": self.meta.get("index_label", ""), "title": title, "sections": []}
        head = Block("matter", f'<header class="chead mat"><h1>{esc(title)}</h1>'
                               f'<p class="lead">{esc(self.meta.get("index_lead", "본문 각주에 나온 용어를 모았다. 쪽 번호를 누르면 처음 나온 자리로 간다."))}</p></header>')
        head.flags = {"np", "kn"}
        head.anchors = [key_]
        head.ch, head.chl = key_, title
        head.toc = rec
        rec["block"] = "ix-head"
        head.id = "ix-head"
        self.chapters.append(rec)
        out = [head]
        groups = [("한글", [e for e in entries if key(e)[0] == 0]), ("영문 · 기호", [e for e in entries if key(e)[0] == 1])]
        n = 0
        for gname, es in groups:
            if not es:
                continue
            for k in range(0, len(es), 8):
                chunk = es[k:k + 8]
                rows = "".join(
                    f'<div class="ixr"><span class="ixt">{esc(e["label"])}</span><span class="ixd">{e["text"]}</span>'
                    f'<span class="ixw">{esc(e["chl"])}</span>'
                    f'<a class="ix" href="#b-{e["block"]}" data-to="b:{e["block"]}"><span class="pg" data-to="b:{e["block"]}"></span>쪽</a></div>'
                    for e in chunk)
                hh = f'<p class="ixg">{esc(gname)}</p>' if k == 0 else ""
                n += 1
                b = Block("index", f'<div class="ixblk">{hh}{rows}</div>')
                b.id = f"ix-{n:03d}"
                b.ch, b.chl = key_, title
                out.append(b)
        return out

    def render(self, only_desc=""):
        meta = self.meta
        labels = meta.get("labels", {})
        if meta.get("qa"):
            self.qa_count = self.attach_qa(meta["qa"])
        # 부 여는 쪽 — 질문 목록 채우기
        part_q = {}
        for c in self.chapters:
            if c["kind"] != "part":
                continue
            qs = c.get("questions")
            if qs:
                li = "".join(f"<li>{render_text(q, {}, 'part')}</li>" for q in qs)
            else:
                li = "".join(
                    f'<li><a href="#{ch["key"]}" data-to="{ch["key"]}"><b>{esc(ch["label"])}</b> '
                    f'{esc(plain(ch["title"]))}</a><span>{render_text(ch["question"], {}, "part")}</span></li>'
                    for ch in c["chapters"])
            part_q[c["no"]] = f'<ol class="pql">{li}</ol>'
        # 찾아보기(차례에 들어가도록 먼저 만든다) · 차례
        has_terms = any(not self.fns[f].get("noindex") for f in self.fn_order)
        ix_blocks = self._index_blocks() if (meta.get("index", True) and has_terms) else []
        blocks = []
        for b in self.blocks:
            if b.kind == "toc":
                tb = self._toc_blocks()
                for i, x in enumerate(tb):
                    x.id = f"toc-{i:03d}"
                    x.ch, x.chl, x.module = b.ch, b.chl, b.module
                blocks.extend(tb)
                continue
            if b.kind == "part":
                no = int(re.search(r"<!--PARTQ:(\d+)-->", b.html).group(1))
                b.html = b.html.replace(f"<!--PARTQ:{no}-->", part_q.get(no, ""))
            blocks.append(b)
        blocks.extend(ix_blocks)
        # 앵커 · 연결고리 검사
        anchors = {}
        for b in blocks:
            for a in b.anchors:
                if a in anchors:
                    raise BuildError(f"앵커 «{a}» 가 두 번 나온다 ({anchors[a]} · {b.id})")
                anchors[a] = b.id
        built_ch = {c["key"] for c in self.chapters}
        known = built_ch | set(labels.values())

        def chapter_of(t):
            """연결고리 대상 앵커 → 그 장의 키(가장 긴 접두). c3-2 → c3, case-a-2 → case-a"""
            cands = [k for k in known if t == k or t.startswith(k + "-")]
            if cands:
                return max(cands, key=len)
            m = re.match(r"(c\d+)(-|$)", t)
            return m.group(1) if m else t

        ext = 0
        for b in blocks:
            for t in b.links:
                if t in anchors:
                    continue
                if chapter_of(t) in built_ch:
                    raise BuildError(f"연결고리 대상 «{t}» 가 없다 — 블록 {b.id}")
                ext += 1
                b.html = b.html.replace(f'href="#{t}" data-to="{t}"', f'href="#{t}" data-to="{t}" data-ext="1"')
            if b.tail:
                for t in b.tail.split(","):
                    if t and t not in anchors:
                        b.html = re.sub(rf'\s*<a class="fwd" href="#{re.escape(t)}" data-to="{re.escape(t)}">[^<]*</a>', "", b.html)
        # 블록 HTML
        out = []
        hashes, new_ids = {}, []  # 블록 ID → 내용 해시(다음 판의 «새로» 비교용) · 이번에 «새로» 를 단 블록
        for b in blocks:
            attrs = [f'data-id="{esc(b.id)}"', f'data-k="{esc(b.kind)}"', f'data-ch="{esc(b.ch)}"']
            if b.chl:
                attrs.append(f'data-chl="{esc(b.chl)}"')
            if b.anchors:
                attrs.append(f'data-a="{esc(" ".join(b.anchors))}"')
            for f in ("np", "fp", "kn"):
                if f in b.flags:
                    attrs.append(f'data-{f}="1"')
            if b.group is not None:
                attrs.append(f'data-g="{b.group}"')
            fn_html = ""
            if b.fids:
                fn_html = '<div class="fnsrc" hidden>' + "".join(
                    f'<p class="fne" data-f="{f}"><span class="fnn"></span><b>{esc(self.fns[f]["label"])}</b> — {self.fns[f]["text"]}</p>'
                    for f in b.fids) + "</div>"
            mk = ""
            if b.make:
                mk = (f'<template class="mkt" data-cap="{esc(b.cap or "")}">'
                      + "\n".join(hl_code(ln) for ln in b.make) + "</template>")
            inner = f"{b.html}{fn_html}{mk}"
            hashes[b.id] = hashlib.md5(inner.encode("utf-8")).hexdigest()[:12]
            if self.prev is not None and b.kind not in ("toc", "index") and not b.id.startswith(("toc-", "ix-")) and self.prev.get(b.id) != hashes[b.id]:
                attrs.append('data-new="1"')  # 앞 판에 없거나 내용이 바뀐 블록 — «새로» 띠(book.css)
                new_ids.append(b.id)
            if self.edition and not out:
                inner = f'<p class="edtag">{esc(self.edition)}</p>' + inner  # 첫 블록 위 판 표시
            out.append(f'<div class="blk k-{esc(b.kind)}" {" ".join(attrs)}>{inner}</div>')
        # 장 목록(목록 · 머리글 · 검사용)
        chap = [{"key": c["key"], "kind": c["kind"], "label": c.get("label") or (f'{c["no"]}부' if c["kind"] == "part" else ""),
                 "title": plain(c["title"]), "block": c.get("block", "")} for c in self.chapters]
        info = {"doc": meta["doc"], "title": meta["title"], "short": meta.get("short", meta["title"]) + (f" · {self.edition}" if self.edition else ""),
                "chapters": chap, "built": datetime.now().strftime("%Y-%m-%d %H:%M"), "only": only_desc,
                "home": meta.get("home", "/"), "ext_links": ext}
        if self.x_links:
            info["x_links"] = len(self.x_links)
        if meta.get("reading_log"):
            info["reading_log"] = True  # 읽기 기록(쪽별 시간 · 조작 횟수) — 켠 책만
        css = (ASSETS / "book.css").read_text(encoding="utf-8")
        js = (ASSETS / "book.js").read_text(encoding="utf-8")
        title = meta["title"] + (f" ({only_desc})" if only_desc else "")
        doc = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
               '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
               f'<title>{esc(title)}</title>\n<meta name="description" content="{esc(meta.get("description", ""))}">\n'
               f'<style>{css}</style>\n</head>\n<body data-doc="{esc(meta["doc"])}">\n'
               + BODY.replace("{{HOME}}", esc(info["home"]))
               + f'<div id="bksrc" class="bksrc">{"".join(out)}</div>\n'
               f'<script type="application/json" id="bkmeta">{json.dumps(info, ensure_ascii=False)}</script>\n'
               f'<script>{js}</script>\n</body>\n</html>\n')
        stats = {"blocks": len(blocks), "footnotes": len(self.fns), "chapters": len([c for c in self.chapters if c["kind"] == "chapter"]),
                 "anchors": len(anchors), "ext_links": ext, "x_links": len(self.x_links),
                 "extra_files": dict(self.extra_files), "hashes": hashes, "new": new_ids}
        return doc, stats


ICON = {
    "home": '<svg viewBox="0 0 24 24"><path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/></svg>',
    "rail": '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="15" y1="4" x2="15" y2="20"/></svg>',
    "memo": ('<svg viewBox="0 0 24 24" class="memo-ic"><path d="M5 3h14a2 2 0 0 1 2 2v9l-7 7H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" '
             'fill="#facc15" stroke="#a16207" stroke-width="1.3"/><path d="M14 21v-5a2 2 0 0 1 2-2h5" fill="#fde68a" '
             'stroke="#a16207" stroke-width="1.3"/></svg>'),
    "top": '<svg viewBox="0 0 24 24"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>',
}

BODY = f"""<main class="stage" id="stage"><div class="wrap">
 <p class="loading" id="loading">쪽 나누는 중</p>
 <div class="book" id="book"><div class="notes" id="notes"></div></div>
 <div class="mk" id="spMake"></div>
</div></main>
<aside class="rail" id="rail" aria-label="쪽 목록"></aside>
<div class="fab">
 <a class="fbtn" id="bHome" href="{{{{HOME}}}}" aria-label="노트 목록" title="노트 목록">{ICON["home"]}</a>
 <button type="button" class="fbtn" id="bRail" aria-label="목록 표시 · 숨기기" aria-pressed="true" title="목록 표시 · 숨기기">{ICON["rail"]}</button>
 <button type="button" class="fbtn" id="bMode" aria-label="보기 모드" title="보기 모드"></button>
 <button type="button" class="fbtn memo" id="bMemo" aria-label="메모 붙이기" aria-pressed="false" title="메모 붙이기">{ICON["memo"]}</button>
 <button type="button" class="fbtn" id="bTop" aria-label="맨 앞으로" title="맨 앞으로">{ICON["top"]}</button>
</div>
<div class="chip" id="chip" hidden><button type="button" class="go" id="chipGo">← 돌아가기 <span></span></button><button type="button" class="x" id="chipX" aria-label="닫기">×</button></div>
<div class="toast" id="toast"></div>
"""


def _mark_spans(line):
    """글자 파일 줄 안의 ==강조== · !!빨강!! 표시 → span"""
    h = esc(line)
    h = re.sub(r"==(.+?)==", r'<mark>\1</mark>', h)
    h = re.sub(r"!!(.+?)!!", r'<mark class="bad">\1</mark>', h)
    return h
