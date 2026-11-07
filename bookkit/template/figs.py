# -*- coding: utf-8 -*-
"""과제 파악 책(v3 양식)의 그림 — 데이터(점 · 선 · 이름표 · 단계)만 주면 v3 와 같은 모양의 SVG 글자를 돌려준다

- 과제와 무관하다. 값 · 글은 전부 인자로 받는다(장 파일의 칸 · shared.py 에서 채운 것)
- 단계 재생기에 들어가는 그림은 단계마다 같은 크기(viewBox)여야 한다 — 함수마다 크기가 고정이다
- 좌표: 위도 · 경도면 geo=True(경도 방향을 cos(위도)로 줄인다) · 평면 좌표(x, y)면 geo=False 로 (y, x) 순서로 준다
- 이 파일은 고치지 않는다(빌드가 양식과 다르면 «구조 바뀜» 으로 알린다). 그림이 더 필요하면 그 책의 content/ 에서 Svg 로 그린다
"""
import math

from book.engine import Svg, esc  # 엔진의 SVG 도우미 — build_book.py 가 bookkit/engine 을 불러오기 경로에 넣는다

# 차 색 — 차 하나 = 색 하나, 끝까지 같은 색(v3 시각화 규칙 3)
COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#b45309", "#0f766e", "#db2777", "#4b5563", "#0891b2", "#65a30d", "#ea580c"]


# ════════════════════════════════════════════════════════════
# 좌표 → 그림 위치
# ════════════════════════════════════════════════════════════
def fit_box(points=None, bounds=None, box=(8, 34, 430, 222), pad=(0.012, 0.012, 0.025, 0.03), geo=True):
    """점들이 상자 안 가운데에 비율 그대로 들어가게 하는 변환 → 함수 f(위도, 경도) = (x, y)
    points = [(위도, 경도)] 또는 [(y, x)] · bounds = (아래, 위, 왼쪽, 오른쪽) 를 직접 주면 points 대신 쓴다
    pad = (아래, 위, 왼쪽, 오른쪽) 여백(좌표 단위) · box = (x, y, 폭, 높이)"""
    if bounds is None:
        ys = [p[0] for p in points]
        xs = [p[1] for p in points]
        bounds = (min(ys) - pad[0], max(ys) + pad[1], min(xs) - pad[2], max(xs) + pad[3])
    lat0, lat1, lon0, lon1 = bounds
    bx, by, W, H = box
    if geo:
        k = math.cos(math.radians((lat0 + lat1) / 2))
        wkm, hkm = (lon1 - lon0) * 111.32 * k, (lat1 - lat0) * 110.57
        sc = min(W / wkm, H / hkm)
        ox = bx + (W - wkm * sc) / 2
        oy = by + (H - hkm * sc) / 2

        def f(lat, lon):
            return ox + (lon - lon0) * 111.32 * k * sc, oy + (lat1 - lat) * 110.57 * sc
        return f
    wd, hd = (lon1 - lon0), (lat1 - lat0)
    sc = min(W / wd, H / hd)
    ox = bx + (W - wd * sc) / 2
    oy = by + (H - hd * sc) / 2

    def g(y, x):
        return ox + (x - lon0) * sc, oy + (lat1 - y) * sc
    return g


def text_w(text, size):
    """SVG 글 한 줄의 폭 어림(px) — 한글 · 넓은 글자 = 글자 크기, 그 밖 = 0.6배. 줄바꿈이 있으면 가장 긴 줄"""
    return max((sum(size if ord(ch) > 0x2E7F else size * 0.6 for ch in ln) for ln in str(text).split("\n")), default=0)


def fit_text(text, size, width):
    """폭 width 안에 들게 줄인 글 — 넘치면 끝을 «…» 로(그림 안 글은 줄바꿈이 자동이 아니다)"""
    t = str(text)
    if text_w(t, size) <= width:
        return t
    while t and text_w(t + "…", size) > width:
        t = t[:-1]
    return t + "…"


def _diamond(s, cx, cy, label, dx=-12, dy=3):
    """목적지(사업장) 표식 — 검은 마름모 + 이름"""
    s.parts.append(f'<rect x="{cx - 6:g}" y="{cy - 6:g}" width="12" height="12" fill="#111827" transform="rotate(45 {cx:g} {cy:g})"/>')
    s.text(cx + dx, cy + dy, label, size=10.5, tone="ink", bold=True, halo=True, anchor="end")


# ════════════════════════════════════════════════════════════
# 1. 큰 흐름 + 묶음 막대(v3 «하루 파동 8개») — 한눈에 · 1장
# ════════════════════════════════════════════════════════════
def overview(P):
    """P = {"flow": {"input", "check", "plan", "out1", "out2"},   # 위 흐름 상자 글(줄바꿈 \\n)
            "bars": {"title", "legend": [(이름, 색)], "columns": [{"label", "sub", "sub_tone", "note", "values": [수 …]}],
                     "k": 막대 높이 배율(없으면 자동), "colors": [막대 색 …]},
            "note": 맨 아래 한 줄, "label": 그림 이름}  → 664 × 404
    열 4~12개 · 열 아래 글(label · sub · note)은 열 폭에 맞춰 5자 안팎(열 8개 기준 — 넘으면 옆 열 글과 겹친다)"""
    f, b = P["flow"], P["bars"]
    s = Svg(664, 404)
    s.box(6, 22, 96, 62, f["input"], tone="gray", size=11, bold=True, fill="#ffffff")
    s.arrow(104, 53, 136, 53, tone="gray", sw=1.8, head=7)
    s.box(138, 22, 116, 62, f["check"], tone="amber", size=11, bold=True)
    s.arrow(256, 53, 288, 53, tone="gray", sw=1.8, head=7)
    s.box(290, 22, 122, 62, f["plan"], tone="acc", size=11, bold=True)
    s.arrow(414, 40, 442, 30, tone="gray", sw=1.8, head=7)
    s.arrow(414, 66, 442, 76, tone="gray", sw=1.8, head=7)
    s.box(444, 8, 212, 42, f["out1"], tone="ok", size=11, bold=True)
    s.box(444, 58, 212, 42, f["out2"], tone="ok", size=11, bold=True)
    # 분류 색(1장의 색 표시와 같다)
    s.text(196, 96, "파이프라인", size=10.5, tone="amber", bold=True)
    s.text(351, 96, "알고리즘", size=10.5, tone="acc", bold=True)
    s.text(550, 112, "화면", size=10.5, tone="ok", bold=True)
    s.parts.append('<g transform="translate(0,12)">')
    s.text(8, 124, b["title"], size=12, tone="ink", anchor="start", bold=True)
    lx = 470
    for i, (name, col) in enumerate(b.get("legend", [])):
        s.box(lx + i * 82, 114, 12, 12, "", tone="gray" if not col else col, fill=col, rx=2)
        s.text(lx + i * 82 + 17, 120, name, size=11, anchor="start", tone="gray")
    cols = b["columns"]
    n = len(cols)
    colw = 640 / n
    nv = max(len(c["values"]) for c in cols)
    bw = min(24, (colw - 16) / nv - 4)
    vmax = max(max(c["values"]) for c in cols) or 1
    k = b.get("k") or min(0.40, 150 / vmax)
    colors = b.get("colors") or ["#2563eb", "#0f766e", "#b45309"]
    base = 300
    for i, c in enumerate(cols):
        x0 = 12 + i * colw
        for j, v in enumerate(c["values"]):
            h = v * k
            bx = x0 + 8 + j * (bw + 4)
            s.box(bx, base - h, bw, h, "", tone="gray", fill=colors[j], stroke=colors[j], rx=2, sw=1)
            s.text(bx + bw / 2, base - h - 8, str(v), size=11, tone="ink", bold=True)
        s.line(x0 + 2, base, x0 + colw - 6, base, tone="gray", sw=1)
        cx = x0 + (colw - 4) / 2
        s.text(cx, base + 14, c["label"], size=12, tone="ink", bold=True)
        s.text(cx, base + 30, c.get("sub", ""), size=11, tone=c.get("sub_tone", "gray"), bold=True)
        s.text(cx, base + 45, c.get("note", ""), size=10, tone="ng")
    s.text(332, 372, P.get("note", ""), size=10.5, tone="gray")
    s.parts.append("</g>")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 2. 파일 줄 구간 띠 + 정리 전후 막대(v3 «근무표 파일의 이어 붙인 구조») — 한눈에 · 2장
