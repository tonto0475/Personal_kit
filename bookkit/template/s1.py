# -*- coding: utf-8 -*-
"""1 이 과제가 진짜 묻는 것 — v3 양식
흐름(바꾸지 않는다): 무엇을 만드나 → 입력의 종류(v3: 근무 네 종류) → 큰 흐름 그림 → 진짜로 묻는 것(출처를 그 자리에서) →
      숨은 요구(분류 색 · 어디서 드러나나 · 만들 것) → README 원문 요구(분류 색 · 만들 것) → README 가 말하지 않은 곳(왜 문제 · 기본 가정)
v3 스티커: fef99dfa(처음 나오는 제약은 그 자리에서 출처) · 7ef3fdc7(요구 → 분류 → 만들 것) · 7b382b19(침묵은 칸마다 풀어서)"""
from . import figs, kit, shared
from .content.s1 import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/s1.py


# ══ 구조 — 고치지 않는다(v3 블록 순서 · 상자) ══
def build(w):
    K = kit.slots(w, "s1", fill())
    S = kit.slots(w, "shared", shared.values())
    w.chapter("1", K["제목"], K["질문"])
    if "도메인_제목" in K.v:  # 도메인 한 장 — 칸이 있는 양식만(v3 · 옛 책은 칸이 없어 블록도 없다 — v3 와 같은 책)
        fns, dl = {}, ""
        for name, key in (("무엇을 재나", "도메인_재는_것"), ("단위", "도메인_단위"), ("무엇이 나쁜가", "도메인_나쁜_것"), ("현장에서 고치는 법", "도메인_고치는_법")):
            t, f = K.tf(key)
            fns.update(f or {})
            dl += f"<dt>{kit.esc(name)}</dt><dd>{w.t(t)}</dd>"
        head = K["도메인_제목"]
        w.key("도메인")
        w.html(f'<div class="qi"><p class="qh">{w.t(head)}</p><dl>{dl}</dl></div>', fn=fns or None)
    w.p(*K.tf("무엇을"))
    w.p(*K.tf("입력_종류"))
    if S.need("그림_큰흐름"):
        w.svg(figs.overview(S["그림_큰흐름"]), caption=K["그림_캡션"])

    asks = K.get("진짜로_묻는_것", [])
    w.section(f"진짜로 묻는 것 — {kit.num_kr(len(asks))} 가지" if asks else "진짜로 묻는 것")  # 1차판에서 칸이 비면 개수 없이
    if K.need("진짜로_묻는_것"):
        w.ul(asks)
    w.p(*K.tf("출제_의도"))

    # ── 숨은 요구 ─────────────────────────────────────────
    w.section(K["숨은_요구_제목"])
    w.p(*K.tf("숨은_요구_설명"))
    if K.need("분류_설명"):
        w.html(kit.legend_html(K["분류_설명"]))
    if K.need("숨은_요구"):
        hid = [h for h in K["숨은_요구"] if h[2] == "알고리즘"] + [h for h in K["숨은_요구"] if h[2] != "알고리즘"]
        fns = K.opt("숨은_요구_각주") or (None, None)
        n_alg = sum(1 for h in hid if h[2] == "알고리즘")
        for lo, hi, cap, fn in ((0, n_alg, f"숨은 요구 {kit.span(hid[:n_alg], 0, n_alg)} — 핵심 계산(알고리즘)에 들어가는 것", fns[0]),
                                (n_alg, len(hid), f"숨은 요구 {kit.span(hid[n_alg:], n_alg, len(hid))} — 자료 · 저장 · 화면 · 문서에 들어가는 것", fns[1])):
            rows = [[kit.no(h, i + 1), w.t(f"**{h[0]}**"), w.t(h[1]), kit.chip(h[2]), w.t(h[3])] for i, h in enumerate(hid) if lo <= i < hi]
            if rows:
                w.table(header=["#", "숨은 요구", "어디서 드러나나", "분류", "만들 것"], rows=rows, cls="wr lf", small=True, html_cols=[1, 2, 3, 4],
                        nw_cols=["#", "분류"], caption=cap, fn=fn)

    # ── README 원문 요구 ──────────────────────────────────
    groups = K.get("README_요구", [])
    w.section(f"README 가 글로 요구한 것 — {sum(len(g['rows']) for g in groups) if groups else 'N'}개")
    w.p(*K.tf("README_요구_설명"))
    if K.need("README_요구"):
        lo = 0
        for g in groups:
            hi = lo + len(g["rows"])
            rows = [[kit.no(r, lo + i + 1), w.t(r[0]), kit.chip(r[1]), w.t(r[2])] for i, r in enumerate(g["rows"])]
            w.table(header=["#", "README 원문 요지", "분류", "만들 것"], rows=rows, cls="wr lf", small=True, html_cols=[1, 2, 3], nw_cols=["#", "분류"],
                    caption=f"README 요구 {kit.span(g['rows'], lo, hi)} — {g['name']}", fn=g.get("fn"))
            lo = hi

    # ── README 가 말하지 않은 곳 ──────────────────────────
    sil = K.get("말하지_않은_곳", [])
    w.section(f"README 가 말하지 않은 것 — {len(sil) if sil else 'N'}곳")
    w.p(*K.tf("말하지_않은_곳_설명"))
    if K.need("말하지_않은_곳"):
        for i, s in enumerate(sil):
            t, c, why, dflt = s
            kit.qitem(w, f"{kit.no(s, i + 1)}. {t}", c, [("왜 문제인가", why), ("기본 가정", dflt)], key=kit.rid(s))
    w.p(*K.tf("말하지_않은_곳_맺음"))
