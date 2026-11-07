# -*- coding: utf-8 -*-
"""task10 책의 그림(SVG) — 값은 전부 data.facts() · data.cache() 에서 온다. 크기는 단계 · 조합마다 같게."""
import math

from book.engine import Svg

from . import data as D

BUS_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#b45309", "#0f766e", "#db2777", "#4b5563", "#0891b2", "#65a30d", "#ea580c"]
SHIFT_KR = {"D": "주간 D", "G": "일근 G", "S": "오후 S", "N": "야간 N"}


def _sec(x):
    if x < 1:
        return f"{x:.2f}초"
    if x < 90:
        return f"{x:.1f}초" if x < 10 else f"{x:.0f}초"
    if x < 7200:
        return f"약 {x / 60:.0f}분"
    if x < 172800:
        return f"약 {x / 3600:.0f}시간"
    return f"약 {x / 86400:.0f}일"


# ════════════════════════════════════════════════════════════
# 펼침 1 — 큰 그림 + 평일 하루 파동 띠
# ════════════════════════════════════════════════════════════
def overview_svg(F, date="2026-11-10"):
    s = Svg(664, 404)
    s.box(6, 22, 96, 62, "CSV 7개\n사원 · 근무표\n거점 · 차량 …", tone="gray", size=11, bold=True, fill="#ffffff")
    s.arrow(104, 53, 136, 53, tone="gray", sw=1.8, head=7)
    s.box(138, 22, 116, 62, "검증 · 적용\n전부 아니면 전무", tone="amber", size=11, bold=True)
    s.arrow(256, 53, 288, 53, tone="gray", sw=1.8, head=7)
    s.box(290, 22, 122, 62, "계획 생성\n파동 8개 × 14일", tone="acc", size=11, bold=True)
    s.arrow(414, 40, 442, 30, tone="gray", sw=1.8, head=7)
    s.arrow(414, 66, 442, 76, tone="gray", sw=1.8, head=7)
    s.box(444, 8, 212, 42, "운영자 화면\n날짜 → 버스별 노선 · 탑승자", tone="ok", size=11, bold=True)
    s.box(444, 58, 212, 42, "사원 화면\n사번 → 내 버스 · 타는 곳 · 시각", tone="ok", size=11, bold=True)
    # 분류 색(1장의 색 표시와 같다)
    s.text(196, 96, "파이프라인", size=10.5, tone="amber", bold=True)
    s.text(351, 96, "알고리즘", size=10.5, tone="acc", bold=True)
    s.text(550, 112, "화면", size=10.5, tone="ok", bold=True)
    s.parts.append('<g transform="translate(0,12)">')
    # 파동 띠
    s.text(8, 124, f"평일 하루({date[5:7]}/{date[8:10]}) 파동 8개 — 시각순 · 사원 수", size=12, tone="ink", anchor="start", bold=True)
    leg_x = 470
    s.box(leg_x, 114, 12, 12, "", tone="acc", fill="#2563eb", rx=2)
    s.text(leg_x + 17, 120, "이천(ICN)", size=11, anchor="start", tone="gray")
    s.box(leg_x + 82, 114, 12, 12, "", tone="teal", fill="#0f766e", rx=2)
    s.text(leg_x + 99, 120, "청주(CJU)", size=11, anchor="start", tone="gray")
    base, k = 300, 0.40
    colw = 80
    for i, (sh, direction, t, dd) in enumerate(D.WAVES):
        x0 = 12 + i * colw
        dstr = date if dd == 0 else (__import__("datetime").date.fromisoformat(date) - __import__("datetime").timedelta(days=1)).isoformat()
        ni = F["cnt"][(dstr, "ICN", sh)]
        nc = F["cnt"][(dstr, "CJU", sh)]
        tone_dir = "#2563eb" if direction == "출근" else "#7c3aed"
        for j, (v, col) in enumerate(((ni, "#2563eb"), (nc, "#0f766e"))):
            h = v * k
            bx = x0 + 8 + j * 28
            s.box(bx, base - h, 24, h, "", tone="gray", fill=col, stroke=col, rx=2, sw=1)
            s.text(bx + 12, base - h - 8, str(v), size=11, tone="ink", bold=True)
        s.line(x0 + 2, base, x0 + colw - 6, base, tone="gray", sw=1)
        s.text(x0 + 38, base + 14, D.hm(t), size=12, tone="ink", bold=True)
        s.text(x0 + 38, base + 30, f"{SHIFT_KR[sh].split()[0]} {direction}", size=11, tone=tone_dir, bold=True)
        s.text(x0 + 38, base + 45, "(전날 근무)" if dd == -1 else "", size=10, tone="ng")
    s.text(332, 372, "05:40 에 사업장에 닿은 버스가 30분 뒤 06:10 퇴근에 다시 쓰일 수 있다 — 버스 대수 계산이 이 간격에서 출발한다", size=10.5, tone="gray")
    s.parts.append("</g>")
    return s.render("하루 파동 8개")


