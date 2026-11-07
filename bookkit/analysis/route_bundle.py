# -*- coding: utf-8 -*-
r"""분석 틀 ① 경로 · 묶기형 — 곳마다 수(사람 · 물건)가 있고, 정원이 있는 차로 묶어 돌린다 → steps.json

    python3 bookkit/analysis/route_bundle.py --demo --out <steps.json>                      작은 가짜 데이터로 돌려 본다
    python3 bookkit/analysis/route_bundle.py --book bookkit/books/<이름>                   책의 과제 자료로 → <책>/contracts/steps.json

쓰는 법(A3 카드): 이 파일을 <책>/work/a3.py 로 복사 → 아래 «입력 연결 칸» load() 만 과제에 맞게 고친다 → 돌린다 → 검사기
- 기본 규칙(방안 A) = 목적지에서 먼 곳부터 정원까지 담기 · 고치기(방안 B 의 속) = 한 곳씩 바꿔 총길이 줄이기 · 이어 붙이기 = 시간대별 경로를 차에 잇기
- 조건별 실행 = 정원(cap)을 바꿔 차 수 · 총길이 · 필요 대수
- 과제 내용은 load() 에만 들어간다(이 틀에는 특정 과제의 숫자 · 이름이 없다)
"""
import argparse
import sys
from pathlib import Path

# 이 파일이 있는 폴더 — 틀 폴더(bookkit/analysis) 또는 책의 work/(복사해 쓸 때)
HERE = Path(__file__).resolve().parent
# 분석 틀 공용(_common.py) — 위쪽 폴더에서 bookkit/analysis 를 찾는다(work/ 로 복사해도 그대로 돈다)
sys.path.insert(0, str(next((p / "analysis" for p in [HERE, *HERE.parents] if (p / "analysis" / "_common.py").is_file()), HERE)))
sys.path.insert(0, str(HERE))
import _common as C  # noqa: E402


# ════════════════════════════════════════════════════════════
# 입력 연결 칸 — 과제마다 고친다(이 함수만)
# ════════════════════════════════════════════════════════════
def load(task):
    """과제 폴더 → 입력 dict
        points  {곳: (y, x)}      — 위도 · 경도면 geo=True
        demand  {곳: 수}          — 한 묶음(같은 시각 · 같은 목적지)에 태울 수
        end     (y, x) | None    — 공동 목적지(없으면 None — 경로가 마지막 곳에서 끝난다)
        end_label · cap(정원) · have(보유 대수) · geo · short {곳: 짧은 이름} · veh(차 이름) · unit(수 단위)
        waves   [{"label", "start": 분, "demand": {곳: 수}}] — 하루의 묶음들(이어 붙이기용 · 없으면 demand 하나만)
        speed   거리 1 당 분(이동 시간 = 거리 × speed)
        caps    조건별 실행에 쓸 정원 목록"""
    raise NotImplementedError("load() 를 과제에 맞게 고친다 — 예: csv 를 읽어 points · demand 를 만든다(demo() 참고)")


def demo():
    """작은 가짜 데이터(평면 좌표) — 틀이 도는지 보기만 한다"""
    pts = {"P1": (2.0, 1.0), "P2": (4.0, 2.0), "P3": (5.0, 5.0), "P4": (3.0, 7.0), "P5": (1.0, 8.0), "P6": (6.0, 8.0), "P7": (7.0, 3.0), "P8": (8.0, 6.0)}
    dem = {"P1": 4, "P2": 6, "P3": 5, "P4": 7, "P5": 3, "P6": 6, "P7": 5, "P8": 4}
    waves = [{"label": "1차", "start": 360, "demand": dem}, {"label": "2차", "start": 400, "demand": {k: max(1, v - 2) for k, v in dem.items()}},
             {"label": "3차", "start": 470, "demand": {k: v for k, v in dem.items() if k in ("P2", "P3", "P6", "P8")}}]
    return {"points": pts, "demand": dem, "end": (0.0, 4.0), "end_label": "목적지", "cap": 12, "have": 5, "geo": False,
            "short": {k: k for k in pts}, "veh": "차", "unit": "명", "waves": waves, "speed": 3.0, "caps": [8, 10, 12, 15]}


