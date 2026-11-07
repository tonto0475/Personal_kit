#!/usr/bin/env python3
# 제출 전 문서 점검 — 읽기 전용(표준 라이브러리만 · 파이썬 3.8 이상)
#
# 사용
#   python3 ~/.codex/skills/ready-end/doc_check.py [--root 저장소] [--since 커밋]
#
# 점검 4가지
#   1. 문서에 적힌 경로가 실제로 있나(src/ · tests/ · docs/ … 로 시작하고 확장자가 있는 상대 경로)
#   2. 진행 표의 커밋 해시가 git 에 있나(머리 칸 이름에 «커밋» 이 든 열)
#   3. 고아 문서 — docs/ 아래 .md 중 어디에서도 가리키지 않는 것
#   4. 🚹 줄 보존 — docs/ 아래 .md 를 바꾼 커밋에서 내용이 있는 🚹 줄이 사라지거나 바뀌었나
# 종료코드: 0 문제 없음 · 1 문제 있음 · 2 git 저장소 아님 · 인자 오류
# 아무 파일도 쓰지 않는다
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# 경로로 인정하는 맨 앞 폴더
PATH_HEADS = ("src", "tests", "scripts", "docs", "config", "data", "out", "assets", "logs")
# 문서 속 경로 후보 — 앞 글자가 경로 글자면 안 됨(절대경로 · URL · kit/docs/… 의 중간 조각 제외)
PATH_RE = re.compile(r"(?<![\w./\\-])((?:" + "|".join(PATH_HEADS) + r")/[^\s`'\"|,;]+)")
# 후보에서 확장자로 끝나는 가장 긴 앞부분 — «docs/a.md를» → «docs/a.md»
EXT_RE = re.compile(r"^(.*\.[A-Za-z0-9]+)(?![A-Za-z0-9])")
# 자리 표시 글자 — 하나라도 들면 실제 경로가 아니라 양식 칸
PLACEHOLDER_CHARS = set("()<>«»「」*（）[]{}")
# 커밋 해시 후보(7 ~ 40자리 16진수)
HASH_RE = re.compile(r"(?<![0-9A-Za-z])([0-9a-fA-F]{7,40})(?![0-9A-Za-z])")
# 수정 범위 콜아웃 머리 줄 — warning(승인 전) · success(승인 후)
SCOPE_HEAD_RE = re.compile(r"^>\s*\[!(warning|success)\][-+]?(.*)$")
# 🚹 줄 판정용 — 줄 앞의 인용 «>» · 목록 기호 · 들여쓰기를 벗긴다
LEAD_RE = re.compile(r"^[\s>]*(?:[-*+]\s+|\d+[.)]\s+)?")
# 유저 표식
USER_MARK = "🚹"
# 점검에서 빼는 docs 하위 폴더
SKIP_DOC_DIRS = {"examples", "surveys"}
# 경로 · 해시 점검에서 빼는 문서 이름(정책 문서 — 과제를 하며 채우는 문서가 아님)
SKIP_FILL_NAMES = {"CODE_RULE.md", "UI_RULE.md"}
# 고아 점검에서 다른 문서를 걸을 때 건너뛰는 폴더
SKIP_WALK_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache"}


# git 명령 실행 → (종료코드, 표준 출력 글자)
# root: 저장소 / args: git 인자
def git(root: Path, *args: str) -> tuple:
    # 실행 결과 — 한글 경로가 \351… 로 바뀌지 않게 quotepath 끔
    r = subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(root), *args],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


