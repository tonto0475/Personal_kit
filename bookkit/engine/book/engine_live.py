# -*- coding: utf-8 -*-
r"""책 엔진 확장 — 조작 블록(단계 재생기 · 조건 슬라이더 · 크게 열기) (명세 LIVE_SPEC.md · 사용법 README 11절)

Writer 의 stepper · slider · open_full 이 이 모듈의 함수를 부른다(engine.py 에서 위임). 조작 블록을 쓰지 않는 책은 이 모듈을 불러오지도 않는다.
원칙: 안 만져도 읽히는 책 + 확인용 조작. 숫자 · 그림 · 표시 글자는 전부 빌드 때 파이썬이 미리 만든다 — 브라우저는 골라서 보여 주기만 한다.
블록 첫 화면(초기 상태)은 이 모듈이 HTML 로 바로 그려 둔다(쪽 나누기가 그 높이로 잰다). 단계 · 조건이 바뀌어도 높이가 변하지 않게
- 그림은 같은 viewBox(비율 고정 상자) · 글은 모든 단계의 글을 한 칸에 겹쳐 두고(가장 긴 글이 높이를 정한다) 하나만 보인다
"""
import itertools
import json
import re
from pathlib import Path
from urllib.parse import quote

from .engine import BuildError, esc, fmt_val, table_html

HERE = Path(__file__).resolve().parent  # book\
STUDY = HERE.parent  # study_html\
DATA_LIMIT = 500 * 1024  # 블록 하나 데이터 한도(바이트) — 넘으면 빌드 경고

# 단추 안 그림(글자 대신 SVG — 기기 글꼴에 따라 이모지로 바뀌는 것을 막는다)
IC = {
    "first": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5v14M19 5l-9 7 9 7z"/></svg>',
    "prev": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 5l-9 7 9 7z"/></svg>',
    "next": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5l9 7-9 7z"/></svg>',
    "play": ('<svg viewBox="0 0 24 24" aria-hidden="true"><path class="ip" d="M5 4l8 8-8 8zM13 4l8 8-8 8z"/>'
             '<path class="ipa" d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>'),
}


# ════════════════════════════════════════════════════════════
# 도우미
# ════════════════════════════════════════════════════════════
def _json_safe(data):
    """<script type=application/json> 안에 넣는 글자 — «<» 를 풀어 </script> 로 끊기지 않게 한다"""
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _viewbox(svg, where, what):
    """SVG 글자의 viewBox 폭 · 높이 — 없으면 빌드를 멈춘다"""
    m = re.search(r'<svg[^>]*\sviewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)\s*"', str(svg))
    if not m:
        raise BuildError(f"{where}: {what} 의 그림이 viewBox 가 있는 <svg> 가 아니다 (Svg(w, h).render() 결과를 넣을 것)")
    return float(m.group(1)), float(m.group(2))


def _vs(v):
    """값 → 열쇠 · 표시 글자 — 파이썬 str 그대로(2.0 → «2.0»). frames 열쇠를 f"{cap}|{배율}" 로 만든 것과 같다"""
    return str(v)


def _fmt_metric(v, fmt):
    """지표 값 하나의 글자 — fmt 이 안 맞으면(예: 실수에 d) 기본 표시로"""
    if fmt:
        try:
            return format(v, fmt)
        except (TypeError, ValueError):
            pass
    return fmt_val(v)


def _prec(fmt):
    """fmt → 소수 자릿수(JS 가 입력과의 차이를 같은 자릿수로 적는다). 모르면 None"""
    m = re.fullmatch(r"[,_]?\.(\d+)f", fmt or "")
    if m:
        return int(m.group(1))
    return 0 if fmt in ("d", ",d") else None


