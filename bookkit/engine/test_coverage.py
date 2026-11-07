# -*- coding: utf-8 -*-
r"""분석 틀 ④ 배치 · 덮기형 시험 — demo 실행 · 계약 검사 · 보이는 칸 계산 · 고치기가 줄이지 않음 · 양식 빌드

    python3 bookkit/engine/test_coverage.py            → PASS / FAIL(종료 코드)

- 임시 폴더에만 쓴다(키트 · 책 폴더는 건드리지 않는다)
"""
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 키트 bookkit 폴더 · 양식 · 예시 계약 · 계약 검사기 · 틀 파일
KIT = HERE.parent
TEMPLATE = KIT / "template"
EXAMPLE = KIT / "contracts" / "example"
CHECK = KIT / "contracts" / "check_contract.py"
FRAME = KIT / "analysis" / "coverage_place.py"
# steps.json 이 채우는 양식 칸 — 이 틀의 결과로 비면 안 된다
STEP_SLOTS = ("재생기_채우기", "재생기_고치기", "재생기_이어붙이기", "그림_큰흐름", "순서_표", "순서_지도", "전부세기_표", "조건별_표")
# 공개 저장소에 넣지 않는 낱말
BANNED = ("버스", "노선", "정류장")

sys.path.insert(0, str(KIT / "analysis"))
import coverage_place as P  # noqa: E402


# args: 실행 인자
def run(*args):
    """파이썬 실행 → (종료 코드, 출력 글)"""
    # 실행 결과
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


# log: 빌드 출력
def blanks(log):
    """빌드 출력의 빈 칸 목록(«  빈 칸: 장 · 칸» 줄) → 모음"""
    return {b.strip() for b in re.findall(r"^\s+빈 칸: (.+)$", log, re.M)}


