# -*- coding: utf-8 -*-
r"""분석 틀 ④ 배치 · 덮기형 — 정해진 대수의 장치(카메라 · 센서)를 후보 위치 · 방향에 놓아 영역을 가장 많이 덮는다 → steps.json

    python3 bookkit/analysis/coverage_place.py --demo --out <steps.json>                    작은 가짜 데이터로 돌려 본다
    python3 bookkit/analysis/coverage_place.py --book bookkit/books/<이름>                 책의 과제 자료로 → <책>/contracts/steps.json

쓰는 법(A3 카드): 이 파일을 <책>/work/a3.py 로 복사 → «입력 연결 칸» load() 만 과제에 맞게 고친다 → 돌린다 → 검사기
- 기본 규칙(방안 A) = 새로 덮는 칸이 가장 많은 후보부터 고르는 탐욕법 · 고치기(방안 B 의 속) = 고른 것을 하나씩 다른 후보로 바꿔 덮는 칸 늘리기
- 조건별 실행 = 대수(또는 비용 상한) · 시야각 · 거리를 바꿔 커버리지 · 목표 달성 여부
- 전부 세기 = 고르는 조합을 작은 크기에서 실제로 재고 큰 크기는 «추정» 행(_common.brute_table 과 같은 표 — 순서가 아니라 조합이라 가짓수만 다르다)
- 과제 내용은 load() 에만 들어간다(이 틀에는 특정 과제의 숫자 · 이름이 없다)

재생기 대응(양식에 칸을 칠하는 그림이 없어 route_map · timetable 칸에 맞춘다 — 엔진 · 양식은 그대로)
- 채우기 · 고치기 = 지도. 회색 점 = 아직 안 덮인 칸(이름표 = 가중치) · 색 점 + 후보에서 뻗은 선 = 그 장치가 덮은 칸 · × = 장애물 · 빨간 × = 빠진 후보
- 이어 붙이기 = 줄 하나가 장치 한 대, 막대 = 그 장치가 더한 커버리지 구간(가로축 0~100% · 시각 눈금 없음). 목표에 닿을 때까지 더 놓아 본다(비용 상한은 보지 않는다) · 보유선 아래 빨간 줄 = 모자란 대수
- 좌표 = (y, x) 정수 칸 · 방향 = 도(0 = +x · 90 = +y · 지도 위쪽이 +y)
"""
import argparse
import itertools
import math
import sys
import time
from pathlib import Path

# 이 파일이 있는 폴더 — 틀 폴더(bookkit/analysis) 또는 책의 work/(복사해 쓸 때)
HERE = Path(__file__).resolve().parent
# 분석 틀 공용(_common.py) — 위쪽 폴더에서 bookkit/analysis 를 찾는다(work/ 로 복사해도 그대로 돈다)
sys.path.insert(0, str(next((p / "analysis" for p in [HERE, *HERE.parents] if (p / "analysis" / "_common.py").is_file()), HERE)))
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402

# 지도에 그리는 칸 수 상한 — 넘으면 일정 간격의 칸만 그린다(숫자는 전체 칸으로 계산)
MAX_SHOW = 120
# 이어 붙이기 줄 수 상한 — 양식 시간표 권장 16줄
MAX_ROWS = 16
# 고치기 단계 수 상한 — 재생기 표 8행(출발 + 7)
MAX_STEPS = 7
# 재생기 표 행 수 상한 — RULES.md 6절
MAX_TABLE = 8
# 전부 세기를 실제로 재는 가짓수 상한
BRUTE_LIMIT = 300_000
# 시야를 따라가며 장애물을 보는 간격 — 칸 1 당 표본 수
LOS_STEP = 4
# 커버리지가 늘었다고 보는 최소 증가분(실수 오차 제외)
MIN_GAIN = 1e-9


# ════════════════════════════════════════════════════════════
# 입력 연결 칸 — 과제마다 고친다(이 함수만)
# ════════════════════════════════════════════════════════════
# task: 과제 폴더
def load(task):
    """과제 폴더 → 입력 dict
        grid       (행 수, 열 수) — 또는 cells [(y, x) …] 칸 목록(둘 중 하나)
        weight     {(y, x): 가중치} (선택 — 없는 칸은 1)
        obstacles  [(y, x) …] 시야를 막고 덮을 대상에서도 빠지는 칸(선택)
        sites      {후보 이름: (y, x)} 설치 가능한 곳 · 한 곳에 한 대 · short {후보: 짧은 이름}(선택)
        dirs       [도 …] 돌릴 수 있는 방향 · site_dirs {후보: [도 …]}(선택 — 후보마다 다르면)
        fov(시야각 도) · reach(거리)
        count(대수) 또는 budget(비용 상한) + cost {후보: 비용}(둘 다 주면 둘 다 지킨다)
        goal       목표 비율(0~1)
        counts · budgets · fovs · reaches  조건별 실행에 쓸 값 목록(선택)
        veh(장치 이름) · cell(칸 이름) · flow(큰 흐름 상자 글 · 선택)"""
    raise NotImplementedError("load() 를 과제에 맞게 고친다 — 예: 도면 csv 를 읽어 grid · obstacles · sites 를 만든다(demo() 참고)")


