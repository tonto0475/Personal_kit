# -*- coding: utf-8 -*-
r"""v3 동일성 시험 — 양식 + v3 내용(books/_selftest_v3)을 2차판 · v3 호환으로 빌드해 v3 정본과 블록 · 펼침 그림을 견준다

    python3 bookkit/engine/same_v3.py                 블록 비교(바이트) → PASS / FAIL
    python3 bookkit/engine/same_v3.py --png <폴더>     + 펼침 PNG 17장 픽셀 비교(playwright · Pillow 필요)

- 빌드 인자 = --stage 2 --strict --v3-compat(«새로» 띠 · 판 표시 · 고정 블록 id 를 끈 판 — v3 와 바이트 비교용)
- 자체 시험 책이 없으면(공개 저장소) «SKIP» 을 찍고 종료 코드 0
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 키트 bookkit 폴더
KIT = HERE.parent
# 자체 시험 책 · v3 정본 html · 정본 펼침 그림 폴더
BOOK = KIT / "books" / "_selftest_v3"
GOLD = BOOK / "gold" / "task10_guide_v3.html"
GOLD_PNG = BOOK / "gold" / "Image"


def blocks(html):
    """책 html → 블록 html 목록(bksrc 안 «<div class="blk » 로 시작하는 조각)"""
    body = html.split('<div id="bksrc" class="bksrc">', 1)[1].split('</div>\n<script type="application/json" id="bkmeta">', 1)[0]
    return [b for b in re.split(r'(?=<div class="blk )', body) if b]


def compare_png(a_dir, b_dir):
    """두 폴더의 spread_*.png 를 픽셀로 견준다 → (같은 장 수, 다른 장 이름 목록)"""
    from PIL import Image, ImageChops
    same, diff = 0, []
    for g in sorted(Path(b_dir).glob("spread_*.png")):
        p = Path(a_dir) / g.name
        if not p.is_file():
            diff.append(f"{g.name}(없음)")
            continue
        x, y = Image.open(p).convert("RGB"), Image.open(g).convert("RGB")
        if x.size != y.size or ImageChops.difference(x, y).getbbox():
            diff.append(g.name)
        else:
            same += 1
    return same, diff


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="v3 동일성 시험")
    ap.add_argument("--png", help="펼침 PNG 를 찍을 폴더(주면 픽셀 비교까지)")
    a = ap.parse_args(argv)
    if not BOOK.is_dir() or not GOLD.is_file():
        print("SKIP — 자체 시험 책 · v3 정본이 없다(PASS 아님)")
        return 0
    out = Path(tempfile.mkdtemp(prefix="same_v3_")) / "v3.html"
    r = subprocess.run([sys.executable, str(HERE / "build_book.py"), str(BOOK), "--stage", "2", "--strict", "--v3-compat", "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print("FAIL — 빌드 실패\n" + r.stdout[-1500:] + r.stderr[-1500:])
        return 1
    a_bl, g_bl = blocks(out.read_text(encoding="utf-8")), blocks(GOLD.read_text(encoding="utf-8"))
    same = sum(1 for x, y in zip(a_bl, g_bl) if x == y)
    ok = len(a_bl) == len(g_bl) == same
    print(f"블록 {len(a_bl)} / 정본 {len(g_bl)} · 바이트 같음 {same}")
    if not ok:
        k = next((i for i, (x, y) in enumerate(zip(a_bl, g_bl)) if x != y), min(len(a_bl), len(g_bl)))
        print(f"  첫 차이 #{k}:\n  빌드 {a_bl[k][:300] if k < len(a_bl) else '(없음)'}\n  정본 {g_bl[k][:300] if k < len(g_bl) else '(없음)'}")
    if a.png and ok:
        shot = Path(a.png)
        shot.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(HERE / "book" / "check_book.py"), str(out), "--spreads", "all",
                            "--spread-name", "spread_{:02d}.png", "--shot-dir", str(shot)], capture_output=True, text=True, encoding="utf-8")
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:])
        n, diff = compare_png(shot, GOLD_PNG)
        print(f"펼침 PNG 같음 {n} · 다름 {len(diff)}" + (f" — {', '.join(diff)}" if diff else ""))
        ok = ok and not diff and n == len(list(GOLD_PNG.glob('spread_*.png')))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
