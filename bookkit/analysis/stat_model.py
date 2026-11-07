# -*- coding: utf-8 -*-
r"""분석 틀 ⑤ 측정 · 관리도형 — 판(웨이퍼 · 기판 · 시편) 위 여러 좌표에서 잰 어긋남(벡터 dx · dy 또는 값 하나)을 성분으로 나누고, 장비 · 하위 단위별로 이상을 잡는다 → steps.json

    python3 bookkit/analysis/stat_model.py --demo --out <steps.json>                        작은 가짜 데이터로 돌려 본다
    python3 bookkit/analysis/stat_model.py --book bookkit/books/<이름>                     책의 과제 자료로 → <책>/contracts/steps.json

쓰는 법(A3 카드): 이 파일을 <책>/work/a3.py 로 복사 → «입력 연결 칸» load() 만 과제에 맞게 고친다 → 돌린다 → 검사기
- 입력 모양 = 측정 한 줄마다 (판 · 장비 · 하위 단위 · 묶음 · 시각 · 좌표 x, y · 값 dx, dy) — 값이 하나면(두께 · 높이) dy 를 빼고 "vector": False
- 기본 규칙(방안 A) = 판마다 1차 최소제곱 분해(평행 이동 · 회전 · 배율 · 직교 — 값 하나면 평균 · 기울기) → 성분마다 평균 ± 3σ 관리 한계
  σ = 같은 하위 단위에서 시간순으로 이웃한 두 판의 차이 평균 ÷ 1.128(관리도 표준 — 천천히 흐르는 드리프트 · 장비끼리 차이에 σ 가 부풀지 않는다)
- 방안 B = 고차 성분(2차 · 3차 항)까지 최소제곱 — 1차로 못 빼는 휜 모양을 더 뺀다(남는 어긋남이 얼마나 더 주나)
- 공통 단계 = 성분 값을 시간순으로 관리도에 찍어 이탈 점 → 어느 장비 · 하위 단위가 늘 밖(치우침)인가 · 갈수록 밖(드리프트)인가
- 판정 = 판마다 |평균| + 3σ(축마다 · 큰 쪽)이 허용(spec)을 넘으면 재작업 · 보정값 = 장비 · 하위 단위별 성분 평균의 부호를 뒤집은 값
- 전부 세기 = 성분 값을 후보 격자로 전부 대 보는 시간(작은 크기 실측 · 큰 크기 추정) — 최소제곱이 한 번에 푸는 시간과 견준다
- 조건별 실행 = 관리 한계 배수(k)를 바꿔 이탈 점 수 · 잡은 곳
- 과제 내용은 load() 에만 들어간다(이 틀에는 특정 과제의 숫자 · 이름이 없다) · 표준 라이브러리 + _common 만(대회 리눅스에서 바로 돈다)

재생기 대응(양식 kit 재생기 칸의 "kind" — 엔진은 그대로 · 양식 figs 에 그림 셋을 더했다)
- 채우기 = "quiver" 화살표 지도 — 한 판의 어긋남을 화살표로, 한 단계에 성분 하나를 뺀다(화살표가 줄어든다)
- 고치기 = "quiver" 잔차 지도 — 1차를 뺀 잔차에서 2차 · 3차를 더 뺀다 · 점 허용보다 긴 화살표는 빨강
- 이어 붙이기 = "chart" 관리도 — 묶음(로트) 하나씩 시간순으로 점을 찍고 한계 밖은 빨간 고리 · 오른쪽 = 줄마다 이탈 수
- 순서 지도 = "arrows" — 가장 작은 경우(평행 이동 x 하나)의 후보 둘을 뺀 화살표를 나란히
"""
import argparse
import itertools
import math
import random
import statistics
import sys
import time
from pathlib import Path

# 이 파일이 있는 폴더 — 틀 폴더(bookkit/analysis) 또는 책의 work/(복사해 쓸 때)
HERE = Path(__file__).resolve().parent
# 분석 틀 공용(_common.py) — 위쪽 폴더에서 bookkit/analysis 를 찾는다(work/ 로 복사해도 그대로 돈다)
sys.path.insert(0, str(next((p / "analysis" for p in [HERE, *HERE.parents] if (p / "analysis" / "_common.py").is_file()), HERE)))
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402

# 관리도 σ 상수 — 이웃한 두 값 차이(이동 범위)의 평균 ÷ d2(2) = σ
D2 = 1.128
# 성분이 걸렸다고 보는 이탈 비율 — 그 줄(장비 · 하위 단위) 판의 이 비율 이상이 한계 밖이고 3장 이상
FLAG_FRAC = 0.25
FLAG_MIN = 3
# 전부 세기 — 성분 하나의 후보 수 · 실제로 재는 조합 수 상한
GRID = 21
BRUTE_LIMIT = 20_000
# 관리도 재생기 단계 수 상한(묶음이 많으면 몇 개씩 묶어 찍는다) · 재생기 표 행 수 상한(RULES.md 6절)
MAX_CHART_STEPS = 16
MAX_TABLE = 8
# 관리도 줄(계열) 수 상한 — 색 구분 · 오른쪽 목록
MAX_SERIES = 8


# ════════════════════════════════════════════════════════════
# 입력 연결 칸 — 과제마다 고친다(이 함수만)
# ════════════════════════════════════════════════════════════
# task: 과제 폴더
def load(task):
    """과제 폴더 → 입력 dict
        rows     [{"unit": 판, "group": 장비, "sub": 하위 단위(없으면 None), "batch": 묶음, "t": 시간순 열쇠(숫자 · 정렬되는 글),
                   "x", "y": 판 위 좌표, "dx", "dy": 잰 값(값 하나면 "dx" 만)}] — 측정 한 줄 = 한 칸
        vector   True = (dx, dy) 벡터 · False = 값 하나(dx 만 · 성분 = 평균 · 기울기)
        names    {"unit": "웨이퍼", "group": "장비", "sub": "척", "batch": "로트", "value": "어긋남"} — 글에 쓰는 이름
        unit_len(값 단위 · 예 "nm") · unit_pos(좌표 단위 · 예 "mm") · radius(판 반지름 — 그림 테두리 · 없으면 점 범위)
        spec     판 허용 — |평균| + 3σ 가 넘으면 재작업 · point_limit(선택 — 점 하나 허용 · 없으면 잔차 길이 평균 + 3σ)
        k(관리 한계 배수 · 기본 3) · ks(조건별 실행 배수 목록) · order(방안 B 차수 · 기본 3)
        short {장비 · "장비-하위": 짧은 이름}(선택) · flow(큰 흐름 상자 글 · 선택) · task(과제 이름)"""
    raise NotImplementedError("load() 를 과제에 맞게 고친다 — 예: 측정 csv 를 읽어 rows 를 만든다(demo() · fake_rows() 참고)")


