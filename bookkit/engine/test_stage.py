# -*- coding: utf-8 -*-
r"""단계별 배포 시험 — 양식 + 예시 계약(contracts/example)으로 1차판 → 2차판을 빌드해 판 표시 · 회색 자리 · 고정 블록 ID · «새로» 띠를 본다

    python3 bookkit/engine/test_stage.py            → PASS / FAIL(종료 코드)

1. 양식을 임시 폴더에 책으로 복사 · reqs.json 만 넣고 --stage 1 → 1 · 3 · 5장만 내용 · 나머지 장은 회색 자리 · 빨간 빈 칸 0 · --strict 통과
2. facts · steps 를 넣고 --stage 2 → 판 표시 «2차판» · «새로» 왼쪽 막대(글자표 없음)가 바뀐 블록에만 · 1차판에 있던 블록 ID(s3-Q1 …)가 그대로
3. 같은 2차판을 한 번 더 → «새로» 0
4. --stage 2 --strict 는 빈 칸(글 칸)이 남아 실패해야 한다 · 1차판 --strict 는 통과
5. 중간판 — 1차판 → --chapters 로 장을 늘려 가며 → 2차판: 판 파일 · versions.json · 회색 자리 · 앞 판 대비 «새로» · --strict 는 빈 칸으로 안 막힌다 · 잘못 쓰면 실패
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 키트 bookkit 폴더 · 양식 · 예시 계약
KIT = HERE.parent
TEMPLATE = KIT / "template"
EXAMPLE = KIT / "contracts" / "example"


def build(book, *args):
    """빌드 → (종료 코드, 출력 글, html)"""
    r = subprocess.run([sys.executable, str(HERE / "build_book.py"), str(book), *args], capture_output=True, text=True, encoding="utf-8")
    html = (book / "dist" / "stagetest.html")
    return r.returncode, r.stdout + r.stderr, html.read_text(encoding="utf-8") if html.is_file() else ""


def ids(html):
    """블록 ID 목록"""
    return re.findall(r'<div class="blk [^"]*" data-id="([^"]+)"', html)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fails = []

    # 단언 하나 — 틀리면 이유를 모은다
    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    tmp = Path(tempfile.mkdtemp(prefix="stagetest_"))
    book = tmp / "stagetest"
    shutil.copytree(TEMPLATE, book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', '"doc": "stagetest",', 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    shutil.copy(EXAMPLE / "reqs.json", book / "contracts" / "reqs.json")

    print("1차판(reqs 만)")
    code, out, h1 = build(book, "--stage", "1", "--strict")
    check(code == 0, f"1차판 --strict 통과(종료 코드 {code})")
    check("빈 칸 0" in out, "빨간 빈 칸 0")
    check(h1.count('class="later"') > 5, f"회색 «2차판에서 채워짐» 자리 {h1.count('class=' + chr(34) + 'later' + chr(34))}곳")
    check("!!⟦빈 칸" not in h1 and 'class="bad">⟦빈 칸' not in h1, "빨간 «빈 칸» 글 없음")
    check('class="edtag">1차판 · 알고리즘 · 함정 준비 중' in h1, "첫 블록 위 판 표시 «1차판 …»")
    check('"short": "' in h1 and "1차판" in h1.split('id="bkmeta">', 1)[1][:400], "머리글(short)에 판 표시")
    i1 = ids(h1)
    check("s3-Q1" in i1 and "s1-S1" in i1, "질문 · 말하지 않은 곳 블록 ID = 항목 id(s3-Q1 · s1-S1)")
    check("질문 1." in h1 and "README 요구 1~" in h1, "책 번호 = id 번호(질문 1 · README 요구 1~)")
    check('data-new="1"' not in h1, "앞 판이 없으면 «새로» 없음")
    check((book / "dist" / "stagetest.blocks.json").is_file(), "앞 판 기억 파일(dist/stagetest.blocks.json)")
    check(len([b for b in i1 if b.startswith("s4")]) == 2, "4장은 자리만(장 머리 + 회색 한 줄)")

    print("2차판(facts · steps 추가)")
    for n in ("facts", "steps"):
        shutil.copy(EXAMPLE / f"{n}.json", book / "contracts" / f"{n}.json")
    code, out, h2 = build(book, "--stage", "2")
    check(code == 0, f"2차판 빌드(종료 코드 {code})")
    check('class="edtag">2차판' in h2, "판 표시 «2차판»")
    i2 = ids(h2)
    new = re.findall(r'data-id="([^"]+)"[^>]*data-new="1"', h2)
    check(0 < len(new) < len(i2), f"«새로» 블록 {len(new)} / 전체 {len(i2)}")
    check(all(x in i2 for x in i1 if not x.startswith(("pv", "s2", "s4", "aA", "aB", "aC", "toc"))), "1차판의 1 · 3 · 5장 블록 ID 가 2차판에 그대로")
    check("s3-Q1" not in new, "바뀌지 않은 질문 블록(s3-Q1)은 «새로» 아님")
    check(any(x.startswith("s4") for x in new), "4장(새로 실린 장)은 «새로»")
    check('content:"새로"' not in h2 and ".blk[data-new]::before" not in h2, "«새로» 글자표 없음 — 본문을 가리지 않는다")
    check(".blk[data-new]{background:linear-gradient(90deg,#fca5a5 0 3px" in h2, "«새로» 왼쪽 빨간 세로 막대는 유지")
    check(f"«새로» {len(new)}블록" in out, f"빌드 출력의 «새로» 수 = 표시된 블록 수 {len(new)}")
    code, out, h3 = build(book, "--stage", "2")
    check('data-new="1"' not in h3, "같은 2차판 다시 → «새로» 0")

    print("판마다 새 파일(덮어쓰기 금지)")
    dist = book / "dist"
    files = sorted(p.name for p in dist.glob("stagetest__v*.html"))
    check(files == ["stagetest__v1_1차판.html", "stagetest__v2_2차판.html", "stagetest__v3_2차판.html"], f"판 파일 3개(같은 판 다시 = 새 N) {files}")
    check((dist / "stagetest__v1_1차판.html").read_text(encoding="utf-8") == h1, "1차판 파일은 2차판 빌드 뒤에도 그대로")
    check((dist / "stagetest__v3_2차판.html").read_text(encoding="utf-8") == h3, "최신 복사본 dist/stagetest.html = 마지막 판")
    vj = json.loads((dist / "versions.json").read_text(encoding="utf-8"))
    vs = vj["versions"]
    check([v["n"] for v in vs] == [1, 2, 3] and vj["latest"] == "stagetest__v3_2차판.html", f"versions.json 판 목록 {[v['n'] for v in vs]}")
    check(vs[0]["new"] is None and vs[1]["new"] == len(new) and vs[2]["new"] == 0 and vs[1]["base"] == 1 and vs[0]["base"] is None,
          f"versions.json «새로» 수 · 기반 판 {[(v['new'], v['base']) for v in vs]}")
    check(all(v["blocks"] > 0 and "at" in v for v in vs) and vs[0]["blanks"] == 0, "versions.json 블록 수 · 시각 · 빈 칸")
    code, out, h5 = build(book, "--stage", "2", "--label", "정원 우선")
    check((dist / "stagetest__v4_정원_우선.html").is_file(), "--label → stagetest__v4_정원_우선.html")
    vs = json.loads((dist / "versions.json").read_text(encoding="utf-8"))["versions"]
    check(vs[-1]["name"] == "정원 우선" and vs[-1]["label"] == "정원 우선" and vs[-1]["stage"] == 2, f"라벨 판 기록 {vs[-1]}")
    n_files = len(list(dist.glob("stagetest__v*.html")))
    build(book, "--stage", "2", "--only", "s1")
    build(book, "--stage", "2", "--out", str(tmp / "o.html"))
    check(len(list(dist.glob("stagetest__v*.html"))) == n_files and len(json.loads((dist / "versions.json").read_text(encoding="utf-8"))["versions"]) == 4,
          "--only · --out 은 판 파일 · 판 목록을 만들지 않는다")
    code, out, _ = build(book, "--stage", "2", "--strict")
    check(code == 1 and "STRICT 실패" in out, "2차판 --strict = 빈 칸이 남으면 실패")

    print("자료 정리 전 표시")
    st = book / "contracts" / "steps.json"
    st.write_text(st.read_text(encoding="utf-8").replace('"type": "route",', '"type": "route",\n "data": "raw",', 1), encoding="utf-8")
    code, out, h4 = build(book, "--stage", "2")
    check("자료 정리 전 · 2차판 갱신" in h4, "steps.json data = raw → 4장 머리 «자료 정리 전 · 2차판 갱신»")

    print("중간판(1차판 → 장을 늘려 가며 → 2차판)")
    shutil.rmtree(book)
    shutil.copytree(TEMPLATE, book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', '"doc": "stagetest",', 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    shutil.copy(EXAMPLE / "reqs.json", book / "contracts" / "reqs.json")
    dist = book / "dist"
    build(book, "--stage", "1", "--strict")
    h1 = (dist / "stagetest__v1_1차판.html").read_text(encoding="utf-8")
    code, out, m0 = build(book, "--stage", "1", "--chapters", "s1,s3,s5,s4", "--label", "계약 전", "--strict")
    check(code == 0 and "s4" in out, f"steps 계약이 아직 없어도 4장 중간판이 멈추지 않는다(종료 코드 {code})")

    shutil.copy(EXAMPLE / "steps.json", book / "contracts" / "steps.json")
    code, out, m1 = build(book, "--stage", "1", "--chapters", "s1,s3,s5,s4", "--label", "4장까지", "--strict")
    check(code == 0 and "빈 칸 0" in out, f"중간판 --strict 는 빈 칸으로 안 막힌다(종료 코드 {code})")
    check((dist / "stagetest__v3_4장까지.html").read_text(encoding="utf-8") == m1, "판 파일 stagetest__v3_4장까지.html = 최신 복사본")
    check((dist / "stagetest__v1_1차판.html").read_text(encoding="utf-8") == h1, "1차판 파일은 그대로")
    check('class="edtag">4장까지 · 나머지 장 준비 중' in m1, "첫 블록 위 판 표시 «4장까지 · 나머지 장 준비 중»")
    im = ids(m1)
    new = re.findall(r'data-id="([^"]+)"[^>]*data-new="1"', m1)
    check(len([b for b in im if b.startswith("s4")]) > 2, "4장이 자리가 아니라 내용으로 실린다")
    check(len([b for b in im if b.startswith("s2")]) == 2 and m1.count('class="later"') > 5, "2장은 회색 자리 · 빈 칸은 회색")
    check(any(x.startswith("s4") for x in new) and all(x.startswith(("s1", "s4")) for x in new), f"«새로» = steps 로 바뀐 1장 그림 · 4장뿐({len(new)}블록)")
    check(m1.count(".cat-pipe{") == 1, "분류 칩 CSS 가 한 번(빈 장이 대신 싣는다)")
    vs = json.loads((dist / "versions.json").read_text(encoding="utf-8"))["versions"]
    v = vs[-1]
    check((v["name"], v["label"], v["stage"], v["chapters"], v["new"], v["base"]) == ("4장까지", "4장까지", 1, ["s1", "s3", "s4", "s5"], len(new), 2), f"판 목록 기록 {v}")
    check(vs[0]["chapters"] is None, "1차판의 판 목록 chapters = 없음")

    code, out, m2 = build(book, "--stage", "1", "--chapters", "s1,s3,s4,s5", "--label", "4장까지")
    check('data-new="1"' not in m2 and (dist / "stagetest__v4_4장까지.html").is_file(), "같은 중간판 다시 → 새 파일 · «새로» 0")
    code, out, m3 = build(book, "--stage", "1", "--chapters", "s1,s3,s4,s5")
    check((dist / "stagetest__v5_중간판.html").is_file() and 'class="edtag">중간판 · 나머지 장 준비 중' in m3, "--label 없으면 판 이름 «중간판»")

    shutil.copy(EXAMPLE / "facts.json", book / "contracts" / "facts.json")
    code, out, m4 = build(book, "--stage", "1", "--chapters", "pv,s1,s2,s3,s4,s5", "--label", "2장까지", "--strict")
    new = re.findall(r'data-id="([^"]+)"[^>]*data-new="1"', m4)
    check(code == 0 and any(x.startswith("s2") for x in new), f"facts 뒤 2장 중간판 — «새로» 에 2장(종료 코드 {code} · {len(new)}블록)")
    check(m4.count(".cat-pipe{") == 1, "한눈에를 실으면 CSS 는 한눈에만 싣는다(두 번 안 실린다)")

    code, out, m5 = build(book, "--stage", "2")
    new = re.findall(r'data-id="([^"]+)"[^>]*data-new="1"', m5)
    check(code == 0 and 'class="edtag">2차판' in m5 and any(x.startswith("aA") for x in new) and "s3-Q1" not in new, f"2차판 «새로» = 마지막 중간판 대비({len(new)}블록 · 부록 있음 · 안 바뀐 s3-Q1 없음)")

    code, out, _ = build(book, "--stage", "1", "--chapters", "s9")
    check(code != 0 and "--chapters 에 모르는 이름" in out, "모르는 장 이름 → 실패")
    n_files = len(list(dist.glob("stagetest__v*.html")))
    for args in (("--stage", "2", "--chapters", "s1"), ("--chapters", "s1"), ("--stage", "1", "--chapters", "s1", "--only", "s1")):
        code, out, _ = build(book, *args)
        check(code != 0 and "--chapters 는" in out, f"잘못 쓴 조합 {args} → 실패")
    check(len(list(dist.glob("stagetest__v*.html"))) == n_files, "실패한 빌드는 판 파일을 만들지 않는다")
    shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not fails else f"FAIL {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
