#!/usr/bin/env python3
# 코덱스 허브 — 이 Codex 세션을 devview 허브에 붙이고 지금 작업(상태 줄) · 큰 완료(누적)를 알림 · 표준 라이브러리만
"""
사용(작업 폴더 = 키트에서):
  python3 ~/.codex/skills/codex-hub/hub.py register --nick main|2nd|이름 [--effort high] [--model 이름]
  python3 ~/.codex/skills/codex-hub/hub.py status "❇️_1 : UI 구현. 운영자 화면"
  python3 ~/.codex/skills/codex-hub/hub.py log "❇️_1 운영자 화면 완료 · src/ui/admin.py"
  python3 ~/.codex/skills/codex-hub/hub.py whoami
  python3 ~/.codex/skills/codex-hub/hub.py send --to 2nd '글'   다른 세션에 codex queue · 글 앞에 «@보낸이름 » 자동(유저 지시와 구별)
  python3 ~/.codex/skills/codex-hub/hub.py hook        Codex 훅이 stdin JSON 으로 부름(선택 · 출력 없음 · 늘 종료코드 0)
  python3 ~/.codex/skills/codex-hub/hub.py register --nick main --claude [--tmux 대상]   Claude Code 세션(tmux 안에서 띄운 것)
Claude 세션: 세션 id = 자기 claude 프로세스의 ~/.claude/sessions/<pid>.json(부모를 거슬러 찾음 · 없으면 작업 폴더 projects 의 최근 jsonl)
  · 보내기 = tmux 괄호 붙여넣기(load-buffer + paste-buffer -p + Enter — 여러 줄이 한 메시지 · 2026-11-03 WSL claude 2.1.302 실측)
파일 = <작업 폴더>/.codex-hub/ — Codex 샌드박스가 작업 폴더 밖에 못 써서 · git 제외
  sessions/<닉>.json 등록 · 상태 줄 / logs/<닉>.jsonl 누적(덧붙이기만) / events/<thread>.jsonl 훅 사건
작업 폴더 찾기: CODEX_HUB_DIR(.codex-hub 경로) → 위로 올라가며 .codex-hub 가 있는 곳 → AGENTS.md 가 있는 곳 → 현재 폴더
자기 세션 = 환경변수 CODEX_THREAD_ID(Codex 가 넣어 줌) · 등록의 thread 와 같은 값
effort: Codex 기록(rollout turn_context) → 자기 Codex 프로세스 인자(model_reasoning_effort) → --effort → ~/.codex/config.toml → «?»
출력: 성공 한 줄 · 실패는 «실패: 원인» 한 줄 + 종료코드 1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 허브 폴더 이름
HUB = ".codex-hub"
# 역할 닉네임(대문자로 와도 이 글자로 맞춤)
ROLES = ("main", "2nd")
# 닉네임 허용 모양 — 파일 이름으로 쓰므로 글자 · 숫자 · 한글 · _ · - 만
NICK_RE = re.compile(r"^[0-9A-Za-z가-힣_-]{1,24}$")
# 상태 줄 · 누적 한 줄 최대 글자 수(넘으면 거부 — 화면은 넘치면 … · 툴팁)
TEXT_MAX = 200
# send 글 최대 글자 수(devview queue 와 같음)
SEND_MAX = 20000
# effort 로 받는 값
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")
# 프로세스 인자에서 effort 찾기 — -c model_reasoning_effort=high · --config model_reasoning_effort="high"
EFFORT_ARG = re.compile(r"model_reasoning_effort\s*=\s*['\"]?([a-z]+)")
# config.toml 맨 위 칸의 effort
EFFORT_CFG = re.compile(r"^\s*model_reasoning_effort\s*=\s*['\"]([a-z]+)['\"]", re.M)
# 기록 파일 끝에서 읽는 바이트(마지막 turn_context 를 찾기에 충분)
TAIL_BYTES = 2 * 1024 * 1024


# 거부 · 실패 — 원인 한 줄
class HubError(Exception):
    pass


# 지금 시각 글자(YYYY-MM-DD HH:MM:SS)
def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# 허브 폴더 찾기 — 반환 경로(.codex-hub · 없으면 만들 자리)
# start: 찾기 시작 폴더(없으면 현재 폴더)
def hub_dir(start=None):
    # 환경변수 지정
    env = os.environ.get("CODEX_HUB_DIR")
    if env:
        return Path(env).expanduser()
    # 시작 폴더
    base = Path(start or os.getcwd()).resolve()
    # 시작 폴더와 그 위 폴더들
    chain = [base, *base.parents]
    for d in chain:
        if (d / HUB).is_dir():
            return d / HUB
    for d in chain:
        if (d / "AGENTS.md").is_file():
            return d / HUB
    return base / HUB


# 닉네임 맞추기 — 역할 이름은 소문자로 · 모양 검사
# nick: 받은 닉네임
def norm_nick(nick):
    # 앞뒤 공백 뺀 값
    n = str(nick or "").strip()
    if n.lower() in ROLES:
        n = n.lower()
    if not NICK_RE.match(n):
        raise HubError(f"닉네임 «{n}» — 글자 · 숫자 · 한글 · _ · - 로 24자 이내")
    return n


# 한 줄 글 다듬기 — 줄바꿈은 « · » 로 · 빈 글 · 너무 긴 글 거부
# text: 받은 글 / what: 이름(상태 줄 · 누적)
def one_line(text, what):
    # 줄바꿈을 이은 글
    t = " · ".join(x.strip() for x in str(text or "").splitlines() if x.strip())
    if not t:
        raise HubError(f"{what} 없음")
    if len(t) > TEXT_MAX:
        raise HubError(f"{what} {len(t)}자 — {TEXT_MAX}자 이내(60자 안팎 권장)")
    return t


# JSON 쓰기 — 임시 파일 → 교체(읽는 devview 가 반쪽 파일을 보지 않게)
# path: 대상 / data: 내용
def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # 임시 파일
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # 윈도우 — devview 가 읽는 순간이면 교체가 막혀 잠깐 쉬고 다시
    for _ in range(60):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.03)
    os.replace(tmp, path)


# JSON 읽기(없거나 깨지면 None)
# path: 파일
def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# 한 줄 덧붙이기 — 한 번의 write 로(동시에 써도 줄이 섞이지 않게)
# path: jsonl 파일 / obj: 줄 내용
def append_line(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    # 쓸 바이트
    raw = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    # 파일 기술자 — 덧붙이기 모드
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)


# Codex 홈 — CODEX_HOME > ~/.codex
def codex_home():
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser()


# 이 thread 의 기록 파일(rollout) — 최근 날짜 폴더부터 · 없으면 None
# thread: 세션 id
def find_rollout(thread):
    if not thread:
        return None
    # 세션 폴더
    base = codex_home() / "sessions"
    if not base.is_dir():
        return None
    # 오늘 · 어제 날짜 폴더 먼저(대부분 여기)
    for days in (0, 1):
        # 날짜 폴더
        d = base / time.strftime("%Y/%m/%d", time.localtime(time.time() - days * 86400))
        if d.is_dir():
            # 맞는 파일 목록
            hits = sorted(d.glob(f"rollout-*{thread}.jsonl"))
            if hits:
                return hits[-1]
    # 그 밖 — 전체에서
    hits = sorted(base.rglob(f"rollout-*{thread}.jsonl"))
    return hits[-1] if hits else None


# 기록에서 effort · 모델 — 마지막 turn_context(또는 thread_settings_applied) 기준 · (effort, 모델)
# path: 기록 파일
def rollout_settings(path):
    effort = model = None
    try:
        # 파일 크기
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
            # 끝 부분 바이트
            raw = f.read()
    except OSError:
        return None, None
    for line in raw.splitlines():
        if b'"turn_context"' not in line and b"thread_settings_applied" not in line:
            continue
        try:
            # 줄 사전
            o = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            continue
        # 내용 칸
        p = o.get("payload") if isinstance(o, dict) else None
        if not isinstance(p, dict):
            continue
        if o.get("type") == "turn_context":
            # 협업 모드 설정 칸
            cm = ((p.get("collaboration_mode") or {}).get("settings") or {}) if isinstance(p.get("collaboration_mode"), dict) else {}
            effort = p.get("effort") or cm.get("reasoning_effort") or effort
            model = p.get("model") or model
        elif p.get("type") == "thread_settings_applied":
            # 세션 설정 칸
            ts = p.get("thread_settings") or {}
            effort = ts.get("reasoning_effort") or effort
            model = ts.get("model") or model
    return effort, model


# 자기 Codex 프로세스 인자에서 effort(리눅스 /proc · 부모를 거슬러 올라가며) — 없으면 None
def process_effort():
    # 지금 프로세스 번호
    pid = os.getpid()
    for _ in range(16):
        try:
            # 명령줄 · 상태 줄
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        # 인자 속 effort
        m = EFFORT_ARG.search(cmd)
        if m and m.group(1) in EFFORTS:
            return m.group(1)
        # 부모 번호 — «pid (이름) 상태 ppid …» (이름에 괄호가 있어도 마지막 ) 뒤)
        try:
            pid = int(stat.rsplit(")", 1)[1].split()[1])
        except (IndexError, ValueError):
            return None
        if pid <= 1:
            return None
    return None


# config.toml 의 기본 effort — 없으면 None
def config_effort():
    try:
        # 설정 글
        text = (codex_home() / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return None
    # 첫 [표] 앞(맨 위 칸)만
    head = re.split(r"^\s*\[", text, maxsplit=1, flags=re.M)[0]
    m = EFFORT_CFG.search(head)
    return m.group(1) if m and m.group(1) in EFFORTS else None


# effort 정하기 — (값, 출처) · 기록 → 프로세스 인자 → --effort → 설정 → «?»
# rollout_effort: 기록 값 / given: --effort 값
def pick_effort(rollout_effort, given):
    if rollout_effort:
        return rollout_effort, "기록"
    # 프로세스 인자 값
    pe = process_effort()
    if pe:
        return pe, "프로세스"
    if given:
        if given not in EFFORTS:
            raise HubError(f"--effort «{given}» — {' · '.join(EFFORTS)}")
        return given, "인자"
    # 설정 값
    ce = config_effort()
    if ce:
        return ce, "설정"
    return "?", "?"


# 자기 thread id(없으면 None) — Codex = CODEX_THREAD_ID · Claude = 자기 claude 프로세스의 세션 id
def my_thread():
    th = (os.environ.get("CODEX_THREAD_ID") or "").strip()
    if th:
        return th
    me = my_claude()
    return me.get("sessionId") if me else None


# Claude 홈 — CLAUDE_CONFIG_DIR > ~/.claude
def claude_home():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")).expanduser()


# 자기 claude 프로세스 — 부모를 거슬러 ~/.claude/sessions/<pid>.json 이 있는 첫 프로세스 · {pid, sessionId, cwd, procStart, …} · 없으면 None
#   CODEX_HUB_CLAUDE_PID(시험용)가 있으면 그 번호부터
def my_claude():
    # 세션 폴더 · 시작 번호
    base = claude_home() / "sessions"
    pid = int(os.environ.get("CODEX_HUB_CLAUDE_PID") or os.getpid())
    for _ in range(16):
        d = read_json(base / f"{pid}.json")
        if isinstance(d, dict) and d.get("sessionId"):
            return dict(d, pid=pid)
        try:
            # 부모 번호 — «pid (이름) 상태 ppid …»
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
            pid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            return None
        if pid <= 1:
            return None
    return None


# Claude 기록 폴더 이름 — 작업 폴더 경로의 글자 · 숫자 밖은 «-»(/home/user/workspace/kit → -home-user-workspace-kit)
# cwd: 작업 폴더
def claude_project(cwd):
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


# Claude 기록 파일 — 세션 id 가 있으면 그 파일 · 없으면 그 폴더에서 가장 최근에 바뀐 jsonl · 못 찾으면 None
# cwd: 작업 폴더 / sid: 세션 id
def claude_transcript(cwd, sid=None):
    # 기록 폴더
    base = claude_home() / "projects"
    if sid:
        p = base / claude_project(cwd) / f"{sid}.jsonl"
        if p.is_file():
            return p
        hits = sorted(base.glob(f"*/{sid}.jsonl"))
        return hits[-1] if hits else None
    hits = sorted((base / claude_project(cwd)).glob("*.jsonl"), key=lambda x: x.stat().st_mtime)
    return hits[-1] if hits else None


# Claude 기록의 마지막 모델(assistant message.model) — 없으면 None
# path: 기록 파일
def claude_model(path):
    model = None
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
            raw = f.read()
    except OSError:
        return None
    for line in raw.splitlines():
        if b'"assistant"' not in line:
            continue
        try:
            o = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            continue
        m = o.get("message") if isinstance(o, dict) else None
        if isinstance(m, dict) and m.get("model") and not str(m["model"]).startswith("<"):
            model = m["model"]
    return model


# 등록 파일 경로
# hub: 허브 폴더 / nick: 닉네임
def session_path(hub, nick):
    return hub / "sessions" / f"{nick}.json"


# 자기 등록 찾기 — --nick 이 있으면 그것 · 없으면 CODEX_THREAD_ID 와 thread 가 같은 등록 → (닉네임, 내용)
# hub: 허브 폴더 / nick: --nick 값
def find_me(hub, nick=None):
    if nick:
        # 맞춘 닉네임
        n = norm_nick(nick)
        # 등록 내용
        data = read_json(session_path(hub, n))
        if not data:
            raise HubError(f"«{n}» 등록 없음 — register --nick {n} 먼저")
        return n, data
    # 자기 thread
    th = my_thread()
    if not th:
        raise HubError("CODEX_THREAD_ID 없음 — --nick 이름 을 붙여서")
    # Claude — /clear 뒤 세션 id 가 바뀌어도 같은 claude 프로세스면 자기 등록
    cpid = None if os.environ.get("CODEX_THREAD_ID") else (my_claude() or {}).get("pid")
    for p in sorted((hub / "sessions").glob("*.json")):
        # 등록 내용
        data = read_json(p)
        if data and (data.get("thread") == th or (cpid and data.get("claude_pid") == cpid)):
            return p.stem, data
    raise HubError("허브에 등록 안 됨 — register --nick 이름 먼저(이름을 모르면 유저에게 «허브에 쓸 이름?»)")


# register — 등록(같은 닉네임이 있으면 새 값으로 바꿈)
# a: 명령줄 값 / hub: 허브 폴더
def cmd_register(a, hub):
    if not a.nick:
        raise HubError("--nick 없음 — 역할 스킬이 정해 준 이름(main · 2nd) · 없으면 유저에게 «허브에 쓸 이름?»")
    if a.claude:
        return register_claude(a, hub)
    # 닉네임 · thread · 기록 파일
    nick = norm_nick(a.nick)
    thread = a.thread or my_thread()
    rp = find_rollout(thread)
    # 기록의 effort · 모델
    r_eff, r_model = rollout_settings(rp) if rp else (None, None)
    effort, src = pick_effort(r_eff, a.effort)
    # 등록 파일
    path = session_path(hub, nick)
    # 이전 등록(상태 줄은 이어 씀)
    old = read_json(path) or {}
    data = {"nick": nick, "thread": thread, "effort": effort, "effort_src": src, "model": a.model or r_model or old.get("model"),
            "cwd": os.getcwd(), "registered_at": now_text(), "status": old.get("status", "") if old.get("thread") == thread else "",
            "status_at": old.get("status_at", "") if old.get("thread") == thread else ""}
    write_json(path, data)
    # 출력 조각
    th = f"thread {thread[:8]}…" if thread else "thread 없음(CODEX_THREAD_ID 비어 있음 — 맥락 · 상태는 안 보임)"
    return f"허브 등록: {nick} · {th} · effort {effort}({src})"


# register --claude — Claude Code 세션 등록(kind claude) · 세션 id · 기록 파일 · tmux 대상
# a: 명령줄 값 / hub: 허브 폴더
def register_claude(a, hub):
    nick = norm_nick(a.nick)
    # 자기 claude 프로세스(세션 id · 작업 폴더)
    me = my_claude() or {}
    cwd = me.get("cwd") or os.getcwd()
    sid = a.thread or me.get("sessionId")
    tp = claude_transcript(cwd, sid)
    if not sid and tp:
        sid = tp.stem
    # tmux 대상 · 소켓 — --tmux 가 없으면 지금 창(TMUX_PANE)
    pane = a.tmux or os.environ.get("TMUX_PANE") or None
    sock = (os.environ.get("TMUX") or "").split(",")[0] or None
    path = session_path(hub, nick)
    old = read_json(path) or {}
    same = old.get("thread") == sid
    data = {"nick": nick, "kind": "claude", "thread": sid, "transcript": str(tp) if tp else None,
            "claude_pid": me.get("pid"), "claude_proc": me.get("procStart"), "tmux": pane, "tmux_socket": sock if pane else None,
            "effort": a.effort or "?", "effort_src": "인자" if a.effort else "?",
            "model": a.model or (claude_model(tp) if tp else None) or old.get("model"),
            "cwd": cwd, "registered_at": now_text(), "status": old.get("status", "") if same else "",
            "status_at": old.get("status_at", "") if same else ""}
    write_json(path, data)
    th = f"세션 {sid[:8]}…" if sid else "세션 id 없음(기록을 못 찾음 — 대화는 안 보임)"
    tm = f"tmux {pane}" if pane else "tmux 밖 — 읽기만 등록(보내기 · 마법봉은 tmux 안에서 띄워야: tmux new -s 이름 'command claude')"
    return f"허브 등록: {nick} · Claude · {th} · {tm}"


# status — 상태 줄 바꾸기
# a: 명령줄 값 / hub: 허브 폴더
def cmd_status(a, hub):
    # 닉네임 · 등록 내용
    nick, data = find_me(hub, a.nick)
    data["status"] = one_line(a.text, "상태 줄")
    data["status_at"] = now_text()
    write_json(session_path(hub, nick), data)
    return f"상태 줄 갱신: {nick}"


# log — 누적 한 줄 덧붙이기
# a: 명령줄 값 / hub: 허브 폴더
def cmd_log(a, hub):
    # 닉네임
    nick, _ = find_me(hub, a.nick)
    append_line(hub / "logs" / f"{nick}.jsonl", {"at": now_text(), "text": one_line(a.text, "누적")})
    return f"누적 1줄: {nick}"


# whoami — 자기 등록 한 줄
# a: 명령줄 값 / hub: 허브 폴더
def cmd_whoami(a, hub):
    # 닉네임 · 등록 내용
    nick, d = find_me(hub, a.nick)
    return (f"{nick} · thread {d.get('thread') or '없음'} · effort {d.get('effort')}({d.get('effort_src')})"
            f" · 모델 {d.get('model') or '?'} · 등록 {d.get('registered_at')}")


# queue 실행 명령 앞부분 — CODEX_HUB_CODEX(시험용 · 경로 또는 JSON 목록) → PATH 의 codex(윈도우는 node + codex.js · cmd.exe 를 거치면 기호가 풀려서)
def codex_cmd():
    env = os.environ.get("CODEX_HUB_CODEX")
    if env:
        cmd = json.loads(env) if env.startswith("[") else [env]
        return [sys.executable, *cmd] if cmd[0].endswith(".py") else cmd
    # 실행 파일
    exe = shutil.which("codex.cmd" if os.name == "nt" else "codex") or shutil.which("codex")
    if not exe:
        raise HubError("codex 실행 파일 없음(PATH)")
    if os.name == "nt" and exe.lower().endswith(".cmd"):
        # npm 설치 폴더의 codex.js
        js = Path(exe).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        if not (js.is_file() and node):
            raise HubError(f"codex.cmd 만 찾음({exe})")
        return [node, str(js)]
    return [exe]


# tmux 실행 명령 앞부분 — CODEX_HUB_TMUX(시험용 · 경로 또는 JSON 목록) → PATH 의 tmux
def tmux_cmd():
    env = os.environ.get("CODEX_HUB_TMUX")
    if env:
        cmd = json.loads(env) if env.startswith("[") else [env]
        return [sys.executable, *cmd] if cmd[0].endswith(".py") else cmd
    exe = shutil.which("tmux")
    if not exe:
        raise HubError("tmux 없음(PATH) — Claude 세션에 보내려면 tmux 필요")
    return [exe]


# Claude 세션에 글 넣기 — 괄호 붙여넣기(load-buffer → paste-buffer -p) 뒤 Enter · 여러 줄도 한 메시지
#   (2026-11-03 WSL claude 2.1.302 실측: 줄바꿈 · 따옴표 · $ · ` 가 기록에 그대로 · 유저 메시지(origin human))
# reg: 받는 세션 등록 / text: 글
def tmux_send(reg, text):
    target = reg.get("tmux")
    if not target:
        raise HubError(f"«{reg.get('nick')}» tmux 대상 없음 — 그 Claude 를 tmux 안에서 띄우고 다시 등록해야 보낼 수 있음")
    base = tmux_cmd() + (["-S", reg["tmux_socket"]] if reg.get("tmux_socket") else [])
    buf = f"hub-{os.getpid()}-{int(time.time() * 1000) % 100000}"
    steps = (([*base, "display-message", "-p", "-t", target, "#{pane_id}"], None),
             ([*base, "load-buffer", "-b", buf, "-"], text.encode("utf-8")),
             ([*base, "paste-buffer", "-p", "-d", "-b", buf, "-t", target], None),
             ([*base, "send-keys", "-t", target, "Enter"], None))
    for i, (args, data) in enumerate(steps):
        if i == 3:
            # 붙여넣기를 입력창이 다 받은 뒤 Enter(바로 누르면 붙여넣기 중간에 전송될 수 있음)
            time.sleep(0.3)
        try:
            r = subprocess.run(args, input=data if data is not None else b"", capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise HubError(f"tmux 실행 실패 — {e}") from None
        if r.returncode != 0:
            why = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
            raise HubError(f"tmux {args[len(base)]} 실패(대상 {target}) — {(why[-1] if why else '출력 없음')[:200]}")


# 앱 서버로 바로 보내기 → "steer" · "start" · 못 보내면 None
# hub: 허브 폴더(키트/.codex-hub) / thread: 받는 세션 / text: 글
def try_steer(hub, thread, text):
    p = Path(hub).parent / "devview" / "steer.py"
    if not p.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("hub_steer", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.send(thread, text)
    except Exception:  # noqa: BLE001 — 어떤 실패든 queue 로 물러난다
        return None


# send — 다른 세션에 글 보내기(codex queue) · 글 앞에 «@보낸이름 » 이 붙어 유저 지시와 구별된다
# a: 명령줄 값 / hub: 허브 폴더
def cmd_send(a, hub):
    # 보낸 세션(CODEX_THREAD_ID 로 찾은 자기 등록 — 이름을 인자로 받지 않음) · 받는 세션 등록
    me, _ = find_me(hub)
    to = norm_nick(a.to)
    reg = read_json(session_path(hub, to))
    if not reg:
        raise HubError(f"«{to}» 등록 없음 — 그 세션이 $codex-hub 로 붙어야 보낼 수 있음")
    if not reg.get("thread"):
        raise HubError(f"«{to}» thread 없음")
    if reg.get("thread") == my_thread():
        raise HubError("자기 자신에게는 못 보냄")
    # 보낼 글
    text = str(a.text or "").strip()
    if not text:
        raise HubError("보낼 글 없음")
    if len(text) > SEND_MAX:
        raise HubError(f"글 {len(text)}자 — {SEND_MAX}자 이내")
    if reg.get("kind") == "claude":
        tmux_send(reg, f"@{me} {text}")
        return f"보냄: {me} → {to} · tmux {reg.get('tmux')}"
    # 앱 서버로 바로(키트 devview/steer.py) — 없거나 안 되면 아래 codex queue
    how = try_steer(hub, reg["thread"], f"@{me} {text}")
    if how:
        return f"보냄: {me} → {to} · {how}"
    # 셸 없이 인자 목록 · 글이 «-» 로 시작해도 옵션이 아니게 = 로 붙임
    try:
        r = subprocess.run([*codex_cmd(), "queue", "--thread", reg["thread"], f"--message=@{me} {text}"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except subprocess.TimeoutExpired:
        raise HubError("queue 응답 없음(30초) — Codex 데몬 연결 확인") from None
    # 출력 끝 줄
    last = next((x.strip() for x in reversed((r.stdout + r.stderr).splitlines()) if x.strip()), "")
    if r.returncode != 0:
        raise HubError(f"queue 실패(종료코드 {r.returncode}) — {last[:200] or '출력 없음'}")
    return f"보냄: {me} → {to} · {last[:120]}"


# hook — Codex 훅 사건 한 줄(stdin JSON) → events/<thread>.jsonl · 출력 없음 · 실패해도 종료코드 0
def cmd_hook():
    try:
        # 훅 입력
        p = json.loads(sys.stdin.read() or "{}")
        if not isinstance(p, dict):
            return
        # 사건 이름 · 세션 id
        event = str(p.get("hook_event_name") or "")
        sid = str(p.get("session_id") or my_thread() or "")
        if not event or not re.fullmatch(r"[0-9A-Za-z_-]{1,80}", sid or "x"):
            return
        # 남길 줄 — 본문(프롬프트 · 명령 글자)은 남기지 않음
        line = {"at": now_text(), "ts": round(time.time(), 3), "event": event}
        for k in ("source", "tool_name", "matcher", "stop_hook_active", "turn_id"):
            if p.get(k) not in (None, ""):
                line[k] = p[k]
        append_line(hub_dir(p.get("cwd") or None) / "events" / f"{sid or 'unknown'}.jsonl", line)
    except Exception:  # noqa: BLE001 — 훅 실패로 Codex 를 막지 않음
        return


# 명령줄 해석기
def build_parser():
    # 해석기
    ap = argparse.ArgumentParser(prog="hub.py", description="코덱스 허브 — 등록 · 상태 줄 · 누적")
    # 명령 묶음
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="명령")
    # 등록
    p = sub.add_parser("register", help="허브에 붙기")
    p.add_argument("--nick", default=None, help="main · 2nd · 이름")
    p.add_argument("--effort", default=None, help="기록 · 프로세스에서 못 찾을 때 쓸 값")
    p.add_argument("--model", default=None, help="모델 이름(기록에서 못 찾을 때)")
    p.add_argument("--thread", default=None, help="세션 id(기본 CODEX_THREAD_ID · 시험용)")
    p.add_argument("--claude", action="store_true", help="Claude Code 세션으로 등록(보내기 = tmux)")
    p.add_argument("--tmux", default=None, help="Claude 세션의 tmux 대상(기본 지금 창 TMUX_PANE)")
    for name, what in (("status", "상태 줄"), ("log", "누적 한 줄")):
        p = sub.add_parser(name, help=what)
        p.add_argument("text", help=what)
        p.add_argument("--nick", default=None, help="자기 닉네임(CODEX_THREAD_ID 가 없을 때)")
    p = sub.add_parser("send", help="다른 세션에 글(codex queue · 앞에 @보낸이름)")
    p.add_argument("--to", required=True, help="받는 세션 이름(등록 이름)")
    p.add_argument("text", help="보낼 글")
    p = sub.add_parser("whoami", help="자기 등록 보기")
    p.add_argument("--nick", default=None)
    sub.add_parser("hook", help="Codex 훅 사건 기록(stdin JSON)")
    return ap


# 명령줄 진입점 — 종료코드
# argv: 인자(없으면 sys.argv)
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    # 해석 결과
    a = build_parser().parse_args(argv)
    if a.cmd == "hook":
        cmd_hook()
        return 0
    try:
        # 허브 폴더 · 결과 한 줄
        hub = hub_dir()
        out = {"register": cmd_register, "status": cmd_status, "log": cmd_log, "whoami": cmd_whoami, "send": cmd_send}[a.cmd](a, hub)
    except (HubError, OSError) as err:
        print(f"실패: {err}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
