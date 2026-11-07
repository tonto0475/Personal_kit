# -*- coding: utf-8 -*-
"""학습 노트 HTML 생성 공용 엔진
- 장(page)마다 «캔버스(개념) + 대시보드(예시)» 구조, 한 파일 안에서 #p01 · #p02 … 로 이동
- 예시 코드는 빌드 때 실제로 실행해 결과 표를 싣는다(지어낸 값 없음)
- 출력 두 벌: 아티팩트용 조각(doctype · head 없음) · 서버용 완전한 문서
"""
import html
import re
import warnings

import numpy as np
import pandas as pd


# ════════════════════════════════════════════════════════════
# 값 실행 · 표시
# ════════════════════════════════════════════════════════════
def fmt(v):
    if v is None:
        return "None"
    if v is pd.NA:
        return "<NA>"
    if isinstance(v, float) and np.isnan(v):
        return "NaN"
    if isinstance(v, pd.Timestamp):
        return v.strftime("%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, str) and v != v.strip():
        return repr(v)  # 앞뒤 공백이 보이도록
    if isinstance(v, (float, np.floating)):
        t = f"{v:g}"
        return t + ".0" if t.lstrip("-").isdigit() else t  # 실수는 30.0 처럼 — 출력 결과(print)와 같은 모양으로
    return str(v)


def show(v):
    """numpy 스칼라는 파이썬 값으로(np.int64(12) → 12)"""
    return repr(v.item() if isinstance(v, np.generic) else v)


def run_block(env, lines):
    """마지막 줄을 식으로 평가한 값을 돌려준다(앞 줄은 실행만). → (값, 에러 문구, 경고 이름 목록)"""
    # 끝에서부터 «식으로 컴파일되는 가장 짧은 꼬리» 를 찾는다 — 여러 줄에 걸친 식도 결과로 받기 위해
    split = None
    for k in range(len(lines) - 1, -1, -1):
        try:
            compile("\n".join(lines[k:]), "<식>", "eval")
            split = k
            break
        except SyntaxError:
            continue
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            if split is None:  # 마지막이 대입문이면 실행만 한다
                exec("\n".join(lines), env)
                return None, None, [type(x.message).__name__ for x in w]
            if split:
                exec("\n".join(lines[:split]), env)
            return eval("\n".join(lines[split:]), env), None, [type(x.message).__name__ for x in w]
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e).splitlines()[0]}", [type(x.message).__name__ for x in w]