def demo():
    """작은 가짜 데이터(격자 7 × 10 · 후보 6곳 · 3대) — 틀이 도는지 보기만 한다"""
    # 가중치가 큰 칸 묶음 — 오른쪽 위 구역
    hot = {(y, x): 3 for y in range(4, 7) for x in range(7, 10)}
    # 후보 위치
    sites = {"C1": (3, 8), "C2": (0, 0), "C3": (1, 5), "C4": (6, 9), "C5": (6, 5), "C6": (4, 0)}
    return {"grid": (7, 10), "weight": hot, "obstacles": [(2, 4), (3, 4), (4, 4), (3, 5)], "sites": sites, "dirs": [0, 90, 180, 270],
            "fov": 100, "reach": 6.0, "count": 3, "goal": 0.8, "counts": [2, 3, 4, 5], "fovs": [60, 100, 140], "reaches": [4.0, 6.0, 8.0],
            "veh": "카메라", "cell": "칸"}


# ════════════════════════════════════════════════════════════
# 보이는 칸 — 거리 · 시야각 · 장애물 가림
# ════════════════════════════════════════════════════════════
# inp: 입력 dict
def field(inp):
    """입력 → (덮을 칸 목록, 장애물 모음, 칸별 가중치 {칸: 값})"""
    # 장애물 칸 모음
    blocked = {tuple(c) for c in inp.get("obstacles", ())}
    # 격자 전체 또는 주어진 칸 목록
    raw = inp.get("cells") or list(itertools.product(range(inp["grid"][0]), range(inp["grid"][1])))
    # 덮을 칸 — 장애물 제외
    cells = [tuple(c) for c in raw if tuple(c) not in blocked]
    # 칸별 가중치 입력
    given = inp.get("weight", {})
    return cells, blocked, {c: given.get(c, 1) for c in cells}


# a: 시작 좌표 / b: 끝 좌표 / blocked: 장애물 칸 모음
def clear(a, b, blocked):
    """a 에서 b 까지 직선이 장애물 칸을 지나지 않나 — 양 끝 칸은 보지 않는다(벽에 붙인 장치 · 벽 앞 칸)"""
    # 직선 위 표본 수
    n = math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) * LOS_STEP)
    # i: 표본 번호
    for i in range(1, n):
        # 표본이 든 칸 — 소수 좌표를 가장 가까운 칸으로
        c = (math.floor(a[0] + (b[0] - a[0]) * i / n + 0.5), math.floor(a[1] + (b[1] - a[1]) * i / n + 0.5))
        if c in blocked and c != tuple(a) and c != tuple(b):
            return False
    return True


# inp: 입력 dict
def sights(inp):
    """후보마다 가리지 않고 보이는 칸 → {후보: {칸: (거리, 각도)}}
    장애물 가림은 방향 · 시야각 · 거리와 무관해 한 번만 계산(조건별 실행이 다시 쓴다)"""
    cells, blocked, _ = field(inp)
    # 결과 표
    out = {}
    # s: 후보 이름 / p: 후보 좌표
    for s, p in inp["sites"].items():
        out[s] = {c: (math.hypot(c[0] - p[0], c[1] - p[1]), math.degrees(math.atan2(c[0] - p[0], c[1] - p[1])) % 360)
                  for c in cells if clear(p, c, blocked)}
    return out


# inp: 입력 dict / sight: sights() 결과 / fov: 시야각 / reach: 거리
def options(inp, sight, fov, reach):
    """후보 × 방향 → [{"site", "dir", "cells": 보이는 칸 모음}] — 보이는 칸이 없는 것은 뺀다"""
    # 결과 목록
    out = []
    for s in inp["sites"]:
        # d: 방향(도)
        for d in inp.get("site_dirs", {}).get(s, inp.get("dirs", [0])):
            # 보이는 칸 — 거리 안 · 시야각 안(제자리 칸은 방향과 무관)
            seen = frozenset(c for c, (dist, ang) in sight[s].items() if dist <= reach and (dist == 0 or abs((ang - d + 180) % 360 - 180) <= fov / 2))
            if seen:
                out.append({"site": s, "dir": d, "cells": seen})
    return out


# wt: 칸별 가중치 / opts: 후보 × 방향 목록 / picks: 고른 번호 목록
def covered(wt, opts, picks):
    """고른 것들이 덮는 가중치 합"""
    return sum(wt[c] for c in set().union(*(opts[i]["cells"] for i in picks)))