# ════════════════════════════════════════════════════════════
def file_band(P):
    """P = {"title": 띠 위 제목, "total": 줄 수(폭 배율의 분모),
            "segments": [{"a", "b", "color", "inside": 띠 안 글 | None, "inside_tone",
                          "callout": 설명 글 | None, "callout_tone", "at": "above" | "below", "x": "mid" | "right", "anchor": "end" | "start"}],
            "compare": {"title", "rows": [(이름, 값, 값 글자, "ok" | "ng")], "note"}, "label"}  → 664 × 262
    구간 폭 = 640 × 줄 수 ÷ total(최소 7px). 설명 글은 화살표 끝 왼쪽(x = mid)이나 구간 오른쪽 끝(x = right)에 오른쪽 맞춤
    왼쪽 가장자리 구간은 "anchor": "start" — 글이 화살표 오른쪽으로 늘어난다(오른쪽 맞춤이면 그림 밖으로 나간다)
    "at": "above" 설명 글은 띠 제목과 같은 높이(y 22)다 — 띠 오른쪽 절반 구간에만 쓴다(왼쪽이면 제목과 겹친다)"""
    s = Svg(664, 262)
    x0, wtot = 12, 640
    s.text(8, 14, P["title"], size=12, anchor="start", tone="ink", bold=True)
    x = x0
    pos = []
    for g in P["segments"]:
        wpx = max(7, wtot * (g["b"] - g["a"] + 1) / P["total"])
        pos.append((x, wpx))
        s.box(x, 44, wpx, 34, "", tone="gray", fill=g["color"], stroke="#ffffff", rx=0, sw=1)
        x += wpx
    for g, (gx, gw) in zip(P["segments"], pos):
        if g.get("inside"):
            s.text(gx + gw / 2, 61, g["inside"], size=11, tone=g.get("inside_tone", "ink"), bold=True)
    for g, (gx, gw) in zip(P["segments"], pos):
        if not g.get("callout"):
            continue
        cx = gx + gw / 2
        tone = g.get("callout_tone", "ng")
        anchor = g.get("anchor", "end")  # «start» = 설명 글을 화살표 오른쪽으로(왼쪽 가장자리 구간)
        if anchor == "start":
            tx = gx + gw + 2 if g.get("x") == "right" else cx + 4
        else:
            tx = gx + gw + 2 if g.get("x") == "right" else cx - 4
        if g.get("at") == "above":
            s.arrow(cx, 28, cx, 42, tone=tone, sw=1.4, head=6)
            s.text(tx, 22, g["callout"], size=10.5, tone=tone, bold=True, anchor=anchor)
        else:
            s.arrow(cx, 120, cx, 80, tone=tone, sw=1.4, head=6)
            s.text(tx, 132, g["callout"], size=10.5, tone=tone, bold=True, anchor=anchor)
    cp = P.get("compare")
    if cp:
        s.text(8, 166, cp["title"], size=12, anchor="start", tone="ink", bold=True)
        sc = 380 / max(max(r[1] for r in cp["rows"]), 1)
        fill = {"ok": "#16a34a", "ng": "#dc2626"}
        y = 196
        for name, v, txt, tone in cp["rows"]:
            s.text(8, y, name, size=11.5, anchor="start", tone=tone, bold=True)
            s.box(96, y - 12, v * sc, 24, "", tone=tone, fill=fill.get(tone, tone), stroke=fill.get(tone, tone), rx=2)
            s.text(96 + v * sc + 8, y, txt, size=12, anchor="start", tone=tone, bold=True)
            y += 36
        if cp.get("note"):
            s.text(660, y - 36, cp["note"], size=11, anchor="end", tone="ng")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 3. 시스템 층(v3 «시스템 층») — 한눈에 · 5장