def table_html(obj, hl=None):
    """DataFrame · Series → 표 HTML. 그 밖의 값은 None"""
    if isinstance(obj, pd.DataFrame):
        hdr = [str(obj.index.name or "")] + [str(c) for c in obj.columns]
        rows = [[idx] + list(r) for idx, r in zip(obj.index, obj.itertuples(index=False))]
    elif isinstance(obj, pd.Series):
        hdr = [str(obj.index.name or ""), str(obj.name) if obj.name is not None else "값"]
        rows = [[i, v] for i, v in obj.items()]
    else:
        return None
    out = ['<div class="tbl"><table><thead><tr>']
    for i, h in enumerate(hdr):
        out.append(f'<th class="{"ix" if i == 0 else ""}">{esc(h)}</th>')
    out.append("</tr></thead><tbody>")
    for r, row in enumerate(rows):
        out.append(f'<tr class="{"hl" if hl and r in hl else ""}">')
        for i, v in enumerate(row):
            t = fmt(v)
            cls = "ix" if i == 0 else ("nan" if t in ("NaN", "<NA>", "None") else "")
            out.append(f'<td class="{cls}">{esc(t)}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


# ════════════════════════════════════════════════════════════
# 코드 표시 — 문자열 · 주석만 칠한다
# ════════════════════════════════════════════════════════════
def esc(s):
    return html.escape(str(s), quote=True)


_TOK = re.compile(r'("[^"\n]*"|\'[^\'\n]*\')|(#.*$)')


def hl_code(line):
    out, pos = [], 0
    for m in _TOK.finditer(line):
        out.append(esc(line[pos:m.start()]))
        if m.group(1):
            out.append(f'<span class="s">{esc(m.group(1))}</span>')
        else:
            out.append(f'<span class="c">{esc(m.group(2))}</span>')
        pos = m.end()
    out.append(esc(line[pos:]))
    return "".join(out)


def pre(lines, extra=None):
    body = "\n".join(hl_code(ln) for ln in lines)
    if extra:
        body += "\n" + extra
    return f'<pre class="code"><code>{body}</code></pre>'


# ════════════════════════════════════════════════════════════
# 예시 카드 — 위: 타이핑한 코드 · 아래: 실행 결과
# ════════════════════════════════════════════════════════════
def card(env, spec):
    """spec: title · code(마지막 줄 = 결과) | repl(식 목록 «식 → 값») | text(글 그대로) · hl(강조 행) · note"""
    t = f'<div class="ct">{esc(spec["title"])}</div>'
    note = f'<p class="cn">{esc(spec["note"])}</p>' if spec.get("note") else ""
    if "text" in spec:
        return f'<div class="card">{t}<pre class="code raw"><code>{esc(spec["text"])}</code></pre>{note}</div>'
    if "repl" in spec:
        setup = spec.get("code", [])
        if setup:
            exec("\n".join(setup), env)
        exprs = spec["repl"]
        w = max(len(e) for e in exprs)
        rows = []
        for e in exprs:
            v, err, _ = run_block(env, [e])
            assert not (err and err.split(":")[0] in ("SyntaxError", "NameError", "AttributeError")), (spec["title"], e, err)
            val =f'<span class="err">{esc(err)}</span>' if err else f'<span class="out">{esc(show(v))}</span>'
            rows.append(f'{hl_code(e.ljust(w))}  <span class="ar">→</span> {val}')
        body = "\n".join([hl_code(s) for s in setup] + rows)
        return f'<div class="card">{t}<pre class="code"><code>{body}</code></pre>{note}</div>'
    res, err, warns = run_block(env, spec["code"])
    assert not (err and err.split(":")[0] in ("SyntaxError", "NameError", "AttributeError")), (spec["title"], err)  # 코드 오타는 빌드를 멈춘다
    parts = [t, pre(spec["code"])]
    if warns:
        parts.append(f'<p class="warn">경고: {esc(", ".join(dict.fromkeys(warns)))}</p>')
    if err:
        parts.append(f'<p class="errbox">{esc(err)}</p>')
    elif res is not None:
        # print() 했을 때 콘솔에 찍히는 모양 그대로 — 코드 바로 아래 별도 테두리, 그다음 표
        with pd.option_context("display.width", 120, "display.max_columns", 30):
            txt = str(res.item() if isinstance(res, np.generic) else res)
        parts.append(f'<div class="obox"><p class="oh">※ 출력 결과</p><pre class="code"><code>{esc(txt)}</code></pre></div>')
        th = table_html(res, spec.get("hl"))
        if th:
            parts.append(th)
    parts.append(note)
    return f'<div class="card">{"".join(parts)}</div>'


def example_html(page_setup, ex):
    """대시보드에 뜨는 예시 한 벌 — 이 장의 준비 코드(데이터 맥락) + 예시 카드들. 예시마다 새 환경"""
    env = {"pd": pd, "np": np}
    exec("import io", env)
    out = []
    if page_setup and ex.get("setup", True):
        code = page_setup["code"]
        exec("\n".join(code), env)
        res = None
        if page_setup.get("show"):
            res, _, _ = run_block(env, [page_setup["show"]])
        th = table_html(res) if res is not None else ""
        out.append(f'<div class="card setup"><div class="ct">준비 — 이 장에서 쓰는 데이터</div>{pre(code)}{th or ""}</div>')
    for spec in ex["cards"]:
        out.append(card(env, spec))
    return "".join(out)


# ════════════════════════════════════════════════════════════
# 캔버스 조각
# ════════════════════════════════════════════════════════════
def ul(items):
    return "<ul>" + "".join(f"<li>{it}</li>" for it in items) + "</ul>"


def btn(page_id, key, label):
    return f'<button type="button" class="exbtn" data-ex="{page_id}-{key}" aria-expanded="false">예시 · {esc(label)}</button>'


def item(title, body, buttons="", tone=""):
    return (f'<article class="item {tone}"><h3>{title}</h3><div class="ib">{body}</div>'
            f'{f"<div class=bt>{buttons}</div>" if buttons else ""}</article>')


def mini_table(hdr, rows):
    h = "".join(f"<th>{c}</th>" for c in hdr)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl"><table class="mini"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def code_inline(s):
    return f"<code>{esc(s)}</code>"


# ════════════════════════════════════════════════════════════
# 문서 조립
# ════════════════════════════════════════════════════════════
def build(doc_title, doc_label, pages, description):
    """pages: [dict(id, no, eyebrow, title, sub, items[html], take, setup, examples{key: {title, cards}})]
    → (아티팩트 조각, 서버용 완전 문서)"""
    nav_opts = "".join(f'<option value="{p["id"]}">{p["no"]} · {esc(p["eyebrow"])}</option>' for p in pages)
    secs, tmpls = [], []
    for i, p in enumerate(pages):
        prev_id = pages[i - 1]["id"] if i else ""
        next_id = pages[i + 1]["id"] if i + 1 < len(pages) else ""
        take = f'<p class="take">{p["take"]}</p>' if p.get("take") else ""
        secs.append(
            f'<section class="page" id="{p["id"]}" data-page hidden aria-labelledby="{p["id"]}-h">'
            f'<div class="canvas"><header class="ph"><p class="eb">{p["no"]} · {esc(p["eyebrow"])}</p>'
            f'<h2 id="{p["id"]}-h">{p["title"]}</h2><p class="sub">{p["sub"]}</p></header>'
            f'<div class="grid">{"".join(p["items"])}</div>{take}</div>'
            f'<div class="dash" hidden><div class="dh"><p class="dt"></p>'
            f'<button type="button" class="up">개념으로 ↑</button><button type="button" class="x" aria-label="예시 닫기">닫기</button></div>'
            f'<div class="db"></div></div>'
            f'<nav class="pn">{f"<a href=#{prev_id}>← 이전</a>" if prev_id else "<span></span>"}'
            f'{f"<a href=#{next_id}>다음 →</a>" if next_id else "<span></span>"}</nav></section>')
        for key, ex in p.get("examples", {}).items():
            tmpls.append(f'<template id="t-{p["id"]}-{key}" data-title="{esc(ex["title"])}">'
                         f'{example_html(p.get("setup"), ex)}</template>')
    body = (f'<header class="top"><div class="tw"><p class="brand">{esc(doc_label)}</p>'
            f'<div class="nav"><a class="pv" href="#" aria-label="이전 장">←</a>'
            f'<select id="pagesel" aria-label="장 이동">{nav_opts}</select>'
            f'<a class="nx" href="#" aria-label="다음 장">→</a></div></div></header>'
            f'<main class="wrap">{"".join(secs)}</main>{"".join(tmpls)}')
    head = (f'<title>{esc(doc_title)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'<meta name="description" content="{esc(description)}">\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600'
            '&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">\n'
            f"<style>{CSS}</style>\n")
    frag = head + body + f"<script>{JS}</script>\n"
    full = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            f'{head}<style>{RESET}</style>\n</head>\n<body>\n{body}\n<script>{JS}</script>\n</body>\n</html>\n')
    return frag, full