# ════════════════════════════════════════════════════════════
# 기본 규칙(방안 A) — 목적지에서 먼 곳부터 정원까지
# ════════════════════════════════════════════════════════════
def rule_far_first(points, demand, end, cap, geo):
    """먼 곳부터 차에 담는다 — 차가 차면 다음 차. 한 곳 수가 정원보다 많으면 나눠 담는다 → [(차, 곳, 수)]"""
    ref = end if end is not None else (sum(p[0] for p in points.values()) / len(points), sum(p[1] for p in points.values()) / len(points))
    order = sorted(demand, key=lambda n: -C.dist(points[n], ref, geo))
    steps, b, load = [], 0, 0
    for n in order:
        left = demand[n]
        while left > 0:
            if load == cap:
                b, load = b + 1, 0
            take = min(left, cap - load)
            steps.append((b, n, take))
            load += take
            left -= take
    return steps


def plan(inp, cap):
    """정원 cap 으로 방안 A → 고치기 → (차 수, A 총길이, 고친 뒤 총길이)"""
    pts, end, geo = inp["points"], inp["end"], inp["geo"]
    cost = lambda names: C.route_len(names, pts, end, geo)  # noqa: E731
    steps = rule_far_first(pts, inp["demand"], end, cap, geo)
    nv = 1 + max(b for b, _, _ in steps)
    st = [[] for _ in range(nv)]
    for b, n, c in steps:
        st[b].append([n, c])
    rec = C.local_search(st, cost, cap, max_steps=50)
    return nv, rec[0][3], rec[-1][3]


