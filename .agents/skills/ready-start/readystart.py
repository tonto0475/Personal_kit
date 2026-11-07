#!/usr/bin/env python3
# ReadyStart.md — 세션 띄우는 명령 + 준비 상태 (ready-start 0단계 · 단계마다 한 줄)
#   python3 ~/.codex/skills/ready-start/readystart.py write [--kit 키트] [--root 루트]   명령 파일을 쓴다(있으면 덮어씀 — 이 스킬이 만드는 파일)
#   python3 ~/.codex/skills/ready-start/readystart.py status 항목 "🟢 내용" [--kit 키트]   맨 아래 «준비 상태» 에 한 줄 덧붙임
#
# 왜 파일인가: 터미널 출력은 복사가 불편하다 → 유저가 에디터에서 줄마다 복사해 새 탭에 붙여 넣는다
#   두 세션(MAIN · 2ND)은 이 파일의 «준비 상태» 를 보고 venv · devview · 커밋을 기다릴지 정한다
# 키트 찾기: --kit → 지금 폴더에 AGENTS.md · docs/ 가 있으면 지금 폴더 → <루트>/kit
# 루트 찾기: --root → git rev-parse --show-toplevel → 키트의 부모
# 종료코드: 0 정상 · 2 키트 · 파일 없음
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

NAME = "ReadyStart.md"
STATUS_HEAD = "## 준비 상태"
MODEL = "gpt-6.1-sol"
# 역할 → (강도, 시작 메시지)
# 시작 메시지 — MAIN «$main»(허브 연결 → 바로 과제 파악) · 2ND «$2nd 파악시작»(허브 연결 → 대기 서브 → 가볍게 과제 훑기) (2026-11-04 유저 지정)
# MAIN 강도 — 첫 실행은 high(온톨로지가 끝나면 유저가 직접 내린다 · 2026-11-04 유저 지정)
# 검증은 세션이 아니라 MAIN 의 서브(2026-11-04 유저 지정 — INSP 세션 없앰)
ROLES = [("MAIN", "high", "$main"), ("2ND", "medium", "$2nd 파악시작")]
# 명령에 늘 붙이는 설정 — 플랫폼 설정에 같은 키가 다른 값이면 merge 가 안 바꾸므로 -c 로도(-c 가 설정 파일보다 앞섬)
#   서브 V2 + 기다리기 하한 10분 · 최대 1시간(키트 .codex/config.toml 과 같은 값 · 0.163 --strict-config 통과 2026-11-04)
EXTRA = ["model_verbosity=high", "service_tier=fast",
         "features.multi_agent_v2.enabled=true",
         "features.multi_agent_v2.min_wait_timeout_ms=600000",
         "features.multi_agent_v2.default_wait_timeout_ms=600000",
         "features.multi_agent_v2.max_wait_timeout_ms=3600000",
         "agents.max_concurrent_threads_per_session=8"]
# 전용 앱 서버 소켓(devview/steer.py 의 SOCK_REL 과 같게) — 세션을 여기 붙여야 턴 중 글이 바로 들어간다(steer · 2026-11-06 실측)
SOCK = "$HOME/.codex/rs/app.sock"


# 키트 = 작업 폴더(AGENTS.md 와 docs/ 가 있는 곳)
def is_kit(p: Path) -> bool:
    return (p / "AGENTS.md").is_file() and (p / "docs").is_dir()