# 서버용 문서에만 넣는 기본 리셋(아티팩트는 게시 때 같은 역할의 뼈대가 붙는다)
RESET = """:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
body{margin:0}img{max-width:100%}[hidden]{display:none!important}"""

CSS = r"""
/* 레이아웃: 위 고정 바(장 이동) → 장마다 «캔버스(개념) + 대시보드(예시, 누를 때만 생김)» → 이전 · 다음 */
:root{
  --bg:#f6f8fb; --paper:#ffffff; --ink:#111827; --ink2:#4b5563; --ink3:#8a94a3;
  --line:#dbe3ee; --soft:#eef2f7; --soft2:#f5f7fa;
  --acc:#2563eb; --acc-t:#eaf1ff; --pd:#7c3aed; --pd-t:#f3eeff;
  --ng:#dc2626; --ng-t:#fdecec; --ok:#16a34a; --ok-t:#eaf7ee; --warn:#b45309; --warn-t:#fff4e0;
  --code-bg:#f1f4f9; --str:#0f7b4f; --cmt:#8a94a3;
  --f-body:"IBM Plex Sans KR","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif;
  --f-mono:"IBM Plex Mono",Consolas,"D2Coding",ui-monospace,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0f141c; --paper:#161d28; --ink:#e7ecf3; --ink2:#a9b4c3; --ink3:#7b8696;
  --line:#2a3546; --soft:#1d2633; --soft2:#1a222e;
  --acc:#6b9bff; --acc-t:#1b2a47; --pd:#a78bfa; --pd-t:#262042;
  --ng:#f87171; --ng-t:#3a1d22; --ok:#4ade80; --ok-t:#16301f; --warn:#fbbf24; --warn-t:#352a12;
  --code-bg:#121923; --str:#5fd39a; --cmt:#7b8696; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0f141c; --paper:#161d28; --ink:#e7ecf3; --ink2:#a9b4c3; --ink3:#7b8696;
  --line:#2a3546; --soft:#1d2633; --soft2:#1a222e;
  --acc:#6b9bff; --acc-t:#1b2a47; --pd:#a78bfa; --pd-t:#262042;
  --ng:#f87171; --ng-t:#3a1d22; --ok:#4ade80; --ok-t:#16301f; --warn:#fbbf24; --warn-t:#352a12;
  --code-bg:#121923; --str:#5fd39a; --cmt:#7b8696; color-scheme:dark}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto}}
body{background:var(--bg);color:var(--ink);font-family:var(--f-body);font-size:15px;line-height:1.6;
  -webkit-text-size-adjust:100%}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--paper)}
code{font-family:var(--f-mono);font-size:.88em;background:var(--soft);padding:.05em .35em;border-radius:4px}
.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--paper);border-bottom:1px solid var(--line)}
.tw,.wrap{max-width:1180px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.tw{display:flex;align-items:center;gap:12px;padding-block:10px;flex-wrap:wrap}
.brand{margin:0;font-weight:700;font-size:14px;letter-spacing:.02em;color:var(--acc);flex:1 1 auto;min-width:0}
.nav{display:flex;gap:6px;align-items:center;min-width:0}
.nav a{display:grid;place-items:center;width:34px;height:34px;border:1px solid var(--line);border-radius:8px;color:var(--ink);text-decoration:none}
.nav select{height:34px;max-width:min(62vw,320px);border:1px solid var(--line);border-radius:8px;background:var(--paper);color:var(--ink);font:inherit;font-size:14px;padding:0 8px}
.wrap{padding-block:18px 48px}
.page{display:flex;flex-direction:column;gap:14px}
.canvas,.dash{background:var(--paper);border:1px solid var(--line);border-radius:12px;scroll-margin-top:70px}
.canvas{padding:20px 22px 18px}
.ph{margin-bottom:14px}
.eb{margin:0;color:var(--acc);font-weight:700;font-size:13px;letter-spacing:.04em}
.ph h2{margin:.15em 0 .1em;font-size:clamp(20px,2.6vw,26px);line-height:1.3;text-wrap:balance}
.sub{margin:0;color:var(--ink2);font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:12px}
.item{background:var(--soft2);border:1px solid var(--line);border-radius:10px;padding:13px 15px;min-width:0;display:flex;flex-direction:column;gap:8px}
.item h3{margin:0;font-size:15.5px;line-height:1.4}
.item.bad h3{color:var(--ng)} .item.good h3{color:var(--ok)} .item.key h3{color:var(--pd)}
.ib{font-size:14.2px;color:var(--ink);min-width:0}
.ib p{margin:0 0 .4em} .ib p:last-child{margin-bottom:0}
.ib ul{margin:0;padding-left:1.1em} .ib li{margin:.15em 0}
.bt{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto}
.exbtn{font:inherit;font-size:13px;font-weight:600;color:var(--pd);background:var(--pd-t);border:1px solid color-mix(in srgb,var(--pd) 40%,transparent);
  border-radius:999px;padding:4px 12px;cursor:pointer}
.exbtn:hover{border-color:var(--pd)}
.exbtn[aria-expanded="true"]{background:var(--pd);color:var(--paper);border-color:var(--pd)}
.exbtn:focus-visible,.nav a:focus-visible,.nav select:focus-visible,.dh button:focus-visible,.pn a:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.take{margin:14px 0 0;padding:10px 14px;border-radius:10px;background:var(--acc-t);color:var(--acc);font-weight:600;font-size:14.2px}
.dash{padding:14px 16px 16px;border-color:color-mix(in srgb,var(--pd) 45%,var(--line))}
.dh{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.dt{margin:0;font-weight:700;color:var(--pd);flex:1 1 auto;min-width:0}
.dh button{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--paper);color:var(--ink2);border-radius:8px;padding:3px 10px;cursor:pointer}
.db{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:12px;align-items:start}
.card{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--paper);min-width:0;display:flex;flex-direction:column;gap:8px}
.card.setup{background:var(--soft2)}
.ct{font-weight:600;font-size:13.5px;color:var(--ink2)}
.cn{margin:0;font-size:13px;color:var(--ink2)}
pre.code{margin:0;background:var(--code-bg);border-radius:8px;padding:9px 11px;overflow-x:auto;font-size:13px;line-height:1.55}
pre.code code{background:none;padding:0;font-size:inherit;white-space:pre}
pre.code .s{color:var(--str)} pre.code .c{color:var(--cmt)}
pre.code .ar{color:var(--ink3)} pre.code .out{color:var(--pd);font-weight:600} pre.code .err{color:var(--ng);font-weight:600}
.tbl{overflow-x:auto;max-width:100%}
.tbl table{border-collapse:collapse;font-family:var(--f-mono);font-size:13px;font-variant-numeric:tabular-nums}
.tbl th,.tbl td{padding:4px 12px;text-align:center;white-space:nowrap;border-bottom:1px solid var(--line)}
.tbl th{color:var(--pd);font-weight:600;background:var(--soft);border-bottom:2px solid var(--pd)}
.tbl th.ix,.tbl td.ix{color:var(--ink3);font-weight:600}
.tbl td.nan{color:var(--ink3)}
.tbl tr.hl td{background:var(--ng-t)}
.tbl table.mini{font-family:var(--f-body);font-size:13.5px}
.tbl table.mini th{color:var(--ink2);border-bottom:2px solid var(--line)}
.tbl table.mini td{text-align:left;white-space:normal}
.val{margin:0;font-family:var(--f-mono);color:var(--pd);font-weight:600}
.obox{border:1px solid var(--line);border-radius:8px;padding:6px 8px 8px;min-width:0}
.obox .oh{margin:0 0 4px;font-size:12.5px;font-weight:600;color:var(--ink2)}
.obox pre.code{background:var(--soft2)}
.obox pre.code code{white-space:pre!important;overflow-wrap:normal!important}  /* 콘솔 출력은 줄을 접으면 열이 어긋난다 — 넘치면 상자 안에서 가로 스크롤 */
.errbox{margin:0;padding:8px 10px;border-radius:8px;background:var(--ng-t);color:var(--ng);font-family:var(--f-mono);font-size:13px;font-weight:600;overflow-wrap:anywhere}
.warn{margin:0;padding:6px 10px;border-radius:8px;background:var(--warn-t);color:var(--warn);font-size:13px;font-weight:600}
.pn{display:flex;justify-content:space-between}
.pn a{color:var(--acc);text-decoration:none;font-weight:600;font-size:14px;padding:6px 2px}
@media (max-width:640px){.canvas{padding:16px 14px}.dash{padding:12px}.canvas,.dash{scroll-margin-top:124px}.tbl th,.tbl td{padding:4px 9px}
  pre.code{font-size:12.5px} pre.code code{white-space:pre-wrap;overflow-wrap:anywhere}}  /* 폰: 결과 값이 옆으로 숨지 않게 줄바꿈 */
"""