# inp: 입력 dict / picks: 고른 번호 목록 / opts: 후보 × 방향 목록
def spent(inp, opts, picks):
    """고른 것들의 비용 합 — 비용 표가 없으면 한 대 1"""
    return sum(inp.get("cost", {}).get(opts[i]["site"], 1) for i in picks)


# ════════════════════════════════════════════════════════════
# 방안 A · 고치기
# ════════════════════════════════════════════════════════════
# inp: 입력 dict / opts: 후보 × 방향 목록 / wt: 칸별 가중치 / count: 대수 상한(None = 없음) / budget: 비용 상한(None = 없음) / start: 이미 놓은 번호 목록
def greedy(inp, opts, wt, count, budget, start=()):
    """새로 덮는 가중치가 가장 큰 후보부터 고른다 — 상한에 닿거나 더 덮을 칸이 없으면 멈춘다 → 고른 번호 목록(고른 순서 · start 뒤에 이어 붙인다)"""
    # 고른 번호 · 덮은 칸 모음
    picks = list(start)
    seen = set().union(*(opts[i]["cells"] for i in picks))
    while count is None or len(picks) < count:
        # 이미 쓴 후보
        used = {opts[i]["site"] for i in picks}
        # 가장 나은 (늘어난 값, 번호)
        best = None
        # i: 번호 / o: 후보 × 방향 하나
        for i, o in enumerate(opts):
            if o["site"] in used or (budget is not None and spent(inp, opts, picks + [i]) > budget):
                continue
            # 새로 덮는 가중치
            g = sum(wt[c] for c in o["cells"] - seen)
            if g > MIN_GAIN and (best is None or g > best[0] + MIN_GAIN):
                best = (g, i)
        if best is None:
            break
        picks.append(best[1])
        seen |= opts[best[1]]["cells"]
    return picks


# inp: 입력 dict / opts: 후보 × 방향 목록 / wt: 칸별 가중치 / picks: 출발 번호 목록 / budget: 비용 상한 / max_steps: 단계 수 상한
def improve(inp, opts, wt, picks, budget, max_steps=MAX_STEPS):
    """고른 것 하나를 다른 후보로 바꿔 덮는 값이 가장 많이 느는 것을 받아들인다(늘지 않으면 멈춘다)
    → [{"picks", "value", "slot", "old", "new"}] (첫 줄 = 출발점 · 덮는 값은 단계마다 늘기만 한다)"""
    # 지금 고른 번호
    cur = list(picks)
    # 단계 기록
    rec = [{"picks": list(cur), "value": covered(wt, opts, cur), "slot": None, "old": None, "new": None}]
    for _ in range(max_steps):
        # 지금 덮는 값
        base = rec[-1]["value"]
        # 가장 나은 (늘어난 값, 자리, 새 번호)
        best = None
        # slot: 바꿀 자리 / old: 그 자리 번호
        for slot, old in enumerate(cur):
            # 나머지 고른 것
            rest = cur[:slot] + cur[slot + 1:]
            # 나머지가 쓴 후보
            used = {opts[i]["site"] for i in rest}
            for j, o in enumerate(opts):
                if j == old or o["site"] in used or (budget is not None and spent(inp, opts, rest + [j]) > budget):
                    continue
                # 바꿨을 때 늘어난 값
                g = covered(wt, opts, rest + [j]) - base
                if g > MIN_GAIN and (best is None or g > best[0] + MIN_GAIN):
                    best = (g, slot, j)
        if best is None:
            break
        _, slot, j = best
        # 빠지는 번호
        old = cur[slot]
        cur[slot] = j
        rec.append({"picks": list(cur), "value": covered(wt, opts, cur), "slot": slot, "old": old, "new": j})
    return rec


# inp: 입력 dict / sight: sights() 결과 / wt: 칸별 가중치 / fov: 시야각 / reach: 거리 / count: 대수 상한 / budget: 비용 상한 / start: 이어 시작할 번호 목록
def solve(inp, sight, wt, fov, reach, count, budget, start=()):
    """한 조건의 방안 A + 고치기 → (후보 × 방향 목록, 방안 A 번호 목록, 고치기 기록)"""
    opts = options(inp, sight, fov, reach)
    picks = greedy(inp, opts, wt, count, budget, start)
    return opts, picks, improve(inp, opts, wt, picks, budget)


