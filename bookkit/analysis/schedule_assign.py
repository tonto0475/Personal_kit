# -*- coding: utf-8 -*-
r"""분석 틀 ③ 일정 · 배정형 — 시작 · 끝 시각이 정해진 일(작업 · 수업 · 정비)을 자원(사람 · 기계 · 방)에 겹치지 않게 배정한다 → steps.json

    python3 bookkit/analysis/schedule_assign.py --demo --out <steps.json>                   작은 가짜 데이터로 돌려 본다
    python3 bookkit/analysis/schedule_assign.py --book bookkit/books/<이름>                책의 과제 자료로 → <책>/contracts/steps.json

쓰는 법(A3 카드): 이 파일을 <책>/work/a3.py 로 복사 → «입력 연결 칸» load() 만 과제에 맞게 고친다 → 돌린다 → 검사기
- 기본 규칙(방안 A) = 시작 시각 순서로, 그 일 장소에 시간 안에 닿는 자원 가운데 가장 일찍 비는 자원 · 없으면 새 자원
- 고치기 = 자원끼리 일을 옮기거나 맞바꿔 이동 합계 줄이기 · 이어 붙이기 = 자원 × 시각 시간표
- 조건별 실행 = 일 사이 준비 시간(분)을 바꿔 필요한 자원 수
- 그림: 시각별 막대(동시에 진행 중인 일 수 vs 보유 자원)
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
        points  {장소: (y, x)} · geo · short {장소: 짧은 이름} — 장소가 하나뿐이면 점 하나
        tasks   [{"id", "start": 분, "end": 분, "place": 장소}]
        have(보유 자원 수) · speed(거리 1 당 이동 분 · 이동이 없으면 0) · setup(일 사이 준비 분) · res(자원 이름) · job(일 이름)
        setups  조건별 실행에 쓸 준비 시간 목록"""
    raise NotImplementedError("load() 를 과제에 맞게 고친다 — 예: 일정 csv 를 읽어 tasks 를 만든다(demo() 참고)")


def demo():
    """작은 가짜 데이터(평면 좌표 · 일 10개 · 자원 3) — 틀이 도는지 보기만 한다"""
    pts = {"R1": (1.0, 1.0), "R2": (1.0, 5.0), "R3": (4.0, 3.0), "R4": (5.0, 6.0)}
    raw = [(540, 600, "R1"), (550, 620, "R2"), (560, 590, "R3"), (600, 660, "R4"), (610, 640, "R1"), (620, 700, "R3"),
           (630, 690, "R2"), (650, 720, "R1"), (700, 760, "R4"), (705, 750, "R2")]
    tasks = [{"id": f"W{i + 1}", "start": a, "end": b, "place": p} for i, (a, b, p) in enumerate(raw)]
    return {"points": pts, "geo": False, "short": {k: k for k in pts}, "tasks": tasks, "have": 3, "speed": 2.0, "setup": 5,
            "res": "담당", "job": "작업", "setups": [0, 5, 10, 20]}


def deadhead(inp, setup):
    """장소 a → b 로 옮겨 다음 일을 시작하기까지 걸리는 분(이동 + 준비) — 표"""
    pts, geo, spd = inp["points"], inp["geo"], inp.get("speed", 0.0)
    return {a: {b: round(C.dist(pts[a], pts[b], geo) * spd + setup, 1) for b in pts} for a in pts}


