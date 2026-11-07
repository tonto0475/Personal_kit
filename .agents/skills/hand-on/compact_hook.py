#!/usr/bin/env python3
# 압축 직후 참조 목록 훅 — Codex hooks.json 의 SessionStart(matcher ^compact$) 가 부른다(직접 실행은 시험용) · 표준 라이브러리만
#   모델에 넣는 글(additionalContext) = «어디를 · 언제 읽나» 경로 · 절 번호뿐 — 문서 · 스킬 본문은 싣지 않는다(목표 1,500자 · 600토큰 이하)
#   왜: 대회 Codex 는 맥락 창이 작아 압축이 잦다 — 압축마다 역할 스킬을 통째로 다시 읽으면 토큰 · 시간이 샌다(10/31 실전)
#       10/30 판(PreCompact 스냅숏 + «$hand-on 하라» 안내)은 문서를 더 읽게 해 작업이 늘었다 → 11/01 참조 목록만으로 바꿈
#   절 제목은 스킬 · 문서 파일의 제목 줄에서 그때그때 뽑는다(지어내지 않게 · 파일이 바뀌어도 따라가게) — 못 찾으면 번호만
#   역할 판별(ready-start/whoami.py 함수 재사용): 세션 이름(/rename MAIN 등) → 대화 기록의 첫 유저 메시지($main / $2nd · $ready-start 준비 세션은 역할 없음)
#             못 하면 두 역할 줄을 다 넣고 «내 역할 줄만»
# 입력: stdin JSON — hook_event_name · source · session_id · transcript_path · cwd
# SessionStart(compact) 밖의 이벤트 · 깨진 입력 → 출력 없이 종료코드 0(훅 실패로 Codex 를 막지 않는다)
# 시험: python3 -m pytest -q .agents/skills/hand-on
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 스킬 폴더 — 이 파일이 든 hand-on 의 부모(설치본 ~/.codex/skills · 키트 .agents/skills 둘 다 형제 구조)
SKILLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILLS / "ready-start"))

# 모델에게 보이는 스킬 경로(설치 위치) — X 자리에 스킬 이름
SKILL_SHOWN = "~/.codex/skills/X/SKILL.md"

# 역할마다 «언제 → 어느 파일 · 어느 절» — 파일은 스킬 이름 또는 키트 기준 docs/ 경로
REFS = {
    "MAIN": [
        ("흐름 · 섹션 지시 · 서브 운영", "main", ["1-1", "1-2", "1-3", "1-4", "1-5", "1-6", "1-7"]),
        ("지도", "ontology", ["1", "2"]),
        ("검증 · 보고", "main", ["3-2", "3-4", "3-5"]),
        ("코드", "docs/CODE_RULE.md", ["5", "7", "11", "13"]),
        ("화면", "docs/UI_RULE.md", ["8"]),
        ("hand_off · WORKLOG 쓰기", "docs/DOC_GUIDE.md", ["2", "3"]),
        ("결정", "docs/hand_off.md", []),
        ("그래프", "docs/flowtree.md", []),
        ("책", "bookkit/README.md", []),
        ("뼈대", "skeleton/README.md", []),
    ],
    "2ND": [
        ("운영 · 할 일", "2nd", ["1-3", "2-1", "2-2"]),
        ("문서 설명", "docs/DOC_GUIDE.md", ["1"]),
        ("서술형 모의", "ready-end", ["5-1"]),
        ("설명 폼", "survey", ["2-1"]),
        ("그래프", "docs/flowtree.md", []),
        ("책", "bookkit/README.md", []),
    ],
}
# 키트 파일로 읽는 경로 머리말(그 밖은 스킬 이름)
KIT_PREFIXES = ("docs/", "bookkit/", "skeleton/")
# 키트(작업 폴더) — cwd 에 docs/WORKLOG.md 가 있으면 cwd, 루트에서 뜬 세션이면 cwd/kit
def kit_dir(cwd: Path) -> Path:
    for k in (cwd, cwd / "kit"):
        if (k / "docs" / "WORKLOG.md").is_file():
            return k
    return cwd


# 참조 대상 → 실제 파일(제목을 뽑을 곳)
def ref_file(kit: Path, target: str) -> Path:
    return kit / target if target.startswith(KIT_PREFIXES) else SKILLS / target / "SKILL.md"