# ════════════════════════════════════════════════════════════
# 펼침 2 — 근무표 파일의 이어 붙인 구조 + 11/17 청주 일근 인원
# ════════════════════════════════════════════════════════════
def band_svg(F):
    s = Svg(664, 262)
    total = F["dup_last"] - 1  # 2~dup_last 줄
    x0, wtot = 12, 640
    segs = [("정상", 2, F["unreg_first"] - 1, "#c7d2e6"), ("명단 밖 3명", F["unreg_first"], F["unreg_last"], "#f59e0b"),
            ("청주 2주차 블록", F["slash_first"], F["slash_last"], "#dc2626"), ("중복 행", F["dup_first"], F["dup_last"], "#7c3aed")]
    s.text(8, 14, "schedule.csv 를 줄 번호 구간으로 나누면", size=12, anchor="start", tone="ink", bold=True)
    x = x0
    pos = {}
    for name, a, b, col in segs:
        wpx = max(7, wtot * (b - a + 1) / total)
        pos[name] = (x, wpx)
        s.box(x, 44, wpx, 34, "", tone="gray", fill=col, stroke="#ffffff", rx=0, sw=1)
        x += wpx
    # 설명선
    ax, aw = pos["정상"]
    s.text(ax + aw / 2, 61, f"2~{F['unreg_first'] - 1:,}줄 — 정상 형식", size=11, tone="ink", bold=True)
    bx, bw = pos["청주 2주차 블록"]
    s.text(bx + bw / 2, 61, "블록", size=11, tone="#ffffff", bold=True)
    ux, uw = pos["명단 밖 3명"]
    s.arrow(ux + uw / 2, 120, ux + uw / 2, 80, tone="amber", sw=1.4, head=6)
    s.text(ux + uw / 2 - 4, 132, f"{F['unreg_first']:,}~{F['unreg_last']:,}줄\n명단에 없는 사번 {F['n_unreg']}명({F['unreg_rows']}행)", size=10.5, tone="amber", bold=True, anchor="end")
    s.arrow(bx + bw / 2, 28, bx + bw / 2, 42, tone="ng", sw=1.4, head=6)
    s.text(bx + bw / 2 - 4, 22, f"{F['slash_first']:,}~{F['slash_last']:,}줄 {F['slash_rows']:,}행 — 날짜 / · 사번 앞자리 0 소실", size=10.5, tone="ng", bold=True, anchor="end")
    dx, dw = pos["중복 행"]
    s.arrow(dx + dw / 2, 120, dx + dw / 2, 80, tone="pur", sw=1.4, head=6)
    s.text(dx + dw + 2, 132, f"{F['dup_first']:,}~{F['dup_last']:,}줄\n(사번, 날짜) 중복 {F['dup_rows']}행", size=10.5, tone="pur", bold=True, anchor="end")
    # 11/17 청주 일근
    s.text(8, 166, "11/17 청주 일근 출근자 수", size=12, anchor="start", tone="ink", bold=True)
    good, naive = F["cju_g_1117"], F["cju_g_1117_naive"]
    sc = 380 / max(good, 1)
    s.text(8, 196, "정리한 뒤", size=11.5, anchor="start", tone="ok", bold=True)
    s.box(96, 184, good * sc, 24, "", tone="ok", fill="#16a34a", stroke="#16a34a", rx=2)
    s.text(96 + good * sc + 8, 196, f"{good}명", size=12, anchor="start", tone="ok", bold=True)
    s.text(8, 232, "그냥 읽으면", size=11.5, anchor="start", tone="ng", bold=True)
    s.box(96, 220, naive * sc, 24, "", tone="ng", fill="#dc2626", stroke="#dc2626", rx=2)
    s.text(96 + naive * sc + 8, 232, f"{naive}명", size=12, anchor="start", tone="ng", bold=True)
    s.text(660, 232, "에러 없이 이 숫자가 나온다", size=11, anchor="end", tone="ng")
    return s.render("근무표 파일의 이어 붙인 구조")