# git 루트 — 저장소가 아니면 None
def git_root(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


# (키트, 루트) 정하기 — 못 찾으면 키트 None
def locate(kit: str | None, root: str | None) -> tuple[Path | None, Path]:
    cwd = Path.cwd()
    r = Path(root).resolve() if root else None
    if kit:
        k = Path(kit).resolve()
    elif is_kit(cwd):
        k = cwd
    else:
        base = r or git_root(cwd) or cwd
        k = base / "kit" if is_kit(base / "kit") else None
    if r is None:
        r = git_root(k or cwd) or (k.parent if k else cwd)
    return k, r


# 세션 하나 띄우는 명령 — '$main' 은 작은따옴표(맨글자 · 큰따옴표면 bash 가 빈 변수로 지운다)
def codex_line(kit: Path, root: Path, effort: str, prompt: str) -> str:
    parts = ["codex", "-C", shlex.quote(str(kit)), "--add-dir", shlex.quote(str(root)), "-m", MODEL,
             "-c", f"model_reasoning_effort={effort}"]
    for kv in EXTRA:
        parts += ["-c", kv]
    parts += ["--approve-for-me", f"'{prompt}'"]
    return " ".join(parts)


# 전용 앱 서버 — 뒤로 띄움(탭을 닫아도 안 끊기게) · 서브 상한 8 은 여기 있어야 먹는다(TUI 에만 주면 조용히 3개) · --add-dir 은 --remote 가 거부해서 writable_roots
def server_line(root: Path) -> str:
    parts = ["mkdir -p -m 700 ~/.codex/rs;", "setsid", "nohup", "codex", "app-server", "--listen", f"unix://{SOCK}",
             "-c", "check_for_update_on_startup=false",
             "-c", shlex.quote(f'sandbox_workspace_write.writable_roots=["{root}"]')]
    for kv in EXTRA:
        parts += ["-c", kv]
    return " ".join(parts) + " > ~/.codex/rs/server.log 2>&1 < /dev/null &"


# 앱 서버에 붙는 세션 — 옵션은 TUI 에도 준다(--approve-for-me 는 TUI 인자로만 먹는다)
def remote_line(kit: Path, effort: str, prompt: str) -> str:
    parts = ["codex", "--remote", f"unix://{SOCK}", "-C", shlex.quote(str(kit)), "-m", MODEL,
             "-c", "check_for_update_on_startup=false", "-c", f"model_reasoning_effort={effort}"]
    for kv in EXTRA:
        parts += ["-c", kv]
    parts += ["--approve-for-me", f"'{prompt}'"]
    return " ".join(parts)


# ReadyStart.md 본문
def render(kit: Path, root: Path) -> str:
    q = lambda p: shlex.quote(str(p))
    now = time.strftime("%H:%M")
    out = [f"# ReadyStart — 세션 띄우는 명령 ($ready-start 가 씀 · 커밋하지 않음 · {time.strftime('%Y-%m-%d %H:%M')})",
           "",
           "- 순서: 0 devview → 1 MAIN → 2 2ND · 줄마다 **새 터미널 탭**에서 붙여 넣기 · 0번을 먼저(압축 훅이 두 세션에 먹게) · 1 · 2 는 동시에 해도 된다",
           "- 처음 뜰 때 «폴더 신뢰» 는 예 · «Hooks need review» 는 2(Trust all and continue)",
           "- 두 세션은 뜨자마자 일을 시작한다 — venv · devview · git 커밋이 필요한 일만 맨 아래 «준비 상태» 를 보고 기다린다",
           "",
           "## 0) devview + 압축 훅 + 앱 서버",
           "새 터미널 탭에서 붙여 넣기(띄운 탭은 닫지 않는다 · 훅이 이미 있으면 «이미 있음» 이 떠도 그대로 진행)",
           "```bash",
           f"bash {q(kit / 'scripts' / 'hooks' / 'install_hooks.sh')}; {server_line(root)} bash {q(kit / 'devview' / 'dv')}",
           "```"]
    for i, (role, effort, prompt) in enumerate(ROLES, 1):
        out += ["", f"## {i}) {role}", "새 터미널 탭에서 붙여 넣기", "```bash", remote_line(kit, effort, prompt), "```"]
    out += ["",
            "## 앱 서버가 안 뜰 때(1 · 2번이 소켓 오류로 끝남)",
            "- 원인은 ~/.codex/rs/server.log · 아래 일반 명령으로 띄운다 — 글은 큐로 간다(턴이 끝나야 들어감 · 나머지는 같다)",
            "```bash", *[codex_line(kit, root, e, p) for _, e, p in ROLES], "```",
            "- 서버가 중간에 죽으면 0번 줄의 앱 서버 부분만 다시 띄운다 — TUI 는 자동 재접속 · 진행 중이던 턴은 끊긴다",
            "",
            "## 압축 훅이 안 먹을 때",
            "- 훅(~/.codex/hooks.json)은 세션이 **뜰 때** 읽힌다 → 0번 줄(또는 «준비 상태» 의 훅 줄)보다 먼저 뜬 세션은 첫 압축 전에 /quit → "
            "그 탭 명령의 `codex` 를 `codex resume <그 세션 /status 의 chat ID>` 로 바꿔 다시 띄우면 먹는다(대화 · 설정은 그대로)",
            "",
            f"{STATUS_HEAD}",
            "> ready-start 가 단계마다 한 줄 덧붙인다 · 🟢 됨 · 🟠 유저 판단 · 🔴 안 됨 · ⏳ 진행 중 · 두 세션은 이 절만 본다(sed -n '/^## 준비 상태/,$p')",
            "",
            f"- {now} 시작 — ⏳ 준비 중(git 이름 → git 등록 → config → 훅 → AGENTS · 스킬 → venv → envcheck → devview)"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ReadyStart.md — 세션 띄우는 명령 + 준비 상태")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="명령 파일 쓰기")
    w.add_argument("--kit")
    w.add_argument("--root")
    s = sub.add_parser("status", help="준비 상태 한 줄 덧붙이기")
    s.add_argument("item")
    s.add_argument("text")
    s.add_argument("--kit")
    a = ap.parse_args(argv)

    kit, root = locate(a.kit, getattr(a, "root", None))
    if kit is None or not kit.is_dir():
        print("키트 못 찾음 — --kit <키트 폴더> 로 준다(AGENTS.md · docs/ 가 있는 곳)", file=sys.stderr)
        return 2
    path = kit / NAME
    if a.cmd == "write":
        path.write_text(render(kit, root), encoding="utf-8")
        print(path)
        return 0
    if not path.is_file():
        print(f"{path} 없음 — 먼저 write", file=sys.stderr)
        return 2
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- {time.strftime('%H:%M')} {a.item} — {a.text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