# seed: 난수 씨앗 / n_batch: 묶음 수 / per_batch: 묶음당 판 수 / n_site: 판당 측정 칸 수 / groups: 장비 이름 / subs: 하위 단위 이름
# drift: (장비, 성분 이름, 끝 값) — 그 장비의 성분이 시간에 따라 0 → 끝 값 / bias: (장비, 하위, 성분 이름, 값) — 늘 치우침
def fake_rows(seed=7, n_batch=12, per_batch=4, n_site=20, groups=("E1", "E2", "E3"), subs=("A", "B"), drift=("E2", "rot", 0.04),
              bias=("E1", "B", "Tx", 4.0), radius=140.0, noise=1.0):
    """가짜 측정 줄 — 판마다 평행 이동 · 회전 · 배율 · 직교 + 공통 2차 휨 + 잡음. 묶음 하나 = 장비 하나(돌아가며) · 판은 하위 단위를 번갈아"""
    rng = random.Random(seed)
    # 측정 칸 — 동심원 위에 고르게(가운데 하나 포함)
    sites = [(0.0, 0.0)]
    rings = [(0.35, 6), (0.7, max(1, (n_site - 7) // 2)), (0.95, n_site - 7 - max(1, (n_site - 7) // 2))]
    for frac, cnt in rings:
        for j in range(cnt):
            a = 2 * math.pi * (j + 0.5 * (frac > 0.5)) / cnt
            sites.append((radius * frac * math.cos(a), radius * frac * math.sin(a)))
    rows = []
    # 장비마다 지금까지 처리한 묶음 수 — 드리프트 진행
    seen = {g: 0 for g in groups}
    n_of = {g: sum(1 for b in range(n_batch) if groups[b % len(groups)] == g) for g in groups}
    for b in range(n_batch):
        g = groups[b % len(groups)]
        prog = seen[g] / max(1, n_of[g] - 1)
        seen[g] += 1
        for w in range(per_batch):
            s = subs[w % len(subs)]
            comp = {"Tx": rng.gauss(0, 0.8), "Ty": rng.gauss(0, 0.8), "rot": rng.gauss(0, 0.004), "magx": rng.gauss(0.01, 0.004),
                    "magy": rng.gauss(0.01, 0.004), "orth": rng.gauss(0, 0.004)}
            if drift and g == drift[0]:
                comp[drift[1]] += drift[2] * prog
            if bias and g == bias[0] and s == bias[1]:
                comp[bias[2]] += bias[3]
            unit = f"B{b + 1:02d}-{w + 1:02d}"
            for x, y in sites:
                dx = comp["Tx"] + comp["magx"] * x - comp["rot"] * y + comp["orth"] * y / 2 + 1.5e-4 * x * x + rng.gauss(0, noise)
                dy = comp["Ty"] + comp["magy"] * y + comp["rot"] * x + comp["orth"] * x / 2 + 1.5e-4 * y * y + rng.gauss(0, noise)
                rows.append({"unit": unit, "group": g, "sub": s, "batch": f"B{b + 1:02d}", "t": b * per_batch + w, "x": round(x, 2), "y": round(y, 2),
                             "dx": round(dx, 3), "dy": round(dy, 3)})
    return rows


def demo():
    """작은 가짜 데이터(장비 3 × 하위 2 · 묶음 12 · 판 48 · 판당 20칸) — 틀이 도는지 보기만 한다. E2 회전이 흐르고 E1-B 가 x 로 치우쳤다"""
    return {"rows": fake_rows(), "vector": True, "names": {"unit": "판", "group": "장비", "sub": "하위", "batch": "묶음", "value": "어긋남"},
            "unit_len": "nm", "unit_pos": "mm", "radius": 150.0, "spec": 8.0, "k": 3, "ks": [2, 2.5, 3, 3.5], "order": 3}


# ════════════════════════════════════════════════════════════
# 성분 — 이름 · 글 · 단위 종류 · 바탕 모양(좌표 → (dx 몫, dy 몫))
# ════════════════════════════════════════════════════════════
# 벡터: dx = Tx + magx·x − rot·y + orth·y/2 · dy = Ty + magy·y + rot·x + orth·x/2 (1차 여섯 개 = dx · dy 각각 1 · x · y 와 같은 공간)
VECTOR = [("평행 이동", [("Tx", "이동 x", "len", lambda x, y: (1.0, 0.0)), ("Ty", "이동 y", "len", lambda x, y: (0.0, 1.0))]),
          ("회전", [("rot", "회전", "ang", lambda x, y: (-y, x))]),
          ("배율", [("magx", "배율 x", "ratio", lambda x, y: (x, 0.0)), ("magy", "배율 y", "ratio", lambda x, y: (0.0, y))]),
          ("직교", [("orth", "직교", "ang", lambda x, y: (y / 2, x / 2))])]
# 값 하나: v = off + tx·x + ty·y
SCALAR = [("평균", [("off", "평균", "len", lambda x, y: (1.0, 0.0))]),
          ("기울기", [("tx", "기울기 x", "ratio", lambda x, y: (x, 0.0)), ("ty", "기울기 y", "ratio", lambda x, y: (y, 0.0))])]


# inp: 입력 dict
def comps_of(inp):
    """입력 → 성분 목록(VECTOR | SCALAR)"""
    return VECTOR if inp.get("vector", True) else SCALAR


# inp: 입력 dict / kind: len · ratio · ang
def unit_of(inp, kind):
    """성분 값의 단위 글 — nm · mm 이면 배율 ppm · 각 µrad"""
    ul, up = inp.get("unit_len", ""), inp.get("unit_pos", "")
    if kind == "len":
        return ul
    if (ul, up) == ("nm", "mm"):
        return "ppm" if kind == "ratio" else "µrad"
    return f"{ul}/{up}" if ul and up else ""


# word: 낱말 / pair: "을/를" · "이/가" · "은/는" · "과/와"
def josa(word, pair):
    """받침에 맞는 조사를 붙인 글 — «직교를» · «회전을»"""
    a, b = pair.split("/")
    ch = str(word)[-1:]
    has = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 > 0
    return f"{word}{a if has else b}"


# s: 초
def sec_long(s):
    """초 → 시간 글 — 아주 긴 시간은 «약 10^N년»(_common.sec_text 는 일 단위 숫자가 끝없이 길어진다)"""
    if s < 86400 * 365 * 100:
        return C.sec_text(s)
    return f"약 10^{int(math.log10(s / (86400 * 365)))}년"


# v: 숫자
def num(v, nd=2):
    """글에 쓸 숫자 — 유효 자리를 남기고 반올림(작은 값은 자리를 더)"""
    if v == 0 or not math.isfinite(v):
        return 0
    d = max(nd, nd - int(math.floor(math.log10(abs(v)))) - 1) if abs(v) < 1 else nd - 1
    r = round(v, d)
    return int(r) if r == int(r) and abs(r) >= 1 else r


# ════════════════════════════════════════════════════════════
# 최소제곱 — 정규 방정식 + 가우스 소거(성분 20개 안팎이라 이걸로 충분)
# ════════════════════════════════════════════════════════════
# cols: 열 목록(열마다 식 수만큼 값) / vals: 식의 오른쪽 값
def lstsq(cols, vals):
    """제곱합이 가장 작은 계수 → 계수 목록. 열끼리 구분이 안 되면(좌표가 한 줄에 몰림 · 칸이 너무 적음) ValueError"""
    m = len(cols)
    N = [[sum(a * b for a, b in zip(cols[i], cols[j])) for j in range(m)] + [sum(a * v for a, v in zip(cols[i], vals))] for i in range(m)]
    # 기준 크기 — 거의 0 인 기둥을 가른다
    big = max(abs(N[i][i]) for i in range(m)) or 1.0
    for c in range(m):
        p = max(range(c, m), key=lambda r: abs(N[r][c]))
        if abs(N[p][c]) < big * 1e-12:
            raise ValueError("성분을 가를 수 없다 — 측정 칸이 한 줄에 몰렸거나 너무 적다")
        N[c], N[p] = N[p], N[c]
        for r in range(m):
            if r != c and N[r][c]:
                f = N[r][c] / N[c][c]
                N[r] = [a - f * b for a, b in zip(N[r], N[c])]
    return [N[i][m] / N[i][i] for i in range(m)]


# xs · ys: 좌표 / fns: 바탕 모양 목록 / vector: 벡터인가
def columns(xs, ys, fns, vector):
    """바탕 모양 → 최소제곱 열(벡터면 칸마다 dx 식 · dy 식 두 줄)"""
    out = []
    for f in fns:
        col = []
        for x, y in zip(xs, ys):
            bx, by = f(x, y)
            col += [bx, by] if vector else [bx]
        out.append(col)
    return out


# dx · dy: 값 / vector: 벡터인가
def stacked(dx, dy, vector):
    """식의 오른쪽 값(벡터면 dx, dy 번갈아)"""
    return [v for pair in zip(dx, dy) for v in pair] if vector else list(dx)


# xs · ys · dx · dy: 한 판의 칸 / comps: 성분 목록 / vector: 벡터인가
def fit_linear(xs, ys, dx, dy, comps, vector):
    """1차 분해 → ({성분 열쇠: 값}, [(성분 이름, [(열쇠, 값)], dx 몫, dy 몫)] — 빼는 순서)"""
    terms = [t for _, ts in comps for t in ts]
    coef = lstsq(columns(xs, ys, [t[3] for t in terms], vector), stacked(dx, dy, vector))
    val = {t[0]: c for t, c in zip(terms, coef)}
    parts = []
    for name, ts in comps:
        px = [sum(val[t[0]] * t[3](x, y)[0] for t in ts) for x, y in zip(xs, ys)]
        py = [sum(val[t[0]] * t[3](x, y)[1] for t in ts) for x, y in zip(xs, ys)]
        parts.append((name, [(t[0], val[t[0]]) for t in ts], px, py))
    return val, parts


# order: 차수 / scale: 좌표 나눌 값(조건수 — 3차 항이 너무 커지지 않게)
def poly_fns(order, scale, vector):
    """1차 ~ order 차 단항식 바탕 모양 — 벡터면 dx · dy 따로(같은 단항식 두 벌)"""
    mono = [(i, j) for d in range(order + 1) for i in range(d + 1) for j in [d - i]]
    out = []
    for i, j in mono:
        def f(x, y, i=i, j=j):
            return (x / scale) ** i * (y / scale) ** j
        out.append(lambda x, y, f=f: (f(x, y), 0.0))
        if vector:
            out.append(lambda x, y, f=f: (0.0, f(x, y)))
    return out


# xs · ys · dx · dy: 한 판의 칸 / order: 차수 / scale: 좌표 나눌 값
def resid_poly(xs, ys, dx, dy, order, scale, vector):
    """order 차까지 한꺼번에 최소제곱으로 뺀 잔차 → (dx, dy)"""
    fns = poly_fns(order, scale, vector)
    coef = lstsq(columns(xs, ys, fns, vector), stacked(dx, dy, vector))
    rx = [v - sum(c * f(x, y)[0] for c, f in zip(coef, fns)) for x, y, v in zip(xs, ys, dx)]
    ry = [v - sum(c * f(x, y)[1] for c, f in zip(coef, fns)) for x, y, v in zip(xs, ys, dy)]
    return rx, ry


# dx · dy: 값 / vector: 벡터인가
def m3s(dx, dy, vector):
    """판 하나의 |평균| + 3σ — 축마다 재고 큰 쪽(값 하나면 dx 만)"""
    out = []
    for v in ([dx, dy] if vector else [dx]):
        out.append(abs(statistics.fmean(v)) + 3 * statistics.pstdev(v))
    return max(out)


# dx · dy: 값
def mean_len(dx, dy):
    """화살표 길이 평균"""
    return statistics.fmean(math.hypot(a, b) for a, b in zip(dx, dy))


# ════════════════════════════════════════════════════════════
# 판마다 분해 — 방안 A(1차) · 방안 B(고차)
# ════════════════════════════════════════════════════════════
# inp: 입력 dict
def units(inp):
    """측정 줄 → 판 목록(시간순) [{"unit", "group", "sub", "key"(장비-하위), "batch", "t", "x", "y", "dx", "dy"}]"""
    by = {}
    for r in inp["rows"]:
        u = by.setdefault(r["unit"], {"unit": r["unit"], "group": r["group"], "sub": r.get("sub"), "batch": r.get("batch", ""), "t": r.get("t", 0),
                                      "x": [], "y": [], "dx": [], "dy": []})
        u["x"].append(float(r["x"]))
        u["y"].append(float(r["y"]))
        u["dx"].append(float(r["dx"]))
        u["dy"].append(float(r.get("dy", 0.0)))
    out = sorted(by.values(), key=lambda u: (u["t"], str(u["unit"])))
    for u in out:
        u["key"] = f"{u['group']}-{u['sub']}" if u["sub"] not in (None, "") else str(u["group"])
    return out


# inp: 입력 dict / us: 판 목록
def decompose(inp, us):
    """판마다 1차 분해 · 잔차 · 고차 잔차 · |평균| + 3σ 를 판 dict 에 더한다"""
    vec, comps = inp.get("vector", True), comps_of(inp)
    order = inp.get("order", 3)
    scale = inp.get("radius") or max(max(abs(v) for v in u["x"] + u["y"]) for u in us) or 1.0
    for u in us:
        val, parts = fit_linear(u["x"], u["y"], u["dx"], u["dy"], comps, vec)
        u["coef"], u["parts"] = val, parts
        u["rx"] = [v - sum(p[2][i] for p in parts) for i, v in enumerate(u["dx"])]
        u["ry"] = [v - sum(p[3][i] for p in parts) for i, v in enumerate(u["dy"])]
        u["m_raw"] = m3s(u["dx"], u["dy"], vec)
        u["m_A"] = m3s(u["rx"], u["ry"], vec)
        # 차수마다 고차 잔차(칸이 모자라면 그 차수까지만)
        u["hi"] = {}
        for o in range(2, order + 1):
            n_par = (o + 1) * (o + 2) // 2 * (2 if vec else 1)
            if len(u["dx"]) * (2 if vec else 1) >= 2 * n_par:
                u["hi"][o] = resid_poly(u["x"], u["y"], u["dx"], u["dy"], o, scale, vec)
        top = max(u["hi"]) if u["hi"] else None
        u["m_B"] = m3s(*u["hi"][top], vec) if top else u["m_A"]
    return us


# ════════════════════════════════════════════════════════════
# 관리도 — 성분마다 평균 ± kσ(σ = 이웃 차이) · 이탈 · 치우침 / 드리프트 판정
# ════════════════════════════════════════════════════════════
# inp: 입력 dict
def metrics(inp):
    """관리도에 올리는 값 → [(열쇠, 글, 단위)] — 1차 성분 전부 + 잔차(|평균| + 3σ)"""
    out = [(t[0], t[1], unit_of(inp, t[2])) for _, ts in comps_of(inp) for t in ts]
    return out + [("res", "잔차", inp.get("unit_len", ""))]


# u: 판 / m: 값 열쇠
def value(u, m):
    """판의 관리도 값"""
    return u["m_A"] if m == "res" else u["coef"][m]


# us: 판 목록 / m: 값 열쇠
def limits(us, m, k):
    """(가운데, σ) — 가운데 = 전체 평균 · σ = 하위 단위마다 시간순 이웃 차이의 평균 ÷ 1.128"""
    vals = [value(u, m) for u in us]
    mr = []
    for key in dict.fromkeys(u["key"] for u in us):
        seq = [value(u, m) for u in us if u["key"] == key]
        mr += [abs(b - a) for a, b in zip(seq, seq[1:])]
    sig = (statistics.fmean(mr) / D2) if mr else statistics.pstdev(vals)
    return statistics.fmean(vals), sig or 1e-12


# seq: 시간순 값
def trend(seq):
    """시간순 값의 직선 기울기 × (개수 − 1) = 처음부터 끝까지 바뀐 양"""
    n = len(seq)
    if n < 3:
        return 0.0
    xm, ym = (n - 1) / 2, statistics.fmean(seq)
    sxx = sum((i - xm) ** 2 for i in range(n))
    return sum((i - xm) * (v - ym) for i, v in enumerate(seq)) / sxx * (n - 1)


# inp: 입력 dict / us: 판 목록 / k: 한계 배수
def chart_all(inp, us, k):
    """모든 값의 관리도 → {"lim": {열쇠: (가운데, σ)}, "out": {열쇠: {판 번호}}, "found": [찾은 곳]}
    찾은 곳 = 장비(하위 단위 전부가 걸렸거나 하위가 없을 때) 또는 하위 단위 — 그 줄 판의 25% 이상(3장 이상)이 한계 밖
    종류 = 드리프트(처음 → 끝 변화가 평균 치우침보다 크다 — 갈수록 밖) / 치우침(늘 밖)"""
    lim, out, found = {}, {}, []
    groups = list(dict.fromkeys(u["group"] for u in us))
    for m, label, unit in metrics(inp):
        c, s = limits(us, m, k)
        lim[m] = (c, s)
        out[m] = {i for i, u in enumerate(us) if abs(value(u, m) - c) > k * s}

        # level: group · key / name: 이름
        def flagged(level, name):
            idx = [i for i, u in enumerate(us) if u[level] == name]
            n_out = sum(1 for i in idx if i in out[m])
            return n_out >= max(FLAG_MIN, FLAG_FRAC * len(idx)), idx, n_out

        for g in groups:
            keys = list(dict.fromkeys(u["key"] for u in us if u["group"] == g))
            subs = [kk for kk in keys if flagged("key", kk)[0]] if keys != [g] else []
            g_ok, g_idx, g_out = flagged("group", g)
            hits = []
            if subs and len(subs) < len(keys):  # 하위 일부만 — 그 하위만
                hits = [("key", kk) for kk in subs]
            elif g_ok or subs:
                hits = [("group", g)]
            for level, name in hits:
                _, idx, n_out = flagged(level, name)
                seq = [value(us[i], m) for i in idx]
                ch, off = trend(seq), statistics.fmean(seq) - c
                found.append({"level": level, "name": name, "metric": m, "label": label, "unit": unit, "out": n_out, "n": len(idx),
                              "kind": "드리프트" if abs(ch) >= abs(off) else "치우침", "change": ch, "offset": off, "sigma": s,
                              "first": next((r for r, i in enumerate(idx) if i in out[m]), None)})
    found.sort(key=lambda f: -f["out"] / f["n"])
    return {"lim": lim, "out": out, "found": found}


# ════════════════════════════════════════════════════════════
# 전부 세기 — 성분 값을 후보 격자로 전부 대 보기
# ════════════════════════════════════════════════════════════
# u: 판 / inp: 입력 dict / unit: 단위 글
def brute_grid(u, inp):
    """성분 k 개의 후보(하나에 21개)를 전부 대 보고 제곱합이 가장 작은 것을 찾는 시간 — 작은 k 는 실측, 큰 k 는 가짓수 비율로 추정
    → (표 칸, 실측 {k: 초}, 최소제곱 한 번 초)"""
    vec, comps = inp.get("vector", True), comps_of(inp)
    terms = [t for _, ts in comps for t in ts]
    cols = columns(u["x"], u["y"], [t[3] for t in terms], vec)
    vals = stacked(u["dx"], u["dy"], vec)
    best = lstsq(cols, vals)
    sec = {}
    for k in range(1, len(terms) + 1):
        if GRID ** k > BRUTE_LIMIT:
            break
        # 성분마다 후보 — 최소제곱 값 둘레 21개(격자 탐색이 같은 답 근처를 찾게)
        cand = [[best[j] * (1 + (g - GRID // 2) / (GRID // 2)) for g in range(GRID)] for j in range(k)]
        rest = [v - sum(best[j] * cols[j][i] for j in range(k, len(terms))) for i, v in enumerate(vals)]
        t0 = time.perf_counter()
        min(itertools.product(*cand), key=lambda cs: sum((r - sum(c * cols[j][i] for j, c in enumerate(cs))) ** 2 for i, r in enumerate(rest)))
        sec[k] = time.perf_counter() - t0
    kmax = max(sec)
    t0 = time.perf_counter()
    for _ in range(20):
        lstsq(cols, vals)
    lsq = (time.perf_counter() - t0) / 20
    n_all = len(terms)
    n_b = n_all + sum(1 for o in range(2, inp.get("order", 3) + 1) for _ in range(o + 1)) * (2 if vec else 1)
    rows = [[f"{k}개", f"{GRID ** k:,}", C.sec_text(s), "실측"] for k, s in sec.items()]
    rows += [[f"{k}개", f"{GRID ** k:,}", sec_long(sec[kmax] * GRID ** (k - kmax)), f"추정({kmax}개의 시간 × 가짓수 비율)"]
             for k in sorted({n_all, n_b}) if k > kmax]
    bad = [[i, "전부 대 보는 데 걸린 시간"] for i, r in enumerate(rows) if r[3] != "실측"]
    return ({"header": ["성분 수", f"후보 조합 가짓수(성분 하나에 {GRID}개)", "전부 대 보는 데 걸린 시간", "구분"], "rows": rows, "small": True, "bad_cells": bad,
             "caption": f"성분 수에 따라 «후보를 전부 대 보기» 가 걸리는 시간 — 최소제곱은 한 번에 {C.sec_text(lsq)}"}, sec, lsq)


# ════════════════════════════════════════════════════════════
# 재생기 칸
# ════════════════════════════════════════════════════════════
# inp: 입력 dict / u: 판
def plate(inp, u, peak):
    """화살표 지도 판 칸 — 가장 긴 화살표(peak)가 판 지름의 약 1/8 이 되게 배율"""
    R = inp.get("radius") or max(math.hypot(x, y) for x, y in zip(u["x"], u["y"])) * 1.05
    # 눈금 화살표 값 — 1 · 2 · 5 × 10^n 중 가장 긴 화살표 이하
    bar = max([v * 10 ** e for e in range(-3, 4) for v in (1, 2, 5) if v * 10 ** e <= max(peak, 1e-9)] or [peak])
    return {"x": u["x"], "y": u["y"], "radius": R, "scale": 26 / max(peak, 1e-9), "bar": num(bar), "unit": inp.get("unit_len", "")}


# inp: 입력 dict / u: 판 / nm: 이름 표
def fill_player(inp, u, nm):
    """재생기 1 «채우기» — 성분을 하나씩 빼는 화살표 지도"""
    vec, ul = inp.get("vector", True), inp.get("unit_len", "")
    dx, dy = list(u["dx"]), list(u["dy"])
    peak = max(math.hypot(a, b) for a, b in zip(dx, dy))
    P = plate(inp, u, peak)
    names = [p[0] for p in u["parts"]]
    steps, rows = [], []
    l0 = mean_len(dx, dy)

    # done: 뺀 성분 수
    def lines(done):
        out = []
        for i, (name, kv, _, _) in enumerate(u["parts"]):
            vals = " · ".join(f"{num(v)}" for _, v in kv)
            units = unit_of(inp, next(t[2] for _, ts in comps_of(inp) for t in ts if t[0] == kv[0][0]))
            mark = "✓ " if i < done else ("▶ " if i == done else "")
            out.append([f"{mark}{name} {vals} {units}", "#9aa3ad" if i < done - 1 else (C.COLORS[0] if i == done - 1 else "#374151")])
        out.append([f"남은 길이 평균 {num(mean_len(dx, dy))} {ul}", "#111827"])
        return out

    steps.append({"dx": list(dx), "dy": list(dy), "head": f"{nm['unit']} {u['unit']} — 잰 그대로", "row": 0, "lines": lines(0),
                  "text": f"**{nm['unit']} {u['unit']} 의 {nm['value']}** — 칸 {len(dx)}곳 · 화살표 길이 평균 **{num(l0)} {ul}**. 한 단계에 성분 하나씩 빼 본다."})
    rows.append(["0", "—", "—", f"{num(l0)}"])
    for i, (name, kv, px, py) in enumerate(u["parts"]):
        before = mean_len(dx, dy)
        dx = [a - b for a, b in zip(dx, px)]
        dy = [a - b for a, b in zip(dy, py)]
        after = mean_len(dx, dy)
        unit = unit_of(inp, next(t[2] for _, ts in comps_of(inp) for t in ts if t[0] == kv[0][0]))
        vals = " · ".join(f"{num(v)}" for _, v in kv)
        txt = f"**{josa(name, '을/를')} 뺀다** — {vals} {unit}. 길이 평균 {num(before)} → **{num(after)} {ul}**."
        if i == len(names) - 1:
            txt += f" 남은 것 = 1차로 못 빼는 **잔차**(|평균| + 3σ {num(u['m_A'])} {ul})."
        steps.append({"dx": dx, "dy": dy, "head": f"{name}까지 뺌 — 길이 평균 {num(after)} {ul}", "row": i + 1, "lines": lines(i + 1), "text": txt})
        rows.append([str(i + 1), name, f"{vals} {unit}", f"{num(after)}"])
    return {"kind": "quiver", "title": f"{nm['value']}을 성분으로 나누기 — 한 단계에 하나씩 뺀다", "task": "다음을 눌러 가며 → 어느 성분을 뺄 때 화살표가 가장 많이 줄어드는지 봐",
            "caption": f"점 = 측정 칸 · 화살표 = 그 칸의 {nm['value']}(길이를 키워 그렸다 · 왼쪽 아래 눈금) · 오른쪽 = 성분 값", "auto_ms": 1300,
            "plate": P, "frame_title": "1차 성분 빼기", "right_title": "성분(최소제곱 값)", "steps": steps,
            "table": {"header": ["#", "뺀 성분", "값", f"남은 길이 평균({ul})"], "rows": rows[:MAX_TABLE], "small": True}}


# inp: 입력 dict / u: 판 / nm: 이름 표 / plim: 점 허용 / peak: 채우기 그림의 가장 긴 화살표(같은 배율로 그리지 않는다 — 잔차는 작아 따로)
def fix_player(inp, u, nm, plim):
    """재생기 2 «고치기» — 1차 잔차에서 고차 성분을 더 빼는 잔차 지도(점 허용보다 긴 화살표 빨강)"""
    vec, ul = inp.get("vector", True), inp.get("unit_len", "")
    seq = [("1차까지 뺀 잔차", u["rx"], u["ry"])] + [(f"{o}차까지 뺀 잔차", *u["hi"][o]) for o in sorted(u["hi"])]
    peak = max(math.hypot(a, b) for a, b in zip(u["rx"], u["ry"]))
    P = plate(inp, u, peak)
    steps, rows = [], []
    prev = None
    for no, (name, rx, ry) in enumerate(seq):
        m = m3s(rx, ry, vec)
        over = sum(1 for a, b in zip(rx, ry) if math.hypot(a, b) > plim)
        lines = [[f"{'▶ ' if j == no else ''}{s[0]}  {num(m3s(s[1], s[2], vec))}", C.COLORS[0] if j == no else ("#9aa3ad" if j < no else "#374151")]
                 for j, s in enumerate(seq)]
        lines.append([f"점 허용 {num(plim)} {ul} 넘는 칸 {over}", "#dc2626" if over else "#16a34a"])
        if no == 0:
            txt = f"**출발점 — 방안 A 의 잔차.** |평균| + 3σ **{num(m)} {ul}** · 점 허용 넘는 칸 {over}곳. 차수를 하나씩 올려 더 뺀다."
        else:
            txt = f"**{name.split('까지')[0]} 항을 더 뺀다** — |평균| + 3σ {num(prev)} → **{num(m)} {ul}** · 넘는 칸 {over}곳."
            if no == len(seq) - 1:
                txt += " 남은 것은 잡음에 가깝다." if over == 0 else " !!그래도 넘는 칸이 남는다!! — 칸마다 따로 보정하는 수준."
        steps.append({"dx": list(rx), "dy": list(ry), "head": f"{nm['unit']} {u['unit']} · {name} — |평균| + 3σ {num(m)} {ul}", "row": no, "lines": lines, "limit": plim, "text": txt})
        rows.append([str(no) if no else "출발", name, f"{num(m)}", str(over)])
        prev = m
    return {"kind": "quiver", "title": "잔차 지도 — 고차 성분까지 빼기", "task": "다음을 눌러 가며 → 빨간 화살표(점 허용을 넘는 칸)가 판의 어디에 남는지 봐",
            "caption": f"화살표 = 1차 성분을 빼고 남은 {nm['value']}(채우기 그림보다 크게 키웠다 · 왼쪽 아래 눈금) · 빨강 = 점 허용 {num(plim)} {ul} 넘음", "auto_ms": 1300,
            "plate": P, "right_title": f"차수별 |평균| + 3σ({ul})", "steps": steps,
            "table": {"header": ["#", "뺀 것", f"|평균| + 3σ({ul})", "허용 넘는 칸"], "rows": rows[:MAX_TABLE], "small": True}}


# inp: 입력 dict / us: 판 목록 / ch: chart_all 결과 / m: 값 열쇠 / level: group · key / k: 한계 배수 / nm: 이름 표 / sh: 짧은 이름
def chart_player(inp, us, ch, m, level, k, nm, sh):
    """재생기 3 «이어 붙이기» — 관리도. 묶음(로트) 하나씩 시간순으로 점을 찍는다(줄 = 장비 또는 하위 단위)"""
    c, s = ch["lim"][m]
    label, unit = next((lb, un) for mm, lb, un in metrics(inp) if mm == m)
    series = list(dict.fromkeys(u[level] for u in us))[:MAX_SERIES]
    pts = [[i, round(value(u, m), 6), series.index(u[level]), i in ch["out"][m]] for i, u in enumerate(us) if u[level] in series]
    batches = list(dict.fromkeys(u["batch"] for u in us))
    per = math.ceil(len(batches) / MAX_CHART_STEPS)
    chunks = [batches[i:i + per] for i in range(0, len(batches), per)]
    steps, heads, texts = [], [], []
    n_out = {sr: 0 for sr in series}
    n_all = {sr: 0 for sr in series}
    for chunk in chunks:
        idx = [p_no for p_no, p in enumerate(pts) if us[p[0]]["batch"] in chunk]
        steps.append(idx)
        for p_no in idx:
            n_all[series[pts[p_no][2]]] += 1
            n_out[series[pts[p_no][2]]] += pts[p_no][3]
        who = list(dict.fromkeys(series[pts[p][2]] for p in idx))
        bad = [series[pts[p][2]] for p in idx if pts[p][3]]
        b_txt = chunk[0] if len(chunk) == 1 else f"{chunk[0]}~{chunk[-1]}"
        heads.append(f"{nm['batch']} {b_txt} — {label}")
        t = f"**{nm['batch']} {b_txt}** ({' · '.join(sh.get(w, w) for w in who)}) {nm['unit']} {len(idx)}장을 찍는다 — "
        t += (f"!!한계 밖 {len(bad)}장!!({' · '.join(sorted({sh.get(b, b) for b in bad}))})." if bad else "전부 한계 안.")
        texts.append(t)
    worst = max(series, key=lambda sr: n_out[sr])
    heads.append(f"다 찍은 결과 — {label}")
    texts.append(f"이탈 {sum(n_out.values())}점 중 **{sh.get(worst, worst)} {n_out[worst]}점**. 한계 = 평균 {num(c)} ± {k}σ(σ {num(s)} {unit} — 이웃한 두 {nm['unit']}의 차이로 잰 값).")
    first = min(p[0] for p in pts)
    last = max(p[0] for p in pts)
    tick_at = [next(p[0] for p in pts if us[p[0]]["batch"] == ck[0]) for ck in chunks]
    every = max(1, math.ceil(len(chunks) / 8))
    T = {"points": pts, "series": [sh.get(sr, sr) for sr in series], "steps": steps, "center": c, "ucl": c + k * s, "lcl": c - k * s, "k": k,
         "unit": unit, "axis": [first, last], "ticks": [[tick_at[i], chunks[i][0]] for i in range(0, len(chunks), every)],
         "words": {"line": "{mark}{name}  이탈 {out}/{n}", "ucl": "위 한계 {v}", "lcl": "아래 한계 {v}", "center": "평균 {v}"}}
    return {"kind": "chart", "title": f"관리도 — {label}({unit})를 시간순으로 찍기", "task": f"다음을 눌러 가며 → 빨간 고리가 처음 생기는 {nm['batch']}와 그 뒤로 어느 줄이 계속 밖인지 봐",
            "caption": f"점 하나 = {nm['unit']} 하나의 {label} 값 · 색 = {nm['group'] if level == 'group' else nm['group'] + '-' + nm['sub']} · 빨간 점선 = 평균 ± {k}σ · 빨간 고리 = 한계 밖",
            "auto_ms": 1300, "chart": T, "heads": heads, "texts": texts}


# inp: 입력 dict / u: 판 / nm: 이름 표
def small_case(inp, u, nm):
    """가장 작은 경우 — 성분 하나(평행 이동 x)를 후보 일곱 개로 대 본다 → (순서 표 칸, 순서 지도 칸("arrows"), 행 [(후보, 제곱합)])"""
    ul = inp.get("unit_len", "")
    best = statistics.fmean(u["dx"])
    spread = statistics.pstdev(u["dx"]) or 1.0
    step = max([v * 10 ** e for e in range(-3, 4) for v in (1, 2, 5) if v * 10 ** e <= spread / 2] or [spread / 2])
    c0 = round(best / step) * step
    cand = [round(c0 + (j - 3) * step, 6) for j in range(7)]
    rows = [(c, sum((v - c) ** 2 for v in u["dx"])) for c in cand]
    gi = min(range(7), key=lambda i: rows[i][1])
    bi = max(range(7), key=lambda i: rows[i][1])
    tab = {"header": [f"{nm['value']} x 를 이만큼 뺀다면({ul})", "남는 제곱합"], "rows": [[f"{num(c)}", f"{num(s, 3)}"] for c, s in rows], "good_rows": [gi],
           "bad_rows": [bi], "notes": {gi: ["← 가장 작다", "good"], bi: ["← 가장 크다", "bad"]}, "small": True}
    # 이 경우는 x 하나만 바꾸므로 x 몫만 그린다(y 는 두 판이 같아 차이를 가린다)
    gx, bx = [v - rows[gi][0] for v in u["dx"]], [v - rows[bi][0] for v in u["dx"]]
    peak = max(abs(v) for v in gx + bx)
    fig = {"kind": "arrows", "x": u["x"], "y": u["y"], "radius": inp.get("radius") or max(math.hypot(x, y) for x, y in zip(u["x"], u["y"])) * 1.05,
           "scale": 18 / max(peak, 1e-9), "unit": f"{ul} · x 몫만",
           "good": {"dx": gx, "dy": [0.0] * len(gx), "label": f"{num(rows[gi][0])} 뺌 → {num(rows[gi][1], 3)}"},
           "bad": {"dx": bx, "dy": [0.0] * len(bx), "label": f"{num(rows[bi][0])} 뺌 → {num(rows[bi][1], 3)}"},
           "label": "후보 둘을 뺀 화살표"}
    return tab, fig, rows


# ════════════════════════════════════════════════════════════
# 실행
# ════════════════════════════════════════════════════════════
# inp: 입력 dict
def run(inp):
    """입력 → steps.json dict"""
    vec, ul = inp.get("vector", True), inp.get("unit_len", "")
    nm = {"unit": "판", "group": "장비", "sub": "하위", "batch": "묶음", "value": "값", **inp.get("names", {})}
    sh = inp.get("short", {})
    k, spec = inp.get("k", 3), inp.get("spec")
    us = decompose(inp, units(inp))
    ch = chart_all(inp, us, k)
    # 보여 줄 판 — 1차 성분이 가장 큰(화살표가 성분을 뺄 때 크게 줄어드는) 판
    u = max(us, key=lambda x: mean_len(x["dx"], x["dy"]) - mean_len(x["rx"], x["ry"]))
    # 점 허용 — 입력 또는 1차 잔차 길이 평균 + 3σ(전체 칸)
    lens = [math.hypot(a, b) for x in us for a, b in zip(x["rx"], x["ry"])]
    plim = inp.get("point_limit") or statistics.fmean(lens) + 3 * statistics.pstdev(lens)
    pf = fill_player(inp, u, nm)
    # 잔차 지도의 판 — 1차 잔차가 가장 큰 판(빨간 화살표 · 고차로 줄어드는 몫이 가장 잘 보인다)
    u_fix = max(us, key=lambda x: x["m_A"])
    px = fix_player(inp, u_fix, nm, plim)
    # 관리도 — 드리프트가 있으면 그것(시간 그림이 가장 잘 보인다) · 없으면 가장 많이 걸린 것 · 없으면 이탈 점이 가장 많은 값
    drifts = [f for f in ch["found"] if f["kind"] == "드리프트"]
    top = (drifts or ch["found"] or [None])[0]
    if top:
        m, level = top["metric"], top["level"] if top["level"] == "group" else "key"
    else:
        m, level = max(ch["out"], key=lambda mm: len(ch["out"][mm])), "group"
    if len({x[level] for x in us}) > MAX_SERIES:
        level = "group"
    pc = chart_player(inp, us, ch, m, level, k, nm, sh)

    # 조건별 실행 — 관리 한계 배수
    conds = []
    for kk in inp.get("ks", [k]):
        r = chart_all(inp, us, kk)
        conds.append({"name": "한계 배수", "value": f"±{kk}σ", "result": {"이탈 점": sum(len(v) for v in r["out"].values()), "잡은 곳": len(r["found"]),
                                                                       "잡은 곳 이름": " · ".join(f"{sh.get(f['name'], f['name'])} {f['label']}" for f in r["found"][:3]) or "—"}})
    ctab = C.conditions_table(conds, ["한계 배수", "이탈 점", "잡은 곳", "잡은 곳 이름"], ["이탈 점", "잡은 곳", "잡은 곳 이름"], None, None,
                              f"관리 한계 배수별 이탈 점 · 잡은 곳(기준 ±{k}σ)")

    # 4장 표 · 그림
    otab, ofig, orows = small_case(inp, u, nm)
    brute, sec, lsq = brute_grid(u, inp)
    # 큰 흐름 — 묶음을 시간순 12열 이하로 · 열마다 장비별 판 |평균| + 3σ 평균
    batches = list(dict.fromkeys(x["batch"] for x in us))
    per = math.ceil(len(batches) / 12)
    groups = list(dict.fromkeys(x["group"] for x in us))
    legend = [[sh.get(g, g), C.COLORS[i]] for i, g in enumerate(groups[:3])] if len(groups) <= 3 else [[f"전체 {nm['unit']}", C.COLORS[0]]]
    columns_ = []
    for i in range(0, len(batches), per):
        part = [x for x in us if x["batch"] in batches[i:i + per]]
        if len(groups) <= 3:
            vals = [round(statistics.fmean([x["m_raw"] for x in part if x["group"] == g]), 1) if any(x["group"] == g for x in part) else 0 for g in groups]
        else:
            vals = [round(statistics.fmean(x["m_raw"] for x in part), 1)]
        columns_.append({"label": batches[i], "sub": f"{len(part)}장", "values": vals})
    # 장비 · 하위 단위별 이탈 점(모든 값) — 걸린 줄 기준선
    keys = list(dict.fromkeys(x["key"] for x in us))
    bars = [{"label": sh.get(kk, kk), "value": sum(1 for mm in ch["out"] for i in ch["out"][mm] if us[i]["key"] == kk)} for kk in keys]
    n_med = statistics.median([sum(1 for x in us if x["key"] == kk) for kk in keys])
    bar_lim = max(FLAG_MIN, round(FLAG_FRAC * n_med))

    numbers = {"n_rows": len(inp["rows"]), "n_units": len(us), "n_groups": len(groups), "n_keys": len(keys), "n_batches": len(batches),
               "sites": round(statistics.median(len(x["dx"]) for x in us)), "k": k, "spec": spec, "point_limit": num(plim),
               "show_unit": u["unit"], "show_raw": num(mean_len(u["dx"], u["dy"])), "show_A": num(mean_len(u["rx"], u["ry"])),
               "show_m_raw": num(u["m_raw"]), "show_m_A": num(u["m_A"]), "show_m_B": num(u["m_B"]),
               "fix_unit": u_fix["unit"], "fix_m_A": num(u_fix["m_A"]), "fix_m_B": num(u_fix["m_B"]),
               "m_raw_avg": num(statistics.fmean(x["m_raw"] for x in us)), "m_A_avg": num(statistics.fmean(x["m_A"] for x in us)),
               "m_B_avg": num(statistics.fmean(x["m_B"] for x in us)), "n_alarm": sum(len(v) for v in ch["out"].values()), "n_found": len(ch["found"]),
               "chart_metric": next(lb for mm, lb, _ in metrics(inp) if mm == m), "chart_center": num(ch["lim"][m][0]),
               "chart_sigma": num(ch["lim"][m][1]), "chart_ucl": num(ch["lim"][m][0] + k * ch["lim"][m][1]), "chart_lcl": num(ch["lim"][m][0] - k * ch["lim"][m][1]),
               "brute_max_measured": max(sec), "brute_max_sec": round(sec[max(sec)], 4), "lsq_sec": round(lsq, 6),
               "order_best": num(min(r[1] for r in orows), 3), "order_worst": num(max(r[1] for r in orows), 3)}
    for t in [t for _, ts in comps_of(inp) for t in ts]:
        numbers[f"show_{t[0]}"] = num(u["coef"][t[0]])
    if spec is not None:  # 재작업 판정 — 잰 그대로 / 1차 보정 뒤 / 고차 보정 뒤
        numbers.update({"rework_raw": sum(x["m_raw"] > spec for x in us), "rework_A": sum(x["m_A"] > spec for x in us), "rework_B": sum(x["m_B"] > spec for x in us)})
    # 찾은 곳 — 이름 · 값 · 종류 · 이탈 수(앞 4개) + 종류별 첫째
    for i, f in enumerate(ch["found"][:4]):
        numbers.update({f"find{i + 1}_name": sh.get(f["name"], f["name"]), f"find{i + 1}_metric": f["label"], f"find{i + 1}_kind": f["kind"],
                        f"find{i + 1}_out": f["out"], f"find{i + 1}_n": f["n"], f"find{i + 1}_change": num(f["change"]), f"find{i + 1}_offset": num(f["offset"])})
    for kind, tag in (("드리프트", "drift"), ("치우침", "bias")):
        f = next((x for x in ch["found"] if x["kind"] == kind), None)
        numbers[f"{tag}_name"] = sh.get(f["name"], f["name"]) if f else "없음"
        numbers[f"{tag}_metric"] = f["label"] if f else "없음"
        numbers[f"{tag}_out"] = f["out"] if f else 0
        # 보정값 — 그 줄 평균의 부호를 뒤집은 값(치우침) · 드리프트는 마지막 묶음 값의 부호를 뒤집은 값
        if f:
            seq = [value(x, f["metric"]) for x in us if x[f["level"]] == f["name"]]
            numbers[f"{tag}_fix"] = num(-(statistics.fmean(seq) if kind == "치우침" else statistics.fmean(seq[-3:])))
            numbers[f"{tag}_unit"] = f["unit"]
    return {"contract": "steps", "version": 1, "type": "other", "task": inp.get("task", ""), "numbers": numbers,
            "players": {"채우기": pf, "고치기": px, "이어붙이기": pc},
            "figures": {"순서_지도": ofig,
                        "그림_큰흐름": C.overview_fig(columns_, f"{nm['batch']}별 {nm['unit']} |평균| + 3σ({ul}) — 시간순", legend, inp.get("flow")),
                        "시각막대": {"title": f"{nm['group']} · {nm['sub']}별 한계 밖 점 수(값 전부)", "bars": bars, "limit": bar_lim, "limit_label": f"기준 {bar_lim}점",
                                  "unit": "", "label": "줄별 이탈 수"}},
            "tables": {"순서_표": otab, "전부세기_표": brute, "조건별_표": ctab}, "conditions": conds}


# argv: 명령 인자 목록
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="분석 틀 ⑤ 측정 · 관리도형 → steps.json")
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