# ════════════════════════════════════════════════════════════
def layers(P):
    """P = {"screens": [화면 이름 1~3개], "api": 조회 층 글, "store_title", "store": [저장소 줄 ≤ 4],
            "upload", "check", "apply", "apply_label", "job_title", "job": [작업 줄 ≤ 4], "job_note", "save_label", "label"}  → 664 × 400"""
    s = Svg(664, 400)
    n = len(P["screens"])
    sw_ = (312 - 12 * (n - 1)) / n
    for i, name in enumerate(P["screens"]):
        s.box(8 + i * (sw_ + 12), 10, sw_, 44, name, tone="ok", size=12, bold=True)
    for i in range(n):
        cx = 8 + i * (sw_ + 12) + sw_ / 2
        s.arrow(cx, 56, cx, 96, tone="gray", sw=1.6, head=7)
    s.box(8, 98, 312, 48, P["api"], tone="acc", size=11.5, bold=True)
    s.arrow(164, 148, 164, 184, tone="gray", sw=1.6, head=7)
    s.box(8, 186, 312, 110, "", tone="gray", fill="#f8fafc", sw=1.8)
    s.text(164, 202, P["store_title"], size=12, tone="ink", bold=True)
    for i, t in enumerate(P["store"][:4]):
        s.text(26, 226 + i * 18, t, size=11, tone="gray", anchor="start")
    s.box(360, 10, 296, 44, P["upload"], tone="gray", size=12, bold=True, fill="#ffffff")
    s.arrow(508, 56, 508, 76, tone="gray", sw=1.6, head=7)
    s.box(360, 78, 296, 52, P["check"], tone="amber", size=11.5, bold=True)
    s.arrow(508, 132, 508, 152, tone="gray", sw=1.6, head=7)
    s.box(360, 154, 296, 44, P["apply"], tone="ok", size=11.5, bold=True)
    s.arrow(358, 176, 322, 232, tone="ok", sw=1.8, head=7, label=P.get("apply_label", "적용"), lx=336, ly=196)
    s.box(360, 250, 296, 140, "", tone="acc", fill="#eaf1ff", sw=1.8)
    s.text(508, 268, P["job_title"], size=12, tone="acc", bold=True)
    for i, t in enumerate(P["job"][:4]):
        s.text(380, 292 + i * 20, t, size=11, tone="ink", anchor="start")
    s.text(508, 380, P.get("job_note", ""), size=10, tone="acc")
    s.arrow(358, 330, 322, 290, tone="acc", sw=1.8, head=7, label=P.get("save_label", "저장"), lx=334, ly=326)
    s.arrow(508, 248, 508, 232, tone="acc", sw=0, head=0)
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 4. 세 단계 띠(v3 «방안과 무관한 공통 후속 단계») — 4장
# ════════════════════════════════════════════════════════════
def strip3(P):
    """P = {"boxes": [글 3개(줄바꿈 \\n)], "label"}  → 664 × 84. 왼쪽 회색 → 가운데 파랑 → 오른쪽 초록"""
    a, b, c = P["boxes"]
    s = Svg(664, 84)
    s.box(6, 14, 170, 56, a, tone="gray", size=11, bold=True, fill="#ffffff")
    s.arrow(178, 42, 214, 42, tone="gray", sw=1.8, head=7)
    s.box(216, 14, 232, 56, b, tone="acc", size=11, bold=True)
    s.arrow(450, 42, 486, 42, tone="gray", sw=1.8, head=7)
    s.box(488, 14, 168, 56, c, tone="ok", size=11, bold=True)
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 5. 순서 비교 작은 지도(v3 «거점 세 곳의 순서») — 4장 첫 절
# ════════════════════════════════════════════════════════════
def orders_map(P):
    """P = {"points": {이름: (위도, 경도)}, "short": {이름: 짧은 이름}, "target": (위도, 경도), "target_label",
            "best": (순서 [이름 …], 범례 글), "worst": (순서, 범례 글), "geo": True, "label"}  → 300 × 214
    가장 짧은 순서 = 초록 실선 · 가장 긴 순서 = 빨강 점선 · 오른쪽 끝 점의 이름은 자동으로 점 왼쪽에 둔다
    P 에 "kind": "arrows" 가 있으면 측정 화살표 두 판(arrows_pair — 분석 틀 stat_model 의 가장 작은 경우)"""
    if P.get("kind") == "arrows":
        return arrows_pair(P)
    s = Svg(300, 214)
    pts = P["points"]
    best, worst = P["best"], P["worst"]
    names = sorted(set(best[0]) | set(worst[0]))
    lats = [pts[n][0] for n in names] + [P["target"][0]]
    lons = [pts[n][1] for n in names] + [P["target"][1]]
    lat0, lat1, lon0, lon1 = min(lats), max(lats), min(lons), max(lons)
    k = math.cos(math.radians((lat0 + lat1) / 2)) if P.get("geo", True) else 1.0
    W, H = 240, 140
    sc = min(W / ((lon1 - lon0) * k + 1e-9), H / ((lat1 - lat0) + 1e-9))

    def at(lat, lon):
        return 30 + (lon - lon0) * k * sc, 30 + (lat1 - lat) * sc

    s.box(2, 4, 296, 206, "", tone="gray", fill="#f8fafc", sw=1, rx=6)
    for order, col, dash, sw in ((worst[0], "#dc2626", True, 2.0), (best[0], "#16a34a", False, 3.2)):
        xy = [at(*pts[n]) for n in order] + [at(*P["target"])]
        d = "M" + " L".join(f"{x:g} {y:g}" for x, y in xy)
        da = ' stroke-dasharray="6 4"' if dash else ""
        s.parts.append(f'<path d="{d}" stroke="{col}" stroke-width="{sw:g}" fill="none"{da}/>')
    for n in names:
        x, y = at(*pts[n])
        s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="5" fill="#1f2328"/>')
        lab = P["short"].get(n, n)
        if x + 8 + text_w(lab, 11) > 294:  # 오른쪽 끝 점 — 이름을 점 왼쪽으로(상자 밖으로 잘리지 않게)
            s.text(x - 8, y - 9, lab, size=11, tone="ink", bold=True, halo=True, anchor="end")
        else:
            s.text(x + 8, y - 9, lab, size=11, tone="ink", bold=True, halo=True, anchor="start")
    cx, cy = at(*P["target"])
    _diamond(s, cx, cy, P["target_label"], dx=-10, dy=13)
    s.line(14, 196, 38, 196, tone="ok", sw=3)
    s.text(42, 196, best[1], size=10.5, tone="ok", bold=True, anchor="start")
    s.line(158, 196, 182, 196, tone="ng", sw=2, dash=True)
    s.text(186, 196, worst[1], size=10.5, tone="ng", bold=True, anchor="start")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 6. 경로 지도 + 오른쪽 목록(v3 재생기 A · 한 곳씩 고치기의 그림) — 664 × 270
