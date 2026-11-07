#!/usr/bin/env python3
# 키트 ↔ 과제 저장소 겹치는 이름 목록 — 읽기 전용 · 합치기 없음(표준 라이브러리만 · 파이썬 3.8 이상)
#
# 사용(과제 폴더에서)
#   python3 kit/.agents/skills/ready-start/overlap.py [--kit 키트 폴더] [--target 과제 폴더]
#   기본값: 키트 = 이 파일에서 세 단계 위(kit/) · 대상 = 현재 폴더
#
# 보여 주는 것
#   1. 키트와 대상에 같은 상대 경로로 있는 파일(대상 쪽 크기 · 수정 시각)
#   2. 대상 안 어디든 있는 AGENTS.md(Codex 는 하위 폴더 AGENTS.md 도 읽는다)
#   3. 대상 .agents/skills 아래 키트 스킬과 같은 이름 폴더
#   4. 대상 루트의 .codex · .mcp.json · .env.example 유무(참고)
#   5. 요약 — 겹침 N개 · 키트에만 있는 파일 M개
# 종료코드: 0 정상 · 2 인자 · 폴더 오류. 아무 파일도 쓰지 않는다
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# 키트 루트 기본값 — 이 파일이 kit/.agents/skills/ready-start/ 아래에 있다는 전제
KIT_DEFAULT = Path(__file__).resolve().parents[3]
# 걷지 않는 폴더 이름
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
# 대상 루트에서 유무만 보는 항목
ROOT_ITEMS = (".codex", ".mcp.json", ".env.example")


# 폴더 아래 파일의 상대 경로 목록(posix · 정렬)
# root: 걸을 폴더 / skip: 통째로 건너뛸 폴더(절대경로 · 없으면 None)
def walk_files(root: Path, skip=None) -> list:
    # 찾은 파일
    found = []
    for cur, dirs, files in os.walk(root):
        # 건너뛸 하위 폴더를 걷기 전에 뺀다
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not (skip and Path(cur) / d == skip))
        for f in files:
            found.append((Path(cur) / f).relative_to(root).as_posix())
    return sorted(found)


# 크기 · 수정 시각 한 줄
# p: 파일
def describe(p: Path) -> str:
    st = p.stat()
    return f"{st.st_size:,} B · {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}"


# 본체
def main(argv=None) -> int:
    # 출력 인코딩을 코드에서 고정(환경변수에 기대지 않음)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="키트와 과제 저장소의 겹치는 이름 목록(읽기 전용)")
    ap.add_argument("--kit", default=str(KIT_DEFAULT), help="키트 폴더(기본: 이 파일에서 세 단계 위)")
    ap.add_argument("--target", default=".", help="과제 폴더(기본: 현재 폴더)")
    args = ap.parse_args(argv)

    # 키트 · 대상 폴더(절대경로)
    kit = Path(args.kit).resolve()
    target = Path(args.target).resolve()
    for label, p in (("키트", kit), ("대상", target)):
        if not p.is_dir():
            print(f"{label} 폴더 없음: {p} — 종료코드 2", flush=True)
            return 2
    if kit == target:
        print(f"키트와 대상이 같은 폴더: {kit} — 과제 폴더에서 실행하거나 --target 지정 · 종료코드 2", flush=True)
        return 2
    # 대상 안에 있는 키트 폴더 자신(걷기에서 뺌)
    kit_inside = kit if target in kit.parents else None
    print(f"키트: {kit}", flush=True)
    print(f"대상: {target}" + (f" (키트 폴더 {kit.relative_to(target).as_posix()}/ 는 건너뜀)" if kit_inside else ""),
          flush=True)

    # 양쪽 파일 목록
    kit_files = walk_files(kit, skip=target if kit in target.parents else None)
    target_files = walk_files(target, skip=kit_inside)
    print(f"파일 수: 키트 {len(kit_files)}개 · 대상 {len(target_files)}개", flush=True)
    # 대상 파일 집합(빠른 조회)
    target_set = set(target_files)

    # 1. 같은 상대 경로
    same = [f for f in kit_files if f in target_set]
    print(f"\n[1] 같은 상대 경로 파일 {len(same)}개 (대상 쪽 크기 · 수정 시각)", flush=True)
    for f in same:
        print(f"  {f} — {describe(target / f)}", flush=True)

    # 2. 대상 안 AGENTS.md
    agents = [f for f in target_files if f.split("/")[-1] == "AGENTS.md"]
    print(f"\n[2] 대상 안 AGENTS.md {len(agents)}개 (하위 폴더 것도 Codex 가 읽음)", flush=True)
    for f in agents:
        print(f"  {f}", flush=True)

    # 3. 같은 이름 스킬 폴더
    kit_skills = kit / "skills_src" / "skills" if (kit / "skills_src" / "skills").is_dir() else kit / ".agents" / "skills"
    target_skills = target / ".agents" / "skills"
    names = sorted(d.name for d in kit_skills.iterdir() if d.is_dir()) if kit_skills.is_dir() else []
    clash = [n for n in names if (target_skills / n).is_dir()]
    print(f"\n[3] 같은 이름 스킬 폴더 {len(clash)}개 (대상 .agents/skills)", flush=True)
    for n in clash:
        print(f"  .agents/skills/{n}/", flush=True)

    # 4. 대상 루트 참고 항목
    print("\n[4] 대상 루트 참고 항목", flush=True)
    for item in ROOT_ITEMS:
        print(f"  {item} — {'있음' if (target / item).exists() else '없음'}", flush=True)

    # 5. 요약
    print(f"\n요약: 겹침 {len(same)}개 · 키트에만 있는 파일 {len(kit_files) - len(same)}개", flush=True)
    print("다음: 겹치는 파일은 유저가 Codex 와 정한 뒤 직접 옮긴다 · 옮긴 뒤 Codex 세션을 새로 시작해야 AGENTS.md 가 읽힌다",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