def trips_of(inp):
    """일 → 이어 붙이기의 일 칸(같은 장소에서 시작 · 끝)"""
    return [{"start": t["start"], "end": t["end"], "frm": t["place"], "to": t["place"], "color": "#2563eb"} for t in inp["tasks"]]


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
    res, job, have = inp.get("res", "자원"), inp.get("job", "일"), inp["have"]
    dh = deadhead(inp, inp.get("setup", 0))
    trips = trips_of(inp)
    rec = C.chain(trips, dh)
    nres = 1 + max(s["bus"] for s in rec)
    # 재생기 1 «채우기» — 시작 시각 순서로 자원에 담기(지도 = 장소)
    weights = {}
    for t in inp["tasks"]:
        weights[t["place"]] = weights.get(t["place"], 0) + 1
    M = C.map_spec(pts, weights, sh, None, "", geo)
    cost = lambda names: C.route_len(list(names), pts, None, geo)  # noqa: E731  — 자원이 장소를 차례로 옮겨 다닌 길이
    fsteps = [(s["bus"], trips[s["trip"]]["frm"], 1) for s in rec]
    pf, state = C.fill_player(fsteps, nres, M, None, "건", res, cost, f"{job} {len(rec)}건을 시작 시각 순서로 {res}에 담는 과정",
                              f"다음을 눌러 가며 → {res}가 새로 늘어나는 순간을 봐", "시작 시각 순서 · 시간 안에 닿는 자원")
    for st, s in zip(pf["steps"], rec):
        t = inp["tasks"][s["trip"]]
        st["text"] = (f"**{C.hm(t['start'])}~{C.hm(t['end'])} {sh.get(t['place'], t['place'])}** {job} — "
                      + (f"시간 안에 닿는 {res}가 없어 **{res} {s['bus'] + 1}** 을 새로 쓴다." if s["new"] else f"{res} {s['bus'] + 1} 이 맡는다.")
                      + (f" !!보유 {have}을 넘는다.!!" if s["bus"] >= have else ""))
    # 재생기 2 «고치기» — 일을 옮기거나 맞바꿔 이동 합계 줄이기(겹침 검사는 하지 않는 단순판 — 과제에 맞게 cost 에 겹침 벌점을 더한다)
    lrec = C.local_search(state, cost, cap=len(rec))
    px = C.fix_player(lrec, M, cost, res, "건", "한 건씩 고치기 — 이동 합계 줄이기", "다음을 눌러 가며 → 굵어진 자원의 선이 짧아지는지 봐")
    # 재생기 3 «이어 붙이기» — 같은 규칙의 시간표
    pc, nb = C.chain_player(trips, dh, {p: sh.get(p, p) for p in pts}, have, res, job, f"{job}을 {res}에 이어 붙이는 과정",
                            f"다음을 눌러 가며 → {res}가 새로 생기는 순간, 다른 {res}들이 어디에 있는지 오른쪽을 봐")
    # 조건별 실행 — 준비 시간
    conds = []
    for su in inp.get("setups", [inp.get("setup", 0)]):
        r = C.chain(trips, deadhead(inp, su))
        conds.append({"name": "준비 시간", "value": f"{su}분", "result": {f"필요 {res}": 1 + max(x["bus"] for x in r)}})
    ctab = C.conditions_table(conds, ["준비 시간", f"필요 {res}"], [f"필요 {res}"], f"필요 {res}", have, f"준비 시간별 필요 {res}(보유 {have} — 넘으면 빨강)")
    # 4장 표 · 그림
    names_all = sorted(pts, key=lambda n: -weights.get(n, 0))
    brute, sec = C.brute_table(names_all, cost, sizes=tuple(range(3, min(8, len(names_all)) + 1)))
    if len(names_all) >= 4:  # 가장 바쁜 장소를 출발 · 복귀 점으로 두고 나머지 셋의 순서
        base = names_all[0]
        otab, ofig, orows = C.orders_example(names_all[1:4], pts, pts[base], sh.get(base, base), sh, geo)
    else:
        otab, ofig, orows = C.orders_example(names_all[:3], pts, None, sh.get(names_all[2], names_all[2]), sh, geo)
    t0 = min(t["start"] for t in inp["tasks"]) // 30 * 30
    numbers = {"n_tasks": len(rec), "have": have, "need": nres, "setup": inp.get("setup", 0), "move_A": round(lrec[0][3], 1), "move_B": round(lrec[-1][3], 1),
               "B_moves": len(lrec) - 1, "chain_need": nb, "brute_max_measured": max(sec), "brute_max_sec": round(sec[max(sec)], 4)}
    return {"contract": "steps", "version": 1, "type": "schedule", "task": inp.get("task", ""), "numbers": numbers,
            "players": {"채우기": pf, "고치기": px, "이어붙이기": pc},
            "figures": {"순서_지도": ofig,
                        "그림_큰흐름": C.overview_fig(_by_bucket([t["start"] for t in inp["tasks"]]), f"시간대별 {job} 시작 수", [[f"{job} 수", "#2563eb"]],
                                                   inp.get("flow")),
                        "시각막대": C.busy_bars([(t["start"], t["end"]) for t in inp["tasks"]], t0, max(t["end"] for t in inp["tasks"]) + 1, 15, have,
                                             f"보유 {have}", f"시각마다 진행 중인 {job} 수")},
            "tables": {"순서_표": otab, "전부세기_표": brute, "조건별_표": ctab}, "conditions": conds}


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="분석 틀 ③ 일정 · 배정형 → steps.json")
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
