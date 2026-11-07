# -*- coding: utf-8 -*-
r"""분석 틀 ⑤ 측정 · 관리도형 시험 — demo · 계약 검사 · 성분 분해 정확도 · 가짜 과제에서 심어 둔 이상 잡기 · 양식 빌드(재생기 셋 · 도메인 한 장)

    python3 bookkit/engine/test_stat_model.py                    → PASS / FAIL(종료 코드)
    python3 bookkit/engine/test_stat_model.py --keep <폴더>      시험 책 · 가짜 과제를 그 폴더에 남긴다(그림 확인용)

- 임시 폴더에만 쓴다(키트 · 책 폴더는 건드리지 않는다) · 가짜 과제의 값 · 이름은 전부 지어낸 것(장비 T1~T3 · 척 1 · 2 · 로트 L01~L20)
"""
import argparse
import csv
import json
import math
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
FRAME = KIT / "analysis" / "stat_model.py"
# steps.json 이 채우는 양식 칸 — 이 틀의 결과로 비면 안 된다
STEP_SLOTS = ("재생기_채우기", "재생기_고치기", "재생기_이어붙이기", "그림_큰흐름", "순서_표", "순서_지도", "전부세기_표", "조건별_표")
# 도메인 한 장 칸
DOMAIN = ("도메인_제목", "도메인_재는_것", "도메인_단위", "도메인_나쁜_것", "도메인_고치는_법")
# 공개 저장소에 넣지 않는 낱말 — 이 파일에도 글자 그대로 남지 않게 코드 값으로
BANNED = tuple("".join(map(chr, c)) for c in ((48260, 49828), (45432, 49440), (51221, 47448, 51109)))
# 가짜 과제 — 장비 · 척 · 로트 수 · 로트당 판 · 판당 칸 · 회전이 흐르는 장비 · x 로 치우친 (장비, 척)
TOOLS, CHUCKS, N_LOT, PER_LOT, N_SITE = ("T1", "T2", "T3"), ("1", "2"), 20, 4, 30
DRIFT_TOOL, BIAS = "T2", ("T1", "2")

sys.path.insert(0, str(KIT / "analysis"))
import stat_model as M  # noqa: E402

# 가짜 과제의 load() — a3 복사본의 «입력 연결 칸» 을 이것으로 바꾼다(A3 카드가 하는 일 그대로)
LOAD = '''    import csv
    rows = []
    with open(Path(task) / "uploads" / "measure.csv", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append({"unit": r["lot_id"] + "-" + r["wafer_id"], "group": r["tool"], "sub": r["chuck"], "batch": r["lot_id"], "t": r["time"],
                         "x": float(r["x_mm"]), "y": float(r["y_mm"]), "dx": float(r["dx_nm"]), "dy": float(r["dy_nm"])})
    return {"rows": rows, "vector": True, "names": {"unit": "웨이퍼", "group": "장비", "sub": "척", "batch": "로트", "value": "어긋남"},
            "unit_len": "nm", "unit_pos": "mm", "radius": 150.0, "spec": 8.0, "k": 3, "ks": [2, 2.5, 3, 3.5], "order": 3, "task": "가짜 측정 과제",
            "flow": {"input": "측정 파일\\n(uploads)", "check": "검증 · 정리", "plan": "성분 분해\\n관리도", "out1": "장비별 이상 · 보정값", "out2": "재작업 판정"}}
'''


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