# 파일의 «## 번호. 제목» 줄 → {번호: 짧은 제목} — « — » 뒤 · 끝 괄호는 뺀다
def headings(path: Path) -> dict:
    out = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for m in re.finditer(r"^#{2,3} ([0-9]+(?:-[0-9]+)*)\. (.+)$", text, re.M):
        title = m.group(2).split(" — ")[0]
        title = re.sub(r"\s*\([^()]*\)\s*$", "", title).strip()
        out.setdefault(m.group(1), title)
    return out


# 역할 판별 — (역할, 근거) · 못 하면 (None, 사유)
def detect_role(ev: dict):
    try:
        import whoami  # 같은 스킬 묶음의 ready-start/whoami.py
    except ImportError:
        return None, "whoami.py 없음"
    sid = ev.get("session_id")
    try:
        name = (whoami.current_names().get(sid) or {}).get("thread_name") if sid else None
    except (OSError, ValueError):
        name = None
    if name and name.upper() in whoami.ROLE_PROMPTS:
        return name.upper(), f"세션 이름 {name}"
    tp = ev.get("transcript_path")
    if tp and Path(tp).is_file():
        try:
            first = whoami.first_user_text(Path(tp))
        except OSError:
            first = ""
        for role, prompts in whoami.ROLE_PROMPTS.items():
            if first.startswith(prompts):
                return role, f"첫 메시지 {first.split()[0]}"
    return None, "이름 · 첫 메시지로 못 정함"


# 역할 하나의 줄들
def role_lines(role: str, kit: Path) -> list:
    out, files = [], []
    for when, target, nums in REFS[role]:
        shown = target if target.startswith(KIT_PREFIXES) else f"스킬 {target}"
        if not nums:                          # 절 번호 없는 파일 참조 — 한 줄에 모은다(글자 수 예산)
            files.append(f"{when} {shown}")
            continue
        heads = headings(ref_file(kit, target))
        out.append(f"- {when} → {shown} " + " / ".join(f"{n} {heads.get(n, '')}".rstrip() for n in nums))
    if files:
        out.append("- 문서: " + " · ".join(files))
    return out


# 압축 직후 모델에 넣을 글
def context_after_compact(ev: dict) -> str:
    kit = kit_dir(Path(ev.get("cwd") or "."))
    role, why = detect_role(ev)
    lines = ["[압축 직후 — 훅이 넣은 참조 목록] 아래는 경로다. 통째로 다시 읽지 말고, 지금 할 일에 필요한 절만 grep -n 으로 찾아 읽는다.",
             f"- 키트(작업 폴더) = {kit} · docs/ 는 키트 기준 · 스킬 X = {SKILL_SHOWN}",
             "- 먼저: ./kit status --role <내 역할> 한 장(그래프 할 일 · hand_off 🟠🔴 · 미커밋) → docs/WORKLOG.md 맨 위 «🔄 인계» 칸만(--- 줄 앞까지) → 그 칸 «참조 중인 문서» 에 적힌 부분만",
             "- 형식 칸(그래프 · hand_off 기호 · 표 · WORKLOG · 커밋)은 ./kit 도구로만 · 본문 글은 파일에서 직접(AGENTS.md 3절 · ./kit help)",
             "- 확정한 값은 압축 요약이 아니라 문서에서 다시 확인한다 · 0-1 의 문서를 통째로 다시 읽지 않는다"]
    roles = [role] if role else list(REFS)
    if not role:
        lines.append(f"역할 못 정함({why}) — 아래에서 내 역할 줄만 본다")
    for r in roles:
        lines.append(f"내 역할 = {r}({why}) — 할 일에 맞는 줄만:" if role else f"{r}:")
        lines += role_lines(r, kit)
    return "\n".join(lines)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    try:
        ev = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        print("훅 입력 JSON 아님", file=sys.stderr)
        return 0
    if not (isinstance(ev, dict) and ev.get("hook_event_name") == "SessionStart" and ev.get("source") == "compact"):
        return 0
    try:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": context_after_compact(ev)}}, ensure_ascii=False))
    except Exception as e:                # 어떤 실패도 압축 뒤 이어 가기를 막지 않게 — 사유만 남긴다
        print(f"compact_hook 실패: {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