# inp: 입력 dict / sight: sights() 결과 / wt: 칸별 가중치 / cases: 조건 목록 [(이름, 값 글, 시야각, 거리, 대수, 비용 상한) …]
def case_values(inp, sight, wt, cases):
    """조건마다 덮는 값 → {조건 번호: 값}
    대수 · 비용 상한 = 늘려도 줄면 안 된다 — 탐욕법 + 고치기는 대수마다 따로 풀면 앞 대수보다 나빠질 수 있어,
    작은 값부터 풀며 앞 값의 배치에서 이어 시작한 결과와 새로 푼 결과 중 큰 쪽을 쓴다(앞 배치는 상한이 늘어도 그대로 지켜진다)"""
    # 이어 받는 조건 — 이름 → 조건 칸 자리(대수 · 비용 상한)
    rank = {"대수": 4, "비용 상한": 5}
    # 조건 번호별 덮는 값 · 조건 이름별 앞 값의 배치
    vals, prev = {}, {}
    # i: 조건 번호 — 값이 작은 조건부터
    for i in sorted(range(len(cases)), key=lambda i: cases[i][rank[cases[i][0]]] if cases[i][0] in rank else 0):
        name, _, f, d, n, bud = cases[i]
        # 새로 푼 결과
        rec = solve(inp, sight, wt, f, d, n, bud)[2]
        if prev.get(name):
            # 앞 배치에서 이어 시작한 결과
            more = solve(inp, sight, wt, f, d, n, bud, prev[name])[2]
            if more[-1]["value"] > rec[-1]["value"] + MIN_GAIN:
                rec = more
        if name in rank:
            prev[name] = rec[-1]["picks"]
        vals[i] = rec[-1]["value"]
    return vals


# ════════════════════════════════════════════════════════════
# 전부 세기 — 조합
# ════════════════════════════════════════════════════════════
# inp: 입력 dict / opts: 후보 × 방향 목록 / wt: 칸별 가중치 / k: 고를 대수 / budget: 비용 상한 / veh: 장치 이름
def brute_pick(inp, opts, wt, k, budget, veh):
    """후보 × 방향 n 가지에서 k 대를 고르는 조합을 전부 세는 시간 — 작은 크기는 실제로 재고, 큰 크기는 가짓수 비율로 추정
    → (표 칸, 실측 {n: 초}, 전체를 다 세었으면 가장 큰 덮는 값 · 아니면 None)"""
    # 혼자 많이 덮는 순서의 번호
    order = sorted(range(len(opts)), key=lambda i: -covered(wt, opts, [i]))
    # 잴 크기 목록
    sizes, n = [], max(k + 1, 8)
    while n < len(opts) and math.comb(n, k) <= BRUTE_LIMIT:
        sizes.append(n)
        n *= 2
    if math.comb(len(opts), k) <= BRUTE_LIMIT:
        sizes.append(len(opts))
    # 크기별 실측 초 · 전체를 센 가장 큰 덮는 값
    sec, best_all = {}, None
    for n in sizes:
        # 재기 시작 시각
        t = time.perf_counter()
        # 이 크기의 가장 큰 덮는 값
        best = 0
        # combo: 조합 하나
        for combo in itertools.combinations(order[:n], k):
            if len({opts[i]["site"] for i in combo}) == k and (budget is None or spent(inp, opts, combo) <= budget):
                best = max(best, covered(wt, opts, combo))
        sec[n] = time.perf_counter() - t
        if n == len(opts):
            best_all = best
    # 표 행 — 실측
    rows = [[f"{n}가지", f"{math.comb(n, k):,}", C.sec_text(s), "실측"] for n, s in sec.items()]
    # 가장 큰 실측 크기
    nmax = max(sec)
    # 표 행 — 추정(후보가 늘어난 크기)
    rows += [[f"{n}가지", f"{math.comb(n, k):,}", C.sec_text(sec[nmax] * math.comb(n, k) / math.comb(nmax, k)), f"추정({nmax}가지의 시간 × 가짓수 비율)"]
             for n in (nmax * 2, nmax * 4, nmax * 8)]
    # 추정 칸 표시
    bad = [[i, "전부 세는 데 걸린 시간"] for i, r in enumerate(rows) if r[3] != "실측"]
    return ({"header": ["후보 × 방향 수", f"{veh} {k}대 고르는 가짓수", "전부 세는 데 걸린 시간", "구분"], "rows": rows, "small": True, "bad_cells": bad,
             "caption": "후보 × 방향 수에 따라 «전부 세기» 가 걸리는 시간"}, sec, best_all)


# ════════════════════════════════════════════════════════════
# 재생기 칸
# ════════════════════════════════════════════════════════════
# v: 숫자
def num(v):
    """글에 쓸 숫자 — 소수 한 자리 · 정수면 정수"""
    # 반올림한 값
    r = round(v, 1)
    return int(r) if r == int(r) else r


# c: 칸 좌표
def cell_name(c):
    """칸 좌표 → 지도 점 이름"""
    return f"{c[0]}_{c[1]}"


# o: 후보 × 방향 하나 / sh: 짧은 이름 표
def label(o, sh):
    """후보 × 방향 → «C3 90°»"""
    return f"{sh.get(o['site'], o['site'])} {o['dir']}°"


# cells: 덮을 칸 목록
def shown_cells(cells):
    """지도에 그릴 칸 → (칸 모음, 간격) — 많으면 간격마다 하나"""
    # 칸 간격
    s = math.ceil(math.sqrt(len(cells) / MAX_SHOW))
    return {c for c in cells if c[0] % s == 0 and c[1] % s == 0}, s


