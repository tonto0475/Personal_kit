# -*- coding: utf-8 -*-
r"""v3 서식 시험 — 모델이 칸을 v3 와 다르게 채우기 쉬운 곳을 키트가 v3 모양으로 그리고(양식) · 잡는지(빌드 · 계약 검사) 본다

    python3 bookkit/engine/test_format.py            → PASS / FAIL(종료 코드)

2026-11-04 10번 연습판(소넷이 만든 책)과 v3 를 블록마다 비교해 나온 차이에서:
0. 1차판에서 «한눈에» 를 비우면 분류 칩 · ◎ CSS(kit.STYLE)가 빠져 칩이 제목에 붙은 글자로 · dl 이 맨 글로 → 빈 장이 대신 싣는다
1. 원본 줄 사이 설명 글(색 null)의 {F['이름']} — 책에 «{F[…]}» 글자 그대로 나왔다 → 값으로 채운다
2. 결함 «a · b» — 칩 하나로 붙었다 → 칩 둘(v3) · [[글, null]] = 칩 없는 설명 글(v3 «사원 · 날짜마다 한 줄»)
3. 1차판 빈 칸이면 절 제목 «진짜로 묻는 것 — N 가지» → 개수 없이
4. 원본 조각에 식 → 계약 검사 FAIL · 빌드에 식 글자가 남으면 --strict 실패
5. 서식 경고: 절 제목 번호(«4.1 …») · 계약 칸 v3 한도(숨은 요구 · 말하지 않은 곳 제목) · 너무 짧은 이유
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 키트 bookkit 폴더 · 양식 · 예시 계약 · 계약 검사기
KIT = HERE.parent
TEMPLATE = KIT / "template"
EXAMPLE = KIT / "contracts" / "example"
CHECK = KIT / "contracts" / "check_contract.py"


def run(*args):
    """파이썬 실행 → (종료 코드, 출력 글)"""
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fails = []

    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    tmp = Path(tempfile.mkdtemp(prefix="fmttest_"))
    book = tmp / "fmttest"
    shutil.copytree(TEMPLATE, book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', '"doc": "fmttest",', 1), encoding="utf-8")
    con = book / "contracts"
    con.mkdir(exist_ok=True)
    for n in ("facts", "reqs", "steps"):
        shutil.copy(EXAMPLE / f"{n}.json", con / f"{n}.json")
    out = book / "dist" / "fmttest.html"

    print("1차판 — 빈 칸이면 «N 가지» 없음")
    code, log = run(HERE / "build_book.py", book, "--stage", "1", "--out", out)
    h = out.read_text(encoding="utf-8") if out.is_file() else ""
    check(code == 0 and "N 가지" not in h and ">진짜로 묻는 것</h2>" in h, "«진짜로 묻는 것» 절 제목에 «N 가지» 가 없다")
    check(h.count(".cat-pipe{") == 1 and h.index(".cat-pipe{") < h.index('class="qi '), "1차판(한눈에 비움)에도 분류 칩 · ◎ CSS 가 한 번 · ◎ 보다 앞에(빈 장이 대신 싣는다)")

    # 계약에 모델이 쓰기 쉬운 모양을 넣는다
    F = json.loads((con / "facts.json").read_text(encoding="utf-8"))
    F["traps"][0]["raw"].append(["— 이런 줄이 {F['lower_id_rows']}행", None])
    F["defects"][0]["bad"] = "p3 · p4"
    F["defects"][0]["good"] = [["작업장마다 대문자 한 글자", None]]
    (con / "facts.json").write_text(json.dumps(F, ensure_ascii=False, indent=1), encoding="utf-8")
    R = json.loads((con / "reqs.json").read_text(encoding="utf-8"))
    R["hidden"][0]["text"] = "작업장 번호가 소문자로 섞여 있어서 그대로 이으면 짝이 사라지므로 대문자로 맞춰야 한다"
    R["silent"][0]["title"] = "주문 하나를 여러 작업장이 나눠 맡아도 되는지 아니면 한 곳이 다 맡아야 하는지"
    (con / "reqs.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
    s4a = book / "content" / "s4_a.py"
    s4a.write_text(s4a.read_text(encoding="utf-8").replace('"절1_제목": "",', '"절1_제목": "4.1 먼저 쉬운 경우 — 셋",', 1), encoding="utf-8")

    print("2차판 — 양식이 v3 모양으로 그린다")
    code, log = run(HERE / "build_book.py", book, "--stage", "2", "--out", out)
    h = out.read_text(encoding="utf-8") if out.is_file() else ""
    lower = str(F["numbers"]["lower_id_rows"])
    check(f"— 이런 줄이 {lower}행" in h and "{F[" not in h, f"원본 줄 설명 글의 {{F['lower_id_rows']}} → {lower}")
    check('<span class="mono bad">p3</span> · <span class="mono bad">p4</span>' in h, "결함 «p3 · p4» → 빨간 칩 둘")
    check("작업장마다 대문자 한 글자" in h and '<span class="mono good">작업장마다' not in h, "결함 정상 예 [[글, null]] → 칩 없는 글")
    check("서식: 절 제목에 번호를 손으로 붙였다 «4.1" in log, "빌드 «서식:» 이 절 제목 번호를 잡는다")
    check("식 글자 남음" not in log, "식 글자 남음 0")

    print("계약 검사 — v3 한도 · 원본 조각 식")
    code, log = run(CHECK, con)
    check(code == 0, "길이 경고는 PASS 를 막지 않는다")
    check("hidden[0](H1): «text»" in log and "v3 한도 28자" in log, "숨은 요구 text 가 길면 경고(v3 한도 28)")
    check("silent[0](S1): «title»" in log, "말하지 않은 곳 제목이 길면 경고(v3 한도 24)")
    check("«why»" in log and "너무 짧다" in log, "질문 이유가 짧으면 경고")
    F["traps"][0]["raw"].append(["{F['qty_total']}", "bad"])
    (con / "facts.json").write_text(json.dumps(F, ensure_ascii=False, indent=1), encoding="utf-8")
    code, log = run(CHECK, con / "facts.json")
    check(code == 1 and "원본 조각" in log and "계산되지 않는다" in log, "원본 조각에 {식} → FAIL")
    code, log = run(HERE / "build_book.py", book, "--stage", "2", "--strict", "--out", out)
    check(code == 1 and "식 글자 남음" in log, "빌드 --strict — 책에 «{F[…]}» 가 남으면 실패")

    shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not fails else f"FAIL — {len(fails)}개")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