# ════════════════════════════════════════════════════════════
def route_map(M, routes, title, right_title, right_lines, cur=None, hl=None, gone=(), style="fill"):
    """M = 지도 칸 {"points": {이름: (위도, 경도)}, "weights": {이름: 인원}(회색 원 · 이름표 숫자 — 이 순서로 그린다),
                    "short": {이름: 짧은 이름}, "below": [이름표를 점 아래에 둘 이름], "target": (위도, 경도) | None, "target_label",
                    "bounds" | "fit_points" + "pad", "geo": True, "edges": [(이름 a, 이름 b)](선택 — 도로 · 통로 같은 바탕 선)}
    target = None 이면 공동 목적지가 없다(경로는 마지막 들른 곳에서 끝나고 마름모를 그리지 않는다)
    routes = [[(이름, 수) …] 차마다] — 들르는 순서(먼 곳 → 목적지)
    style «fill» = 채우기(cur 차만 굵게 · 같은 곳 연속은 한 점) · «fix» = 고치기(hl 차들을 굵게 위로 · 나머지 흐리게 · gone 에 빨간 ×)
    right_lines = [(글, 색)] — 오른쪽 목록 한 줄씩(줄바꿈 \\n 가능)"""
    s = Svg(664, 270)
    proj = fit_box(points=M.get("fit_points"), bounds=M.get("bounds"), pad=M.get("pad", (0.012, 0.012, 0.025, 0.03)), geo=M.get("geo", True))
    pts = M["points"]
    colors = M.get("colors", COLORS)
    below = set(M.get("below", ()))
    s.text(8, 14, title, size=12, anchor="start", tone="ink", bold=True)
    s.box(6, 28, 438, 234, "", tone="gray", fill="#f8fafc", sw=1, rx=6)
    for a, b in M.get("edges", ()):
        (xa, ya), (xb, yb) = proj(*pts[a]), proj(*pts[b])
        s.parts.append(f'<line x1="{xa:g}" y1="{ya:g}" x2="{xb:g}" y2="{yb:g}" stroke="#d5dbe3" stroke-width="1.2"/>')
    tgt = [proj(*M["target"])] if M.get("target") is not None else []
    cnt = M["weights"]
    for name, c in cnt.items():
        x, y = proj(*pts[name])
        r = 3 + math.sqrt(c) * 0.9
        s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')
    if style == "fill":
        for bi, b in enumerate(routes):
            if not b:
                continue
            col = colors[bi % len(colors)]
            seq = []
            for name, _ in b:
                if not seq or seq[-1] != name:
                    seq.append(name)
            xy = [proj(*pts[n]) for n in seq] + tgt
            on = cur is None or bi == cur
            d = "M" + " L".join(f"{x:g} {y:g}" for x, y in xy)
            s.path(d, tone=col, sw=3.2 if on else 1.6, dash=False)
            for (x, y), n in zip(xy[:len(seq)], seq):
                s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="4.5" fill="{col}" stroke="#ffffff" stroke-width="1.2"/>')
    else:
        hl = set(hl or ())
        order = [b for b in range(len(routes)) if b not in hl] + [b for b in range(len(routes)) if b in hl]
        for bi in order:
            b = routes[bi]
            if not b:
                continue
            col = colors[bi % len(colors)]
            on = not hl or bi in hl
            xy = [proj(*pts[n]) for n, _ in b] + tgt
            d = "M" + " L".join(f"{x:g} {y:g}" for x, y in xy)
            s.parts.append(f'<path d="{d}" stroke="{col}" stroke-width="{3.4 if on else 1.4:g}" fill="none" opacity="{1 if on else 0.35:g}"/>')
            for (x, y) in xy[:len(b)]:
                s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="{4.5 if on else 3:g}" fill="{col}" stroke="#ffffff" stroke-width="1.2" opacity="{1 if on else 0.4:g}"/>')
    for name, c in cnt.items():
        x, y = proj(*pts[name])
        dy = 12 if name in below else -11
        s.text(x, y + dy, f"{M['short'].get(name, name)} {c}", size=10, tone="ink", bold=True, halo=True)
    if style != "fill":
        for _, name in gone:
            x, y = proj(*pts[name])
            s.parts.append(f'<path d="M{x - 7:g} {y - 7:g} L{x + 7:g} {y + 7:g} M{x + 7:g} {y - 7:g} L{x - 7:g} {y + 7:g}" stroke="#dc2626" stroke-width="2.6"/>')
    if tgt:
        _diamond(s, tgt[0][0], tgt[0][1], M["target_label"])
    s.text(456, 14, right_title, size=12, anchor="start", tone="ink", bold=True)
    for i, (t, col) in enumerate(right_lines):
        s.text(456, 38 + i * 28, t, size=10, anchor="start", tone=col)
    return s.render(title)


# ════════════════════════════════════════════════════════════
# 7. 차 시간표(v3 «트립 이어 붙이기» 그림) — 차마다 한 줄 + 오른쪽 «지금 그 차가 있는 곳» — 664 × 300
# ════════════════════════════════════════════════════════════
def timetable(T, k, title):
    """T = 시간표 칸 {"trips": [{"start", "end", "frm", "to", "color"}], "steps": [{"trip": 번호, "bus": 차 번호}],
                      "have": 보유 대수, "axis": (시작 분, 끝 분), "ticks": [눈금 분 …], "rows": 줄 수,
                      "legend": [(이름, 색, 점선?)], "deadhead": 함수(곳 a, 곳 b) → 분, "place": 함수(곳) → 이름, "hm": 함수(분) → «07:30»,
                      "words": {"unit": "차 {k}", "have": "▲ 보유 {n}대", "where": "{t} 에 차가 있는 곳", "end": "아침이 끝났을 때",
                                "done": "{place} {t} 도착 · 트립 {n}개", "take": "▶ {place} {t} 출발을 맡음",
                                "run": "달리는 중 → {t} {place}", "idle": "{place} 에 있음({t}~)"}}
    k = 지금 단계(0부터) · k = len(steps) 이면 «다 붙인 결과» 정리 그림
    rows(줄 수) 기본 10 — 10 을 넘기면 그림 높이가 줄마다 22px 늘어난다(300 + 22 × (rows − 10) · 16줄까지 권장)"""
    trips, steps, have = T["trips"], T["steps"], T["have"]
    W_ = T["words"]
    hm, place = T["hm"], T["place"]
    st = steps[min(k, len(steps) - 1)]
    last_step = k >= len(steps)
    now = trips[st["trip"]]["start"]
    rows = T.get("rows", 10)
    s = Svg(664, 300 + 22 * max(0, rows - 10))
    t0, t1 = T["axis"]
    x0, x1 = 62, 426
    X = lambda m: x0 + (max(t0, min(t1, m)) - t0) * (x1 - x0) / (t1 - t0)  # noqa: E731
    RH, Y0 = 22, 40
    s.text(8, 12, title, size=12, anchor="start", tone="ink", bold=True)
    for i, (lab, col, dash) in enumerate(T["legend"]):
        lx = 456 + i * 50
        da = ' stroke-dasharray="3 2"' if dash else ""
        s.parts.append(f'<rect x="{lx}" y="3" width="16" height="10" rx="2" fill="{"none" if dash else col}" stroke="{col}" stroke-width="1.4"{da}/>')
        s.text(lx + 20, 8, lab, size=10.5, anchor="start", tone="gray")
    s.text(456, 28, W_["where"].format(t=hm(now)) if not last_step else W_["end"], size=11, anchor="start", tone="ink", bold=True)
    for m in T["ticks"]:
        x = X(m)
        s.line(x, Y0 - 4, x, Y0 + rows * RH, tone="#e5e7eb", sw=1)
        s.text(x, Y0 + rows * RH + 12, hm(m), size=10, tone="gray")
    if have < rows:  # 보유선 — 줄 수보다 보유가 많으면 그림 밖이라 그리지 않는다
        yb = Y0 + have * RH - 2
        s.line(4, yb, x1, yb, tone="ng", sw=1.2, dash=True)
        s.text(x0 + 2, yb - 6, W_["have"].format(n=have), size=10, tone="ng", bold=True, anchor="start", halo=True)
    assigned = {}
    for i in range(min(k, len(steps) - 1) + 1):
        assigned.setdefault(steps[i]["bus"], []).append(steps[i]["trip"])
    nb = max(assigned) + 1
    xn = X(now)
    if not last_step:
        s.line(xn, Y0 - 6, xn, Y0 + rows * RH, tone="amber", sw=1.4, dash=True)
    for b in range(rows):
        y = Y0 + b * RH
        over = b >= have
        used = b < nb
        lab_tone = ("ng" if over else "ink") if used else "#c4cad3"
        s.text(8, y + 8, W_["unit"].format(k=b + 1), size=10.5, anchor="start", tone=lab_tone, bold=used and b == st["bus"] and not last_step)
        s.line(x0, y + 8, x1, y + 8, tone="#f1f5f9", sw=1)
        if b not in assigned:
            continue
        prev = None
        for j in assigned[b]:
            t = trips[j]
            if prev is not None:
                dh = T["deadhead"](prev[1], t["frm"])
                if dh > 0.5:
                    s.parts.append(f'<rect x="{X(prev[0]):g}" y="{y + 3:g}" width="{max(2, X(prev[0] + dh) - X(prev[0])):g}" height="10" rx="2" '
                                   'fill="none" stroke="#9aa3ad" stroke-width="1.3" stroke-dasharray="3 2"/>')
            cur = j == st["trip"] and not last_step
            col = "#dc2626" if over else t["color"]
            xa, xb = X(t["start"]), X(t["end"])
            s.parts.append(f'<rect x="{xa:g}" y="{y + 1:g}" width="{max(3, xb - xa):g}" height="14" rx="2" fill="{col}"'
                           + (' stroke="#f59e0b" stroke-width="3"' if cur else "") + "/>")
            prev = (t["end"], t["to"])
        if last_step:
            t = trips[assigned[b][-1]]
            msg, tone = W_["done"].format(place=place(t["to"]), t=hm(t["end"]), n=len(assigned[b])), ("ng" if over else "ink")
        elif b == st["bus"]:
            t = trips[st["trip"]]
            msg, tone = W_["take"].format(place=place(t["frm"]), t=hm(t["start"])), ("ng" if over else "acc")
        else:
            last = [j for j in assigned[b] if j != st["trip"]]
            t = trips[last[-1]]
            if t["end"] > now + 1e-9:
                msg, tone = W_["run"].format(t=hm(t["end"]), place=place(t["to"])), "gray"
            else:
                msg, tone = W_["idle"].format(place=place(t["to"]), t=hm(t["end"])), "ink"
        s.text(456, y + 8, msg, size=10.5, anchor="start", tone=tone, bold=(b == st["bus"] and not last_step))
    return s.render(title)


