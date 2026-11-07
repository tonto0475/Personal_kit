# -*- coding: utf-8 -*-
r"""책 빌드 — 책 폴더(META · ORDER 가 든 __init__.py + 장 파일)를 차례로 실행해 HTML 한 파일로 만든다

    python3 bookkit/engine/build_book.py bookkit/books/<이름>                  → bookkit/books/<이름>/dist/<doc>__v<N>_<판 이름>.html (전체 · 새 판 = 새 파일)
                                                                               + dist/<doc>.html(최신 판 복사본) · dist/versions.json(판 목록)
    python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 2 --label 정원우선   → …/dist/<doc>__v<N>_정원우선.html(방향을 바꾼 판)
    python3 bookkit/engine/build_book.py bookkit/books/<이름> --only s1,s2     → …/dist/_partial/<doc>__s1_s2.html (일부)
    python3 bookkit/engine/build_book.py bookkit/books/<이름> --out <경로>
    python3 bookkit/engine/build_book.py bookkit/books/<이름> --strict         → 빈 칸 · 구조 바뀜이 하나라도 있으면 실패(종료 코드 1)
    python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 1        → 1차판(1장 · 3장 · 5장 — 나머지 장 · 빈 칸은 회색 «2차판에서 채워짐»)
    python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 1 --chapters s1,s3,s5,s4 --label 4장까지 --strict   → 중간판(이 장까지 싣는다 · 나머지 장 · 빈 칸은 회색)
    python3 bookkit/engine/build_book.py bookkit/books/<이름> --stage 2        → 2차판(전부 · --strict 와 함께 빈 칸 0)

--only : 쉼표로 나눈 목록. 숫자 · 범위는 장 번호(6-10 → ch06 ~ ch10), 그 밖은 모듈 이름(pv · s1 · apx …)
         일부 빌드는 기본 출력 이름이 달라 전체 판을 덮어쓰지 않는다
--chapters : 중간판(장이 끝날 때마다 내는 판) — --stage 1 과 함께 · 싣는 장 전체를 모듈 이름으로(META «stage1» 대신 · 순서는 ORDER 대로)
         1차판처럼 없는 숫자 · 빈 칸이 회색이고 --strict 는 구조 바뀜만 본다 · 판 이름 = --label(없으면 «중간판») · 판 파일 · versions.json · «새로» 는 다른 판과 같다
--stage : 판(단계별 배포). 판을 주면 첫 블록 위 · 머리글에 판 표시, 앞 판 결과(출력 옆 <doc>.blocks.json — 블록 ID · 내용 해시)와 견줘
          새로 생기거나 바뀐 블록에 «새로» 띠를 단다(사람 · AI 가 표시하지 않는다). 1차판의 --strict 는 구조 바뀜만 본다(빈 칸 0 은 2차판에서만)
판은 덮어쓰지 않는다 : 전체 빌드는 할 때마다 N 이 하나 늘어난 새 파일(같은 판을 다시 빌드해도) — 앞 판 html 은 그대로 남는다
          판 이름 = --label(유저가 방향을 틀어 다시 만든 판) · 없으면 1차판 · 2차판 · 판 없이 빌드하면 «전체»
          --only(_partial) · --out(그 경로 그대로) · --v3-compat 은 버전 파일을 만들지 않는다
--v3-compat : 옛 블록 ID(장-순번) · 판 표시 없음 · «새로» 없음 — v3 정본과 바이트 비교용(engine/same_v3.py 가 쓴다)
블록 ID : 기본 «장-칸 이름»(계약 항목은 «장-항목 id» — s3-Q1) — 판이 바뀌어 블록 수가 달라져도 읽던 위치 · 스티커 자리가 그대로
없는 모듈은 건너뛴다
빌드 끝에 알리는 것: 경고(각주 · 연결고리) · 빈 칸(양식의 칸을 안 채운 곳 «장 · 칸») · 2차판에서 채워짐(1차판) · «새로» 수 · 구조 바뀜(양식 template 과 다른 장 파일)
검사: python3 bookkit/engine/book/check_book.py <출력 html>
"""
import argparse
import importlib
import importlib.util
import json
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 양식 폴더 — 책의 장 파일 구조가 양식과 같은지 견줄 때 쓴다(bookkit/template)
TEMPLATE = HERE.parent / "template"
# 장 파일에서 «칸»(과제마다 채우는 곳)과 «구조»(고치지 않는 곳)를 가르는 줄의 머리
STRUCT_MARK = "# ══ 구조"