# ════════════════════════════════════════════════════════════
# 펼침 4 — 시스템 층
# ════════════════════════════════════════════════════════════
def layers_svg():
    s = Svg(664, 400)
    s.box(8, 10, 150, 44, "운영자 화면", tone="ok", size=12, bold=True)
    s.box(170, 10, 150, 44, "사원 화면", tone="ok", size=12, bold=True)
    s.arrow(83, 56, 83, 96, tone="gray", sw=1.6, head=7)
    s.arrow(245, 56, 245, 96, tone="gray", sw=1.6, head=7)
    s.box(8, 98, 312, 48, "조회 API\n완성된 «현재 버전» 만 읽는다", tone="acc", size=11.5, bold=True)
    s.arrow(164, 148, 164, 184, tone="gray", sw=1.6, head=7)
    s.box(8, 186, 312, 110, "", tone="gray", fill="#f8fafc", sw=1.8)
    s.text(164, 202, "저장소(파일 DB)", size=12, tone="ink", bold=True)
    for i, t in enumerate(["근무표 · 사원 · 거점 · 차량", "계획 버전(입력 · 설정 · 시드 함께)", "설정(도착 몇 분 전 · 최대 탑승 인원)", "작업 상태(대기 · 계산 중 · 끝)"]):
        s.text(26, 226 + i * 18, t, size=11, tone="gray", anchor="start")
    s.box(360, 10, 296, 44, "CSV 7개 올리기", tone="gray", size=12, bold=True, fill="#ffffff")
    s.arrow(508, 56, 508, 76, tone="gray", sw=1.6, head=7)
    s.box(360, 78, 296, 52, "검증 리포트\n통과분은 임시 영역에 먼저 넣는다", tone="amber", size=11.5, bold=True)
    s.arrow(508, 132, 508, 152, tone="gray", sw=1.6, head=7)
    s.box(360, 154, 296, 44, "한 번에 교체 — 전부 아니면 전무", tone="ok", size=11.5, bold=True)
    s.arrow(358, 176, 322, 232, tone="ok", sw=1.8, head=7, label="적용", lx=336, ly=196)
    s.box(360, 250, 296, 140, "", tone="acc", fill="#eaf1ff", sw=1.8)
    s.text(508, 268, "계획 생성 작업(별도 실행)", size=12, tone="acc", bold=True)
    for i, t in enumerate(["① 파동마다 풀이(경로 만들기)", "② 트립을 버스에 이어 붙이기", "③ 검증기로 숫자 확인", "④ 새 버전 저장 → 현재 버전 교체"]):
        s.text(380, 292 + i * 20, t, size=11, tone="ink", anchor="start")
    s.text(508, 380, "계산은 여기서 돌린다 — 화면 요청 안에서 기다리지 않는다", size=10, tone="acc")
    s.arrow(358, 330, 322, 290, tone="acc", sw=1.8, head=7, label="저장", lx=334, ly=326)
    s.arrow(508, 248, 508, 232, tone="acc", sw=0, head=0)
    return s.render("시스템 층")


# ════════════════════════════════════════════════════════════
# 펼침 5 — 완전탐색이 막히는 장면 · 지도 · 시간표
# ════════════════════════════════════════════════════════════
def brute_svg(C):
    brute = {b["n"]: b for b in C["brute"]}
    sec10 = brute[10]["sec"]
    items = []
    for n in (6, 7, 8, 9, 10, 12, 15):
        perms = math.factorial(n)
        meas = n in brute
        sec = brute[n]["sec"] if meas else sec10 * perms / math.factorial(10)
        items.append((n, perms, sec, meas))
    s = Svg(664, 252)
    s.text(8, 14, "거점 n 개를 도는 순서를 전부 세어 가장 짧은 것을 고르면", size=12, anchor="start", tone="ink", bold=True)
    base, hmax = 190, 130
    mx = math.log10(items[-1][1])
    for i, (n, perms, sec, meas) in enumerate(items):
        x = 28 + i * 90
        h = max(4, hmax * math.log10(perms) / mx)
        col = "#2563eb" if meas else "#b45309"
        s.box(x, base - h, 54, h, "", tone="gray", fill=col, stroke=col, rx=3, dash=not meas, sw=1.5)
        s.text(x + 27, base - h - 22, f"{perms:,}가지", size=10.5, tone="ink", bold=True)
        s.text(x + 27, base - h - 9, _sec(sec), size=11, tone="ng" if sec > 5 else "gray", bold=True)
        s.text(x + 27, base + 14, f"거점 {n}개", size=11.5, tone="ink", bold=True)
        s.text(x + 27, base + 30, "실측" if meas else "추정", size=10.5, tone="gray" if meas else "amber")
    s.line(14, base, 652, base, tone="gray", sw=1)
    s.text(332, 238, "막대 높이는 경우의 수의 자릿수(로그) — 거점 15개면 같은 방식으로 38일이 걸린다", size=10.5, tone="gray")
    return s.render("정류 순서 완전탐색")