def run(inp):
    """입력 → steps.json dict"""
    pts, dem, end, geo, cap = inp["points"], inp["demand"], inp["end"], inp["geo"], inp["cap"]
    veh, unit, sh = inp.get("veh", "차"), inp.get("unit", "명"), inp.get("short", {})
    cost = lambda names: C.route_len(names, pts, end, geo)  # noqa: E731
    M = C.map_spec(pts, dem, sh, end, inp.get("end_label", ""), geo)
    fsteps = rule_far_first(pts, dem, end, cap, geo)
    nv = 1 + max(b for b, _, _ in fsteps)
    pf, state = C.fill_player(fsteps, nv, M, cap, unit, veh, cost, f"먼 곳부터 {sum(dem.values())}{unit}을 {veh}에 채우는 과정",
                              f"다음을 눌러 가며 → {veh}가 바뀔 때 지도의 선이 어느 방향으로 꺾이는지 봐", "먼 곳부터 채우는 중")
    rec = C.local_search(state, cost, cap)
    px = C.fix_player(rec, M, cost, veh, unit, "한 곳씩 고치기 — 채우기 결과에서 출발", "다음을 눌러 가며 → 굵어진 선이 어떻게 곧아지는지, 표의 총합이 얼마나 주는지 봐")
    # 이어 붙이기 — 묶음마다 방안 A 경로를 일(트립)로
    trips, spd = [], inp.get("speed", 1.0)
    end_name = "END"
    for w in inp.get("waves") or [{"label": "", "start": 0, "demand": dem}]:
        ws = rule_far_first(pts, w["demand"], end, cap, geo)
        for b in range(1 + max(x[0] for x in ws)):
            names = []
            for x in ws:
                if x[0] == b and (not names or names[-1] != x[1]):
                    names.append(x[1])
            dur = cost(names) * spd
            trips.append({"start": round(w["start"] - dur), "end": round(w["start"]), "frm": names[0], "to": end_name if end is not None else names[-1],
                          "color": "#2563eb"})
    allp = dict(pts)
    if end is not None:
        allp[end_name] = end
    places = sorted({t["frm"] for t in trips} | {t["to"] for t in trips})
    dh = {a: {b: round(C.dist(allp[a], allp[b], geo) * spd, 1) for b in places} for a in places}
    names = {p: sh.get(p, p) for p in places}
    names[end_name] = inp.get("end_label", end_name)
    pc, nb = C.chain_player(trips, dh, names, inp.get("have", nv), veh, "경로", f"경로를 {veh}에 이어 붙이는 과정",
                            f"다음을 눌러 가며 → {veh}가 새로 생기는 순간, 다른 {veh}들이 어디에 있는지 오른쪽을 봐")
    # 4장 표 · 그림
    names_all = sorted(pts, key=lambda n: -dem.get(n, 0))
    brute, sec = C.brute_table(names_all, cost)
    three = names_all[:3]
    otab, ofig, orows = C.orders_example(three, pts, end, inp.get("end_label", ""), sh, geo)
    conds = []
    for c in inp.get("caps", [cap]):
        n_v, a_len, b_len = plan(inp, c)
        conds.append({"name": "정원", "value": f"{c}{unit}", "result": {"차 수": n_v, "방안 A 총길이": round(a_len, 1), "고친 뒤 총길이": round(b_len, 1)}})
    ctab = C.conditions_table(conds, ["정원", "차 수", "방안 A 총길이", "고친 뒤 총길이"], ["차 수", "방안 A 총길이", "고친 뒤 총길이"], "차 수", inp.get("have"),
                              f"정원별 차 수 · 총길이(보유 {inp.get('have')}대 — 넘으면 빨강)")
    numbers = {"n_places": len(pts), "n_demand": sum(dem.values()), "cap": cap, "have": inp.get("have"), "A_vehicles": nv,
               "A_len": round(rec[0][3], 1), "B_len": round(rec[-1][3], 1), "B_moves": len(rec) - 1, "chain_vehicles": nb, "n_trips": len(trips),
               "brute_max_measured": max(sec), "brute_max_sec": round(sec[max(sec)], 4),
               "order_best": round(min(r[1] for r in orows), 1), "order_worst": round(max(r[1] for r in orows), 1)}
    return {"contract": "steps", "version": 1, "type": "route", "task": inp.get("task", ""), "numbers": numbers,
            "players": {"채우기": pf, "고치기": px, "이어붙이기": pc},
            "figures": {"순서_지도": ofig,
                        "그림_큰흐름": C.overview_fig([{"label": C.hm(w["start"]), "sub": w["label"], "values": [sum(w["demand"].values())]}
                                                    for w in inp.get("waves") or [{"label": "", "start": 0, "demand": dem}]],
                                                   f"묶음별 {unit} 수 — 시각순", [[f"{unit} 수", "#2563eb"]], inp.get("flow")),
                        "시각막대": C.busy_bars([(t["start"], t["end"]) for t in trips], min(t["start"] for t in trips) // 60 * 60,
                                             max(t["end"] for t in trips) + 1, 30, inp.get("have"), f"보유 {inp.get('have')}대", f"시각마다 달리는 {veh} 수")},
            "tables": {"순서_표": otab, "전부세기_표": brute, "조건별_표": ctab}, "conditions": conds}


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="분석 틀 ① 경로 · 묶기형 → steps.json")
    ap.add_argument("--demo", action="store_true", help="작은 가짜 데이터로")
    ap.add_argument("--book", help="책 폴더(과제 폴더는 content/data.py 의 TASK_DIR 또는 위쪽에서 찾는다)")
    ap.add_argument("--task", help="과제 폴더(README.md · uploads/)")
    ap.add_argument("--out", help="출력 steps.json(기본 <책>/contracts/steps.json)")
    a = ap.parse_args(argv)
    if not a.book and not a.demo and HERE.name == "work":  # 책의 work/ 에서 돌리면 그 책
        a.book = str(HERE.parent)
    inp = demo() if a.demo else load(C.task_dir(a.book, a.task))
    out = a.out or (Path(a.book) / "contracts" / "steps.json")
    p = C.write_steps(out, run(inp))
    print(f"saved {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