def select(order, only, flag="--only"):
    """--only · --chapters 해석 → 모듈 이름 목록(ORDER 순서 유지)"""
    if not only:
        return list(order)
    want = set()
    for tok in only.split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", tok)
        if m:
            want.update(f"ch{n:02d}" for n in range(int(m.group(1)), int(m.group(2)) + 1))
        elif tok.isdigit():
            want.add(f"ch{int(tok):02d}")
        else:
            want.add(tok)
    unknown = sorted(want - set(order))
    if unknown:
        raise SystemExit(f"{flag} 에 모르는 이름: {unknown}\n가능한 이름: {', '.join(order)}")
    return [m for m in order if m in want]


def load_book(book_dir):
    """책 폴더를 패키지로 불러온다 — 폴더 이름(숫자 · 밑줄로 시작해도)과 무관한 별칭으로. → (별칭, 패키지)"""
    book_dir = Path(book_dir).resolve()
    init = book_dir / "__init__.py"
    if not init.is_file():
        raise SystemExit(f"책 폴더가 아니다(__init__.py 없음): {book_dir}")
    alias = "bk_" + re.sub(r"\W", "_", book_dir.name)
    spec = importlib.util.spec_from_file_location(alias, init, submodule_search_locations=[str(book_dir)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[alias] = pkg
    spec.loader.exec_module(pkg)
    return alias, pkg


def drift(book_dir):
    """양식(template)과 구조가 다른 파일 목록 — kit.py · figs.py 는 통째로, 장 파일 · __init__.py 는 «# ══ 구조» 줄 아래만 견준다"""
    book_dir = Path(book_dir).resolve()
    if not TEMPLATE.is_dir() or book_dir == TEMPLATE.resolve():
        return []
    out = []
    for t in sorted(TEMPLATE.glob("*.py")):
        b = book_dir / t.name
        if not b.is_file():
            out.append(f"{t.name} — 양식에 있는 파일이 책에 없다")
            continue
        ta, ba = t.read_text(encoding="utf-8"), b.read_text(encoding="utf-8")
        if STRUCT_MARK in ta:
            if STRUCT_MARK not in ba:
                out.append(f"{t.name} — «{STRUCT_MARK}» 줄이 없다(칸과 구조의 경계를 지웠다)")
                continue
            ta, ba = ta.split(STRUCT_MARK, 1)[1], ba.split(STRUCT_MARK, 1)[1]
        if ta != ba:
            tl, bl = ta.splitlines(), ba.splitlines()
            k = next((i for i in range(min(len(tl), len(bl))) if tl[i] != bl[i]), min(len(tl), len(bl)))
            out.append(f"{t.name} — 양식과 다르다(구조 부분 {k + 1}번째 줄: «{(bl[k] if k < len(bl) else '(끝)').strip()[:60]}»)")
    return out


def stub(bk, name, meta, env, style=""):
    """1차판에서 아직 싣지 않는 장 — 장 머리 + 회색 «2차판에서 채워짐» 한 줄(META «stubs» 의 장 번호 · 제목)
    style = 양식 kit.STYLE(분류 칩 · ◎ 항목 · 원본 줄 · 결함 표 CSS) — 원래 «한눈에» 첫 블록이 싣는데 1차판은 그 장을 비우므로 빈 장이 대신 싣는다"""
    def build_stub(w):
        if style:
            w.html(style)
        for no, title in meta.get("stubs", {}).get(name, [(name, name)]):
            w.chapter(no, title, "⟪2차판에서 채워진다⟫")
            w.p(f"⟪2차판에서 채워짐 — {name}⟫ 이 장은 자료 분석(A1) · 알고리즘 분석(A3)이 끝난 뒤 2차판에 실린다.")
            bk.later.append(f"{name} · 장 전체({no})")
    bk.run_module(name, build_stub, env)


def kit_style(alias):
    """책 패키지의 kit.STYLE(없으면 빈 글)"""
    try:
        return getattr(importlib.import_module(f"{alias}.kit"), "STYLE", "") or ""
    except ImportError:
        return ""


# ════════════════════════════════════════════════════════════
# 서식 점검 — v3 와 서식이 갈리는 곳(모델이 칸을 다르게 채우기 쉬운 곳)을 빌드가 알린다
# 한도 = v3 정본(task10_guide_v3)의 같은 블록 최대 + 약간 · v3 를 빌드하면 0건이어야 한다
# ════════════════════════════════════════════════════════════
# 블록 종류 → 글자 수 한도(넘으면 v3 보다 길어 쪽 · 상자 모양이 달라진다)
FMT_LEN = {"p": 350, "box-ng": 220, "box-name": 260, "back": 210, "box-guess": 280, "box-rule": 150, "box-think": 130}
# ◎ 항목 — 제목 · 칸 하나 · 카드 전체 글자 수 한도(v3 최대 80 · 150 · 324)
FMT_QI = {"title": 85, "dd": 170, "total": 360}
# 표(재생기 밖) 행 수 한도 — RULES 6절 «12행 이하 권장»
FMT_ROWS = 12
# v3 가 **굵게** 를 꼭 한 곳 이상 쓴 문단(칸 이름 블록 ID) — 핵심 한 문장 · 결론 숫자
FMT_BOLD = ("s1-무엇을", "s1-입력_종류", "s1-출제_의도", "s2-가장_큰_함정", "aA-A_들어가며1")
# 식이 계산되지 않고 글자로 남은 자리 — «{F['이름']}» · «{hm(…)}» 처럼
FMT_EXPR = re.compile(r"\{\s*[A-Za-z_]\w*\s*[\[\(]|\{F\b")


def _plain(h):
    """블록 HTML → 글(꼬리표 · 각주 표식 제거)"""
    import html as _h
    h = re.sub(r"<style>.*?</style>", "", h, flags=re.S)
    h = re.sub(r"<[^>]+>", "", h)
    return _h.unescape(re.sub(r"\s+", " ", h)).strip()


def format_lint(blocks, stage=None):
    """블록 목록 → (서식 경고 목록, 식 글자 남음 목록 — --strict 실패)"""
    warn, expr = [], []
    for b in blocks:
        bid, k, h = b.id, b.kind, b.html
        body = re.sub(r"<svg.*?</svg>", "", h, flags=re.S)
        text = _plain(body)
        svg_text = " ".join(_plain(x) for x in re.findall(r"<text[^>]*>(.*?)</text>", h, flags=re.S))
        for t in (text, svg_text):
            m = FMT_EXPR.search(t)
            if m:
                expr.append(f"식이 계산되지 않고 글자로 남았다 «{t[m.start():m.start() + 40]}» — 블록 {bid} "
                            f"(원본 조각 · `코드` 안에는 식을 쓸 수 없다 — 값을 넣거나 설명 글로 옮긴다)")
                break
        if stage == 2 and 'class="later"' in h:
            warn.append(f"2차판에 «⟪…⟫» 자리가 남았다 — 블록 {bid} «{text[:40]}» (1차판 표시 · steps.json \"data\": \"raw\" 면 정리한 자료로 다시 돌리고 \"clean\")")
        if k in ("section", "sub"):
            if re.match(r"\d+(\.\d+)+\s", text):
                warn.append(f"절 제목에 번호를 손으로 붙였다 «{text[:30]}» — 블록 {bid} (v3 절 제목은 번호 없음)")
        if k in FMT_LEN and len(text) > FMT_LEN[k]:
            warn.append(f"{k} {len(text)}자 — v3 한도 {FMT_LEN[k]}자 넘음 · 블록 {bid} (둘로 나누거나 줄인다)")
        if k == "html" and 'class="qi' in h:
            m = re.search(r'<p class="qh">(.*?)</p>', h, re.S)
            title = _plain(m.group(1)) if m else ""
            dds = [_plain(x) for x in re.findall(r"<dd>(.*?)</dd>", h, re.S)]
            total = len(title) + sum(map(len, dds))
            if len(title) > FMT_QI["title"]:
                warn.append(f"◎ 제목 {len(title)}자 — v3 한도 {FMT_QI['title']}자 · 블록 {bid} «{title[:30]}»")
            if dds and max(map(len, dds)) > FMT_QI["dd"]:
                warn.append(f"◎ 칸 {max(map(len, dds))}자 — v3 한도 {FMT_QI['dd']}자(칸 하나 2~3문장) · 블록 {bid}")
            if total > FMT_QI["total"]:
                warn.append(f"◎ 카드 {total}자 — v3 한도 {FMT_QI['total']}자 · 블록 {bid}")
        if k == "table":
            rows = h.count("<tr") - 1
            if rows > FMT_ROWS:
                warn.append(f"표 {rows}행 — {FMT_ROWS}행 이하 권장(v3 최대 9) · 블록 {bid}")
        if bid in FMT_BOLD and "<b>" not in h and 'class="later"' not in h:
            warn.append(f"굵게 없음 — 블록 {bid} (v3 는 이 문단의 핵심 한 문장 · 결론 숫자를 **굵게**)")
    return warn, expr


def prev_path(out_path):
    """앞 판 기억 파일 — 출력 html 옆 «<이름>.blocks.json»(블록 ID → 내용 해시)"""
    return Path(out_path).with_suffix(".blocks.json")


def versions_path(latest):
    """판 목록 파일 — 최신 판 복사본(dist/<doc>.html) 옆 versions.json"""
    return Path(latest).parent / "versions.json"


def load_versions(latest):
    """versions.json → 판 목록(없거나 깨졌으면 빈 목록)"""
    p = versions_path(latest)
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("versions", []) if p.is_file() else []
    except (OSError, ValueError, AttributeError):
        return []


def next_version(latest, versions):
    """다음 판 번호 — versions.json 과 dist 의 «<doc>__v<N>_*.html» 중 가장 큰 N + 1(목록이 지워져도 옛 파일을 덮지 않게)"""
    latest = Path(latest)
    pat = re.compile(re.escape(latest.stem) + r"__v(\d+)_")
    ns = [int(v.get("n", 0)) for v in versions]
    ns += [int(m.group(1)) for f in latest.parent.glob(f"{latest.stem}__v*_*.html") if (m := pat.match(f.name))]
    return max(ns, default=0) + 1


def version_name(stage, label, chapters=None):
    """판 이름 — 라벨(방향을 바꾼 판 · 중간판) · 없으면 «중간판» · «N차판» · 판 없이 빌드하면 «전체»"""
    if label:
        return label.strip()
    if chapters:
        return "중간판"
    return f"{stage}차판" if stage else "전체"


def version_file(latest, n, name):
    """판 파일 경로 — dist/<doc>__v<N>_<판 이름>.html(파일 이름에 못 쓰는 글자 · 공백은 _)"""
    latest = Path(latest)
    safe = re.sub(r"[^\w\-]", "_", name, flags=re.U).strip("_") or "판"
    return latest.with_name(f"{latest.stem}__v{n}_{safe}.html")


def build(book_dir, only=None, out=None, stage=None, compat=False, chapters=None, label=None):
    """빌드 → (출력 경로, html, 통계). 쓰기는 이 함수를 __main__ 에서 부를 때만 일어난다
    stage = None(판 없음) · 1 · 2 / compat = v3 호환(옛 블록 ID · 판 표시 · «새로» 끔)
    chapters = 중간판에 싣는 장(쉼표 목록 · stage 1 일 때 META «stage1» 대신) / label = 판 이름(중간판의 판 표시에 쓴다)"""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from book import engine as E
    E.STAGE = stage  # 책(data.py · kit.py)을 불러오기 전에 — 1차판이면 없는 숫자 · 빈 칸이 회색
    from book.engine import Book

    book_dir = Path(book_dir).resolve()
    alias, pkg = load_book(book_dir)
    meta, order = pkg.META, pkg.ORDER
    mods = select(order, only)
    E.TABLE_WARN.clear()
    bk = Book(meta)
    bk.blanks = []  # 빈 칸(«장 · 칸») — 양식의 kit.slots 가 채운다
    bk.later = []  # 1차판의 «2차판에서 채워짐» 자리(빈 칸으로 세지 않는다)
    bk.legacy_ids = compat
    if stage and not compat:
        bk.edition = meta.get("editions", {}).get(stage, f"{stage}차판")
    # 1차판 · 중간판에 싣는 장(그 밖의 장은 회색 자리)
    shown = meta.get("stage1")
    if chapters:
        shown = select(order, chapters, "--chapters")
        bk.edition = f"{version_name(stage, label, shown)} · 나머지 장 준비 중"
    built, skipped = [], []
    t0 = time.perf_counter()
    # 1차판에서 «한눈에» 처럼 STYLE 을 싣는 장이 빠질 때 — 첫 빈 장이 한 번 대신 싣는다(서식 깨짐 방지)
    style_left = kit_style(alias) if stage == 1 and shown is not None and "pv" not in shown else ""
    for name in mods:
        if not (book_dir / f"{name}.py").exists():
            skipped.append(name)
            continue
        t = time.perf_counter()
        n0 = len(bk.blocks)
        if stage == 1 and shown is not None and name not in shown:
            stub(bk, name, meta, meta["env"](), style_left)
            style_left = ""
        else:
            mod = importlib.import_module(f"{alias}.{name}")
            bk.run_module(name, mod.build, meta["env"]())
        built.append(name)
        print(f"  {name:<9} 블록 {len(bk.blocks) - n0:>4}  ({(time.perf_counter() - t) * 1000:,.0f} ms)")
    if not built:
        raise SystemExit("빌드할 모듈이 없다")
    if out:
        path = Path(out)
    elif only:
        safe = re.sub(r"[^0-9A-Za-z_\-]", "_", only)  # 쉼표도 _ 로(파일 주소에서 %2C 로 바뀌지 않게)
        path = book_dir / "dist" / "_partial" / f"{meta['doc']}__{safe}.html"
    else:
        path = book_dir / "dist" / f"{meta['doc']}.html"
    if stage and not compat and not only and prev_path(path).is_file():  # 앞 판이 있으면 «새로» 비교
        bk.prev = json.loads(prev_path(path).read_text(encoding="utf-8")).get("blocks", {})
    html, stats = bk.render(only_desc=only or "")
    if stage == 1:  # 1차판 · 중간판 — 장 파일이 직접 적은 빈 칸(한눈에의 META 칸)도 «2차판 대기» 로(--strict 는 구조 바뀜만)
        bk.later += bk.blanks
        bk.blanks = []
    stats.update(built=built, skipped=skipped, seconds=time.perf_counter() - t0, warnings=bk.warnings + bk.lint() + list(dict.fromkeys(E.TABLE_WARN)),
                 blanks=list(dict.fromkeys(bk.blanks)), later=list(dict.fromkeys(bk.later)), drift=drift(book_dir), stage=stage, compared=bk.prev is not None)
    stats["format"], stats["expr"] = format_lint(bk.blocks, stage)
    stats["title"] = meta.get("short") or meta.get("title") or meta.get("doc", "")  # 판 목록(versions.json)에 싣는 책 제목
    stats["shown"] = shown if chapters else None  # 중간판에 실은 장(판 목록에 남긴다)
    return path, html, stats


def copy_extra(stats, out_path):
    """w.open_full 이 모은 파일(stats["extra_files"])을 출력 html 옆에 «<doc>__<이름>» 으로 복사 → 복사한 경로 목록"""
    out = []
    for dest, src in (stats.get("extra_files") or {}).items():
        target = Path(out_path).parent / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        out.append(target)
    return out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="책 빌드")
    ap.add_argument("book", help="책 폴더 경로 (bookkit/books/<이름>)")
    ap.add_argument("--only", help="일부만: pv,s1 · apx")
    ap.add_argument("--out", help="출력 html 경로")
    ap.add_argument("--strict", action="store_true", help="빈 칸 · 구조 바뀜이 있으면 실패(완성본 확인용 · 1차판은 구조 바뀜만)")
    ap.add_argument("--stage", type=int, choices=(1, 2), help="판 — 1 = 1차판(1 · 3 · 5장) · 2 = 2차판(전부)")
    ap.add_argument("--v3-compat", action="store_true", help="옛 블록 ID · 판 표시 · «새로» 끔(v3 바이트 비교용)")
    ap.add_argument("--label", help="판 이름 — 유저가 방향을 틀어 다시 만든 판(예 «정원우선») · 중간판(예 «4장까지») · 파일 이름 <doc>__v<N>_<라벨>.html")
    ap.add_argument("--chapters", help="중간판에 싣는 장 전체(--stage 1 과 함께): s1,s3,s5,s4 — 나머지 장 · 빈 칸은 회색")
    a = ap.parse_args(argv)
    if a.chapters and (a.stage != 1 or a.only or a.v3_compat):
        ap.error("--chapters 는 --stage 1 과 함께만 쓴다(--only · --v3-compat 과 같이 못 쓴다)")
    sys.path.insert(0, str(HERE))
    from book.engine import BuildError
    try:
        path, html, st = build(a.book, a.only, a.out, a.stage, a.v3_compat, a.chapters, a.label)
    except BuildError as e:
        print("빌드 실패 —", e)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    # 판은 덮어쓰지 않는다 — 전체 빌드(--out · --only · --v3-compat 아님)는 새 판 파일 + 최신 복사본(path) + versions.json
    versioned = not (a.out or a.only or a.v3_compat)
    if versioned:
        versions = load_versions(path)
        n = next_version(path, versions)
        name = version_name(a.stage, a.label, st["shown"])
        vfile = version_file(path, n, name)
        vfile.write_text(html, encoding="utf-8")
        shutil.copyfile(vfile, path)
        versions.append({"n": n, "name": name, "label": (a.label or "").strip(), "stage": a.stage, "chapters": st["shown"], "file": vfile.name,
                         "at": time.strftime("%Y-%m-%d %H:%M:%S"), "blocks": st["blocks"], "blanks": len(st["blanks"]),
                         "new": len(st["new"]) if a.stage and st["compared"] else None, "base": versions[-1]["n"] if versions else None})
        versions_path(path).write_text(json.dumps({"doc": path.stem, "title": st["title"], "latest": vfile.name, "versions": versions}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    else:
        path.write_text(html, encoding="utf-8")
    if a.stage and not a.v3_compat and not a.only:  # 다음 판의 «새로» 비교용 기억
        prev_path(path).write_text(json.dumps({"stage": a.stage, "built": time.strftime("%Y-%m-%d %H:%M:%S"), "blocks": st["hashes"]},
                                              ensure_ascii=False, indent=0), encoding="utf-8")
    if versioned:
        print(f"saved {vfile}  (판 v{n} · {name} — 앞 판 파일은 그대로)  최신 복사본 {path}")
    print(f"saved {path}  ({len(html.encode('utf-8')) / 1024:,.0f} KB · {st['seconds']:.1f} s)")
    print(f"모듈 {len(st['built'])}개 · 블록 {st['blocks']} · 장 {st['chapters']} · 각주 {st['footnotes']} · 앵커 {st['anchors']}"
          + (f" · 범위 밖 연결고리 {st['ext_links']}" if st["ext_links"] else "")
          + (f" · 책 사이 연결고리 {st['x_links']}" if st.get("x_links") else ""))
    copied = copy_extra(st, path)
    if copied:  # w.open_full 의 큰 조작 화면 — 출력 옆에 «<doc>__<이름>» 으로 복사했다(배포할 때 같이 올린다)
        print("함께 배포할 파일:")
        for c in copied:
            print(f"  {c}")
    if st["skipped"]:
        print("건너뜀(파일 없음):", ", ".join(st["skipped"]))
    for w in st["warnings"]:
        print("  경고:", w)
    if st["blanks"]:
        print(f"빈 칸 {len(st['blanks'])}개 — 장 파일 머리의 칸() 에서 채운다:")
        for b in st["blanks"]:
            print(f"  빈 칸: {b}")
    else:
        print("빈 칸 0")
    if st["later"]:
        print(f"2차판에서 채워짐 {len(st['later'])}곳(1차판 — 빈 칸으로 세지 않음): " + ", ".join(st["later"][:12]) + (" …" if len(st["later"]) > 12 else ""))
    if a.stage and not a.v3_compat and not a.only:
        print(f"판 {a.stage} · «새로» {len(st['new'])}블록" + ("" if st["compared"] else " (앞 판 기억 없음 — 이번 판을 기억함)"))
    for d in st["drift"]:
        print(f"  구조 바뀜: {d}")
    for x in st["expr"]:
        print(f"  식 글자 남음: {x}")
    if st["format"]:
        print(f"서식 경고 {len(st['format'])}개 — v3 와 모양이 갈리는 곳(RULES.md 6절 · 칸 길이표):")
        for x in st["format"]:
            print(f"  서식: {x}")
    else:
        print("서식 경고 0")
    if a.strict and (st["blanks"] or st["drift"] or st["expr"]):
        print(f"STRICT 실패 — 빈 칸 {len(st['blanks'])} · 구조 바뀜 {len(st['drift'])} · 식 글자 남음 {len(st['expr'])}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