def _shell(w, kind, inner_cls, head, body, foot, data, fn, id, what, cap, tab=True):
    """공통 껍데기 — 바깥 상자 .live(넘김 제외) + 데이터 script. fn 은 보이는 HTML 에만 적용"""
    visible = head + body + foot
    visible, fids = w._fn(visible, fn)
    raw = _json_safe(data)
    if len(raw.encode("utf-8")) > DATA_LIMIT:
        w.book.warnings.append(f"{w._where()}: {what} 데이터 {len(raw.encode('utf-8')) // 1024:,} KB — {DATA_LIMIT // 1024} KB 넘는다")
    h = (f'<div class="live {inner_cls}"{" tabindex=" + chr(34) + "0" + chr(34) if tab else ""} data-live="{kind}">'
         f'{visible}<script type="application/json" class="lvdata">{raw}</script></div>')
    return w._add(kind, h, fids, id=id, cap=cap)


def _head(w, task, title):
    h = ""
    if task:
        h += f'<p class="lvtask"><b>해 보기</b>{w.t(task)}</p>'
    if title:
        h += f'<p class="lvtitle">{w.t(title)}</p>'
    return h


def _plain(t):
    return re.sub(r"<[^>]+>", "", t or "")


# ════════════════════════════════════════════════════════════
# 1. 단계 재생기
# ════════════════════════════════════════════════════════════
def _tag_rows(h, state, where):
    """표 HTML 의 본문 행에 data-r(행 번호) · 지금 상태 클래스를 단다. state[i] = "" | "lv-cur" | "lv-todo" """
    head, sep, body = h.partition("<tbody>")
    n = [-1]

    def rep(m):
        n[0] += 1
        i = n[0]
        cls = (m.group(1) or "").replace('"', "")
        cls = " ".join(x for x in (cls, state[i] if i < len(state) else "") if x)
        return f'<tr data-r="{i}"{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>'

    body = re.sub(r"<tr(?:\s+class=([^>]*))?>", rep, body)
    if n[0] + 1 != len(state):
        raise BuildError(f"{where}: 단계 표의 행 수가 맞지 않는다 (표 {n[0] + 1} · 기대 {len(state)})")
    return head + sep + body