# rng: 난수 / with_budget: 비용 상한을 쓰나
def random_case(rng, with_budget):
    """임의의 작은 입력"""
    # 행 수 · 열 수
    h, w = rng.randint(4, 7), rng.randint(5, 8)
    # 칸 전체
    every = [(y, x) for y in range(h) for x in range(w)]
    # 장애물 · 후보 칸
    picks = rng.sample(every, rng.randint(0, 5) + 5)
    obstacles, spots = picks[:-5], picks[-5:]
    inp = {"grid": (h, w), "obstacles": obstacles, "sites": {f"C{i + 1}": p for i, p in enumerate(spots)}, "dirs": [0, 90, 180, 270],
           "weight": {c: rng.randint(1, 4) for c in every if rng.random() < 0.3}, "fov": rng.choice([60, 90, 120]), "reach": rng.choice([3.0, 4.0, 6.0]),
           "count": rng.randint(1, 3), "goal": 0.8}
    if with_budget:
        inp["cost"] = {s: rng.randint(1, 3) for s in inp["sites"]}
        inp["budget"] = rng.randint(2, 5)
    return inp


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    # 실패 목록
    fails = []

    # ok: 참이면 통과 / what: 시험 이름
    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    # 임시 폴더 · demo 결과 파일
    tmp = Path(tempfile.mkdtemp(prefix="covtest_"))
    demo = tmp / "demo.json"

    print("demo · 계약 검사")
    code, log = run(FRAME, "--demo", "--out", demo)
    check(code == 0 and demo.is_file(), "--demo --out 이 steps.json 을 쓴다")
    code, log = run(CHECK, demo, "--render")
    check(code == 0 and "PASS demo.json" in log and "경고" not in log, "check_contract --render PASS · 경고 0")
    # demo 결과
    d = json.loads(demo.read_text(encoding="utf-8"))
    # 결과 숫자
    N = d["numbers"]
    check(d["type"] == "other" and set(d["players"]) == {"채우기", "고치기", "이어붙이기"}, "재생기 셋 · type other")
    check(N["B_moves"] >= 1 and N["cov_B"] > N["cov_A"], f"demo 에서 고치기가 실제로 늘린다 {N['cov_A']} → {N['cov_B']}")
    check(N["cov_best"] >= N["cov_B"], f"전부 센 최댓값 {N['cov_best']} ≥ 방안 B {N['cov_B']}")
    check("3번째를 놓는다" in d["players"]["채우기"]["steps"][2]["text"] and "커버리지" in d["players"]["채우기"]["steps"][2]["text"], "단계 글 = 동작 + 결과 숫자")
    check(any(r[3] == "실측" for r in d["tables"]["전부세기_표"]["rows"]) and any(r[3].startswith("추정") for r in d["tables"]["전부세기_표"]["rows"]), "전부 세기 표에 실측 · 추정 행")
    check({c["name"] for c in d["conditions"]} == {"대수", "시야각", "거리"} and all("목표" in c["result"] for c in d["conditions"]), "조건별 = 대수 · 시야각 · 거리 + 목표 달성 여부")
    # 기준 조건 행
    same = [c for c in d["conditions"] if c["value"] == "대수 3대"]
    check(same and same[0]["result"]["커버리지(%)"] == N["cov_B"], "조건별 기준 행 = 방안 B 커버리지")

    print("보이는 칸 — 거리 · 시야각 · 가림")
    # 벽 하나를 사이에 둔 한 줄 격자
    inp = {"grid": (1, 7), "obstacles": [(0, 3)], "sites": {"A": (0, 0)}, "dirs": [0], "fov": 90, "reach": 10.0, "goal": 1.0, "count": 1}
    # 보이는 칸 표
    seen = P.sights(inp)
    check(set(P.options(inp, seen, 90, 10.0)[0]["cells"]) == {(0, 0), (0, 1), (0, 2)}, "장애물 뒤 칸은 안 보이고 장애물도 덮지 않는다")
    check(set(P.options(inp, seen, 90, 1.0)[0]["cells"]) == {(0, 0), (0, 1)}, "거리 밖 칸은 안 보인다")
    inp = {"grid": (5, 5), "sites": {"A": (2, 2)}, "dirs": [90], "fov": 90, "reach": 10.0, "goal": 1.0, "count": 1}
    # 위쪽(+y) 90° 부채꼴
    cells = P.options(inp, P.sights(inp), 90, 10.0)[0]["cells"]
    check((4, 2) in cells and (3, 3) in cells and (3, 1) in cells and (1, 2) not in cells and (2, 4) not in cells, "시야각 — +y 방향 90° 부채꼴만")
    check(len(P.options(inp, P.sights(inp), 360, 10.0)[0]["cells"]) == 25, "시야각 360° = 전부")

    print("고치기가 커버리지를 줄이지 않는다(임의 입력 300개)")
    # 어긴 횟수 — 줄어듦 · 상한 넘김 · 같은 곳 두 대 · 최댓값 초과
    drop = over = dup = beat = 0
    # 고치기가 실제로 늘린 입력 수
    moved = 0
    # 난수
    rng = random.Random(20261104)
    # n: 시행 번호
    for n in range(300):
        inp = random_case(rng, n % 2 == 1)
        _, _, wt = P.field(inp)
        opts, picks, rec = P.solve(inp, P.sights(inp), wt, inp["fov"], inp["reach"], inp["count"], inp.get("budget"))
        # 단계별 덮는 값
        vals = [r["value"] for r in rec]
        drop += any(b <= a for a, b in zip(vals, vals[1:]))
        moved += len(rec) > 1
        # r: 단계 기록
        for r in rec:
            over += len(r["picks"]) > inp["count"] or ("budget" in inp and P.spent(inp, opts, r["picks"]) > inp["budget"])
            dup += len({opts[i]["site"] for i in r["picks"]}) != len(r["picks"])
        if opts and picks:
            # 전부 세어 찾은 최댓값
            best = P.brute_pick(inp, opts, wt, len(picks), inp.get("budget"), "장치")[2]
            beat += best is not None and vals[-1] > best + 1e-9
    check(drop == 0, f"단계마다 덮는 값이 늘기만 한다(어김 {drop})")
    check(over == 0, f"대수 · 비용 상한을 지킨다(어김 {over})")
    check(dup == 0, f"한 곳에 한 대(어김 {dup})")
    check(beat == 0, f"방안 B ≤ 전부 센 최댓값(어김 {beat})")
    check(moved > 0, f"고치기가 실제로 움직인 입력 {moved}개 — 빈 시험이 아니다")

    print("조건별 표 — 대수 · 비용 상한을 늘려도 커버리지가 줄지 않는다(demo + 임의 입력 300개)")
    # demo 대수 행 커버리지
    covs = [c["result"]["커버리지(%)"] for c in d["conditions"] if c["name"] == "대수"]
    check(all(b >= a for a, b in zip(covs, covs[1:])), f"demo 대수 2 · 3 · 4 · 5 대가 단조 {covs}")
    # 어긴 횟수 — 대수 · 비용 상한 / 이어 받아 나아진 입력 수
    rise = lift = 0
    rng = random.Random(20261105)
    for n in range(300):
        inp = random_case(rng, False)
        inp["cost"] = {s: rng.randint(1, 3) for s in inp["sites"]}
        _, _, wt = P.field(inp)
        sight = P.sights(inp)
        # 일부러 뒤섞은 순서 — 표의 행 순서와 무관하게 값이 작은 조건부터 풀어야 한다
        cases = [("대수", "", inp["fov"], inp["reach"], c, None) for c in rng.sample([1, 2, 3, 4, 5], 5)] \
            + [("비용 상한", "", inp["fov"], inp["reach"], None, b) for b in rng.sample([2, 3, 4, 5, 6, 8], 6)]
        vals = P.case_values(inp, sight, wt, cases)
        # name: 조건 이름 / at: 조건 칸 자리
        for name, at in (("대수", 4), ("비용 상한", 5)):
            line = sorted((cases[i][at], vals[i]) for i in range(len(cases)) if cases[i][0] == name)
            rise += any(b[1] < a[1] - 1e-9 for a, b in zip(line, line[1:]))
        lift += any(vals[i] > P.solve(inp, sight, wt, *cases[i][2:])[2][-1]["value"] + 1e-9 for i in range(len(cases)))
    check(rise == 0, f"늘린 조건에서 덮는 값이 줄지 않는다(어김 {rise})")
    check(lift > 0, f"이어 시작이 새로 푼 값보다 나은 입력 {lift}개 — 빈 시험이 아니다")

    print("큰 격자 · 비용 상한 · 목표에 못 닿음")
    inp = {"grid": (40, 60), "obstacles": [(y, 30) for y in range(10, 30)], "sites": {f"C{i + 1}": (i * 6 + 2, (i * 13) % 60) for i in range(6)}, "dirs": [0, 90, 180, 270],
           "fov": 90, "reach": 15.0, "count": 3, "goal": 0.99, "counts": [2, 3]}
    # 큰 격자 결과 · 지도
    big = tmp / "big.json"
    r = P.run(inp)
    P.C.write_steps(big, r)
    # 지도
    M = r["players"]["채우기"]["map"]
    check(len(M["weights"]) <= P.MAX_SHOW + len(inp["sites"]), f"그리는 점 {len(M['weights'])}개 ≤ 상한 — 칸 2,4xx 개를 다 그리지 않는다")
    # 끝 단계 오른쪽 목록 합계
    last = r["players"]["채우기"]["steps"][-1]["state"]
    check(sum(c for st in last for _, c in st) == r["numbers"]["cells_A"], "칸을 줄여 그려도 합계는 전체 칸 수")
    check(r["numbers"]["need_goal"] == 0 and "못 닿는다" in r["players"]["이어붙이기"]["texts"][-1], "목표에 못 닿으면 need_goal 0 · 정리 글에 알림")
    code, log = run(CHECK, big, "--render")
    check(code == 0, "큰 격자도 check_contract --render PASS")
    inp = dict(P.demo(), count=None, budget=5, cost={"C1": 3, "C2": 1, "C3": 2, "C4": 2, "C5": 3, "C6": 1}, counts=[], budgets=[3, 5, 7])
    # 비용 상한 결과 파일
    bud = tmp / "budget.json"
    P.C.write_steps(bud, P.run(inp))
    code, log = run(CHECK, bud, "--render")
    check(code == 0, "대수 없이 비용 상한만 줘도 check_contract --render PASS")

    print("양식 빌드 — steps 칸에 빈 칸이 없다")
    # 시험 책 · 계약 폴더 · 결과 html
    book = tmp / "covtest"
    shutil.copytree(TEMPLATE, book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', '"doc": "covtest",', 1), encoding="utf-8")
    con = book / "contracts"
    con.mkdir(exist_ok=True)
    for name in ("facts", "reqs"):
        shutil.copy(EXAMPLE / f"{name}.json", con / f"{name}.json")
    shutil.copy(EXAMPLE / "steps.json", con / "steps.json")
    out = book / "dist" / "covtest.html"
    code, log = run(HERE / "build_book.py", book, "--stage", "2", "--out", out)
    # 예시 계약으로 빌드했을 때의 빈 칸(글 칸만 남는다)
    base = blanks(log)
    check(code == 0 and base, f"예시 계약 빌드 — 글 칸 빈 칸 {len(base)}개(기준)")
    shutil.copy(demo, con / "steps.json")
    code, log = run(HERE / "build_book.py", book, "--stage", "2", "--out", out)
    # 이 틀 결과로 빌드했을 때의 빈 칸
    mine = blanks(log)
    check(code == 0, "양식 + demo 결과 빌드 종료 코드 0")
    check(not [b for b in mine if b.split(" · ")[1] in STEP_SLOTS], "재생기 · 그림 · 표 칸이 비지 않는다")
    check(mine == base, f"빈 칸이 예시 계약과 같다(더 생긴 칸 {sorted(mine - base)[:5]})")
    # 책 html
    h = out.read_text(encoding="utf-8")
    check("3번째를 놓는다" in h and "한 대씩 바꾸기" in h and "놓은 순서별 더한 커버리지" in h, "재생기 · 큰 흐름이 책에 들어간다")
    check("{F[" not in h and "⟦빈 칸 — 공통" not in h, "식 글자 · 공통 칸 빈 칸 표시 없음")

    print("틀 규칙")
    # 틀 글
    src = FRAME.read_text(encoding="utf-8")
    check(not [w for w in BANNED if w in src], "공개 저장소 금지 낱말이 없다")
    check(not re.search(r"^(import|from) (?!argparse|itertools|math|sys|time|pathlib|_common)", src, re.M), "표준 라이브러리 + _common 만 불러온다")

    shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not fails else f"FAIL — {len(fails)}개")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