def _proj(F):
    lats = [h["lat"] for h in F["hubs"].values() if h["lat"] and h["lat"] > 37]
    lons = [h["lon"] for h in F["hubs"].values() if h["lon"] and h["lon"] > 126.9 and h["lat"] > 37]
    lat0, lat1 = min(lats + [F["site"]["ICN"][0]]) - 0.012, max(lats) + 0.012
    lon0, lon1 = min(lons) - 0.025, max(lons) + 0.03
    k = math.cos(math.radians((lat0 + lat1) / 2))
    wkm, hkm = (lon1 - lon0) * 111.32 * k, (lat1 - lat0) * 110.57
    W, H = 430, 222
    sc = min(W / wkm, H / hkm)
    ox = 8 + (W - wkm * sc) / 2
    oy = 34 + (H - hkm * sc) / 2

    def f(lat, lon):
        return ox + (lon - lon0) * 111.32 * k * sc, oy + (lat1 - lat) * 110.57 * sc

    return f


def map_svg(F, buses, title, right_title, right_lines, cur=None, fills=None, bad_lines=()):
    """이천 권역 지도 + 오른쪽 목록.
    buses = [[(거점이름, 인원), …] …] — 출근 순서(먼 곳 → 사업장). cur = 강조할 버스 번호. fills = 버스별 지금까지 탄 인원(없으면 buses 합)
    right_lines = [(글자, 색)] — 오른쪽 목록 한 줄씩"""
    s = Svg(664, 270)
    proj = _proj(F)
    byname = {h["name"]: h for h in F["hubs"].values() if h["lat"]}
    s.text(8, 14, title, size=12, anchor="start", tone="ink", bold=True)
    s.box(6, 28, 438, 234, "", tone="gray", fill="#f8fafc", sw=1, rx=6)
    cx, cy = proj(*F["site"]["ICN"])
    # 거점 인원
    cnt = F["wave_hub_counts"]
    for name, c in cnt.items():
        h = byname[name]
        x, y = proj(h["lat"], h["lon"])
        r = 3 + math.sqrt(c) * 0.9
        s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')
    # 경로
    for bi, b in enumerate(buses):
        if not b:
            continue
        col = BUS_COLORS[bi % len(BUS_COLORS)]
        seq = []
        for name, _ in b:
            if not seq or seq[-1] != name:
                seq.append(name)
        pts = [proj(byname[n]["lat"], byname[n]["lon"]) for n in seq] + [(cx, cy)]
        on = cur is None or bi == cur
        d = "M" + " L".join(f"{x:g} {y:g}" for x, y in pts)
        s.path(d, tone=col, sw=3.2 if on else 1.6, dash=False)
        for (x, y), n in zip(pts[:-1], seq):
            s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="4.5" fill="{col}" stroke="#ffffff" stroke-width="1.2"/>')
    # 거점 이름
    for name, c in cnt.items():
        h = byname[name]
        x, y = proj(h["lat"], h["lon"])
        dy = -11 if name not in ("사당역", "서현역", "기흥역") else 12
        s.text(x, y + dy, f"{D.HUB_SHORT[name]} {c}", size=10, tone="ink", bold=True, halo=True)
    s.parts.append(f'<rect x="{cx - 6:g}" y="{cy - 6:g}" width="12" height="12" fill="#111827" transform="rotate(45 {cx:g} {cy:g})"/>')
    s.text(cx - 12, cy + 3, "이천캠퍼스", size=10.5, tone="ink", bold=True, halo=True, anchor="end")
    # 오른쪽
    s.text(456, 14, right_title, size=12, anchor="start", tone="ink", bold=True)
    for i, (t, col) in enumerate(right_lines):
        y = 38 + i * 28
        s.text(456, y, t, size=10, anchor="start", tone=col)
    return s.render(title)


def bus_bars_svg_lines(F, step_idx):
    """방안 A 단계 i 까지 버스별 누적 인원 → 오른쪽 목록 줄"""
    steps = F["A1_steps"]
    fills = [0] * len(F["A1_buses"])
    for st in steps[:step_idx + 1]:
        fills[st["bus"]] = st["cum"]
    return fills