# ════════════════════════════════════════════════════════════
# 8. 전부 아니면 전무 실험(v3 «트랜잭션 실험») — 부록 C
# ════════════════════════════════════════════════════════════
def txn(P):
    """P = {"names": [넣는 순서 파일 이름 …](7개 안팎), "fail": 실패하는 위치(0부터), "rows": {"none": {이름: 행 수}, "txn": {이름: 행 수}},
            "labels": {"none": (왼쪽 이름, 아래 설명), "txn": (왼쪽 이름, 아래 설명)}, "order": "넣는 순서 →", "fail_text": "✗ 검증 실패",
            "unit": "행", "label"}  → 664 × 236
    상자 폭 72px — 이름은 영문 11자 · 한글 6자 안쪽(넘으면 끝을 «…» 로 줄인다) · 파일 8개까지"""
    names = P["names"]
    s = Svg(664, 236)
    bw, gap, x0 = 72, 8, 100
    s.text(x0, 12, P.get("order", "넣는 순서 →"), size=10.5, anchor="start", tone="gray")
    rows = (("none", "ng"), ("txn", "ok"))
    for r, (mode, tone) in enumerate(rows):
        lab, note = P["labels"][mode]
        y = 28 + r * 104
        s.text(8, y + 22, lab, size=11.5, anchor="start", tone=tone, bold=True)
        for i, n in enumerate(names):
            x = x0 + i * (bw + gap)
            v = P["rows"][mode][n]
            fail = i == P["fail"]
            fill = "#fdecec" if fail else ("#fff4e0" if v else "#f6f7f9")
            stroke = "#dc2626" if fail else ("#b45309" if v else "#c4cad3")
            s.box(x, y, bw, 46, "", tone="gray", fill=fill, stroke=stroke, sw=2 if fail else 1.3, rx=5)
            s.text(x + bw / 2, y + 15, fit_text(n, 10, bw - 6), size=10, tone="ink", bold=True)
            s.text(x + bw / 2, y + 32, P.get("fail_text", "✗ 검증 실패") if fail else f"{v:,}{P.get('unit', '행')}", size=10.5,
                   tone="ng" if fail else ("amber" if v else "gray"), bold=True)
        s.text(x0, y + 64, note, size=11, anchor="start", tone=tone, bold=True)
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 9. 화면 예시 — 왼쪽 개인 화면(카드) · 오른쪽 운영자 화면(표)(v3 «화면 예시») — 부록 C
# ════════════════════════════════════════════════════════════
def screens(P):
    """P = {"left": {"title", "head": 머리 줄, "cards": [{"tone": "acc"|"pur"|…, "fill", "label", "lines": [(글, 크기, 굵게?, 색)]}] (2장), "foot"},
            "right": {"title", "cols": [(x, 열 이름)], "rows": [[칸 글 …]], "foot"}, "label"}  → 664 × 292
    왼쪽 카드 두 장의 높이 = 92 · 76(v3 와 같다). 오른쪽 표는 8행 안쪽"""
    L, R = P["left"], P["right"]
    s = Svg(664, 292)
    s.box(6, 6, 236, 280, "", tone="gray", fill="#ffffff", sw=1.5, rx=14)
    s.box(7, 7, 234, 32, "", tone="ok", fill="#e9f7ee", sw=0, rx=13)
    s.text(124, 23, L["title"], size=12, tone="ok", bold=True)
    s.text(20, 58, L["head"], size=11, tone="ink", anchor="start", bold=True)
    for (y0, h), c in zip(((72, 92), (174, 76)), L["cards"]):
        s.box(18, y0, 212, h, "", tone=c["tone"], fill=c["fill"], sw=1, rx=6)
        s.text(28, y0 + 16, c["label"], size=10.5, tone=c["tone"], anchor="start", bold=True)
        for i, (t, size, bold, tone) in enumerate(c["lines"]):
            s.text(28, y0 + 36 + i * 20, t, size=size, tone=tone, anchor="start", bold=bold)
    s.text(124, 270, L.get("foot", ""), size=9.5, tone="gray")
    s.box(254, 6, 404, 280, "", tone="gray", fill="#ffffff", sw=1.5, rx=8)
    s.box(255, 7, 402, 32, "", tone="ok", fill="#e9f7ee", sw=0, rx=7)
    s.text(456, 23, R["title"], size=12, tone="ok", bold=True)
    for x, t in R["cols"]:
        s.text(x, 56, t, size=10.5, tone="gray", anchor="start", bold=True)
    xs = [x for x, _ in R["cols"]]
    for i, cells in enumerate(R["rows"]):
        y = 80 + i * 24
        s.line(262, y - 12, 650, y - 12, tone="#eef1f5", sw=1)
        for j, (x, t) in enumerate(zip(xs, cells)):
            s.text(x + (4 if j == 0 else 0), y, t, size=11 if j == 0 else 10.5, tone="ink", anchor="start", bold=j == 0)
    s.text(456, 274, R.get("foot", ""), size=9.5, tone="gray")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 10. 상태 전이(상태 N개 + 화살표 + 가능한 구간) — 배차 · 사건 시뮬레이션형 과제의 «한 대가 거치는 상태»