def stepper(w, steps, title=None, caption=None, table=None, task=None, auto_ms=900, fn=None, id=None, start=0):
    """단계 재생기 블록 — steps = [{"svg": SVG 글자, "text": 꾸밈 글, "row": 표 행 번호 | None}]
    table = {"header": [...], "rows": [[...]], "small": True} (선택) · 단추: 처음 · 이전 · 다음 · 자동 재생 · «3 / 12»"""
    where = w._where()
    if not steps:
        raise BuildError(f"{where}: 단계 재생기에 단계가 없다")
    n = len(steps)
    if not isinstance(start, int) or not 0 <= start < n:
        raise BuildError(f"{where}: start={start} 가 단계 범위(0~{n - 1}) 밖이다")
    norm = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or "svg" not in s or "text" not in s:
            raise BuildError(f"{where}: 단계 {i} 는 {{'svg': …, 'text': …, 'row': …}} 모양이어야 한다")
        norm.append({"svg": str(s["svg"]), "text": s["text"], "row": s.get("row")})
    vb = _viewbox(norm[0]["svg"], where, "단계 0")
    for i, s in enumerate(norm[1:], 1):
        if _viewbox(s["svg"], where, f"단계 {i}") != vb:
            raise BuildError(f"{where}: 단계 {i} 그림의 viewBox 가 단계 0 과 다르다 — 모든 단계를 같은 Svg(w, h) 크기로 (블록 높이가 변하지 않게)")
    rows = None
    first = {}  # 표 행 → 처음 나오는 단계
    if table is not None:
        if "header" not in table or "rows" not in table:
            raise BuildError(f"{where}: table 은 header · rows 가 필요하다")
        rows = table["rows"]
    for i, s in enumerate(norm):
        r = s["row"]
        if r is None:
            continue
        if rows is None or not isinstance(r, int) or not 0 <= r < len(rows):
            raise BuildError(f"{where}: 단계 {i} 의 row={r} 가 표 행 범위 밖이다 (table 없음 또는 {len(rows or [])}행)")
        first.setdefault(r, i)

    def state_at(k):
        cur = norm[k]["row"]
        return ["lv-cur" if r == cur else "lv-todo" if (r in first and first[r] > k) else "" for r in range(len(rows or []))]

    tab_html = ""
    if table is not None:
        opts = {k: v for k, v in table.items() if k not in ("header", "rows", "max_rows", "dtype")}
        th = table_html(header=table["header"], rows=rows, **opts)
        tab_html = f'<div class="lvtab">{_tag_rows(th, state_at(start), where)}</div>'
    texts = "".join(f'<p class="lvs{" on" if i == start else ""}" data-i="{i}">{w.t(s["text"])}</p>' for i, s in enumerate(norm))
    head = _head(w, task, title)
    body = (f'<div class="lvfig" style="aspect-ratio:{vb[0]:g}/{vb[1]:g}">{norm[start]["svg"]}</div>'
            f'<div class="lvtxt">{texts}</div>{tab_html}'
            '<div class="lvbar">'
            f'<button type="button" class="lvb" data-a="first" title="처음">{IC["first"]}처음</button>'
            f'<button type="button" class="lvb" data-a="prev" title="이전">{IC["prev"]}이전</button>'
            f'<button type="button" class="lvb" data-a="next" title="다음">{IC["next"]}다음</button>'
            f'<button type="button" class="lvb" data-a="play" aria-pressed="false" title="자동 재생">{IC["play"]}자동</button>'
            f'<span class="lvpos" aria-live="polite">{start + 1} / {n}</span></div>')
    foot = f'<p class="cap">{w.t(caption)}</p>' if caption else ""
    data = {"kind": "stepper", "start": start, "auto": int(auto_ms), "steps": [{"svg": s["svg"], "row": s["row"]} for s in norm],
            "first": {str(k): v for k, v in first.items()}, "rows": len(rows or [])}
    return _shell(w, "stepper", "lv-step", head, body, foot, data, fn, id, "단계 재생기", _plain(foot) or _plain(head))


