#!/usr/bin/env python3
# bookkit → 지도 초안 도구 시험 — 예시 계약으로 실제로 실행해 출력 파일 · 종료코드를 확인
#   python3 scripts/ontology/test_from_bookkit.py   (pytest 로도 돈다)
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("from_bookkit.py")
# 키트 루트
KIT = Path(__file__).resolve().parents[2]
# 예시 계약 폴더 · 예시 과제 폴더
EXAMPLE = KIT / "bookkit" / "contracts" / "example"
TASK = EXAMPLE / "task"


# 도구 한 번 실행 → (종료코드, 출력)
# args: 도구 인자
def run(*args):
    r = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


# 예시 계약 → 초안: 칸이 채워지고 숫자 자리가 실측 값으로 풀렸나
def test_example_draft():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "ONTOLOGY_draft.md"
        code, log = run(EXAMPLE, "--task", TASK, "--out", out)
        assert code == 0, log
        text = out.read_text(encoding="utf-8")
        for want in ("> | Q1 |", "> | R1 |", "데이터 · T1", "숨은 요구 H1", "station_id(두 파일에 같은 이름 열",
                     "> | orders.csv | ? | qty |", "qty_total = 40", "**1.** (초안)"):
            assert want in text, want
        assert "{F[" not in text and "!!" not in text and "**작업장" not in text
        # 예시 계약에 id 가 다 붙어 순번 대체 없음(11/03 id 고정)
        assert "순번 대체: 없음" in log


# 계약에 id 가 있으면 순번 대신 그 id 를 쓴다
def test_uses_contract_ids():
    with tempfile.TemporaryDirectory() as d:
        c = Path(d) / "contracts"
        shutil.copytree(EXAMPLE, c, ignore=shutil.ignore_patterns("task"))
        reqs = json.loads((c / "reqs.json").read_text(encoding="utf-8"))
        for i, r in enumerate(reqs["readme"], 7):
            r["id"] = f"R{i}"
        reqs["questions"][0]["id"] = "Q9"
        (c / "reqs.json").write_text(json.dumps(reqs, ensure_ascii=False), encoding="utf-8")
        out = Path(d) / "draft.md"
        code, log = run(c, "--out", out)
        assert code == 0, log
        text = out.read_text(encoding="utf-8")
        assert "> | R7 |" in text and "> | Q9 |" in text and "> | R1 |" not in text
        assert "readme" not in log.split("순번 대체:")[1]


# 정본 ONTOLOGY.md 는 덮지 않고, 있는 초안은 --force 없이 덮지 않는다
def test_refuses_overwrite():
    with tempfile.TemporaryDirectory() as d:
        canon = Path(d) / "ONTOLOGY.md"
        code, log = run(EXAMPLE, "--out", canon)
        assert code == 1 and not canon.exists(), log
        out = Path(d) / "draft.md"
        out.write_text("서브가 고친 초안", encoding="utf-8")
        code, log = run(EXAMPLE, "--out", out)
        assert code == 1 and out.read_text(encoding="utf-8") == "서브가 고친 초안", log
        code, log = run(EXAMPLE, "--out", out, "--force")
        assert code == 0 and "> | Q1 |" in out.read_text(encoding="utf-8"), log


# 계약이 없는 폴더는 조용히 빈 초안을 만들지 않고 실패
def test_missing_contracts():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "draft.md"
        code, log = run(d, "--out", out)
        assert code != 0 and not out.exists(), log


if __name__ == "__main__":
    # 시험 함수 목록
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t()
            print("  통과 " + t.__name__, flush=True)
        except AssertionError as e:
            fails += 1
            print("  실패 " + t.__name__ + "  → " + str(e)[:300], flush=True)
    print(f"{len(tests) - fails}/{len(tests)} 통과")
    sys.exit(1 if fails else 0)
