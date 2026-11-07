# -*- coding: utf-8 -*-
r"""분석 틀 ② 배차 · 사건 시뮬레이션형 — 일(요청)이 시각마다 생기고, 정해진 대수의 차가 하나씩 맡아 처리한다 → steps.json

    python3 bookkit/analysis/dispatch_sim.py --demo --out <steps.json>                      작은 가짜 데이터로 돌려 본다
    python3 bookkit/analysis/dispatch_sim.py --book bookkit/books/<이름>                   책의 과제 자료로 → <책>/contracts/steps.json

쓰는 법(A3 카드): 이 파일을 <책>/work/a3.py 로 복사 → «입력 연결 칸» load() 만 과제에 맞게 고친다 → 돌린다 → 검사기
- 기본 규칙(방안 A) = 요청이 생긴 순서로, 그 출발지에 가장 일찍 닿는 차가 맡는다(먼저 온 요청 먼저 · 가까운 차)
- 고치기 = 차끼리 맡은 일을 옮기거나 맞바꿔 빈 차 이동 합계 줄이기 · 이어 붙이기 = 시뮬레이션 결과를 차 × 시각 시간표로
- 조건별 실행 = 차 대수를 바꿔 평균 · 최대 기다림 · 늦은 일 수
- 그림: 상태 전이(한 대가 거치는 상태) · 시각별 막대(바쁜 차 수 vs 보유)
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
        points   {곳: (y, x)} · geo · short {곳: 짧은 이름}
        jobs     [{"id", "t": 생긴 시각(분), "frm": 출발지, "to": 도착지, "work": 싣고 내리는 분(선택), "due": 끝내야 할 시각(선택)}]
        depot    차가 처음 있는 곳(points 의 이름) · fleet(보유 대수) · speed(거리 1 당 분) · veh(차 이름) · job(일 이름)
        fleets   조건별 실행에 쓸 대수 목록 · states(선택 — 상태 전이 그림 칸, 없으면 기본 다섯 상태)"""
    raise NotImplementedError("load() 를 과제에 맞게 고친다 — 예: 요청 로그 csv 를 읽어 jobs 를 만든다(demo() 참고)")


def demo():
    """작은 가짜 데이터(평면 좌표 · 요청 12개 · 차 3대) — 틀이 도는지 보기만 한다"""
    pts = {"S1": (1.0, 1.0), "S2": (1.0, 6.0), "S3": (4.0, 3.0), "S4": (6.0, 7.0), "S5": (7.0, 2.0), "D0": (4.0, 0.0)}
    raw = [(0, "S1", "S3"), (2, "S2", "S4"), (5, "S5", "S1"), (6, "S3", "S2"), (9, "S4", "S5"), (11, "S1", "S4"),
           (12, "S2", "S3"), (15, "S5", "S2"), (18, "S3", "S1"), (19, "S4", "S1"), (22, "S2", "S5"), (24, "S1", "S2")]
    jobs = [{"id": f"J{i + 1}", "t": 480 + t, "frm": a, "to": b, "work": 2, "due": 480 + t + 25} for i, (t, a, b) in enumerate(raw)]
    return {"points": pts, "geo": False, "short": {k: k for k in pts}, "jobs": jobs, "depot": "D0", "fleet": 3, "speed": 1.5,
            "veh": "차", "job": "운반", "fleets": [2, 3, 4, 5]}


# ════════════════════════════════════════════════════════════
# 기본 규칙(방안 A) — 생긴 순서로 · 가장 일찍 닿는 차
# ════════════════════════════════════════════════════════════
def simulate(inp, fleet):
    """사건 순서 시뮬레이션 → 일마다 {"job", "bus", "free", "at", "dh", "arrive", "start", "end", "wait", "late", "cands"}"""
    pts, geo, spd = inp["points"], inp["geo"], inp.get("speed", 1.0)
    tt = lambda a, b: C.dist(pts[a], pts[b], geo) * spd  # noqa: E731
    cars = [(min(j["t"] for j in inp["jobs"]), inp["depot"])] * fleet  # (비는 시각, 있는 곳)
    out = []
    for j in sorted(inp["jobs"], key=lambda x: (x["t"], x["id"])):
        cands = []
        for b, (free, at) in enumerate(cars):
            dh = tt(at, j["frm"])
            cands.append({"bus": b, "free": free, "at": at, "dh": dh, "arrive": max(free, j["t"]) + dh})
        c = min(cands, key=lambda x: (x["arrive"], x["bus"]))
        start = max(c["arrive"], j["t"])
        end = start + j.get("work", 0) + tt(j["frm"], j["to"])
        cars[c["bus"]] = (end, j["to"])
        late = j.get("due") is not None and end > j["due"]
        out.append({"job": j, "bus": c["bus"], "free": c["free"], "at": c["at"], "dh": c["dh"], "arrive": c["arrive"], "start": start, "end": end,
                    "wait": start - j["t"], "late": late, "cands": cands})
    return out


