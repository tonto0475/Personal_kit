# -*- coding: utf-8 -*-
r"""책 검사 — 헤드리스 브라우저에서 쪽 나누기가 끝나기를 기다린 뒤 숫자로 잰다(창을 띄우지 않는다)
    py -3 book\check_book.py dist\pandas_book.html
    py -3 book\check_book.py dist\pandas_book.html --shots 1,5,12 --spreads 3,4 --shot-dir <폴더>

검사 항목(화면마다)
- 쪽보다 큰 블록 0 · 쪽 세로 넘침 0 · 쪽 가로 넘침 0(표 · 그림이 쪽 폭을 넘음)
- 각주 누락 0 — 본문 표식마다 그 쪽 아래에 설명이 있고, 설명마다 표식이 있다
- ↩ 연결고리 · 차례 · 찾아보기 링크의 대상이 책 안에 있다(일부 빌드의 범위 밖 링크는 따로 센다)
- 화면 전체 가로 스크롤 없음 · 스크립트 오류 없음
화면: PC 1920×1080(두 페이지) · 폰 412×915(한 페이지)
출력: 장별 쪽 수 · 문제 목록 · PASS/FAIL. --shots 는 쪽 번호(1부터), --spreads 는 펼침 번호(1부터 · all = 전부)를 PNG 로
브라우저(playwright · Chromium)가 없으면 «SKIP» 을 알리고 종료 코드 0 으로 끝난다 — PASS 가 아니다(쪽 크기는 bookkit/RULES.md 6절로 미리 지킨다)
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # 대회 리눅스처럼 playwright 가 없는 곳 — main 이 «건너뜀» 을 알리고 끝낸다
    sync_playwright = None

VIEWS = {"pc": dict(w=1920, h=1080, mode=2, mobile=False), "phone": dict(w=412, h=915, mode=1, mobile=True)}
HEADED = os.environ.get("CC_HEADED") == "1"


def open_book(br, url, w, h, mode, mobile=False, scale=1):
    ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale, is_mobile=mobile, has_touch=mobile)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"{url}?mode={mode}")
    pg.wait_for_function("window.__book && window.__book.ready", timeout=180000)
    return ctx, pg, errs


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--views", default="pc,phone")
    ap.add_argument("--shots", default="", help="쪽 번호 목록(1부터) — 한 페이지 보기로 크게 찍는다")
    ap.add_argument("--spreads", default="", help="펼침 번호 목록(1부터) · all = 전부 — 두 페이지 보기로 찍는다")
    ap.add_argument("--spread-name", default="s{:03d}.png", help="펼침 PNG 이름 형식(예: spread_{:02d}.png)")
    ap.add_argument("--shot-dir", default="")
    a = ap.parse_args(argv)
    if sync_playwright is None:
        print("SKIP — 브라우저 검사를 건너뛰었다: playwright 가 없다(PASS 아님). 쪽 크기는 bookkit/RULES.md 6절 기준으로 미리 지킨다")
        return 0
    path = Path(a.html).resolve()
    url = path.as_uri()
    shot_dir = Path(a.shot_dir) if a.shot_dir else Path(__file__).resolve().parent / "_shots" / path.stem
    fails = []
    pages_pc = 0
    with sync_playwright() as p:
        try:
            br = p.chromium.launch(headless=not HEADED)
        except Exception as e:  # 브라우저 파일이 없다(playwright install 안 함) 등
            print(f"SKIP — 브라우저 검사를 건너뛰었다: Chromium 을 띄우지 못했다({type(e).__name__}: {str(e).splitlines()[0][:120]}) (PASS 아님)")
            return 0
        for name in [v.strip() for v in a.views.split(",") if v.strip()]:
            v = VIEWS[name]
            ctx, pg, errs = open_book(br, url, v["w"], v["h"], v["mode"], v["mobile"])
            if HEADED:
                pg.bring_to_front()
            r = pg.evaluate("(() => { const b = window.__book; return {pages: b.pages, ms: b.ms, errors: b.errors, chapters: b.chapters, blocks: b.blocks, ext: b.ext_links, x: document.querySelectorAll('#book a.backx').length}; })()")
            hscroll = pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1 || document.getElementById('stage').scrollWidth > document.getElementById('stage').clientWidth + 1")
            print(f"[{name} {v['w']}×{v['h']} · {'두' if v['mode'] == 2 else '한'} 페이지] 쪽 {r['pages']} · 블록 {r['blocks']} · 쪽 나누기 {r['ms']} ms"
                  + (f" · 범위 밖 연결고리 {r['ext']}" if r["ext"] else "")
                  + (f" · 책 사이 연결고리 {r['x']}" if r["x"] else ""))
            if name == "pc":
                pages_pc = r["pages"]
            if name == "pc" or len(VIEWS) == 1:
                for c in r["chapters"]:
                    lab = (c["label"] + " " if c["label"] else "") + c["title"]
                    print(f"    {lab[:34]:<34} {c['first']:>4}–{c['last']:<4} ({c['pages']}쪽)")
            cnt = Counter(e["kind"] for e in r["errors"])
            for k, n in cnt.items():
                print(f"  문제 {k}: {n}")
                for e in [x for x in r["errors"] if x["kind"] == k][:6]:
                    print("     ", {kk: vv for kk, vv in e.items() if kk != "kind"})
            fails += [f"{name}: {e['kind']}" for e in r["errors"]]
            if hscroll:
                fails.append(f"{name}: 화면 가로 스크롤")
                print("  문제 화면 가로 스크롤")
            for e in errs:
                fails.append(f"{name}: 스크립트 오류 {e}")
                print("  문제 스크립트 오류:", e)
            ctx.close()
        # 쪽 · 펼침 PNG
        shots = [int(x) for x in a.shots.split(",") if x.strip()]
        if a.spreads.strip() == "all":  # 두 페이지 보기의 펼침 전부 — 쪽 수를 몰라도 된다
            if not pages_pc:
                ctx, pg, _ = open_book(br, url, 1920, 1080, 2)
                pages_pc = pg.evaluate("window.__book.pages")
                ctx.close()
            spreads = list(range(1, (pages_pc + 1) // 2 + 1))
        else:
            spreads = [int(x) for x in a.spreads.split(",") if x.strip()]
        if shots or spreads:
            shot_dir.mkdir(parents=True, exist_ok=True)
        if shots:
            ctx, pg, _ = open_book(br, url, 1100, 1400, 1, scale=1.5)
            pg.evaluate("document.body.classList.add('norail')")
            for n in shots:
                el = pg.locator(f'#book > section.page[data-pi="{n - 1}"]')
                if not el.count():
                    print("  쪽 없음:", n)
                    continue
                el.scroll_into_view_if_needed()
                pg.wait_for_timeout(150)
                out = shot_dir / f"p{n:03d}.png"
                el.screenshot(path=str(out))
                print("  찍음", out)
            ctx.close()
        if spreads:
            ctx, pg, _ = open_book(br, url, 1920, 1080, 2, scale=1)
            pg.evaluate("document.body.classList.add('norail')")
            for s in spreads:
                pg.evaluate(f"window.__book.go({(s - 1) * 2})")
                pg.wait_for_timeout(200)
                out = shot_dir / a.spread_name.format(s)
                pg.locator("#book").screenshot(path=str(out))
                print("  찍음", out)
            ctx.close()
        br.close()
    print("PASS" if not fails else f"FAIL ({len(fails)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