# inp: 입력 dict / blocked: 장애물 칸 모음 / wt: 칸별 가중치 / opts: 후보 × 방향 목록 / sh: 짧은 이름 표 / show: 그릴 칸 모음
def cover_map(inp, blocked, wt, opts, sh, show):
    """지도 칸(figs.route_map) — 그릴 칸 = 회색 점(이름표 = 가중치) · 후보 = 회색 점(이름표 = 혼자 덮는 값이 가장 큰 때) · 장애물 = 바탕 선 ×"""
    # 후보 좌표 모음 — 같은 자리 칸은 그리지 않아 이름표가 겹치지 않는다
    at_site = {tuple(p) for p in inp["sites"].values()}
    # 지도 점 · 그리는 점 무게 · 짧은 이름
    pts, weights, short = {}, {}, {}
    for c in sorted(show):
        pts[cell_name(c)] = c
        short[cell_name(c)] = ""
        if c not in at_site:
            weights[cell_name(c)] = wt[c]
    for s, p in inp["sites"].items():
        pts[s] = tuple(p)
        short[s] = sh.get(s, s)
        weights[s] = num(max((covered(wt, opts, [i]) for i, o in enumerate(opts) if o["site"] == s), default=0))
    # 장애물 × 를 그리는 바탕 선
    edges = []
    for y, x in sorted(blocked):
        # 네 모서리 점 이름
        a, b, c, d = (f"ob{y}_{x}_{k}" for k in "abcd")
        pts.update({a: (y - 0.3, x - 0.3), b: (y + 0.3, x + 0.3), c: (y - 0.3, x + 0.3), d: (y + 0.3, x - 0.3)})
        edges += [[a, b], [c, d]]
    M = C.map_spec(pts, weights, short, None, "", False)
    # 범위에 장애물까지 넣는다(map_spec 은 그리는 점만 본다)
    M["fit_points"] = [pts[n] for n in weights] + [tuple(c) for c in blocked]
    M["pad"] = C._pad(M["fit_points"])
    M["edges"] = edges
    return M


# opts: 후보 × 방향 목록 / picks: 고른 번호 목록 / n_slot: 자리 수 / wt: 칸별 가중치 / show: 그릴 칸 모음
def routes(opts, picks, n_slot, wt, show):
    """고른 것 → 재생기 state — 자리마다 [[후보, 새로 덮은 값], [칸, 0], [후보, 0], [칸, 0] …]
    후보 → 칸 → 후보 로 되돌아가 지도에 부채꼴 선이 그려진다 · 겹친 칸은 먼저 놓은 자리의 몫 · 오른쪽 목록의 합계 = 첫 줄 값"""
    # 앞 자리가 덮은 칸
    seen = set()
    # 자리별 경로
    out = [[] for _ in range(n_slot)]
    # b: 자리 번호 / i: 고른 번호
    for b, i in enumerate(picks):
        o = opts[i]
        # 이 자리가 새로 덮은 칸
        new = o["cells"] - seen
        seen |= new
        out[b] = [[o["site"], num(sum(wt[c] for c in new))]]
        for c in sorted(new & show):
            out[b] += [[cell_name(c), 0], [o["site"], 0]]
    return out