def _by_bucket(times, n_max=12):
    """시각 목록 → 큰 흐름 막대 열(같은 폭 시간대 · 열 n_max 개 이하)"""
    t0, t1 = min(times), max(times) + 1
    step = next(s for s in (10, 15, 30, 60, 120, 180, 240) if (t1 - t0) / s <= n_max)
    a = int(t0 // step * step)
    cols = []
    while a < t1:
        cols.append({"label": C.hm(a), "sub": f"{step}분", "values": [sum(1 for t in times if a <= t < a + step)]})
        a += step
    return cols


def run(inp):
    """입력 → steps.json dict"""
    pts, geo, sh = inp["points"], inp["geo"], inp.get("short", {})
    veh, job, fleet = inp.get("veh", "차"), inp.get("job", "일"), inp["fleet"]
    sim = simulate(inp, fleet)
    # 재생기 1 «채우기» — 일을 차에 맡기는 순서(지도 = 출발지)
    weights = {}
    for j in inp["jobs"]:
        weights[j["frm"]] = weights.get(j["frm"], 0) + 1
    M = C.map_spec(pts, weights, sh, None, "", geo)
    cost = lambda names: C.route_len(list(names), pts, None, geo)  # noqa: E731  — 맡은 출발지들을 차례로 도는 길이(시각은 보지 않는 어림 — 과제에 맞게 고친다)
    fsteps = [(s["bus"], s["job"]["frm"], 1) for s in sim]
    pf, state = C.fill_player(fsteps, fleet, M, None, "건", veh, cost, f"{job} {len(sim)}건을 생긴 순서로 {veh}에 맡기는 과정",
                              f"다음을 눌러 가며 → 같은 {veh}가 멀리 떨어진 출발지를 오가는 곳을 봐", "생긴 순서 · 가장 일찍 닿는 차")
    for st, s in zip(pf["steps"], sim):
        st["text"] = (f"**{C.hm(s['job']['t'])} {sh.get(s['job']['frm'], s['job']['frm'])}→{sh.get(s['job']['to'], s['job']['to'])}** {job} — "
                      f"{veh} {s['bus'] + 1} 이 {C.hm(s['arrive'])} 에 닿아 맡는다(기다림 {s['wait']:.0f}분)." + (" !!늦음!!" if s["late"] else ""))
    # 재생기 2 «고치기» — 맡은 일(출발지)을 옮기거나 맞바꿔 빈 차 길이 줄이기(정원 없음)
    rec = C.local_search(state, cost, cap=len(sim))
    px = C.fix_player(rec, M, cost, veh, "건", "한 건씩 고치기 — 빈 차 이동 줄이기", "다음을 눌러 가며 → 굵어진 차의 선이 짧아지는지, 표의 총합이 얼마나 주는지 봐")
    # 재생기 3 «이어 붙이기» — 시뮬레이션 결과 시간표
    order = list(range(len(sim)))
    trips = [{"start": round(s["start"], 1), "end": round(s["end"], 1), "frm": s["job"]["frm"], "to": s["job"]["to"],
              "color": "#dc2626" if s["late"] else "#2563eb"} for s in sim]
    texts = []
    for s in sim:
        others = [c for c in s["cands"] if c["bus"] != s["bus"]]
        near = min(others, key=lambda c: c["arrive"]) if others else None
        texts.append(f"**{C.hm(s['job']['t'])} {sh.get(s['job']['frm'], s['job']['frm'])}** {job} 요청 — {veh} {s['bus'] + 1} 이 "
                     f"{sh.get(s['at'], s['at'])}에서 {s['dh']:.0f}분 달려 {C.hm(s['arrive'])} 도착"
                     + (f"(다음으로 빠른 {veh} {near['bus'] + 1} 은 {C.hm(near['arrive'])})" if near else "") + f". 기다림 {s['wait']:.0f}분."
                     + (" !!끝낼 시각을 넘긴다.!!" if s["late"] else ""))
    n_late = sum(s["late"] for s in sim)
    texts.append(f"**{veh} {fleet}대로 {len(sim)}건.** 평균 기다림 {sum(s['wait'] for s in sim) / len(sim):.1f}분 · 최대 {max(s['wait'] for s in sim):.0f}분 · 늦은 일 {n_late}건.")
    heads = [f"요청 {k + 1} / {len(sim)} — 생긴 순서" for k in order] + [f"다 맡긴 결과 — {veh} {fleet}대"]
    places = sorted(set(pts))
    dh = {a: {b: round(C.dist(pts[a], pts[b], geo) * inp.get("speed", 1.0), 1) for b in places} for a in places}
    pc = C.timetable_player(trips, [{"trip": i, "bus": s["bus"]} for i, s in enumerate(sim)], heads, texts, dh, {p: sh.get(p, p) for p in places},
                            fleet, veh, job, f"요청을 {veh}에 맡겨 처리하는 과정 — {veh} {fleet}대", f"다음을 눌러 가며 → 모든 {veh}가 바쁠 때 기다림이 어떻게 느는지 봐")
    # 조건별 실행 — 대수
    conds = []
    for f in inp.get("fleets", [fleet]):
        r = simulate(inp, f)
        conds.append({"name": "대수", "value": f"{f}대", "result": {"평균 기다림(분)": round(sum(x["wait"] for x in r) / len(r), 1),
                                                                 "최대 기다림(분)": round(max(x["wait"] for x in r)), "늦은 일": sum(x["late"] for x in r)}})
    ctab = C.conditions_table(conds, ["대수", "평균 기다림(분)", "최대 기다림(분)", "늦은 일"], ["평균 기다림(분)", "최대 기다림(분)", "늦은 일"], "늦은 일", 0,
                              "대수별 기다림 · 늦은 일(늦은 일이 있으면 빨강)")
    # 4장 표 · 그림 — 한 대가 세 곳을 도는 순서 · 전부 세기
    names_all = sorted(weights, key=lambda n: -weights[n])
    brute, sec = C.brute_table(names_all + [n for n in pts if n not in names_all and n != inp["depot"]], cost)
    otab, ofig, orows = C.orders_example(names_all[:3], pts, pts[inp["depot"]], sh.get(inp["depot"], inp["depot"]), sh, geo)
    st = inp.get("states") or {
        "title": f"{veh} 한 대가 거치는 상태", "states": [{"name": "대기", "tone": "gray"}, {"name": "이동", "tone": "amber"},
                                                      {"name": "일 하는 중", "tone": "acc"}, {"name": "끝", "tone": "ok"}],
        "edges": [{"a": 0, "b": 1, "label": "배정"}, {"a": 1, "b": 2, "label": "도착"}, {"a": 2, "b": 3},
                  {"a": 3, "b": 0, "label": "다음 일 없음"}, {"a": 3, "b": 1, "label": "다음 일", "tone": "acc"}],
        "spans": [], "label": "상태 전이"}  # 기본 모양만 — 과제의 상태 · 규칙(구간 표시 spans)은 load() 의 states 로 준다
    t0 = min(s["start"] for s in sim) // 30 * 30
    numbers = {"n_jobs": len(sim), "fleet": fleet, "wait_avg": round(sum(s["wait"] for s in sim) / len(sim), 1), "wait_max": round(max(s["wait"] for s in sim)),
               "n_late": n_late, "empty_A": round(rec[0][3], 1), "empty_B": round(rec[-1][3], 1), "B_moves": len(rec) - 1,
               "brute_max_measured": max(sec), "brute_max_sec": round(sec[max(sec)], 4)}
    return {"contract": "steps", "version": 1, "type": "dispatch", "task": inp.get("task", ""), "numbers": numbers,
            "players": {"채우기": pf, "고치기": px, "이어붙이기": pc},
            "figures": {"순서_지도": ofig, "상태전이": st,
                        "그림_큰흐름": C.overview_fig(_by_bucket([j["t"] for j in inp["jobs"]]), f"시간대별 {job} 요청 수", [[f"{job} 수", "#2563eb"]], inp.get("flow")),
                        "시각막대": C.busy_bars([(s["start"] - s["dh"], s["end"]) for s in sim], t0, max(s["end"] for s in sim) + 1, 5, fleet,
                                             f"보유 {fleet}대", f"시각마다 일하는 {veh} 수")},
            "tables": {"순서_표": otab, "전부세기_표": brute, "조건별_표": ctab}, "conditions": conds}


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="분석 틀 ② 배차 · 사건 시뮬레이션형 → steps.json")
    ap.add_argument("--demo", action="store_true", help="작은 가짜 데이터로")
    ap.add_argument("--book", help="책 폴더")
    ap.add_argument("--task", help="과제 폴더(README.md · uploads/)")
    ap.add_argument("--out", help="출력 steps.json(기본 <책>/contracts/steps.json)")
    a = ap.parse_args(argv)
    if not a.book and not a.demo and HERE.name == "work":  # 책의 work/ 에서 돌리면 그 책
        a.book = str(HERE.parent)
    inp = demo() if a.demo else load(C.task_dir(a.book, a.task))
    p = C.write_steps(a.out or (Path(a.book) / "contracts" / "steps.json"), run(inp))
    print(f"saved {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