# ════════════════════════════════════════════════════════════
# 펼침 5 — 하루 버스 시간표(조건 슬라이더 그림)
# ════════════════════════════════════════════════════════════
def gantt_svg(frame, have, title):
    """frame = cache fleet frame(trips · chains) — chains 는 시간 역순으로 저장돼 있다"""
    s = Svg(664, 226)
    t0, t1 = 2 * 60, 24 * 60
    x0, x1 = 64, 634
    RH = 16
    X = lambda m: x0 + (m - t0) * (x1 - x0) / (t1 - t0)  # noqa: E731
    s.text(8, 12, title, size=12, anchor="start", tone="ink", bold=True)
    s.box(430, 3, 11, 11, "", tone="acc", fill="#2563eb", rx=2)
    s.text(446, 9, "출근", size=10.5, anchor="start", tone="gray")
    s.box(480, 3, 11, 11, "", tone="pur", fill="#7c3aed", rx=2)
    s.text(496, 9, "퇴근", size=10.5, anchor="start", tone="gray")
    s.box(530, 3, 11, 11, "", tone="ng", fill="#dc2626", rx=2)
    s.text(546, 9, "보유 초과 버스", size=10.5, anchor="start", tone="ng")
    for h in range(3, 25, 3):
        x = X(h * 60)
        s.line(x, 24, x, 24 + 11 * RH + 2, tone="#e5e7eb", sw=1)
        s.text(x, 24 + 11 * RH + 14, f"{h % 24:02d}:00", size=10, tone="gray")
    trips = frame["trips"]
    chains = []
    for c in frame["chains"]:
        chains.append(sorted(c, key=lambda i: trips[i][1]))
    chains.sort(key=lambda c: trips[c[0]][1])
    for ri, c in enumerate(chains):
        y = 25 + ri * RH
        over = ri >= have
        s.text(8, y + 7, f"버스 {ri + 1}", size=10.5, anchor="start", tone="ng" if over else "gray", bold=over)
        s.line(x0, y + 7, x1, y + 7, tone="#f1f5f9", sw=1)
        for i in c:
            name, a, b, n, L = trips[i]
            col = "#dc2626" if over else ("#2563eb" if "출근" in name else "#7c3aed")
            xa, xb = X(max(a, t0)), X(min(b, t1))
            s.box(xa, y + 1, max(3, xb - xa), 12, "", tone="gray", fill=col, stroke=col, rx=2, sw=1)
    return s.render(title)


def chain_strip_svg():
    s = Svg(664, 84)
    s.box(6, 14, 170, 56, "방안이 만든\n트립 목록\n(경로 · 시작 · 끝 시각)", tone="gray", size=11, bold=True, fill="#ffffff")
    s.arrow(178, 42, 214, 42, tone="gray", sw=1.8, head=7)
    s.box(216, 14, 232, 56, "버스에 이어 붙이기\n앞 트립이 끝난 자리에서 다음 트립\n시작 시각에 닿으면 같은 버스", tone="acc", size=11, bold=True)
    s.arrow(450, 42, 486, 42, tone="gray", sw=1.8, head=7)
    s.box(488, 14, 168, 56, "검증기\n전원 1회 · 정원 · 도착 시각\n보유 대수 이하", tone="ok", size=11, bold=True)
    return s.render("방안과 무관한 공통 후속 단계")


# ════════════════════════════════════════════════════════════
# 개편판(v3) 그림
# ════════════════════════════════════════════════════════════
def map_svg2(F, buses, title, right_title, right_lines, hl=(), gone=()):
    """이천 권역 지도 — 버스 여럿을 함께 강조(hl). gone = [(버스, 거점)] 이번에 빠진 정류(빨간 ×)
    buses = [[(거점, 인원)…]] 출근 순서(먼 곳 → 사업장). 크기는 map_svg 와 같다(664 × 270)"""
    s = Svg(664, 270)
    proj = _proj(F)
    byname = {h["name"]: h for h in F["hubs"].values() if h["lat"]}
    s.text(8, 14, title, size=12, anchor="start", tone="ink", bold=True)
    s.box(6, 28, 438, 234, "", tone="gray", fill="#f8fafc", sw=1, rx=6)
    cx, cy = proj(*F["site"]["ICN"])
    cnt = F["wave_hub_counts"]
    for name, c in cnt.items():
        h = byname[name]
        x, y = proj(h["lat"], h["lon"])
        r = 3 + math.sqrt(c) * 0.9
        s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="#e5e7eb" stroke="#9ca3af" stroke-width="1"/>')
    hl = set(hl)
    order = [b for b in range(len(buses)) if b not in hl] + [b for b in range(len(buses)) if b in hl]
    for bi in order:
        b = buses[bi]
        if not b:
            continue
        col = BUS_COLORS[bi % len(BUS_COLORS)]
        on = not hl or bi in hl
        pts = [proj(byname[n]["lat"], byname[n]["lon"]) for n, _ in b] + [(cx, cy)]
        d = "M" + " L".join(f"{x:g} {y:g}" for x, y in pts)
        s.parts.append(f'<path d="{d}" stroke="{col}" stroke-width="{3.4 if on else 1.4:g}" fill="none" opacity="{1 if on else 0.35:g}"/>')
        for (x, y) in pts[:-1]:
            s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="{4.5 if on else 3:g}" fill="{col}" stroke="#ffffff" stroke-width="1.2" opacity="{1 if on else 0.4:g}"/>')
    for name, c in cnt.items():
        h = byname[name]
        x, y = proj(h["lat"], h["lon"])
        dy = -11 if name not in ("사당역", "서현역", "기흥역") else 12
        s.text(x, y + dy, f"{D.HUB_SHORT[name]} {c}", size=10, tone="ink", bold=True, halo=True)
    for _, name in gone:
        h = byname[name]
        x, y = proj(h["lat"], h["lon"])
        s.parts.append(f'<path d="M{x - 7:g} {y - 7:g} L{x + 7:g} {y + 7:g} M{x + 7:g} {y - 7:g} L{x - 7:g} {y + 7:g}" stroke="#dc2626" stroke-width="2.6"/>')
    s.parts.append(f'<rect x="{cx - 6:g}" y="{cy - 6:g}" width="12" height="12" fill="#111827" transform="rotate(45 {cx:g} {cy:g})"/>')
    s.text(cx - 12, cy + 3, "이천캠퍼스", size=10.5, tone="ink", bold=True, halo=True, anchor="end")
    s.text(456, 14, right_title, size=12, anchor="start", tone="ink", bold=True)
    for i, (t, col) in enumerate(right_lines):
        s.text(456, 38 + i * 28, t, size=10, anchor="start", tone=col)
    return s.render(title)