# ════════════════════════════════════════════════════════════
# 2. 조건 슬라이더
# ════════════════════════════════════════════════════════════
def slider(w, params, frames, render="svg", metrics=None, task=None, predict=None, title=None, caption=None, fn=None, id=None):
    """조건 슬라이더 블록 — params = [{"key", "label", "values", "default", "unit"}] · frames = {"30|1.5": {"svg", "metrics", "note"}}
    metrics = [{"key", "fmt", "unit", "bad_above"}] · predict = {"q", "at": {key: 값}, "metric"}"""
    where = w._where()
    if render != "svg":
        raise BuildError(f"{where}: slider 의 render 는 «svg» 만 된다 (canvas 는 오른쪽 축소판이 빈칸이 된다) — {render!r}")
    if not params:
        raise BuildError(f"{where}: 슬라이더에 조건(params)이 없다")
    ps, seen = [], set()
    for p in params:
        for k in ("key", "label", "values", "default"):
            if k not in p:
                raise BuildError(f"{where}: 조건 {p} 에 «{k}» 가 없다")
        if p["key"] in seen:
            raise BuildError(f"{where}: 조건 key «{p['key']}» 가 두 번 나온다")
        seen.add(p["key"])
        keys = [_vs(v) for v in p["values"]]
        if len(set(keys)) != len(keys) or not keys:
            raise BuildError(f"{where}: 조건 «{p['key']}» 의 values 가 비었거나 겹친다 {p['values']}")
        if _vs(p["default"]) not in keys:
            raise BuildError(f"{where}: 조건 «{p['key']}» 의 default {p['default']} 가 values 에 없다")
        unit = p.get("unit", "")
        ps.append({"key": p["key"], "label": p["label"], "keys": keys, "texts": [k + unit for k in keys],
                   "default": keys.index(_vs(p["default"]))})
    frames = {("|".join(str(x) for x in k) if isinstance(k, (tuple, list)) else k): f for k, f in frames.items()}  # 열쇠를 튜플로 줘도 된다
    allowed = {"|".join(c) for c in itertools.product(*[p["keys"] for p in ps])}
    for k in frames:
        if k not in allowed:
            raise BuildError(f"{where}: frames 열쇠 «{k}» 가 조건 조합이 아니다 (예: {sorted(allowed)[:3]})")
    dkey = "|".join(p["keys"][p["default"]] for p in ps)
    if dkey not in frames:
        raise BuildError(f"{where}: 기본 조합 «{dkey}» 의 frame 이 없다")
    vb = _viewbox(frames[dkey]["svg"], where, f"frame {dkey}")
    for k, f in frames.items():
        if "svg" not in f:
            raise BuildError(f"{where}: frame «{k}» 에 svg 가 없다")
        if _viewbox(f["svg"], where, f"frame {k}") != vb:
            raise BuildError(f"{where}: frame «{k}» 그림의 viewBox 가 기본 frame 과 다르다 — 같은 크기로")
    # 지표 정의
    if metrics is None:
        metrics = list(frames[dkey].get("metrics", {}).keys())
    ms = []
    for m in metrics:
        m = {"key": m} if isinstance(m, str) else dict(m)
        m.setdefault("fmt", None)
        m.setdefault("unit", "")
        m.setdefault("bad_above", None)
        ms.append(m)
    mkeys = [m["key"] for m in ms]
    base = frames[dkey].get("metrics", {})

    def mval(m, f):
        """frame 하나의 지표 하나 → {"v", "t", "d", "bad"}"""
        raw = (f.get("metrics") or {}).get(m["key"])
        if raw is None:
            return {"v": None, "t": "–", "d": "", "bad": False}
        t = _fmt_metric(raw, m["fmt"]) + m["unit"]
        d = ""
        b = base.get(m["key"])
        if isinstance(b, (int, float)) and isinstance(raw, (int, float)):
            diff = raw - b
            if abs(diff) < 1e-12:
                d = "기준"
            else:
                d = f"{'▲ +' if diff > 0 else '▼ -'}{_fmt_metric(abs(diff), m['fmt'])}"
        return {"v": raw, "t": t, "d": d, "bad": m["bad_above"] is not None and raw > m["bad_above"]}

    jf = {k: {"svg": str(f["svg"]), "m": {m["key"]: mval(m, f) for m in ms}} for k, f in frames.items()}
    # 예측
    pd = None
    if predict is not None:
        for k in ("q", "at", "metric"):
            if k not in predict:
                raise BuildError(f"{where}: predict 에 «{k}» 가 없다")
        if predict["metric"] not in mkeys:
            raise BuildError(f"{where}: predict 의 metric «{predict['metric']}» 가 지표 목록에 없다 {mkeys}")
        at = {}
        for pk, pv in predict["at"].items():
            pp = next((p for p in ps if p["key"] == pk), None)
            if pp is None or _vs(pv) not in pp["keys"]:
                raise BuildError(f"{where}: predict.at 의 {pk}={pv} 가 조건 값이 아니다")
            at[pk] = pp["keys"].index(_vs(pv))
        mm = next(m for m in ms if m["key"] == predict["metric"])
        pd = {"at": at, "metric": predict["metric"], "prec": _prec(mm["fmt"]), "unit": mm["unit"]}
    # 첫 화면(= 기본 조합)
    ctl = ""
    for i, p in enumerate(ps):
        n = len(p["keys"])
        ticks = "".join(f"<span>{esc(t)}</span>" for t in p["texts"])
        ctl += (f'<div class="lvp"><span class="lvpl">{w.t(p["label"])}</span><div class="lvpc">'
                f'<input type="range" class="lvr" min="0" max="{n - 1}" step="1" value="{p["default"]}" data-p="{i}"'
                f' aria-label="{esc(_plain(w.t(p["label"])))}" aria-valuetext="{esc(p["texts"][p["default"]])}"{" disabled" if n == 1 else ""}>'
                f'<div class="lvticks">{ticks}</div></div><output class="lvpv" data-p="{i}">{esc(p["texts"][p["default"]])}</output></div>')
    tiles = "".join(
        f'<div class="lvm" data-m="{esc(m["key"])}"><span class="lvmk">{esc(m["key"])}</span>'
        f'<b class="lvmv{" bad" if jf[dkey]["m"][m["key"]]["bad"] else ""}">{esc(jf[dkey]["m"][m["key"]]["t"])}</b>'
        f'<span class="lvmd">{esc(jf[dkey]["m"][m["key"]]["d"]) or "&nbsp;"}</span></div>' for m in ms)
    notes = "".join(f'<p class="lvn{" on" if k == dkey else ""}" data-k="{esc(k)}">{w.t(f["note"])}</p>'
                    for k, f in frames.items() if f.get("note"))
    pred_html = ""
    if predict is not None:
        pred_html = ('<div class="lvpred"><p class="lvq">' + w.t(predict["q"]) + '</p><div class="lvpi">'
                     '<input type="number" step="any" class="lvpin" aria-label="예측값">'
                     '<button type="button" class="lvb" data-a="check">확인</button></div>'
                     '<p class="lvpr" aria-live="polite"></p></div>')
    head = _head(w, task, title)
    body = (f'<div class="lvctl">{ctl}</div>'
            f'<div class="lvfig" style="aspect-ratio:{vb[0]:g}/{vb[1]:g}">{frames[dkey]["svg"]}<span class="lvmiss" hidden>계산 안 함</span></div>'
            f'<div class="lvmets">{tiles}</div>' + (f'<div class="lvnotes">{notes}</div>' if notes else "") + pred_html)
    foot = f'<p class="cap">{w.t(caption)}</p>' if caption else ""
    data = {"kind": "slider", "params": ps, "frames": jf, "metrics": [{"key": m["key"], "prec": _prec(m["fmt"])} for m in ms], "predict": pd}
    return _shell(w, "slider", "lv-slide", head, body, foot, data, fn, id, "조건 슬라이더", _plain(foot) or _plain(head))


