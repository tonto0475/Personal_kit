#!/usr/bin/env python3
# 스킬이 잘 옮겨졌나 — 키트(kit/.agents/skills)의 스킬 폴더를 Codex 가 읽는 두 곳과 파일 단위로 비교
#   ① ~/.codex/skills(옛 설치 사본) ② Codex 를 띄운 폴더(키트 = 작업 폴더)부터 git 루트까지의 .agents/skills
#   python3 ~/.codex/skills/ready-start/skillcheck.py [--kit 키트폴더] [--repo 과제폴더]
# 결과는 풀어 쓴 문장 한 줄씩 · 종료코드 0 다 같음 / 1 빠짐 · 다름 있음 / 2 폴더 없음
# «파일이 제자리에 같게 있나» 까지만 본다 — 스킬은 암묵 호출을 꺼 두어 목록에 안 실리는 게 정상이다
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

CODEX_SKILLS = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "skills"


# 키트 스킬 폴더 찾기 — 인자 → 홈의 kit · 과제 폴더의 kit → 이 파일이 키트 안에 있으면 그 키트
def kit_skills(arg) -> Path | None:
    cands = [arg] if arg else [Path.home() / "kit", Path("/home/user/kit"), Path.cwd() / "kit",
                               Path(__file__).resolve().parents[3]]
    for c in cands:
        # 설치본은 .agents → skills_src 로 이름이 바뀌어 있다(install.sh) · 원본 저장소는 .agents/skills
        for p in (Path(c) / "skills_src" / "skills", Path(c) / ".agents" / "skills"):
            if p.is_dir():
                return p
    return None


# 과제 저장소 루트 — 인자 → git rev-parse → 지금 폴더
def repo_root(arg) -> Path:
    if arg:
        return Path(arg)
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


# 폴더 안 파일 → {상대 경로: sha256} (__pycache__ 는 뺌)
def digest(root: Path) -> dict:
    out = {}
    for f in root.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            out[f.relative_to(root).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="키트 스킬이 Codex 가 읽는 곳에 잘 옮겨졌나")
    ap.add_argument("--kit")
    ap.add_argument("--repo")
    a = ap.parse_args()
    src = kit_skills(a.kit)
    if src is None:
        print("키트 스킬 폴더(kit/.agents/skills)를 못 찾음 — --kit 로 키트 폴더를 알려 줘")
        return 2
    # 읽는 곳 — ~/.codex/skills + 지금 폴더(Codex 를 띄운 폴더 · 키트 = 작업 폴더면 키트)부터 저장소 루트까지의 .agents/skills
    top = repo_root(a.repo).resolve()
    walk, here = [], Path.cwd().resolve()
    # 지금 폴더가 저장소 안일 때만 그 사이 폴더를 본다
    while top in here.parents:
        walk.append(here / ".agents" / "skills")
        here = here.parent
    walk.append(top / ".agents" / "skills")
    places = [p for p in (CODEX_SKILLS, *walk) if p.is_dir()]
    if not places:
        print(f"Codex 가 읽는 스킬 폴더가 없음({CODEX_SKILLS} · 저장소 루트/.agents/skills) — 설치 한 줄(install.sh)이 스킬을 못 옮김")
        return 2
    names = sorted(d.name for d in src.iterdir() if d.is_dir() and (d / "SKILL.md").is_file())
    bad = 0
    # 같은 이름이 두 곳에 다 있으면 Codex 가 «$이름» 만으로는 고르지 못해 에러 없이 안 불린다(0.163 소스) — 보고만 · 정리는 유저가
    dup = [n for n in names if len({str(p.resolve()) for p in places if (p / n / "SKILL.md").is_file()}) > 1]
    print(f"키트 {src} · 스킬 {len(names)}개 → 읽는 곳 {' · '.join(str(p) for p in places)}")
    for n in names:
        want = digest(src / n)
        hits = [p for p in places if (p / n / "SKILL.md").is_file()]
        if not hits:
            bad += 1
            print(f"빠짐 | {n} — 읽는 곳 어디에도 없음(SKILL.md 없음)")
            continue
        # 키트 파일이 전부 같은 내용으로 있으면 같음(읽는 곳에 더 있는 파일은 상관없음)
        same = [p for p in hits if all(digest(p / n).get(k) == v for k, v in want.items())]
        if same:
            print(f"같음 | {n} — 파일 {len(want)}개 · {same[0]}")
            continue
        bad += 1
        got = digest(hits[0] / n)
        miss = sorted(set(want) - set(got))
        diff = sorted(k for k in want if k in got and want[k] != got[k])
        print(f"다름 | {n} — {hits[0]} · 없는 파일 {len(miss)}개{(' ' + ', '.join(miss[:3])) if miss else ''}"
              f" · 내용 다른 파일 {len(diff)}개{(' ' + ', '.join(diff[:3])) if diff else ''}"
              " (설치가 «같은 이름은 건너뜀» 이라 옛 판이 남았을 수 있음)")
    for n in dup:
        print(f"중복 | {n} — 읽는 곳 두 곳에 다 있음 · «${n}» 이름만으로는 안 불릴 수 있다 · 어느 쪽을 남길지는 유저가 정한다(지우지 않음)")
    print("요약 | " + ("키트 스킬이 전부 같게 옮겨짐" if not bad else f"{bad}개 스킬이 빠지거나 다름")
          + (f" · 중복 {len(dup)}개(유저 판단)" if dup else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