# ════════════════════════════════════════════════════════════
def _curve_arrow(s, x1, y1, x2, y2, up, tone, label, depth):
    """두 상자 사이 곡선 화살표 — up=True 면 위로 휜다(앞으로 건너뛰기) · False 면 아래로(뒤로 돌아가기) · depth = 상자에서 곡선 꼭대기까지(px)"""
    col = {"ng": "#dc2626", "ok": "#16a34a", "acc": "#2563eb", "amber": "#b45309", "pur": "#7c3aed"}.get(tone, "#4b5563")
    mx = (x1 + x2) / 2
    lift = 2 * depth
    cy = y1 - lift if up else y1 + lift
    s.parts.append(f'<path d="M{x1:g} {y1:g} Q{mx:g} {cy:g} {x2:g} {y2:g}" stroke="{col}" stroke-width="1.6" fill="none"/>')
    dx, dy = x2 - mx, y2 - cy
    ln = math.hypot(dx, dy) or 1
    ux, uy = dx / ln, dy / ln
    bx, by = x2 - ux * 7, y2 - uy * 7
    px, py = -uy * 3.9, ux * 3.9
    s.parts.append(f'<path d="M{x2:g} {y2:g} L{bx + px:g} {by + py:g} L{bx - px:g} {by - py:g} Z" fill="{col}"/>')
    if label:
        s.text(mx, (y1 + cy) / 2 + (-7 if up else 9), label, size=10, tone=tone if tone in ("ng", "ok", "acc", "amber", "pur") else "gray",
               bold=True, halo=True)


def states(P):
    """P = {"title": 위 제목, "states": [{"name": 상태 이름, "sub": 아래 작은 글(선택), "tone": "acc"|"ok"|"ng"|"amber"|"gray"|"pur"}] (2~6개 · 왼쪽 → 오른쪽 한 줄),
            "edges": [{"a": 시작 상태 번호, "b": 끝 상태 번호, "label": 글(10자 안쪽), "tone"}],
            "spans": [{"a": 첫 상태, "b": 끝 상태, "text": 글, "tone": "ok"}](선택 — 상자 아래 띠: 이 구간에서만 가능한 일),
            "note": 맨 아래 한 줄(선택), "label": 그림 이름}  → 664 × 270
    이웃(b = a + 1)은 곧은 화살표 · 앞으로 건너뛰면 위 곡선 · 뒤로 돌아가면 아래 곡선
    상태 이름은 상자 폭 안쪽(상태 4개면 한글 8자 · 6개면 5자) — 넘치면 끝을 «…» 로 줄인다"""
    st = P["states"]
    n = len(st)
    gap = 34
    bw = min(118, (648 - gap * (n - 1)) / n)
    x0 = (664 - (n * bw + (n - 1) * gap)) / 2
    y, h = 70, 48
    xs = [x0 + i * (bw + gap) for i in range(n)]
    s = Svg(664, 270)
    s.text(8, 14, P.get("title", ""), size=12, anchor="start", tone="ink", bold=True)
    for x, t in zip(xs, st):
        tone = t.get("tone", "acc")
        s.box(x, y, bw, h, "", tone=tone, sw=1.6, rx=8)
        s.text(x + bw / 2, y + (18 if t.get("sub") else 24), fit_text(t["name"], 12, bw - 8), size=12, tone=tone, bold=True)
        if t.get("sub"):
            s.text(x + bw / 2, y + 35, fit_text(t["sub"], 10, bw - 8), size=10, tone="gray")
    for e in P.get("edges", []):
        a, b = e["a"], e["b"]
        tone = e.get("tone", "gray")
        if b == a + 1:
            s.arrow(xs[a] + bw + 2, y + h / 2, xs[b] - 2, y + h / 2, tone=tone, sw=1.6, head=7)
            if e.get("label"):
                s.text((xs[a] + bw + xs[b]) / 2, y + h / 2 - 9, e["label"], size=10, tone=tone, bold=True, halo=True)
        else:
            up = b > a
            ya = y if up else y + h
            depth = 14 + 12 * abs(b - a)  # 멀리 건너뛸수록 깊게 — 같은 상자에서 나가는 곡선끼리 겹치지 않게
            _curve_arrow(s, xs[a] + bw / 2 + (10 if up else -10), ya - (2 if up else -2), xs[b] + bw / 2 - (10 if up else -10), ya - (2 if up else -2),
                         up, tone, e.get("label", ""), depth)
    for sp in P.get("spans", []):
        tone = sp.get("tone", "ok")
        xa, xb = xs[sp["a"]] + 4, xs[sp["b"]] + bw - 4
        yb = 222
        s.line(xa, yb, xb, yb, tone=tone, sw=3)
        s.line(xa, yb - 6, xa, yb + 6, tone=tone, sw=2)
        s.line(xb, yb - 6, xb, yb + 6, tone=tone, sw=2)
        s.text((xa + xb) / 2, yb + 18, sp["text"], size=10.5, tone=tone, bold=True)
    if P.get("note"):
        s.text(332, 262, P["note"], size=10.5, tone="gray")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 11. 시각별 막대 + 임계선 — 시각마다 동시에 필요한 수와 한도(보유 · 용량)를 견준다
# ════════════════════════════════════════════════════════════
def time_bars(P):
    """P = {"title": 위 제목, "bars": [{"label": 시각 글("07:00" · 6자 안쪽), "value": 수}] (4~24개),
            "limit": 한도 수(선택 — 빨간 점선), "limit_label": "보유 8대"(그림 오른쪽 여백 · 한글 6자 안쪽), "unit": 막대 위 숫자 뒤 글(선택),
            "note": 맨 아래 한 줄(선택), "label": 그림 이름}  → 664 × 240
    한도를 넘는 막대 = 빨강 · 나머지 = 파랑. 막대가 16개를 넘으면 위 숫자는 한도를 넘는 막대에만, 아래 시각 글은 하나 걸러 하나"""
    bars = P["bars"]
    n = len(bars)
    lim = P.get("limit")
    vmax = max([b["value"] for b in bars] + ([lim] if lim is not None else [])) or 1
    x0, x1, base, top = 40, 590, 190, 44
    colw = (x1 - x0) / n
    bw = max(4, min(30, colw - 6))
    k = (base - top) / vmax
    s = Svg(664, 240)
    s.text(8, 14, P.get("title", ""), size=12, anchor="start", tone="ink", bold=True)
    s.line(x0 - 4, base, x1, base, tone="gray", sw=1)
    crowded = n > 16
    for i, b in enumerate(bars):
        v = b["value"]
        over = lim is not None and v > lim
        col = "#dc2626" if over else "#2563eb"
        cx = x0 + colw * (i + 0.5)
        if v:
            s.box(cx - bw / 2, base - v * k, bw, v * k, "", tone="gray", fill=col, stroke=col, rx=2, sw=1)
        if not crowded or over:
            s.text(cx, base - v * k - 7, f"{v}{P.get('unit', '')}", size=10.5, tone="ng" if over else "ink", bold=True)
        if not crowded or i % 2 == 0:
            s.text(cx, base + 14, b["label"], size=10, tone="gray")
    if lim is not None:
        yl = base - lim * k
        s.line(x0 - 4, yl, x1, yl, tone="ng", sw=1.4, dash=True)
        s.text(x1 + 6, yl, P.get("limit_label", f"한도 {lim}"), size=10.5, tone="ng", bold=True, anchor="start")
    if P.get("note"):
        s.text(332, 228, P["note"], size=10.5, tone="gray")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 12. 같은 번호 두 줄 비교 — 원본 줄(빨강)과 정리한 줄(초록)을 줄바꿈 없이 위아래로