# 파일 읽기(utf-8 · 깨진 글자는 대체)
# p: 파일
def read_text(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")


# 과제를 하며 채우는 문서인가 — docs/ 아래 .md 중 examples · surveys 제외
# rel: 저장소 기준 상대 경로(posix)
def is_work_doc(rel: str) -> bool:
    parts = rel.split("/")
    return (len(parts) >= 2 and parts[0] == "docs" and rel.endswith(".md")
            and not (len(parts) >= 3 and parts[1] in SKIP_DOC_DIRS))


# docs/ 아래 점검 대상 .md 목록(상대 경로 정렬)
# root: 저장소
def list_docs(root: Path) -> list:
    # docs 폴더
    docs = root / "docs"
    if not docs.is_dir():
        return []
    return sorted(p.relative_to(root).as_posix() for p in docs.rglob("*.md")
                  if p.is_file() and is_work_doc(p.relative_to(root).as_posix()))


# 줄마다 «수정 범위 콜아웃 안인가» 표시
# lines: 문서 줄 목록
def scope_flags(lines: list) -> list:
    # 줄별 표시
    flags = []
    # 지금 수정 범위 콜아웃 안인가
    inside = False
    for line in lines:
        m = SCOPE_HEAD_RE.match(line)
        if m:
            inside = "수정 범위" in m.group(2)
        elif not line.startswith(">"):
            inside = False
        flags.append(inside)
    return flags


# 문서 줄에서 경로 후보 뽑기 — 자리 표시 · 확장자 없는 것은 버림
# line: 한 줄
def find_paths(line: str) -> list:
    # 찾은 경로
    found = []
    for m in PATH_RE.finditer(line):
        e = EXT_RE.match(m.group(1))
        if not e:
            continue
        # 확장자까지 자른 경로
        p = e.group(1)
        if PLACEHOLDER_CHARS & set(p):
            continue
        found.append(p)
    return found


# 수정 범위 콜아웃의 «생성 예정 파일» 목록에 든 경로 모으기
# lines: 문서 줄 목록
def planned_paths(lines: list) -> set:
    # 생성 예정 경로
    planned = set()
    # 지금 «생성 예정» 목록 구간인가
    listing = False
    for line, inside in zip(lines, scope_flags(lines)):
        if not inside:
            listing = False
            continue
        if "생성 예정" in line:
            listing = True
        if listing:
            planned.update(find_paths(line))
    return planned


# 점검 1 — 문서에 적힌 경로가 실제로 있나
# root: 저장소 / docs: 점검 문서 / texts: 문서별 줄 목록
def check_paths(root: Path, docs: list, texts: dict) -> list:
    # 모든 문서의 생성 예정 경로(다른 문서에 적은 계획도 인정)
    planned = set()
    for rel in docs:
        planned |= planned_paths(texts[rel])
    # 문제 줄
    problems = []
    for rel in docs:
        if Path(rel).name in SKIP_FILL_NAMES:
            continue
        for no, line in enumerate(texts[rel], 1):
            for p in find_paths(line):
                if (root / p).exists():
                    continue
                # 생성 예정 표시
                tag = " (생성 예정 목록)" if p in planned else ""
                problems.append(f"{rel}:{no} — {p}{tag}")
    return problems


# 마크다운 표 줄이면 칸 목록, 아니면 None — 콜아웃 안 표(«> |»)도 인정
# line: 한 줄
def table_cells(line: str):
    # 인용 «>» 를 벗긴 줄
    s = re.sub(r"^(\s*>)+\s*", "", line).strip()
    if not s.startswith("|"):
        return None
    s = s[1:-1] if s.endswith("|") and len(s) > 1 else s[1:]
    return [c.strip() for c in s.split("|")]


# 표 구분 줄(|---|---|)인가
# cells: 칸 목록
def is_sep(cells: list) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


# 점검 2 — 진행 표 커밋 해시가 git 에 있나
# root: 저장소 / docs: 점검 문서 / texts: 문서별 줄 목록
def check_hashes(root: Path, docs: list, texts: dict) -> list:
    # 해시별 확인 결과(같은 해시를 여러 번 묻지 않게)
    known = {}
    # 문제 줄
    problems = []
    for rel in docs:
        if Path(rel).name in SKIP_FILL_NAMES:
            continue
        # 줄 목록
        lines = texts[rel]
        # 지금 표의 커밋 열 번호들(표 밖이면 None)
        cols = None
        for i, line in enumerate(lines):
            cells = table_cells(line)
            if cells is None:
                cols = None
                continue
            if is_sep(cells):
                continue
            if cols is None:
                # 표 머리 줄 — 다음 줄이 구분 줄일 때만 머리로 인정
                nxt = table_cells(lines[i + 1]) if i + 1 < len(lines) else None
                cols = [k for k, c in enumerate(cells) if "커밋" in c] if nxt and is_sep(nxt) else []
                continue
            for k in cols:
                if k >= len(cells):
                    continue
                for h in HASH_RE.findall(cells[k]):
                    if h not in known:
                        known[h] = git(root, "cat-file", "-e", h + "^{commit}")[0] == 0
                    if not known[h]:
                        problems.append(f"{rel}:{i + 1} — {h}")
    return problems


# 점검 3 — 고아 문서
# root: 저장소 / docs: 점검 문서
def check_orphans(root: Path, docs: list) -> list:
    # 가리키는 쪽이 될 수 있는 .md 전부(저장소 루트의 kit/ 는 설치본 사본이라 뺌)
    sources = {}
    for p in root.rglob("*.md"):
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if SKIP_WALK_DIRS & set(parts[:-1]) or parts[0] == "kit" or not p.is_file():
            continue
        sources[rel] = read_text(p)
    # 문제 줄
    problems = []
    for rel in docs:
        # 이 문서의 이름
        name = Path(rel).name
        if not any(rel in text or name in text for src, text in sources.items() if src != rel):
            problems.append(rel)
    return problems


# 🚹 줄인가 — 표식 뒤에 글자가 있는 유저 줄(AI 줄 속 «(🚹 동의)» 출처 표시는 아님)
# line: 한 줄
def user_line(line: str) -> bool:
    # 앞 기호를 벗긴 본문
    body = LEAD_RE.sub("", line, count=1)
    return body.startswith(USER_MARK) and body[len(USER_MARK):].strip() != ""


# 내용 있는 🚹 줄 개수 — 수정 범위 콜아웃 안 줄은 회차마다 다시 쓰는 칸이라 뺌
# text: 문서 글
def user_lines(text: str) -> Counter:
    # 줄 목록
    lines = [ln.rstrip() for ln in text.splitlines()]
    return Counter(ln for ln, inside in zip(lines, scope_flags(lines)) if not inside and user_line(ln))


# 점검 4 — 🚹 줄 보존
# root: 저장소 / since: 이 커밋 뒤부터(없으면 처음부터)
def check_user_lines(root: Path, since: str, docs_spec: str = "docs") -> list:
    # 커밋 목록(오래된 것부터) — 각 줄 «커밋 부모1 부모2…»
    code, out = git(root, "rev-list", "--reverse", "--parents", f"{since}..HEAD" if since else "HEAD")
    if code != 0:
        return []
    # 문제 줄
    problems = []
    for row in out.split("\n"):
        ids = row.split()
        if len(ids) < 2:
            continue
        # 이 커밋 · 비교 기준(병합이면 첫 부모)
        commit, parent = ids[0], ids[1]
        _, names = git(root, "diff", "--name-status", "-M", parent, commit, "--", docs_spec)
        for entry in names.split("\n"):
            cols = entry.split("\t")
            if len(cols) < 2:
                continue
            # 변경 종류 · 옛 경로 · 새 경로(이름 바뀜이면 둘이 다름)
            kind, old = cols[0][:1], cols[1]
            new = cols[2] if len(cols) >= 3 else old
            if kind not in ("M", "R") or not old.endswith(".md"):
                continue
            # 바뀌기 전 · 뒤 🚹 줄
            before = user_lines(git(root, "show", f"{parent}:{old}")[1])
            after = user_lines(git(root, "show", f"{commit}:{new}")[1])
            for ln in sorted((before - after).elements()):
                problems.append(f"{commit[:7]} · {new} · {ln.strip()[:60]}")
    return problems


# 점검 결과 한 덩이 출력 → 문제 수
# title: 점검 이름 / problems: 문제 줄 / hint: 문제가 있을 때 덧붙일 안내
def report(title: str, problems: list, hint: str = "") -> int:
    if not problems:
        print(f"  통과 — {title}", flush=True)
        return 0
    print(f"  문제 {len(problems)}건 — {title}", flush=True)
    for p in problems:
        print(f"    {p}", flush=True)
    if hint:
        print(f"    → {hint}", flush=True)
    return len(problems)


# 본체
def main(argv=None) -> int:
    # 출력 인코딩을 코드에서 고정(환경변수에 기대지 않음)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="제출 전 문서 점검(읽기 전용)")
    ap.add_argument("--root", default=".", help="저장소 폴더(기본: 현재 폴더의 git 최상위)")
    ap.add_argument("--since", default="", help="🚹 점검을 이 커밋 뒤부터")
    args = ap.parse_args(argv)

    # 저장소 최상위
    start = Path(args.root)
    if not start.is_dir():
        print(f"폴더 없음: {start}", flush=True)
        return 2
    code, top = git(start, "rev-parse", "--show-toplevel")
    if code != 0 or not top.strip():
        print(f"git 저장소 아님: {start.resolve()} — 종료코드 2", flush=True)
        return 2
    root = Path(top.strip())
    if args.since and git(root, "rev-parse", "--verify", "--quiet", args.since + "^{commit}")[0] != 0:
        print(f"없는 커밋: --since {args.since} — 종료코드 2", flush=True)
        return 2
    # 작업 폴더(docs/ 가 있는 곳) — 지정 폴더가 루트 아래 하위 폴더면 그곳 · 루트에 docs/ 가 없고 kit/docs 가 있으면 kit
    #   문서 · 경로 점검은 작업 폴더 기준, git 은 루트 기준(키트 = 작업 폴더 구성)
    here = start.resolve()
    if here != root and root in here.parents:
        base = here
    elif not (root / "docs").is_dir() and (root / "kit" / "docs").is_dir():
        base = root / "kit"
    else:
        base = root
    wrel = base.relative_to(root).as_posix() if base != root else ""
    print(f"저장소: {root}" + (f" · 작업 폴더 {wrel}" if wrel else ""), flush=True)

    # 점검 문서와 줄
    docs = list_docs(base)
    texts = {rel: read_text(base / rel).splitlines() for rel in docs}
    print(f"점검 문서 {len(docs)}개 (docs/ 아래 .md · examples · surveys 제외)", flush=True)

    # 문제 합계
    total = 0
    print("[1/4] 문서에 적힌 경로가 실제로 있나", flush=True)
    total += report("문서 경로", check_paths(base, docs, texts),
                    "문서를 고치거나 파일을 만든다(생성 예정 목록이면 아직 안 만든 것)")
    print("[2/4] 진행 표 커밋 해시가 git 에 있나", flush=True)
    total += report("커밋 해시", check_hashes(root, docs, texts), "표의 해시를 실제 커밋으로 고친다")
    print("[3/4] 고아 문서(어디에서도 가리키지 않음)", flush=True)
    total += report("고아 문서", check_orphans(base, docs),
                    "docs/DOC_GUIDE.md 1절 문서 지도에 한 줄 추가 · 지울지는 유저 확인")
    print("[4/4] 🚹 줄 보존" + (f"({args.since} 뒤부터)" if args.since else "(처음부터)"), flush=True)
    total += report("🚹 줄", check_user_lines(root, args.since, f"{wrel}/docs" if wrel else "docs"),
                    "커밋 · 파일 · 사라진 줄 — 유저가 직접 고친 거면 무시, 아니면 유저에게 확인")

    if total:
        print(f"문제 {total}건 — 종료코드 1", flush=True)
        return 1
    print("문제 없음 — 종료코드 0", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