# inp: 입력 dict
def run(inp):
    """입력 → steps.json dict"""
    cells, blocked, wt = field(inp)
    sh = inp.get("short", {})
    # 장치 이름 · 칸 이름 · 목표 비율 · 시야각 · 거리 · 대수 상한 · 비용 상한
    veh, cell, goal, fov, reach, count, budget = (inp.get("veh", "장치"), inp.get("cell", "칸"), inp["goal"], inp["fov"], inp["reach"],
                                                  inp.get("count"), inp.get("budget"))
    # 전체 가중치 · 목표 비율(%)
    total, goal_pct = sum(wt.values()), num(goal * 100)
    # value: 덮은 값
    pct = lambda value: num(100 * value / total)  # noqa: E731  — 덮은 값 → 커버리지(%)
    sight = sights(inp)
    opts, picks, rec = solve(inp, sight, wt, fov, reach, count, budget)
    # 자리 수 · 그릴 칸 · 칸 간격
    n_slot = len(picks)
    show, stride = shown_cells(cells)
    M = cover_map(inp, blocked, wt, opts, sh, show)
    # 지도 글 — 칸을 간격으로 줄였으면 알린다
    thin = f" · {stride}칸마다 하나만 그린다(숫자는 전체 {cell})" if stride > 1 else ""
    if any(v != 1 for v in wt.values()):  # 가중치가 있으면 재생기의 «칸» 숫자는 칸 수가 아니라 가중치 합
        thin += f" · {cell} 숫자 = 가중치 합"
    # 오른쪽 목록 글
    words = {"line": "{mark}" + veh + " {k}  {fill}" + cell, "empty": veh + " {k}  —\n"}

    # 재생기 1 «채우기» — 한 단계 = 한 대 놓기
    fsteps, frows = [], []
    for b, i in enumerate(picks):
        o = opts[i]
        # 이번까지 덮은 값 · 커버리지
        val = covered(wt, opts, picks[:b + 1])
        cov = pct(val)
        # 이번에 늘어난 값
        gain = val - (covered(wt, opts, picks[:b]) if b else 0)
        txt = f"**{b + 1}번째를 놓는다** — {label(o, sh)} · 새로 {num(gain)}{cell} · 커버리지 **{cov}%**."
        if b == n_slot - 1:
            txt += f" ++목표 {goal_pct}% 를 넘는다.++" if cov >= goal_pct else f" !!목표 {goal_pct}% 에 {num(goal_pct - cov)}%p 모자란다.!!"
        fsteps.append({"state": routes(opts, picks[:b + 1], n_slot, wt, show), "cur": b, "head": f"{b + 1}번째 — 커버리지 {cov}%", "text": txt,
                       "row": b if b < MAX_TABLE else None})
        frows.append([f"{veh} {b + 1}", label(o, sh), f"{num(gain)}", f"{cov}%"])
    pf = {"title": f"{veh} {n_slot}대를 새로 덮는 {cell}이 많은 곳부터 놓는 과정", "task": f"다음을 눌러 가며 → 뒤로 갈수록 새로 덮는 {cell}이 얼마나 주는지 봐",
          "caption": f"한 단계 = {veh} 한 대 놓기. 회색 점 = 아직 안 덮인 {cell} · 색 점과 선 = 그 {veh}가 덮은 {cell} · × = 장애물{thin}", "auto_ms": 1100,
          "map": M, "frame_title": "새로 덮는 값이 가장 큰 후보부터", "right_title": f"{veh}별 새로 덮은 {cell}", "words": words, "cap": "", "steps": fsteps,
          "table": {"header": [veh, "놓은 곳 · 방향", f"새로 덮음({cell})", "커버리지"], "rows": frows[:MAX_TABLE], "small": True}}

    # 재생기 2 «고치기» — 한 단계 = 한 대 바꾸기
    xsteps, xrows = [], []
    # no: 단계 번호 / r: 단계 기록
    for no, r in enumerate(rec):
        cov = pct(r["value"])
        st = routes(opts, r["picks"], n_slot, wt, show)
        if no == 0:
            txt, head, row = (f"**출발점 — 채우기 결과.** 커버리지 **{cov}%**. 한 대만 다른 후보로 바꿔 보고 늘면 받아들인다.", f"출발점 — 커버리지 {cov}%",
                              ["출발", "채우기 결과 그대로", f"{cov}%"])
            hl, gone = [], []
        else:
            # 앞 단계 커버리지 · 빠지는 것 · 들어오는 것
            prev, a, b = pct(rec[no - 1]["value"]), opts[r["old"]], opts[r["new"]]
            txt = f"**고치기 {no} — 바꾸기.** {veh} {r['slot'] + 1} 을 {label(a, sh)} 에서 {label(b, sh)} 로 바꾼다. 커버리지 **{prev}% → {cov}%**."
            head, row = f"고치기 {no} — 커버리지 {prev}% → {cov}%", [str(no), f"{label(a, sh)} → {label(b, sh)}", f"{cov}%"]
            hl, gone = [r["slot"]], ([[r["slot"], a["site"]]] if a["site"] != b["site"] else [])
        if no == len(rec) - 1:
            txt += " 더 바꿔 봐도 늘지 않아 **여기서 멈춘다.**" if no < MAX_STEPS else " (단계 수 상한에서 멈춘다)"
        xsteps.append({"state": st, "hl": hl, "gone": gone, "head": head, "text": txt, "row": no})
        xrows.append(row)
    px = {"title": f"한 대씩 바꾸기 — 덮는 {cell} 늘리기", "task": f"다음을 눌러 가며 → 굵어진 {veh}의 부채꼴이 어디로 옮겨 가는지, 표의 커버리지가 얼마나 느는지 봐",
          "caption": f"빨간 × = 이번에 빠진 후보. 굵은 선 = 이번에 바뀐 {veh}{thin}", "auto_ms": 1300, "map": M, "right_title": f"{veh}별 덮은 {cell}", "words": words,
          "steps": xsteps, "table": {"header": ["#", "고친 것", "커버리지"], "rows": xrows, "small": True}}

    # 재생기 3 «이어 붙이기» — 목표에 닿을 때까지 더 놓아 본다(줄 = 한 대 · 막대 = 더한 커버리지 구간)
    more = greedy(inp, opts, wt, MAX_ROWS, None)
    # 놓을 때마다의 커버리지(앞에 0)
    trail = [0] + [100 * covered(wt, opts, more[:n + 1]) / total for n in range(len(more))]
    # 목표에 처음 닿는 대수 — 0 = 후보를 다 써도 못 닿는다
    need_goal = next((n for n in range(1, len(trail)) if trail[n] >= goal * 100), 0)
    if need_goal:
        more = more[:need_goal]
        trail = trail[:need_goal + 1]
    # 쓸 수 있는 대수
    have = count if count is not None else n_slot
    # 시간표 칸 일 — 시작 · 끝 = 커버리지(%) · 곳 = 후보
    trips = [{"start": round(trail[n], 1), "end": round(trail[n + 1], 1), "frm": opts[i]["site"], "to": opts[i]["site"], "color": "#2563eb"} for n, i in enumerate(more)]
    # 오른쪽 글 표 — 후보마다 방향과 더한 몫
    names = {opts[i]["site"]: f"{label(opts[i], sh)} +{num(trail[n + 1] - trail[n])}%p" for n, i in enumerate(more)}
    heads = [f"{n + 1}번째 — 커버리지 {num(trail[n + 1])}%" for n in range(len(more))]
    texts = [f"**{n + 1}번째** {label(opts[i], sh)} — 커버리지 {num(trail[n])}% → **{num(trail[n + 1])}%**." + (f" !!보유 {have}대를 넘는다.!!" if n >= have else "")
             for n, i in enumerate(more)]
    end_word = f"고치기 없이 탐욕법만으로 목표 {goal_pct}% 까지 **{need_goal}대**" if need_goal else f"!!후보를 다 써도 목표 {goal_pct}% 에 못 닿는다!!(최대 {num(trail[-1])}%)"
    heads.append(f"다 놓은 결과 — {veh} {len(more)}대 · 커버리지 {num(trail[-1])}%")
    texts.append(f"{end_word}(보유 {have}대).")
    # 후보 사이 이동 표 — 시간표 칸이 곳 전부 × 전부를 요구(이 틀은 이동이 없어 0)
    dh = {a: {b: 0 for b in names} for a in names}
    pc = C.timetable_player(trips, [{"trip": n, "bus": n} for n in range(len(more))], heads, texts, dh, names, have, veh, "더한 몫",
                            f"{veh}를 더 놓을수록 커버리지가 어떻게 느는가", "다음을 눌러 가며 → 막대가 짧아지는 곳, 보유선을 넘는 곳을 봐")
    # 시간 눈금 대신 0~100% 구간 — 양식이 눈금을 시각 글로만 찍어 눈금을 비우고 숫자는 오른쪽 글 · 단계 글로
    T = pc["timetable"]
    T.update({"axis": [0, 100], "ticks": [], "legend": [["더한 몫", "#2563eb", False]]})
    T["words"].update({"where": "놓을 때마다 더한 몫", "end": "다 놓았을 때", "done": "{place}", "take": "▶ {place}", "run": "{place}", "idle": "{place}"})
    pc["caption"] = f"줄 하나 = {veh} 한 대 · 막대 = 그 {veh}가 더한 커버리지 구간(왼쪽 끝 0% · 오른쪽 끝 100%) · 빨간 줄 = 보유를 넘긴 {veh}"

    # 조건별 실행 — 대수(또는 비용 상한) · 시야각 · 거리
    conds = []
    # 조건 하나의 (이름, 값 글, 시야각, 거리, 대수, 비용 상한)
    cases = ([("대수", f"대수 {n}대", fov, reach, n, budget) for n in inp.get("counts", [])]
             + [("비용 상한", f"비용 상한 {n}", fov, reach, count, n) for n in inp.get("budgets", [])]
             + [("시야각", f"시야각 {n}°", n, reach, count, budget) for n in inp.get("fovs", [])]
             + [("거리", f"거리 {n}", fov, n, count, budget) for n in inp.get("reaches", [])])
    cases = cases or [("기준", "기준", fov, reach, count, budget)]
    # 조건 번호별 덮는 값
    vals = case_values(inp, sight, wt, cases)
    # i: 조건 번호 / name: 조건 이름 / value: 값 글
    for i, (name, value, *_) in enumerate(cases):
        cov = pct(vals[i])
        conds.append({"name": name, "value": value, "result": {"커버리지(%)": cov, "목표까지(%p)": num(max(0, goal_pct - cov)), "목표": "달성" if cov >= goal_pct else "미달"}})
    cols = ["커버리지(%)", "목표까지(%p)", "목표"]
    ctab = C.conditions_table(conds, ["조건", *cols], cols, "목표까지(%p)", 0, f"조건별 커버리지(목표 {goal_pct}% — 못 미치면 빨강)")

    # 4장 표 · 그림 — 1번째를 놓은 뒤 둘째 자리 비교 · 전부 세기
    first = opts[picks[0]]
    # 둘째 후보마다 (이름, 방향 글, 덮는 값)
    second = []
    for s in inp["sites"]:
        if s != first["site"]:
            # 그 후보의 번호들
            own = [i for i, o in enumerate(opts) if o["site"] == s]
            if own:
                i = max(own, key=lambda j: covered(wt, opts, [picks[0], j]))
                second.append((s, label(opts[i], sh), covered(wt, opts, [picks[0], i])))
    second.sort(key=lambda r: -r[2])
    if len(second) > 6:
        second = second[:5] + second[-1:]
    # 마지막 행 번호
    last = len(second) - 1
    otab = {"header": [f"{label(first, sh)} 다음에 놓을 곳", "커버리지"], "rows": [[r[1], f"{pct(r[2])}%"] for r in second], "good_rows": [0], "bad_rows": [last],
            "notes": {0: ["← 가장 많다", "good"], last: ["← 가장 적다", "bad"]}, "small": True}
    ofig = {"points": {r[0]: tuple(inp["sites"][r[0]]) for r in second}, "short": sh, "target": tuple(inp["sites"][first["site"]]),
            "target_label": sh.get(first["site"], first["site"]), "best": [[second[0][0]], f"가장 많다 {pct(second[0][2])}%"],
            "worst": [[second[last][0]], f"가장 적다 {pct(second[last][2])}%"], "geo": False, "label": "둘째 자리"}
    # 전부 셀 대수 — 비용 상한이 있으면 방안 A 가 놓은 대수(고치기도 대수를 지켜 같은 크기로 견준다) · 보이는 칸이 있는 후보 수를 넘지 않는다
    k = min(n_slot if count is None or budget is not None else count, len({o["site"] for o in opts}))
    brute, sec, best_all = brute_pick(inp, opts, wt, k, budget, veh)
    # 큰 흐름 막대 열 — 놓은 순서마다 새로 덮은 몫(열 12개까지)
    columns = [{"label": f"{n + 1}번째", "sub": sh.get(opts[i]["site"], opts[i]["site"]), "values": [num(trail[n + 1] - trail[n])]} for n, i in enumerate(more[:12])]
    # 대수별 안 덮인 비율 — 양식 막대는 한도를 넘으면 빨강이라 «허용선을 넘는 막대 = 아직 모자람» 으로 쓴다
    bars = [{"label": f"{n}대", "value": num(100 - trail[n])} for n in range(1, len(trail))]
    numbers = {"n_cells": len(cells), "n_sites": len(inp["sites"]), "n_opts": len(opts), "count": n_slot, "goal_pct": goal_pct, "cov_A": pct(rec[0]["value"]), "cov_B": pct(rec[-1]["value"]),
               "cells_A": len(set().union(*(opts[i]["cells"] for i in rec[0]["picks"]))), "cells_B": len(set().union(*(opts[i]["cells"] for i in rec[-1]["picks"]))),
               "B_moves": len(rec) - 1, "need_goal": need_goal, "cov_more": num(trail[-1]), "brute_max_measured": max(sec), "brute_max_sec": round(sec[max(sec)], 4)}
    if best_all is not None:  # 전체 조합을 다 세었을 때만 — 방안과 견줄 진짜 최댓값
        numbers["cov_best"] = pct(best_all)
    return {"contract": "steps", "version": 1, "type": "other", "task": inp.get("task", ""), "numbers": numbers,
            "players": {"채우기": pf, "고치기": px, "이어붙이기": pc},
            "figures": {"순서_지도": ofig,
                        "그림_큰흐름": C.overview_fig(columns, "놓은 순서별 더한 커버리지(%p)", [["더한 몫", "#2563eb"]], inp.get("flow")),
                        "시각막대": {"title": f"{veh} 대수별 안 덮인 비율(%)", "bars": bars, "limit": num(100 - goal_pct), "limit_label": f"허용 {num(100 - goal_pct)}%", "unit": "%",
                                  "label": "대수별 안 덮인 비율"}},
            "tables": {"순서_표": otab, "전부세기_표": brute, "조건별_표": ctab}, "conditions": conds}


# argv: 명령 인자 목록
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="분석 틀 ④ 배치 · 덮기형 → steps.json")
    ap.add_argument("--demo", action="store_true", help="작은 가짜 데이터로")
    ap.add_argument("--book", help="책 폴더")
    ap.add_argument("--task", help="과제 폴더(README.md · uploads/)")
    ap.add_argument("--out", help="출력 steps.json(기본 <책>/contracts/steps.json)")
    # 해석한 인자
    a = ap.parse_args(argv)
    if not a.book and not a.demo and HERE.name == "work":  # 책의 work/ 에서 돌리면 그 책
        a.book = str(HERE.parent)
    inp = demo() if a.demo else load(C.task_dir(a.book, a.task))
    # 쓴 파일 경로
    p = C.write_steps(a.out or (Path(a.book) / "contracts" / "steps.json"), run(inp))
    print(f"saved {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