# ════════════════════════════════════════════════════════════
def pair_rows(P):
    """P = {"title": 위 제목, "heads": (위 줄 이름, 아래 줄 이름) 예 ("원본", "정리"), "rows": [{"no": 번호 글(줄 번호 · 키 값), "a": 위 줄, "b": 아래 줄}] (8개 이하),
            "tones": (위 색, 아래 색)(선택 · 기본 ("ng", "ok")), "note": 맨 아래 한 줄(선택), "label"}  → 664 × (34 + 46 × 행 + 4 · note 가 있으면 + 22)
    두 줄은 고정폭 글꼴 한 줄씩 — 긴 줄은 줄바꿈 대신 글자를 작게(가장 긴 줄이 폭에 들게 · 최소 7px)"""
    rows = P["rows"][:8]
    ha, hb = P.get("heads", ("원본", "정리"))
    ta, tb = P.get("tones", ("ng", "ok"))
    cols = {"ng": ("#991b1b", "#fdecec"), "ok": ("#15803d", "#e9f7ee"), "gray": ("#374151", "#f4f6f9"), "acc": ("#1d4ed8", "#eaf1ff")}
    xt = 118
    longest = max([text_w(r["a"], 1) for r in rows] + [text_w(r["b"], 1) for r in rows] + [1])  # 글자 크기 1 일 때 폭
    size = max(7.0, min(11.0, (650 - xt) / (longest * 1.05)))
    H = 34 + 46 * len(rows) + (22 if P.get("note") else 4)
    s = Svg(664, H)
    s.text(8, 14, P.get("title", ""), size=12, anchor="start", tone="ink", bold=True)
    for i, r in enumerate(rows):
        y = 34 + i * 46
        s.box(6, y, 652, 40, "", tone="gray", fill="#ffffff", sw=1, rx=5)
        s.text(14, y + 21, fit_text(r["no"], 11, 56), size=11, anchor="start", tone="ink", bold=True)
        for j, (txt, head, tone) in enumerate(((r["a"], ha, ta), (r["b"], hb, tb))):
            fg, bg = cols.get(tone, cols["gray"])
            yy = y + 5 + j * 16
            s.parts.append(f'<rect x="{xt - 4:g}" y="{yy:g}" width="{656 - xt:g}" height="14" rx="2" fill="{bg}"/>')
            s.text(xt - 8, yy + 7, head, size=9.5, anchor="end", tone=tone if tone in ("ng", "ok", "acc") else "gray", bold=True)
            s.parts.append(f'<text x="{xt:g}" y="{yy + 7:g}" dominant-baseline="central" font-family="Consolas,D2Coding,Noto Sans Mono,monospace" '
                           f'font-size="{size:.1f}" fill="{fg}" xml:space="preserve">{esc(str(txt))}</text>')
    if P.get("note"):
        s.text(332, H - 8, P["note"], size=10.5, tone="gray")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 13. 측정 화살표 — 판 위 칸마다 잰 어긋남(벡터)을 화살표로(분석 틀 stat_model · 재생기 "kind": "quiver" · 순서 지도 "kind": "arrows")
# ════════════════════════════════════════════════════════════
def _arrow_v(s, x1, y1, x2, y2, col, sw=1.4):
    """작은 화살표 — 머리 = 채운 세모(길이의 45% · 5px 까지) · 아주 짧으면 점 하나"""
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 0.8:
        s.parts.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="1.3" fill="{col}"/>')
        return
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    h = min(5.0, L * 0.45)
    bx, by = x2 - ux * h, y2 - uy * h
    s.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{col}" stroke-width="{sw:g}"/>')
    s.parts.append(f'<path d="M{x2:.1f} {y2:.1f} L{bx - uy * h * 0.55:.1f} {by + ux * h * 0.55:.1f} L{bx + uy * h * 0.55:.1f} {by - ux * h * 0.55:.1f} Z" fill="{col}"/>')


def _plate(s, pl, box):
    """판 테두리(반지름이 있으면 원) → 좌표 변환 f(y, x)"""
    R = pl.get("radius")
    if R:
        bounds = (-R, R, -R, R)
    else:
        xs, ys = pl["x"], pl["y"]
        dy, dx = (max(ys) - min(ys)) or 1, (max(xs) - min(xs)) or 1
        bounds = (min(ys) - dy * 0.08, max(ys) + dy * 0.08, min(xs) - dx * 0.08, max(xs) + dx * 0.08)
    proj = fit_box(bounds=bounds, box=box, geo=False)
    if R:
        cx, cy = proj(0, 0)
        s.parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{proj(0, R)[0] - cx:.1f}" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>')
    return proj


def _arrows(s, pl, proj, dx, dy, col, limit=None):
    """칸마다 점 + 화살표(값 × scale px · 위쪽 = +y) — limit 보다 긴 화살표는 빨강"""
    sc = pl["scale"]
    for x, y, a, b in zip(pl["x"], pl["y"], dx, dy):
        px, py = proj(y, x)
        s.parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="1.6" fill="#6b7280"/>')
        over = limit is not None and math.hypot(a, b) > limit
        _arrow_v(s, px, py, px + a * sc, py - b * sc, "#dc2626" if over else col, 1.9 if over else 1.4)