# folder: 과제 폴더
def make_task(folder):
    """가짜 과제 — README + uploads/measure.csv(로트 20 · 판 80 · 칸 2,400). T2 회전이 시간에 따라 0 → 0.05 µrad · T1 척 2 의 x 가 +4 nm"""
    rng = random.Random(20261105)
    (folder / "uploads").mkdir(parents=True)
    (folder / "README.md").write_text(
        "# 가짜 측정 과제(시험용)\n\n판 위 30곳에서 잰 위치 어긋남(dx, dy · nm)을 성분(평행 이동 · 회전 · 배율 · 직교)으로 나누고, "
        "장비 · 척별로 이상(치우침 · 드리프트)을 찾는다. 판마다 재작업 여부(|평균| + 3σ > 8 nm)와 장비별 보정값을 낸다.\n", encoding="utf-8")
    # 칸 — 가운데 + 고리 셋
    sites = [(0.0, 0.0)] + [(r * math.cos(2 * math.pi * j / n + o), r * math.sin(2 * math.pi * j / n + o))
                            for r, n, o in ((45.0, 7, 0.0), (90.0, 10, 0.3), (135.0, 12, 0.1)) for j in range(n)]
    assert len(sites) == N_SITE
    rows = []
    # 장비마다 처리한 로트 수 · 로트 수
    done = {t: 0 for t in TOOLS}
    total = {t: sum(1 for b in range(N_LOT) if TOOLS[b % 3] == t) for t in TOOLS}
    for b in range(N_LOT):
        tool = TOOLS[b % 3]
        prog = done[tool] / (total[tool] - 1)
        done[tool] += 1
        for w in range(PER_LOT):
            ch = CHUCKS[w % 2]
            tx, ty = rng.gauss(0, 0.7), rng.gauss(0, 0.7)
            rot, mx, my, orth = rng.gauss(0, 0.004), rng.gauss(0.01, 0.003), rng.gauss(0.012, 0.003), rng.gauss(0, 0.003)
            if tool == DRIFT_TOOL:
                rot += 0.05 * prog
            if (tool, ch) == BIAS:
                tx += 4.0
            for x, y in sites:
                # 1차 성분 + 판 가장자리 휨(2차) + 칸 잡음
                dx = tx + mx * x - rot * y + orth * y / 2 + 1.2e-4 * x * x + rng.gauss(0, 0.9)
                dy = ty + my * y + rot * x + orth * x / 2 + 1.2e-4 * y * y + rng.gauss(0, 0.9)
                rows.append([f"L{b + 1:02d}", f"W{w + 1:02d}", "A1", tool, ch, f"{x:.2f}", f"{y:.2f}", f"{dx:.3f}", f"{dy:.3f}",
                             f"2026-01-{1 + b // 2:02d}T{8 + (b % 2) * 6:02d}:{w * 10:02d}"])
    with open(folder / "uploads" / "measure.csv", "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["lot_id", "wafer_id", "layer", "tool", "chuck", "x_mm", "y_mm", "dx_nm", "dy_nm", "time"])
        wr.writerows(rows)
    return len(rows)


# book: 책 폴더 / task: 과제 폴더 / name: 문서 이름
def make_book(book, task, name):
    """양식 복사(new_book.py 와 같은 일 — 키트 books/ 가 아닌 임시 폴더에)"""
    shutil.copytree(TEMPLATE, book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{name}",', 1), encoding="utf-8")
    data = book / "content" / "data.py"
    data.write_text(data.read_text(encoding="utf-8").replace("TASK_DIR = None", f"TASK_DIR = {str(task)!r}", 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    (book / "work").mkdir(exist_ok=True)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="분석 틀 ⑤ 측정 · 관리도형 시험")
    ap.add_argument("--keep", help="시험 책 · 가짜 과제를 남길 폴더(없으면 임시 폴더를 지운다)")
    a = ap.parse_args(argv)
    # 실패 목록
    fails = []

    # ok: 참이면 통과 / what: 시험 이름
    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    tmp = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="stattest_"))
    if a.keep and tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    demo = tmp / "demo.json"

    print("demo · 계약 검사")
    code, log = run(FRAME, "--demo", "--out", demo)
    check(code == 0 and demo.is_file(), "--demo --out 이 steps.json 을 쓴다")
    code, log = run(CHECK, demo, "--render")
    check(code == 0 and "PASS demo.json" in log and "경고" not in log, "check_contract --render PASS · 경고 0")
    d = json.loads(demo.read_text(encoding="utf-8"))
    check(d["type"] == "other" and {p.get("kind") for p in d["players"].values()} == {"quiver", "chart"}, "재생기 셋 = 화살표 둘 · 관리도 · type other")
    check(d["figures"]["순서_지도"].get("kind") == "arrows", "순서 지도 = 화살표 두 판")

    print("성분 분해 — 잡음 없는 판에서 값을 그대로 되찾는다")
    # 잡음 없는 판 하나 — 칸 12곳
    xs = [100 * math.cos(i) for i in range(12)]
    ys = [100 * math.sin(1.7 * i) for i in range(12)]
    true = {"Tx": 3.0, "Ty": -2.0, "rot": 0.02, "magx": 0.01, "magy": -0.015, "orth": 0.006}
    dx = [true["Tx"] + true["magx"] * x - true["rot"] * y + true["orth"] * y / 2 for x, y in zip(xs, ys)]
    dy = [true["Ty"] + true["magy"] * y + true["rot"] * x + true["orth"] * x / 2 for x, y in zip(xs, ys)]
    val, parts = M.fit_linear(xs, ys, dx, dy, M.VECTOR, True)
    check(all(abs(val[k] - v) < 1e-9 for k, v in true.items()), "벡터 1차 여섯 성분을 되찾는다")
    rest = [v - sum(p[2][i] for p in parts) for i, v in enumerate(dx)] + [v - sum(p[3][i] for p in parts) for i, v in enumerate(dy)]
    check(max(abs(r) for r in rest) < 1e-9, "성분 넷을 다 빼면 잔차 0")
    check([p[0] for p in parts] == ["평행 이동", "회전", "배율", "직교"], "빼는 순서 = 평행 이동 → 회전 → 배율 → 직교")
    sv, _ = M.fit_linear(xs, ys, [5 + 0.03 * x - 0.01 * y for x, y in zip(xs, ys)], [0.0] * 12, M.SCALAR, False)
    check(abs(sv["off"] - 5) < 1e-9 and abs(sv["tx"] - 0.03) < 1e-9 and abs(sv["ty"] + 0.01) < 1e-9, "값 하나(평균 · 기울기)도 되찾는다")
    bent = [v + 2e-4 * x * x for v, x in zip(dx, xs)]
    rx, ry = M.resid_poly(xs, ys, bent, dy, 2, 150.0, True)
    check(max(abs(r) for r in rx + ry) < 1e-6, "2차 휨은 방안 B(2차)가 다 뺀다")
    try:
        M.fit_linear([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [0.0] * 3, [0.0] * 3, M.VECTOR, True)
        check(False, "한 줄에 몰린 칸 → ValueError")
    except ValueError:
        check(True, "한 줄에 몰린 칸 → ValueError(조용히 틀린 값을 내지 않는다)")
    check(M.josa("직교", "을/를") == "직교를" and M.josa("회전", "을/를") == "회전을", "조사 — 직교를 · 회전을")

    print("가짜 과제 — a3 복사본 · 심어 둔 이상을 방안 A 가 잡는가")
    task = tmp / "task"
    n_rows = make_task(task)
    book = tmp / "stattest"
    make_book(book, task, "stattest")
    src = FRAME.read_text(encoding="utf-8")
    stub = re.search(r'^    raise NotImplementedError\("load\(\).*$\n', src, re.M)
    (book / "work" / "a3.py").write_text(src[:stub.start()] + LOAD + src[stub.end():], encoding="utf-8")
    # 임시 책은 키트 밖이라 위로 올라가도 bookkit/analysis 가 없다 — 틀이 찾는 둘째 자리(work/ 자기 폴더)에 공용을 둔다
    shutil.copy(KIT / "analysis" / "_common.py", book / "work" / "_common.py")
    code, log = run(book / "work" / "a3.py")
    steps = book / "contracts" / "steps.json"
    check(code == 0 and steps.is_file(), f"work/a3.py → contracts/steps.json ({log.strip()[-80:]})")
    code, log = run(CHECK, steps, "--render", "--task", task)
    check(code == 0 and "PASS steps.json" in log and "경고" not in log, "가짜 과제 steps.json — check_contract --render --task PASS · 경고 0")
    s = json.loads(steps.read_text(encoding="utf-8"))
    N = s["numbers"]
    check(N["n_rows"] == n_rows and N["n_units"] == N_LOT * PER_LOT and N["sites"] == N_SITE, f"줄 {N['n_rows']} · 판 {N['n_units']} · 칸 {N['sites']}")
    check(N["drift_name"] == DRIFT_TOOL and N["drift_metric"] == "회전", f"드리프트 = {N['drift_name']} {N['drift_metric']}(심은 것 {DRIFT_TOOL} 회전)")
    check(N["bias_name"] == "-".join(BIAS) and N["bias_metric"] == "이동 x", f"치우침 = {N['bias_name']} {N['bias_metric']}(심은 것 {'-'.join(BIAS)} 이동 x)")
    found = {(N[f"find{i}_name"], N[f"find{i}_metric"]) for i in range(1, N["n_found"] + 1) if f"find{i}_name" in N}
    check(found == {(DRIFT_TOOL, "회전"), ("-".join(BIAS), "이동 x")}, f"찾은 곳이 심은 둘뿐(헛걸림 0) — {sorted(found)}")
    # 치우친 척의 판 수 — T1 로트 7개 × 척 2 판 2장
    n_bias = sum(1 for b in range(N_LOT) if TOOLS[b % 3] == BIAS[0]) * PER_LOT // len(CHUCKS)
    check(N["bias_out"] >= 0.8 * n_bias and N["bias_fix"] < -2, f"치우친 척 판 대부분 이탈({N['bias_out']}) · 보정값 {N['bias_fix']} nm(부호 반대)")
    check(N["m_raw_avg"] > N["m_A_avg"] > N["m_B_avg"], f"|평균| + 3σ 평균 — 잰 그대로 {N['m_raw_avg']} > 방안 A {N['m_A_avg']} > 방안 B {N['m_B_avg']}")
    check(N["rework_raw"] > N["rework_A"] >= N["rework_B"], f"재작업 — 잰 그대로 {N['rework_raw']} > 1차 보정 뒤 {N['rework_A']} ≥ 고차 뒤 {N['rework_B']}")
    # 관리도 — 드리프트 장비의 첫 이탈은 앞쪽 절반이 아니다(0 에서 시작해 흐른다)
    C = s["players"]["이어붙이기"]["chart"]
    si = C["series"].index(DRIFT_TOOL) if DRIFT_TOOL in C["series"] else -1
    mine = [p for p in C["points"] if p[2] == si]
    first = next((i for i, p in enumerate(mine) if p[3]), None)
    check(si >= 0 and first is not None and first >= len(mine) // 3 and mine[-1][3], f"관리도 — {DRIFT_TOOL} 첫 이탈 {first}번째 / {len(mine)} · 마지막 점 이탈")
    allp = sorted(j for st in C["steps"] for j in st)
    check(allp == list(range(len(C["points"]))), "관리도 단계가 점 전부를 한 번씩 찍는다")
    # 채우기 화살표 — 성분을 뺄수록 짧아진다
    lens = [M.mean_len(st["dx"], st["dy"]) for st in s["players"]["채우기"]["steps"]]
    check(lens[-1] < lens[0] / 2 and len(lens) == 5, f"채우기 — 화살표 길이 평균 {round(lens[0], 2)} → {round(lens[-1], 2)}(5단계)")
    fx = [M.m3s(st["dx"], st["dy"], True) for st in s["players"]["고치기"]["steps"]]
    check(fx[-1] < fx[0], f"고치기 — 잔차 |평균| + 3σ {round(fx[0], 2)} → {round(fx[-1], 2)}")
    rows = s["tables"]["전부세기_표"]["rows"]
    check(any(r[3] == "실측" for r in rows) and any(r[3].startswith("추정") for r in rows) and N["lsq_sec"] < N["brute_max_sec"], "전부 대 보기 표 = 실측 · 추정 행 · 최소제곱이 더 빠르다")

    print("값 하나(스칼라) 입력")
    inp = M.demo()
    inp["vector"] = False
    for r in inp["rows"]:
        r.pop("dy")
    sc = tmp / "scalar.json"
    M.C.write_steps(sc, M.run(inp))
    code, log = run(CHECK, sc, "--render")
    check(code == 0 and "PASS" in log, "dy 없는 입력도 check_contract --render PASS")

    print("양식 빌드 — steps 칸 · 도메인 한 장")
    for name in ("facts", "reqs"):
        shutil.copy(EXAMPLE / f"{name}.json", book / "contracts" / f"{name}.json")
    out = book / "dist" / "stattest.html"
    code, log = run(HERE / "build_book.py", book, "--stage", "2", "--out", out)
    mine = blanks(log)
    check(code == 0, "양식 + 가짜 과제 결과 빌드 종료 코드 0")
    check(not [b for b in mine if b.split(" · ")[1] in STEP_SLOTS], "재생기 · 그림 · 표 칸이 비지 않는다")
    check({f"s1 · {k}" for k in DOMAIN} <= mine, "도메인 한 장 칸이 비면 빈 칸으로 센다(5칸)")
    s1 = book / "content" / "s1.py"
    t = s1.read_text(encoding="utf-8")
    fill = {"도메인_제목": "먼저 알 것 — 판 위치 어긋남(가짜 분야)", "도메인_재는_것": "판 30곳에서 아래층과 위층 무늬의 위치 차이를 잰다.",
            "도메인_단위": "값은 nm, 좌표는 mm 다.", "도메인_나쁜_것": "**|평균| + 3σ 가 8 nm 를 넘으면** 그 판은 다시 만든다.",
            "도메인_고치는_법": ("장비에 보정값을 넣어 다음 로트부터 성분을 되돌린다 — 오버레이 계측 결과로.", {"오버레이": "(overlay) 층 사이 위치 어긋남"})}
    for k, v in fill.items():
        t = t.replace(f'        "{k}": "",', f"        {k!r}: {v!r},", 1)
    s1.write_text(t, encoding="utf-8")
    code, log = run(HERE / "build_book.py", book, "--stage", "2", "--out", out)
    check(code == 0 and not [b for b in blanks(log) if b.split(" · ")[1] in DOMAIN], "도메인 칸을 채우면 빈 칸에서 빠진다")
    h = out.read_text(encoding="utf-8")
    check("먼저 알 것 — 판 위치 어긋남" in h and "현장에서 고치는 법" in h and "(overlay)" in h, "도메인 상자 · 각주가 책에 들어간다")
    check(h.index("먼저 알 것") < h.index("진짜로 묻는 것"), "도메인 상자는 1장 앞쪽(진짜로 묻는 것보다 먼저)")
    check("성분으로 나누기" in h and "잔차 지도" in h and "관리도 —" in h and "후보 둘을 뺀 화살표" in h, "재생기 셋 · 순서 그림이 책에 들어간다")
    check("{F[" not in h, "식 글자 없음")
    code, log = run(HERE / "build_book.py", book, "--stage", "1", "--out", book / "dist" / "stage1.html")
    check(code == 0 and "먼저 알 것" in (book / "dist" / "stage1.html").read_text(encoding="utf-8"), "1차판(1 · 3 · 5장)에도 도메인 상자가 실린다")

    print("틀 규칙")
    check(not [w for w in BANNED if w in src], "공개 저장소 금지 낱말이 없다")
    check(not re.search(r"^(import|from) (?!argparse|itertools|math|random|statistics|sys|time|pathlib|_common)", src, re.M), "표준 라이브러리 + _common 만 불러온다")

    if not a.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not fails else f"FAIL — {len(fails)}개")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