# ════════════════════════════════════════════════════════════
# 3. 크게 열기
# ════════════════════════════════════════════════════════════
def open_full(w, path, label, note=None, id=None):
    """크게 열기 블록 — 쪽에 안 들어가는 조작 화면(HTML 한 파일)으로 가는 단추. 빌드가 파일을 출력 옆 «<doc>__<이름>» 으로 복사한다"""
    where = w._where()
    p = Path(path)
    cands = [p] if p.is_absolute() else [STUDY / p, HERE / p]
    src = next((c for c in cands if c.is_file()), None)
    if src is None:
        raise BuildError(f"{where}: 크게 열기 파일이 없다 — {path}")
    dest = f"{w.book.meta['doc']}__{src.name}"
    old = w.book.extra_files.get(dest)
    if old is not None and old != src.resolve():
        raise BuildError(f"{where}: 크게 열기 출력 이름 «{dest}» 가 다른 파일과 겹친다 ({old} · {src})")
    w.book.extra_files[dest] = src.resolve()
    h = (f'<div class="live lv-open"><a class="lvgo" href="{esc(quote(dest))}" target="_blank" rel="noopener" data-full="{esc(dest)}">'
         f'{esc(label)} <span aria-hidden="true">↗</span></a>'
         + (f'<span class="lvnote">{w.t(note)}</span>' if note else "") + "</div>")
    return w._add("openfull", h, id=id, cap=str(label))