def quiver_map(P, st):
    """P = 재생기 칸(kind "quiver") — "plate": {"x": […], "y": […](칸 좌표), "radius": 판 반지름(선택 — 원 테두리), "scale": 값 1 당 px, "bar": 눈금 화살표 값, "unit": 단위 글}
            · "right_title" · "frame_title"(단계 "head" 가 없을 때 위 제목)
       st = 단계 {"dx": […], "dy": […](칸마다 · plate 와 같은 순서), "head", "lines": [(글, 색)](오른쪽 목록 한 줄씩), "limit": 이보다 긴 화살표 빨강(선택)}  → 664 × 270
    화살표 길이 = 값 × scale — 단계마다 같은 배율이라 성분을 뺄수록 짧아진다. 왼쪽 아래 = 눈금 화살표"""
    s = Svg(664, 270)
    pl = P["plate"]
    s.text(8, 14, fit_text(st.get("head", P.get("frame_title", "")), 12, 436), size=12, anchor="start", tone="ink", bold=True)
    s.box(6, 28, 438, 234, "", tone="gray", fill="#f8fafc", sw=1, rx=6)
    proj = _plate(s, pl, (14, 34, 422, 206))
    _arrows(s, pl, proj, st["dx"], st["dy"], "#2563eb", st.get("limit"))
    bar = pl.get("bar")
    if bar:
        _arrow_v(s, 18, 251, 18 + bar * pl["scale"], 251, "#374151", 1.6)
        s.text(24 + bar * pl["scale"], 251, f"{bar} {pl.get('unit', '')}", size=10, anchor="start", tone="gray")
    s.text(456, 14, P.get("right_title", ""), size=12, anchor="start", tone="ink", bold=True)
    for i, (t, col) in enumerate(st.get("lines", ())):
        s.text(456, 40 + i * 22, fit_text(t, 10.5, 204), size=10.5, anchor="start", tone=col)
    return s.render(st.get("head", P.get("frame_title", "")))


def arrows_pair(P):
    """P = {"kind": "arrows", "x", "y"(칸 좌표), "radius"(선택), "scale"(값 1 당 px), "unit",
            "good": {"dx", "dy", "label"}(초록 — 가장 작은 쪽), "bad": {"dx", "dy", "label"}(빨강 — 가장 큰 쪽), "label"}  → 300 × 214
    같은 판에서 후보 둘을 각각 뺀 화살표를 나란히 — 순서 지도(orders_map) 자리에 들어간다"""
    s = Svg(300, 214)
    s.box(2, 4, 296, 206, "", tone="gray", fill="#f8fafc", sw=1, rx=6)
    for j, (key, col, tone) in enumerate((("good", "#16a34a", "ok"), ("bad", "#dc2626", "ng"))):
        x0 = 8 + j * 146
        proj = _plate(s, P, (x0, 12, 138, 150))
        _arrows(s, P, proj, P[key]["dx"], P[key]["dy"], col)
        s.line(x0 + 4, 180, x0 + 24, 180, tone=tone, sw=3)
        s.text(x0 + 28, 180, fit_text(P[key]["label"], 10, 110), size=10, tone=tone, bold=True, anchor="start")
    s.text(150, 199, f"화살표 = 빼고 남은 값(단위 {P.get('unit', '')})", size=10, tone="gray")
    return s.render(P.get("label", ""))


# ════════════════════════════════════════════════════════════
# 14. 관리도 — 시간순으로 찍은 값 + 가운데 · 위 · 아래 한계(재생기 이어 붙이기 "kind": "chart")
# ════════════════════════════════════════════════════════════
def control_chart(C, k, title):
    """C = 관리도 칸 — "points": [(x 위치, 값, 줄 번호, 한계 밖?)], "series": [줄 이름], "steps": [[이 단계에 찍는 점 번호 …]],
            "center" · "ucl" · "lcl"(가운데 · 위 한계 · 아래 한계), "unit", "axis": (x 처음, x 끝), "ticks": [(x, 글)],
            "words": {"line": "{mark}{name}  이탈 {out}/{n}", "ucl": "위 한계 {v}", "lcl": "아래 한계 {v}", "center": "평균 {v}"}
       k = 단계 번호(0 부터 · len(steps) = 다 찍은 결과 — 강조 없음) · title = 위 제목  → 664 × 270
    점 색 = 줄(figs.COLORS) · 이번 단계 점은 크게 · 한계 밖 = 빨간 고리 · 오른쪽 목록 = 줄마다 지금까지의 이탈 수"""
    s = Svg(664, 270)
    pts, steps = C["points"], C["steps"]
    shown = {i for st in steps[:k + 1] for i in st}
    cur = set(steps[k]) if k < len(steps) else set()
    Wd = C.get("words", {})
    x0, x1, y0, y1 = 58, 500, 40, 228
    vals = [p[1] for p in pts] + [C["ucl"], C["lcl"]]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    a0, a1 = C["axis"]

    def fx(i):
        return x0 + (i - a0) / max(1e-9, a1 - a0) * (x1 - x0)

    def fy(v):
        return y1 - (v - lo) / (hi - lo) * (y1 - y0)

    def g(v):
        return f"{v:.3g}"

    s.text(8, 14, fit_text(title, 12, 500), size=12, anchor="start", tone="ink", bold=True)
    s.box(x0 - 8, y0 - 10, x1 - x0 + 16, y1 - y0 + 20, "", tone="gray", fill="#f8fafc", sw=1, rx=4)
    for key, v, tone in (("center", C["center"], "gray"), ("ucl", C["ucl"], "ng"), ("lcl", C["lcl"], "ng")):
        s.line(x0 - 4, fy(v), x1 + 4, fy(v), tone=tone, sw=1.3, dash=True)
        s.text(x0 - 2, fy(v) + (9 if key == "lcl" else -7), Wd.get(key, "{v}").format(v=g(v)), size=9.5, anchor="start", tone=tone, bold=key != "center", halo=True)
    for i, lab in C.get("ticks", ()):
        s.line(fx(i), y1 + 10, fx(i), y1 + 14, tone="gray", sw=1)
        s.text(fx(i), y1 + 24, lab, size=9.5, tone="gray")
    names = C["series"]
    for si in range(len(names)):
        seq = sorted((pts[i][0], pts[i][1]) for i in shown if pts[i][2] == si)
        if len(seq) > 1:
            d = "M" + " L".join(f"{fx(a):.1f} {fy(v):.1f}" for a, v in seq)
            s.parts.append(f'<path d="{d}" stroke="{COLORS[si % len(COLORS)]}" stroke-width="1" fill="none" opacity="0.45"/>')
    for i in sorted(shown):
        a, v, si, out = pts[i]
        x, y = fx(a), fy(v)
        s.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{4.2 if i in cur else 2.8:g}" fill="{COLORS[si % len(COLORS)]}" stroke="#ffffff" stroke-width="0.8"/>')
        if out:
            s.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="none" stroke="#dc2626" stroke-width="2"/>')
    s.text(516, 34, "줄별 이탈", size=11, anchor="start", tone="ink", bold=True)
    cur_s = {pts[i][2] for i in cur}
    for si, name in enumerate(names):
        n = sum(1 for i in shown if pts[i][2] == si)
        o = sum(1 for i in shown if pts[i][2] == si and pts[i][3])
        line = Wd.get("line", "{mark}{name}  이탈 {out}/{n}").format(mark="▶ " if si in cur_s else "", name=name, out=o, n=n)
        s.text(516, 56 + si * 20, fit_text(line, 10.5, 144), size=10.5, anchor="start", tone=COLORS[si % len(COLORS)], bold=o > 0)
    return s.render(title)