def orders_map_svg(F, best, worst):
    """거점 세 곳 — 가장 짧은 순서(초록 실선)와 가장 긴 순서(빨강 점선)"""
    s = Svg(300, 214)
    byname = {h["name"]: h for h in F["hubs"].values() if h["lat"]}
    names = sorted(set(best[0]) | set(worst[0]))
    lats = [byname[n]["lat"] for n in names] + [F["site"]["ICN"][0]]
    lons = [byname[n]["lon"] for n in names] + [F["site"]["ICN"][1]]
    lat0, lat1, lon0, lon1 = min(lats), max(lats), min(lons), max(lons)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    W, H = 240, 140
    sc = min(W / ((lon1 - lon0) * k + 1e-9), H / ((lat1 - lat0) + 1e-9))

    def P(lat, lon):
        return 30 + (lon - lon0) * k * sc, 30 + (lat1 - lat) * sc

    s.box(2, 4, 296, 206, "", tone="gray", fill="#f8fafc", sw=1, rx=6)
    for order, col, dash, sw in ((worst[0], "#dc2626", True, 2.0), (best[0], "#16a34a", False, 3.2)):
        pts = [P(byname[n]["lat"], byname[n]["lon"]) for n in order] + [P(*F["site"]["ICN"])]
        d = "M" + " L".join(f"{x:g} {y:g}" for x, y in pts)
        da = ' stroke-dasharray="6 4"' if dash else ""
        s.parts.append(f'<path d="{d}" stroke="{col}" stroke-width="{sw:g}" fill="none"{da}/>')
    for n in names:
        x, y = P(byname[n]["lat"], byname[n]["lon"])
        s.parts.append(f'<circle cx="{x:g}" cy="{y:g}" r="5" fill="#1f2328"/>')
        s.text(x + 8, y - 9, D.HUB_SHORT[n], size=11, tone="ink", bold=True, halo=True, anchor="start")
    cx, cy = P(*F["site"]["ICN"])
    s.parts.append(f'<rect x="{cx - 6:g}" y="{cy - 6:g}" width="12" height="12" fill="#111827" transform="rotate(45 {cx:g} {cy:g})"/>')
    s.text(cx - 10, cy + 13, "이천캠퍼스", size=10.5, tone="ink", bold=True, halo=True, anchor="end")
    s.line(14, 196, 38, 196, tone="ok", sw=3)
    s.text(42, 196, f"가장 짧다 {best[1]:.1f}km", size=10.5, tone="ok", bold=True, anchor="start")
    s.line(158, 196, 182, 196, tone="ng", sw=2, dash=True)
    s.text(186, 196, f"가장 길다 {worst[1]:.1f}km", size=10.5, tone="ng", bold=True, anchor="start")
    return s.render("거점 세 곳의 순서")


def _place(n):
    if n in ("ICN", "CJU"):
        return "캠퍼스"
    if n in ("이천터미널", "이천기숙사", "청주터미널", "청주기숙사"):
        return n  # «이천» 만 쓰면 이천캠퍼스와 헷갈린다
    return D.HUB_SHORT.get(n, n)


_CH_LOC = {}


def ch_loc(name):
    if not _CH_LOC:
        _CH_LOC.update({k: tuple(v) for k, v in D.cache3()["loc"].items()})
    return _CH_LOC[name]


