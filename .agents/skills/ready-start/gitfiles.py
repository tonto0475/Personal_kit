#!/usr/bin/env python3
# 과제 저장소의 커밋 대상 표 — 파일마다 한 줄 · 전체 경로 · 구분(커밋됨 · 새 파일 · 제외)
#   python3 ~/.codex/skills/ready-start/gitfiles.py [--repo 과제폴더] [--kit 키트폴더]
# - 커밋됨 = git 이 추적 중(git ls-files) · 새 파일 = 추적 안 됨, add 하면 들어감 · 제외 = .gitignore · .git/info/exclude 에 걸림
# - 수천 줄이 되는 폴더(키트 · .venv · venv · node_modules · __pycache__)는 «폴더 · 파일 N개» 한 줄로 묶는다
# 종료코드 0 · git 저장소가 아니면 2
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

FOLD_NAMES = {".venv", "venv", "node_modules", "__pycache__"}
# 키트(= 작업 폴더) 안에서 한 줄로 묶을 도구 폴더 — 앱 조각(src · scripts/race 등)은 파일마다 보인다
KIT_TOOL_DIRS = ("devview", "ref", "scripts/envcheck", "scripts/codex_config", "scripts/hooks", "docs/examples",
                 ".agents/skills", "skills_src")


def git_lines(root: Path, *args: str) -> list[str]:
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, text=True)
    return [x for x in r.stdout.splitlines() if x]


# 묶을 폴더 — 키트 안 도구 폴더(키트가 저장소 안 하위 폴더일 때) 또는 FOLD_NAMES 에 든 첫 폴더
def fold_dir(rel: str, kit_rel: str | None) -> str | None:
    if kit_rel:
        for t in KIT_TOOL_DIRS:
            if rel.startswith(f"{kit_rel}/{t}/"):
                return f"{kit_rel}/{t}"
    parts = rel.split("/")
    for i, p in enumerate(parts[:-1]):
        if p in FOLD_NAMES:
            return "/".join(parts[:i + 1])
    return None


def rows(root: Path, kit: Path | None) -> list[tuple[str, str]]:
    kit_rel = None
    if kit:
        try:
            k = kit.resolve().relative_to(root.resolve()).as_posix()
            kit_rel = k if k != "." else None
        except ValueError:
            pass
    out: list[tuple[str, str]] = []
    groups = [("커밋됨", git_lines(root, "ls-files")),
              ("새 파일", git_lines(root, "ls-files", "--others", "--exclude-standard")),
              ("제외", git_lines(root, "ls-files", "--others", "--ignored", "--exclude-standard"))]
    for kind, files in groups:
        folded: dict[str, int] = {}
        for rel in sorted(files):
            d = fold_dir(rel, kit_rel)
            if d:
                folded[d] = folded.get(d, 0) + 1
            else:
                out.append((kind, str(root / rel)))
        for d, n in sorted(folded.items()):
            out.append((kind, f"{root / d}/ (폴더 · 파일 {n}개)"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--kit")
    a = ap.parse_args()
    start = Path(a.repo) if a.repo else Path.cwd()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start, capture_output=True, text=True)
    if top.returncode != 0:
        print(f"git 저장소가 아님: {start.resolve()}")
        return 2
    root = Path(top.stdout.strip())
    kit = Path(a.kit) if a.kit else (root / "kit" if (root / "kit").is_dir() else None)
    rs = rows(root, kit)
    print("| 구분 | 경로 |")
    print("|---|---|")
    for kind, path in rs:
        print(f"| {kind} | {path} |")
    count = {k: sum(1 for x, _ in rs if x == k) for k in ("커밋됨", "새 파일", "제외")}
    print(f"\n요약: 커밋됨 {count['커밋됨']}줄 · 새 파일 {count['새 파일']}줄 · 제외 {count['제외']}줄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