JS = r"""
(function(){
  const pages=[...document.querySelectorAll('[data-page]')];
  const ids=pages.map(p=>p.id);
  const sel=document.getElementById('pagesel');
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  function cur(){const h=location.hash.slice(1);return ids.includes(h)?h:ids[0];}
  function render(){
    const id=cur();
    pages.forEach(p=>{p.hidden=p.id!==id;});
    sel.value=id;
    const i=ids.indexOf(id);
    document.querySelector('.top .pv').href='#'+(ids[i-1]||id);
    document.querySelector('.top .nx').href='#'+(ids[i+1]||id);
  }
  sel.addEventListener('change',()=>{location.hash=sel.value;});
  addEventListener('hashchange',()=>{render();scrollTo({top:0,behavior:'auto'});});
  addEventListener('keydown',e=>{
    if(e.target.closest('input,select,textarea')||e.altKey||e.ctrlKey||e.metaKey)return;
    const i=ids.indexOf(cur());
    if(e.key==='ArrowRight'&&ids[i+1])location.hash=ids[i+1];
    if(e.key==='ArrowLeft'&&ids[i-1])location.hash=ids[i-1];
  });
  function close(page){
    const d=page.querySelector('.dash');d.hidden=true;d.querySelector('.db').innerHTML='';
    page.querySelectorAll('.exbtn').forEach(b=>b.setAttribute('aria-expanded','false'));
  }
  document.addEventListener('click',e=>{
    const b=e.target.closest('.exbtn');
    if(b){
      const page=b.closest('[data-page]');const d=page.querySelector('.dash');
      if(b.getAttribute('aria-expanded')==='true'){close(page);return;}
      const t=document.getElementById('t-'+b.dataset.ex);if(!t)return;
      page.querySelectorAll('.exbtn').forEach(x=>x.setAttribute('aria-expanded',String(x===b)));
      d.querySelector('.dt').textContent='예시 · '+t.dataset.title;
      const db=d.querySelector('.db');db.innerHTML='';db.appendChild(t.content.cloneNode(true));
      d.hidden=false;
      const r=d.getBoundingClientRect();
      if(r.top>innerHeight*0.6||innerWidth<900)d.scrollIntoView({behavior:reduce?'auto':'smooth',block:'start'});
      return;
    }
    const x=e.target.closest('.dash .x');if(x){const page=x.closest('[data-page]');close(page);page.querySelector('.canvas').scrollIntoView({behavior:reduce?'auto':'smooth',block:'start'});return;}
    const u=e.target.closest('.dash .up');if(u){u.closest('[data-page]').querySelector('.canvas').scrollIntoView({behavior:reduce?'auto':'smooth',block:'start'});}
  });
  render();
})();
"""