def chain_frame(ch, k, have, title):
    """트립 붙이기 k 단계까지 — 버스마다 한 줄(시각 축 03:30~08:30) + 오른쪽에 «지금 그 버스가 있는 곳»"""
    trips = ch["trips"]
    steps = ch["steps"]
    st = steps[min(k, len(steps) - 1)]
    last_step = k >= len(steps)  # k = len(steps) 이면 «다 붙인 결과» 정리 그림
    now = trips[st["trip"]][1]
    s = Svg(664, 300)
    t0, t1 = 3 * 60 + 30, 8 * 60 + 30
    x0, x1 = 62, 426
    X = lambda m: x0 + (max(t0, min(t1, m)) - t0) * (x1 - x0) / (t1 - t0)  # noqa: E731
    RH, Y0 = 22, 40
    s.text(8, 12, title, size=12, anchor="start", tone="ink", bold=True)
    for (lx, col, lab, dash) in ((456, "#2563eb", "출근", False), (506, "#7c3aed", "퇴근", False), (556, "#9aa3ad", "빈 차 이동", True)):
        da = ' stroke-dasharray="3 2"' if dash else ""
        s.parts.append(f'<rect x="{lx}" y="3" width="16" height="10" rx="2" fill="{"none" if dash else col}" stroke="{col}" stroke-width="1.4"{da}/>')
        s.text(lx + 20, 8, lab, size=10.5, anchor="start", tone="gray")
    s.text(456, 28, f"{D.hm(now)} 에 버스가 있는 곳" if not last_step else "아침이 끝났을 때", size=11, anchor="start", tone="ink", bold=True)
    for h in range(4, 9):
        x = X(h * 60)
        s.line(x, Y0 - 4, x, Y0 + 10 * RH, tone="#e5e7eb", sw=1)
        s.text(x, Y0 + 10 * RH + 12, f"{h:02d}:00", size=10, tone="gray")
    yb = Y0 + have * RH - 2
    s.line(4, yb, x1, yb, tone="ng", sw=1.2, dash=True)
    s.text(x0 + 2, yb - 6, f"▲ 보유 {have}대", size=10, tone="ng", bold=True, anchor="start", halo=True)
    assigned = {}
    for i in range(min(k, len(steps) - 1) + 1):
        assigned.setdefault(steps[i]["bus"], []).append(steps[i]["trip"])
    nb = max(assigned) + 1
    xn = X(now)
    if not last_step:
        s.line(xn, Y0 - 6, xn, Y0 + 10 * RH, tone="amber", sw=1.4, dash=True)
    for b in range(10):
        y = Y0 + b * RH
        over = b >= have
        used = b < nb
        lab_tone = ("ng" if over else "ink") if used else "#c4cad3"
        s.text(8, y + 8, f"버스 {b + 1}", size=10.5, anchor="start", tone=lab_tone, bold=used and b == st["bus"] and not last_step)
        s.line(x0, y + 8, x1, y + 8, tone="#f1f5f9", sw=1)
        if b not in assigned:
            continue
        prev = None
        for j in assigned[b]:
            t = trips[j]
            if prev is not None:
                dh = D.haversine_km(*ch_loc(prev[1]), *ch_loc(t[2])) / D.SPEED * 60
                if dh > 0.5:
                    s.parts.append(f'<rect x="{X(prev[0]):g}" y="{y + 3:g}" width="{max(2, X(prev[0] + dh) - X(prev[0])):g}" height="10" rx="2" '
                                   'fill="none" stroke="#9aa3ad" stroke-width="1.3" stroke-dasharray="3 2"/>')
            cur = j == st["trip"] and not last_step
            col = "#dc2626" if over else ("#2563eb" if "출근" in t[0] else "#7c3aed")
            xa, xb = X(t[1]), X(t[3])
            s.parts.append(f'<rect x="{xa:g}" y="{y + 1:g}" width="{max(3, xb - xa):g}" height="14" rx="2" fill="{col}"'
                           + (' stroke="#f59e0b" stroke-width="3"' if cur else "") + "/>")
            prev = (t[3], t[4])
        if last_step:
            t = trips[assigned[b][-1]]
            msg, tone = f"{_place(t[4])} {D.hm(t[3])} 도착 · 트립 {len(assigned[b])}개", ("ng" if over else "ink")
        elif b == st["bus"]:
            t = trips[st["trip"]]
            msg, tone = f"▶ {_place(t[2])} {D.hm(t[1])} 출발을 맡음", ("ng" if over else "acc")
        else:
            last = [j for j in assigned[b] if j != st["trip"]]
            t = trips[last[-1]]
            if t[3] > now + 1e-9:
                msg, tone = f"달리는 중 → {D.hm(t[3])} {_place(t[4])}", "gray"
            else:
                msg, tone = f"{_place(t[4])} 에 있음({D.hm(t[3])}~)", "ink"
        s.text(456, y + 8, msg, size=10.5, anchor="start", tone=tone, bold=(b == st["bus"] and not last_step))
    return s.render(title)


def txn_svg(txn):
    """파일 7개를 차례로 넣다 5번째(hubs)에서 실패 — 트랜잭션 없음 / 있음의 DB 상태(실제로 돌린 결과)"""
    names = ["employees", "schedule", "shifts", "sites", "hubs", "vehicles", "ride_log"]
    s = Svg(664, 236)
    bw, gap, x0 = 72, 8, 100
    s.text(x0, 12, "넣는 순서 →", size=10.5, anchor="start", tone="gray")
    rows = (("none", "트랜잭션 없음", "ng", "앞 4개만 들어간 채 멈춘다 — 반쯤 적용(앞으로도 뒤로도 못 간다)"),
            ("txn", "트랜잭션 있음", "ok", "실패하면 전부 취소 — 적용 전 상태 그대로"))
    for r, (mode, lab, tone, note) in enumerate(rows):
        y = 28 + r * 104
        s.text(8, y + 22, lab, size=11.5, anchor="start", tone=tone, bold=True)
        for i, n in enumerate(names):
            x = x0 + i * (bw + gap)
            v = txn[mode][n]
            fail = i == 4
            fill = "#fdecec" if fail else ("#fff4e0" if v else "#f6f7f9")
            stroke = "#dc2626" if fail else ("#b45309" if v else "#c4cad3")
            s.box(x, y, bw, 46, "", tone="gray", fill=fill, stroke=stroke, sw=2 if fail else 1.3, rx=5)
            s.text(x + bw / 2, y + 15, n, size=10, tone="ink", bold=True)
            s.text(x + bw / 2, y + 32, "✗ 검증 실패" if fail else f"{v:,}행", size=10.5, tone="ng" if fail else ("amber" if v else "gray"), bold=True)
        s.text(x0, y + 64, note, size=11, anchor="start", tone=tone, bold=True)
    return s.render("트랜잭션 실험")


def screens_svg(ex, date_label):
    """사원 화면 · 운영자 화면 예시 — 방안 A 거리순 계획의 실제 값"""
    s = Svg(664, 292)
    s.box(6, 6, 236, 280, "", tone="gray", fill="#ffffff", sw=1.5, rx=14)
    s.box(7, 7, 234, 32, "", tone="ok", fill="#e9f7ee", sw=0, rx=13)
    s.text(124, 23, "사원 화면", size=12, tone="ok", bold=True)
    s.text(20, 58, f"사번 {ex['emp']} · {date_label}", size=11, tone="ink", anchor="start", bold=True)
    s.box(18, 72, 212, 92, "", tone="acc", fill="#eaf1ff", sw=1, rx=6)
    s.text(28, 88, "출근", size=10.5, tone="acc", anchor="start", bold=True)
    hub = D.HUB_SHORT.get(ex["hub"], ex["hub"])
    s.text(28, 108, f"버스 {ex['bus']} · {hub} {D.hm(ex['board'])} 탑승", size=12, tone="ink", anchor="start", bold=True)
    s.text(28, 128, f"→ 이천캠퍼스 {D.hm(ex['arrive'])} 도착", size=11, tone="ink", anchor="start")
    s.text(28, 148, f"타는 시간 약 {ex['ride']:.0f}분", size=10.5, tone="gray", anchor="start")
    s.box(18, 174, 212, 76, "", tone="pur", fill="#f5f0ff", sw=1, rx=6)
    s.text(28, 190, "퇴근", size=10.5, tone="pur", anchor="start", bold=True)
    s.text(28, 210, f"버스 {ex['bus']} · 이천캠퍼스 {D.hm(ex['depart'])} 출발", size=12, tone="ink", anchor="start", bold=True)
    s.text(28, 230, f"→ {hub} {D.hm(ex['home_arrive'])} 도착", size=11, tone="ink", anchor="start")
    s.text(124, 270, "집 좌표 · 다른 사원 정보는 보이지 않는다", size=9.5, tone="gray")
    s.box(254, 6, 404, 280, "", tone="gray", fill="#ffffff", sw=1.5, rx=8)
    s.box(255, 7, 402, 32, "", tone="ok", fill="#e9f7ee", sw=0, rx=7)
    s.text(456, 23, f"운영자 화면 — {date_label} 이천 · 일근 출근", size=12, tone="ok", bold=True)
    for x, t in ((266, "버스"), (304, "들르는 거점(인원)"), (556, "출발"), (606, "탑승")):
        s.text(x, 56, t, size=10.5, tone="gray", anchor="start", bold=True)
    for i, b in enumerate(ex["buses"]):
        y = 80 + i * 24
        s.line(262, y - 12, 650, y - 12, tone="#eef1f5", sw=1)
        s.text(270, y, f"{b['no']}", size=11, tone="ink", anchor="start", bold=True)
        s.text(304, y, "→".join(f"{D.HUB_SHORT[n]}{c}" for n, c in b["stops"]), size=10.5, tone="ink", anchor="start")
        s.text(556, y, D.hm(b["start"]), size=10.5, tone="ink", anchor="start")
        s.text(606, y, f"{b['n']}명", size=10.5, tone="ink", anchor="start")
    s.text(456, 274, f"줄을 누르면 탑승자 명단 · 모두 {D.hm(ex['arrive'])} 캠퍼스 도착", size=9.5, tone="gray")
    return s.render("화면 예시")
