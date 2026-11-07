#!/usr/bin/env python3
"""코덱스 허브 백엔드(devview) — 작업 폴더 .codex-hub(등록 · 상태 줄 · 누적 · magic 요청) + Codex 기록(rollout) 결합 · 표준 라이브러리만

    devview: GET  /api/hub              행 목록(기본 MAIN · 2ND + 추가 등록) · 상태 · effort · 맥락 · 상태 줄 · 마지막 턴
             GET  /api/hub/log?nick=    누적(한 줄씩 · 오래된 것이 위)
             GET  /api/hub/chat?nick=&after=N   대화(유저 메시지 · 최종 답변 · 혼잣말(commentary → note) · 오류 — 주입 문서 · 도구 · 생각 뺌)
             GET  /api/hub/subagents?nick=      그 세션의 서브 줄(이름 · 일함/쉼/중단 · 지금 일 한 줄 — 서브 기록만 이어 읽음)
             POST /api/hub/queue {nick, text}   그 세션에 codex queue(셸 없이 인자 목록)
             POST /api/hub/magic {nick, view, selection, question}   요청 파일 + (2ND 그래프 · Git · 설문 · 앱) 질문 노드 즉시 등록 + queue «🪄 지시 본문 … $역할-magic 요청id»
             (2ND 그래프: 고른 질문 노드 = 질문은 제목 · 메모 있는 설문 노드 = 질문은 메모 → 입력창 없이 · 답 자리 = 그 노드 · 질문 글이 없으면 {need_input} 으로 화면이 입력창)
             (MAIN 그래프: 답한 설문 노드 = «결정: 선택지 · 메모 — 반영하고 이어진 작업 시작» · 답 없는 설문은 빼고 skipped 로 알림)
             (책 스티커: 페이지 서버 POST /api/notes/<id>/magic · /api/notes/<id>/thread/<꼬리 id>/magic → note_magic → 2ND · 답 자리 note)
             (설문 제출: survey.py submit → magic(view survey) → 확정 문항 MAIN · 질문 문항 2ND · 답 자리 survey)
파일: <작업 폴더>/.codex-hub/ — sessions/<닉>.json(hub.py register · status) · logs/<닉>.jsonl(hub.py log) · requests/<요청id>.json(여기서 씀)
짝 맞추기: 등록의 thread = rollout session_meta.id = 세션 안 CODEX_THREAD_ID
queue 실행 파일: DEVVIEW_CODEX(시험용 · 경로 또는 JSON 목록) → 윈도우는 codex.cmd 옆 node + codex.js(cmd.exe 를 거치면 글 속 기호가 풀려서) → PATH 의 codex
Claude 세션(등록 kind claude · hub.py register --claude): 기록 = ~/.claude/projects/<작업 폴더>/<세션 id>.jsonl · 세션 id · 상태 = ~/.claude/sessions/<pid>.json
  (/clear 로 세션 id 가 바뀌어도 같은 claude 프로세스면 따라감) · 보내기 = tmux 괄호 붙여넣기 + Enter(DEVVIEW_TMUX 시험용) · 마법봉 끝 줄 «/역할-magic 요청id»
"""
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_sessions  # noqa: E402
import steer  # noqa: E402
import stream  # noqa: E402

# 허브 폴더 이름
HUB = ".codex-hub"
# 기본 행(역할) · 화면 이름 · magic 스킬
ROLES = ("main", "2nd")
LABELS = {"main": "MAIN", "2nd": "2ND"}
MAGIC = {"main": "main-magic", "2nd": "2nd-magic"}
# 닉네임 모양(hub.py 와 같음)
NICK_RE = re.compile(r"^[0-9A-Za-z가-힣_-]{1,24}$")
# 요청 id 모양
RID_RE = re.compile(r"^m[0-9]{4}-[0-9]{6}-[0-9a-f]{4}$")
# 큐 보기에 보이는 글 길이
QUEUE_TEXT = 400
# queue 글 최대 글자 수
TEXT_MAX = 20000
# 누적 · 대화 응답 최대 줄 수
LOG_MAX = 2000
CHAT_MAX = 3000
# queue 명령 대기 상한(초) — 데몬 연결이 멈췄을 때 요청이 영영 안 끝나지 않게
QUEUE_SEC = 30
# 주입 문서로 보는 유저 역할 글 머리(대화 탭에서 뺌) — 실제 유저 글은 item_completed UserMessage 가 정본
INJECTED = ("<environment_context>", "<user_instructions>", "<skill>", "<INSTRUCTIONS>", "# AGENTS.md instructions",
            "The following is the Codex agent history", "<turn_aborted>", "<subagent_notification>", "<user_shell_command>",
            "<permissions instructions>", "<collaboration_mode>")
# 2ND 답 자리 — 주석을 다는 코드 확장자(magic.py 와 같은 목록) · 문서 확장자
CODE_EXT = {"py", "pyi", "sh", "bash", "zsh", "rb", "pl", "r", "yaml", "yml", "toml", "ini", "cfg", "conf", "dockerfile",
            "makefile", "ps1", "js", "mjs", "cjs", "jsx", "ts", "tsx", "java", "kt", "kts", "c", "h", "cpp", "hpp", "cc", "cs",
            "go", "rs", "swift", "scala", "dart", "php", "scss", "less", "sql", "lua", "hs", "html", "htm", "xml", "vue",
            "svelte", "css", "bat", "cmd"}
DOC_EXT = {"md", "markdown", "txt"}
# thread → rollout 경로(찾은 것 기억)
_ROLLOUT = {}
# rollout 경로 → 대화 뽑기 중간 상태(이어 읽기)
_CHAT = {}
# (경로, 수정 시각, 크기, 30초 묶음) → 세션 계산 결과
_STATE = {}
# queue 실행 명령 · 못 찾은 이유(한 번 찾으면 기억)
_CODEX = {}


# 허브 오류 — HTTP 상태 + 원인 한 줄
class HubError(Exception):
    # status: HTTP 상태 / msg: 원인
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status


# 지금 시각 글자
def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


# JSON 읽기(없거나 깨지면 기본값)
# path: 파일 / default: 기본값
def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# JSON 쓰기 — 임시 파일 → 교체
# path: 대상 / data: 내용
def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # 임시 파일
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# 등록 목록 — 닉네임 → 등록 내용
# root: 작업 폴더
def sessions(root):
    # 결과
    out = {}
    for p in sorted((Path(root) / HUB / "sessions").glob("*.json")):
        # 등록 내용
        d = read_json(p)
        if isinstance(d, dict) and NICK_RE.match(p.stem):
            out[p.stem] = d
    return out


# 닉네임 맞추기(역할은 소문자) · 모양 검사
# nick: 받은 닉네임
def norm_nick(nick):
    # 다듬은 값
    n = str(nick or "").strip()
    if n.lower() in ROLES:
        n = n.lower()
    if not NICK_RE.match(n):
        raise HubError(400, f"닉네임 형식 오류: {n!r}")
    return n


# 화면 이름 — MAIN · 2ND · 추가 세션은 등록 이름 그대로
# nick: 닉네임
def label(nick):
    return LABELS.get(nick, nick)


# thread 의 rollout 파일(없으면 None) — 찾은 경로는 기억(지워졌으면 다시)
# thread: 세션 id
def rollout_for(thread):
    if not thread:
        return None
    # 기억한 경로
    p = _ROLLOUT.get(thread)
    if p and p.is_file():
        return p
    # 세션 폴더
    base = codex_sessions.codex_home() / "sessions"
    if not base.is_dir():
        return None
    # 맞는 파일 목록
    hits = sorted(base.rglob(f"rollout-*{thread}.jsonl"))
    if not hits:
        return None
    _ROLLOUT[thread] = hits[-1]
    return hits[-1]


# 모델 기본 effort — 기록 · 등록에 effort 가 없는 세션(강도를 안 고르고 띄움 → Codex 가 null 로 남김)은 모델 기본값으로 돈다
#   출처: Codex 홈 models_cache.json 의 default_reasoning_level · 파일이 그대로면 다시 안 읽음 · 못 찾으면 None
# model: 모델 이름
def default_effort(model):
    if not model:
        return None
    p = codex_sessions.codex_home() / "models_cache.json"
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return None
    if _DEFAULTS.get("key") != key:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        models = d.get("models") if isinstance(d, dict) else d
        _DEFAULTS.clear()
        _DEFAULTS.update(key=key, map={m.get("slug"): m.get("default_reasoning_level")
                                        for m in models or [] if isinstance(m, dict) and m.get("slug")})
    return _DEFAULTS["map"].get(model)


# 모델 기본 effort 기억(models_cache.json 경로 · 수정 시각 → 모델 → 기본값)
_DEFAULTS = {}


# ======= Claude 세션 — 기록 · 상태 · 보내기 =======
# Claude 기록에서 유저 글로 안 보는 머리(명령 출력 · 작업 알림 · 스킬 본문 주입)
CLAUDE_SKIP = ("<local-command-", "<task-notification>", "Base directory for this skill", "Caveat:", "<system-reminder>")
# 최종 답으로 보는 멈춤 이유(그 밖 = 도구 호출 앞 혼잣말 → note)
CLAUDE_FINAL = ("end_turn", "stop_sequence", "max_tokens")
# 맥락 창 — 모델 이름에 [1m] 이면 100만 · 그 밖 20만
CLAUDE_WINDOW = 200000


# Claude 홈 — CLAUDE_CONFIG_DIR > ~/.claude
def claude_home():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")).expanduser()


# 등록의 claude 프로세스 기록(~/.claude/sessions/<pid>.json) — 같은 프로세스(procStart 같음)일 때만 · 없으면 None
# reg: 등록 내용
def claude_live(reg):
    pid = reg.get("claude_pid")
    if not pid:
        return None
    d = read_json(claude_home() / "sessions" / f"{pid}.json")
    if not isinstance(d, dict) or not d.get("sessionId"):
        return None
    if reg.get("claude_proc") and d.get("procStart") and str(d["procStart"]) != str(reg["claude_proc"]):
        return None
    return d


# 등록의 Claude 기록 파일 — (경로 또는 None, 세션 id, 프로세스 기록)
# reg: 등록 내용
def claude_transcript(reg):
    live = claude_live(reg)
    sid = (live or {}).get("sessionId") or reg.get("thread")
    if not sid:
        return None, None, live
    base = claude_home() / "projects"
    cwd = (live or {}).get("cwd") or reg.get("cwd") or ""
    p = base / re.sub(r"[^A-Za-z0-9]", "-", str(cwd)) / f"{sid}.jsonl"
    if p.is_file():
        return p, sid, live
    if reg.get("transcript") and Path(reg["transcript"]).is_file() and Path(reg["transcript"]).stem == sid:
        return Path(reg["transcript"]), sid, live
    hits = sorted(base.glob(f"*/{sid}.jsonl")) if base.is_dir() else []
    return (hits[-1] if hits else None), sid, live


# Claude 유저 글 다듬기 — 슬래시 명령(<command-name>/x</command-name><command-args>…)은 «/x 인자» · 사람 글이 아니면 None
# text: 글
def claude_user_text(text):
    t = str(text or "").strip()
    if not t or any(t.startswith(x) for x in CLAUDE_SKIP):
        return None
    if "<command-name>" in t:
        name = re.search(r"<command-name>(.*?)</command-name>", t, re.S)
        args = re.search(r"<command-args>(.*?)</command-args>", t, re.S)
        if not name:
            return None
        return (name.group(1).strip() + (" " + args.group(1).strip() if args and args.group(1).strip() else "")).strip()
    if t.startswith("<command-message>"):
        return None
    return t


# Claude 대화 뽑기 상태 — ChatState 와 같은 결과 모양(user · note · assistant · error)
class ClaudeChatState:
    def __init__(self):
        self.offset = 0
        self.rest = b""
        self.items = []
        self.turn = None

    # 줄 하나 반영 — 서브 줄(isSidechain) · 주입(isMeta) · 도구 결과 · 생각 · 도구 호출은 뺌
    # o: 줄 사전
    def feed(self, o):
        if o.get("isSidechain"):
            return
        kind = o.get("type")
        m = o.get("message") if isinstance(o.get("message"), dict) else {}
        at, ts = stamp(o.get("timestamp"))
        if kind == "user":
            if o.get("isMeta"):
                return
            c = m.get("content")
            if isinstance(c, list):
                if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                    return
                c = "".join(str(b.get("text") or "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            text = claude_user_text(c)
            if text is None:
                return
            self.turn = o.get("promptId") or o.get("uuid")
            if text.startswith("[Request interrupted"):
                self.items.append({"role": "error", "text": "턴 중단됨", "at": at, "ts": ts, "turn": self.turn})
                return
            self.items.append({"role": "user", "text": text, "at": at, "ts": ts, "turn": self.turn, "via": "user", "exact": True})
        elif kind == "assistant":
            c = m.get("content")
            texts = [str(b.get("text") or "") for b in c if isinstance(b, dict) and b.get("type") == "text"] if isinstance(c, list) else (
                [c] if isinstance(c, str) else [])
            text = "".join(texts).strip()
            if not text:
                return
            if o.get("isApiErrorMessage"):
                self.items.append({"role": "error", "text": text, "at": at, "ts": ts, "turn": self.turn})
                return
            role = "assistant" if m.get("stop_reason") in CLAUDE_FINAL else "note"
            self.items.append({"role": role, "text": text, "at": at, "ts": ts, "turn": self.turn})


# Claude 세션 계산 — 상태 · 맥락 · 모델 · 마지막 턴(허브 행용) · parse_session 과 같은 칸 이름
# path: 기록 파일 / live: 프로세스 기록(없으면 None)
def claude_state(path, live=None):
    model = usage = None
    last_ts = None
    turn_open = False
    last_done = None
    err = None
    with open(path, "rb") as f:
        raw_all = f.read()
    for raw in raw_all.splitlines():
        if not raw.strip() or not any(k in raw for k in (b'"user"', b'"assistant"', b"turn_duration")):
            continue
        try:
            o = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(o, dict) or o.get("isSidechain"):
            continue
        t = codex_sessions.parse_ts(o.get("timestamp"))
        if t:
            last_ts = t if last_ts is None else max(last_ts, t)
        kind = o.get("type")
        m = o.get("message") if isinstance(o.get("message"), dict) else {}
        if kind == "user" and not o.get("isMeta"):
            c = m.get("content")
            if isinstance(c, str) and claude_user_text(c) is not None:
                turn_open, err = True, None
        elif kind == "assistant":
            if m.get("model") and not str(m["model"]).startswith("<"):
                model = m["model"]
            if isinstance(m.get("usage"), dict) and not o.get("isApiErrorMessage"):
                usage = m["usage"]
            if o.get("isApiErrorMessage"):
                err = "API 오류"
        elif kind == "system" and o.get("subtype") == "turn_duration":
            turn_open = False
            last_done = {"id": o.get("uuid") or f"t{t}", "at": codex_sessions.local_ts(t), "kind": "turn_duration", "error": err}
    # 상태 — 프로세스 기록(busy · idle)이 있으면 그것 · 없으면 기록(유저 글 뒤 turn_duration 없음 = 작업 중)
    st = (live or {}).get("status")
    state = "working" if st == "busy" else ("idle" if st else ("working" if turn_open else "idle"))
    used = None
    if usage:
        used = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    window = 1000000 if model and "[1m]" in model else CLAUDE_WINDOW
    alive = bool(live) and (not live.get("pid") or os.name == "nt" or Path(f"/proc/{live['pid']}").exists())
    return {"state": state, "model": model, "last_done": last_done, "connected": alive,
            "last_event_at": codex_sessions.local_ts(last_ts) if last_ts else None,
            "context": {"used": used, "window": window, "pct": round(used / window * 100, 1) if used is not None else None,
                        "basis": "마지막 assistant usage 의 input + cache 토큰 ÷ 창(추정)"}}


# 행 하나 — Claude 세션
# row: 기본 칸을 채운 행 / reg: 등록 내용
def claude_row(row, reg):
    row["kind"] = "claude"
    row["tmux"] = reg.get("tmux")
    rp, sid, live = claude_transcript(reg)
    if sid:
        row["thread"] = sid
    if not rp:
        row["state"] = "idle"
        row["note"] = "Claude 기록 없음(세션 id 를 못 찾음)"
        return row
    try:
        fst = rp.stat()
        key = ("claude", str(rp), fst.st_mtime_ns, fst.st_size, int(time.time() // 30), (live or {}).get("status"))
        st = _STATE.get(key)
        if st is None:
            st = claude_state(rp, live)
            if len(_STATE) > 200:
                _STATE.clear()
            _STATE[key] = st
    except OSError as e:
        row["note"] = f"기록 읽기 실패: {e}"
        return row
    row.update({"state": st["state"], "context": st["context"], "model": st["model"] or row["model"], "done": st["last_done"],
                "connected": st["connected"], "last_event_at": st["last_event_at"]})
    if not reg.get("tmux"):
        row["note"] = "tmux 밖에서 띄움 — 읽기만(보내기 · 마법봉 불가)"
    return row


# tmux 실행 명령 앞부분 — DEVVIEW_TMUX(시험용 · 경로 또는 JSON 목록) → PATH 의 tmux · 없으면 None
def tmux_cmd():
    env = os.environ.get("DEVVIEW_TMUX")
    if env:
        cmd = json.loads(env) if env.startswith("[") else [env]
        return [sys.executable, *cmd] if cmd[0].endswith(".py") else cmd
    exe = shutil.which("tmux")
    return [exe] if exe else None


# Claude 세션에 글 넣기 — 괄호 붙여넣기(load-buffer → paste-buffer -p) 뒤 Enter · 여러 줄도 한 메시지
#   (2026-11-03 WSL claude 2.1.302 실측: 줄바꿈 · 따옴표 · $ · ` 가 기록에 그대로 · origin human 유저 메시지)
# reg: 받는 세션 등록 / text: 글 / 반환: 결과 한 줄
def tmux_send(reg, text):
    target = reg.get("tmux")
    if not target:
        raise HubError(409, f"{label(reg.get('nick') or '?')} tmux 밖에서 띄운 Claude — 보내기 불가(tmux new -s 이름 'command claude' 로 띄우고 다시 등록)")
    cmd = tmux_cmd()
    if not cmd:
        raise HubError(503, "tmux 없음(PATH) — Claude 세션에 보내려면 tmux 필요")
    base = cmd + (["-S", reg["tmux_socket"]] if reg.get("tmux_socket") else [])
    buf = f"devview-{os.getpid()}-{secrets.token_hex(3)}"
    steps = (([*base, "display-message", "-p", "-t", target, "#{pane_id}"], b""),
             ([*base, "load-buffer", "-b", buf, "-"], text.encode("utf-8")),
             ([*base, "paste-buffer", "-p", "-d", "-b", buf, "-t", target], b""),
             ([*base, "send-keys", "-t", target, "Enter"], b""))
    extra = {"creationflags": 0x08000000} if os.name == "nt" else {}
    for i, (args, data) in enumerate(steps):
        if i == 3:
            # 붙여넣기를 입력창이 다 받은 뒤 Enter
            time.sleep(0.3)
        try:
            r = subprocess.run(args, input=data, capture_output=True, timeout=10, **extra)
        except subprocess.TimeoutExpired:
            raise HubError(504, "tmux 응답 없음(10초)") from None
        except OSError as e:
            raise HubError(503, f"tmux 실행 실패 — {e}") from None
        if r.returncode != 0:
            why = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
            raise HubError(502, f"tmux {args[len(base)]} 실패(대상 {target}) — {(why[-1] if why else '출력 없음')[:200]}")
    return f"tmux {target} 에 붙여넣고 Enter"


# 행 하나 — 등록 + 기록 결합
# nick: 닉네임 / reg: 등록 내용(없으면 None)
def make_row(nick, reg):
    # 행
    row = {"nick": nick, "label": label(nick), "role": nick if nick in ROLES else None, "registered": bool(reg),
           "state": "none", "effort": "?", "effort_src": "?", "context": None, "status": "", "status_at": "",
           "model": None, "thread": None, "done": None, "connected": False}
    if not reg:
        return row
    row.update({"thread": reg.get("thread"), "status": reg.get("status") or "", "status_at": reg.get("status_at") or "",
                "effort": reg.get("effort") or "?", "effort_src": reg.get("effort_src") or "?", "model": reg.get("model"),
                "registered_at": reg.get("registered_at")})
    if reg.get("kind") == "claude":
        return claude_row(row, reg)
    # 기록 파일
    rp = rollout_for(reg.get("thread"))
    if not rp:
        row["state"] = "idle"
        row["note"] = "Codex 기록 없음(thread 를 못 찾음)"
        return row
    try:
        # 세션 계산 결과 — 파일이 그대로면 30초 동안 다시 안 읽음(연결 · 나이 판정이 시간에 따라 바뀌어서)
        fst = rp.stat()
        key = (str(rp), fst.st_mtime_ns, fst.st_size, int(time.time() // 30))
        st = _STATE.get(key)
        if st is None:
            st = codex_sessions.parse_session(rp)
            if len(_STATE) > 200:
                _STATE.clear()
            _STATE[key] = st
    except OSError as e:
        row["note"] = f"기록 읽기 실패: {e}"
        return row
    row.update({"state": st.get("state") or "idle", "context": st.get("context"), "model": st.get("model") or row["model"],
                "done": st.get("last_done"), "connected": bool(st.get("connected")), "last_event_at": st.get("last_event_at")})
    if st.get("effort"):
        row["effort"], row["effort_src"] = st["effort"], "기록"
    elif row["effort"] == "?" and default_effort(row["model"]):
        row["effort"], row["effort_src"] = default_effort(row["model"]), "기본값"
    return row


# 큐 항목 글 — payload_json 안 가장 긴 글자(모양이 바뀌어도 읽히게)
# raw: payload_json 글자
def queue_text(raw):
    try:
        stack = [json.loads(raw)]
    except ValueError:
        return str(raw)[:QUEUE_TEXT]
    # 가장 긴 글자
    best = ""
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            stack += list(x.values())
        elif isinstance(x, list):
            stack += x
        elif isinstance(x, str) and len(x) > len(best):
            best = x
    return best[:QUEUE_TEXT]


# Codex 큐(턴이 끝나야 들어가는 대기 글) — thread → [{text, at}] · ~/.codex/queue_1.sqlite 읽기 전용 · 못 읽으면 빈 값(표시만 안 됨)
def queued():
    p = codex_sessions.codex_home() / "queue_1.sqlite"
    if not p.is_file():
        return {}
    out = {}
    try:
        con = sqlite3.connect(f"{p.as_uri()}?mode=ro", uri=True, timeout=0.3)
        try:
            for thread, raw, ms in con.execute("select thread_id, payload_json, created_at_ms from queued_items order by queue_order"):
                out.setdefault(thread, []).append({"text": queue_text(raw), "at": time.strftime("%H:%M:%S", time.localtime((ms or 0) / 1000))})
        finally:
            con.close()
    except sqlite3.Error:
        return {}
    return out


# GET /api/hub — 행 목록 · queue 준비 상태
# root: 작업 폴더
def rows(root):
    # 등록 목록
    regs = sessions(root)
    stream.등록(root, regs)
    # 추가 세션 — 등록 순서대로
    extra = sorted((n for n in regs if n not in ROLES), key=lambda n: (regs[n].get("registered_at") or "", n))
    # queue 실행 명령 · 이유 — Claude 등록이 있으면 tmux 로도 보낼 수 있음
    cmd, why = codex_cmd()
    ok = bool(cmd) or (any(r.get("kind") == "claude" for r in regs.values()) and bool(tmux_cmd()))
    # 행 · 큐 대기
    out = [make_row(n, regs.get(n)) for n in (*ROLES, *extra)]
    waiting = queued()
    for r in out:
        r["queue"] = waiting.get(r.get("thread"), [])
    return {"rows": out, "dir": str(Path(root) / HUB),
            "queue": {"ok": ok, "reason": None if ok else why}, "t": time.time()}


# GET /api/hub/log — 누적 줄
# root: 작업 폴더 / nick: 닉네임
def log(root, nick):
    # 닉네임 · 누적 파일
    n = norm_nick(nick)
    p = Path(root) / HUB / "logs" / f"{n}.jsonl"
    # 줄 목록
    out = []
    try:
        for raw in p.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_MAX:]:
            try:
                # 줄 사전
                o = json.loads(raw)
            except ValueError:
                continue
            if isinstance(o, dict) and o.get("text"):
                out.append({"at": str(o.get("at") or ""), "text": str(o["text"])})
    except OSError:
        pass
    return {"nick": n, "label": label(n), "lines": out}


# 주입 문서인가(유저 역할이지만 사람이 쓴 글이 아님)
# text: 글
def injected(text):
    # 앞 공백 뺀 글
    t = text.lstrip()
    return any(t.startswith(x) for x in INJECTED)


# 글 조각 목록 → 글(input_text · output_text · text)
# content: content 목록
def join_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(str(c.get("text") or "") for c in content if isinstance(c, dict) and c.get("type") in
                   ("input_text", "output_text", "text", "Text", None))


# rollout 시각 → (지역 시각 글자, 에포크 초)
# s: ISO 시각
def stamp(s):
    # 에포크 초
    t = codex_sessions.parse_ts(s)
    return (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else ""), t


# 대화 뽑기 상태 — 이어 읽을 때 유지
class ChatState:
    def __init__(self):
        # 읽은 바이트 · 남은 반쪽 줄 · 결과 목록 · 지금 턴 id · 그 턴의 시작 원인(user · queue) · 그 턴에 최종 답변이 있었나
        self.offset = 0
        self.rest = b""
        self.items = []
        self.turn = None
        self.via = None
        self.final_in_turn = False

    # 줄 하나 반영
    # o: 줄 사전
    def feed(self, o):
        # 줄 종류 · 내용 · 하위 종류
        kind, p = o.get("type"), o.get("payload")
        if not isinstance(p, dict):
            return
        sub = p.get("type") if isinstance(p.get("type"), str) else None
        at, ts = stamp(o.get("timestamp"))
        if kind == "event_msg" and sub == "task_started":
            self.turn = p.get("turn_id")
            self.via = (p.get("turn_attribution") or {}).get("turn_trigger") if isinstance(p.get("turn_attribution"), dict) else None
            self.final_in_turn = False
        elif kind == "event_msg" and sub == "item_completed":
            # 완료 항목
            it = p.get("item") or {}
            if isinstance(it, dict) and it.get("type") == "UserMessage":
                self.add_user(join_text(it.get("content")), at, ts, exact=True)
        elif kind == "response_item" and sub == "message":
            # 역할 · 글
            role, text = p.get("role"), join_text(p.get("content"))
            if role == "user" and text.strip() and not injected(text):
                self.add_user(text, at, ts, exact=False)
            elif role == "assistant" and p.get("phase") == "final_answer" and text.strip():
                self.items.append({"role": "assistant", "text": text, "at": at, "ts": ts, "turn": self.turn})
                self.final_in_turn = True
            elif role == "assistant" and p.get("phase") in ("commentary", "partial_answer") and text.strip():
                # 작업 중 혼잣말(«~를 확인할게») — 흐린 줄로만 보임(최종 답변 · 점멸 판정에는 안 섞임)
                self.items.append({"role": "note", "text": text, "at": at, "ts": ts, "turn": self.turn})
        elif kind == "event_msg" and sub in ("task_complete", "turn_aborted"):
            # 최종 답변 단계 표시가 없는 판 — 턴 끝의 마지막 답을 최종 답변으로
            last = p.get("last_agent_message")
            if not self.final_in_turn and isinstance(last, str) and last.strip():
                self.items.append({"role": "assistant", "text": last, "at": at, "ts": ts, "turn": self.turn})
            # 오류 칸
            err = p.get("error") if isinstance(p.get("error"), dict) else None
            if err:
                self.items.append({"role": "error", "text": str(err.get("message") or err.get("codex_error_info") or "오류"),
                                   "at": at, "ts": ts, "turn": self.turn})
            if sub == "turn_aborted":
                self.items.append({"role": "error", "text": "턴 중단됨", "at": at, "ts": ts, "turn": self.turn})
            self.turn, self.via, self.final_in_turn = None, None, False

    # 유저 글 추가 — 같은 턴에 같은 글이 이미 있으면 하나로(UserMessage 와 유저 역할 글이 같이 남는 판)
    # text: 글 / at · ts: 시각 / exact: UserMessage(정본)이면 True
    def add_user(self, text, at, ts, exact):
        for it in reversed(self.items[-6:]):
            if it["role"] == "user" and it.get("turn") == self.turn and it["text"].strip() == text.strip():
                if exact:
                    it["exact"] = True
                return
        self.items.append({"role": "user", "text": text, "at": at, "ts": ts, "turn": self.turn, "via": self.via, "exact": exact})


# 기록 이어 읽기 — 지난 위치 뒤 완성된 줄만 st.feed 로 · 끝이 잘린 줄(쓰는 중)은 st.rest 에 두고 다음에 · 망가진 줄은 건너뜀
# path: 기록 파일 / size: 지금 크기 / st: offset · rest · feed 가 있는 상태 / keys: 이 글자가 든 줄만 해석
def read_new(path, size, st, keys):
    if size <= st.offset:
        return
    with open(path, "rb") as f:
        f.seek(st.offset)
        # 새 바이트
        data = st.rest + f.read(size - st.offset)
    st.offset = size
    # 줄 목록 · 끝 반쪽
    parts = data.split(b"\n")
    st.rest = parts.pop()
    for raw in parts:
        if not raw.strip() or not any(k in raw for k in keys):
            continue
        try:
            # 줄 사전
            o = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if isinstance(o, dict):
            st.feed(o)


# rollout 대화 항목 — 바뀐 부분만 이어 읽음
# path: 기록 파일 / claude: Claude 기록이면 True
def chat_items(path, claude=False):
    # 파일 크기
    size = path.stat().st_size
    # 이전 상태
    st = _CHAT.get(str(path))
    if st is None or size < st.offset:
        st = ClaudeChatState() if claude else ChatState()
        _CHAT[str(path)] = st
    # 빠른 거르기 — 대화에 쓰는 줄만 해석
    keys = (b'"user"', b'"assistant"') if claude else (b"UserMessage", b'"user"', b"final_answer", b"commentary", b"partial_answer",
                                                       b"task_complete", b"task_started", b"turn_aborted")
    read_new(path, size, st, keys)
    if len(_CHAT) > 50:
        _CHAT.clear()
        _CHAT[str(path)] = st
    return st.items


# GET /api/hub/chat — 등록한 세션의 대화(after 번호 뒤만)
# root: 작업 폴더 / nick: 닉네임 / after: 이미 받은 개수
def chat(root, nick, after=0):
    # 닉네임 · 등록
    n = norm_nick(nick)
    regs = sessions(root)
    stream.등록(root, regs)
    reg = regs.get(n)
    if not reg or not reg.get("thread"):
        raise HubError(404, f"{label(n)} 미연결 — 세션이 $codex-hub 로 등록해야 보임")
    # 기록 파일 — Claude 는 /clear 뒤 새 세션 id 를 따라감
    claude = reg.get("kind") == "claude"
    if claude:
        rp, sid, _ = claude_transcript(reg)
        if not rp:
            raise HubError(404, f"{label(n)} Claude 기록 없음(세션 {str(sid or reg['thread'])[:8]}…)")
        reg = dict(reg, thread=sid)
    else:
        rp = rollout_for(reg["thread"])
        if not rp:
            raise HubError(404, f"{label(n)} Codex 기록 없음(thread {reg['thread'][:8]}…)")
    # 항목 전체 · 시작 번호
    items = chat_items(rp, claude)
    start = max(0, int(after or 0))
    reset = start > len(items)
    if reset:
        start = 0
    start = max(start, len(items) - CHAT_MAX)
    # 내보낼 항목 — 내부 칸(exact) 뺌 · 번호 i
    out = [dict({k: v for k, v in it.items() if k != "exact"}, i=i) for i, it in enumerate(items[start:], start)]
    return {"nick": n, "label": label(n), "thread": reg["thread"], "total": len(items), "items": out, "reset": reset,
            "live": [] if claude else stream.목록(reg["thread"], items)}


# ======= 서브 상태 — Codex 기록(rollout)만 읽음 · 모델 호출 · app-server 연결 없음 =======
# 근거(WSL Codex 0.163 실측): 긴 명령 중 25초까지 새 줄 없음 → 조용함으로 쉼 판정 안 함 · 턴 시작 · 끝 줄로만
#   서브가 받는 지시(agent_message)는 본문이 암호화돼 있으면 못 읽음 → 도구 호출 · 혼잣말로 넘어감
#   메모리에서 내려간 서브(notLoaded)는 기록에 안 남음 → 쉼과 구별 못 함
# 한 줄 최대 글자
SUB_TEXT = 70
# 해석할 줄 — 이 글자가 없는 줄(토큰 수 · 도구 출력 등)은 건너뜀
SUB_KEYS = (b'"task_started"', b'"task_complete"', b'"turn_aborted"', b'"agent_message"', b'"custom_tool_call"', b'"function_call"',
            b'"commentary"', b'"user"')
# 서브 기록 색인 — base: sessions 폴더 · seen: 머리를 읽은 파일 · kids: 부모 thread → 서브 머리 목록 · full: 전체 훑기 끝남
_SUBS = {}
# 서브 기록 경로 → 이어 읽기 상태
_SUB_STATE = {}
# 색인 · 상태 잠금(서버가 요청마다 스레드)
_SUB_LOCK = threading.Lock()


# 기록 머리 → 서브 정보 — 서브가 아니면 None · 머리 줄을 아직 쓰는 중이면 False
#   thread_spawn 만 서브로 봄(subagent.other 는 승인 검토 같은 내부 세션)
# path: 기록 파일
def sub_head(path):
    with open(path, "rb") as f:
        raw = f.readline()
    if not raw.endswith(b"\n"):
        return False
    try:
        # 머리 줄 내용
        p = json.loads(raw.decode("utf-8", "replace")).get("payload")
        spawn = p["source"]["subagent"]["thread_spawn"]
        parent = spawn["parent_thread_id"]
    except (ValueError, AttributeError, KeyError, TypeError):
        return None
    # 별명 — 자동으로 붙는 이름
    nickname = spawn.get("agent_nickname") or p.get("agent_nickname")
    return {"id": p.get("id"), "parent": parent, "path": str(path), "nickname": nickname,
            "name": spawn.get("agent_path") or p.get("agent_path") or nickname or "?"}


# 부모 thread → 서브 머리 목록 — 처음 한 번 전체를 훑고, 그다음은 최근 날짜 폴더 둘의 새 파일만 머리를 읽음
def sub_index():
    # 세션 폴더
    base = codex_sessions.codex_home() / "sessions"
    if _SUBS.get("base") != base:
        _SUBS.clear()
        _SUB_STATE.clear()
        _SUBS.update(base=base, seen=set(), kids={}, full=False)
    if not base.is_dir():
        return _SUBS["kids"]
    # 볼 파일(sessions/연/월/일/rollout-*.jsonl)
    if _SUBS["full"]:
        files = [f for d in sorted(base.glob("*/*/*"))[-2:] for f in d.glob("rollout-*.jsonl")]
    else:
        files = list(base.rglob("rollout-*.jsonl"))
        _SUBS["full"] = True
    for f in files:
        if f in _SUBS["seen"]:
            continue
        try:
            head = sub_head(f)
        except OSError:
            continue
        if head is False:
            continue
        _SUBS["seen"].add(f)
        if head:
            _SUBS["kids"].setdefault(head["parent"], []).append(head)
    return _SUBS["kids"]


# 도구 호출 줄 → 보일 글 — 스크립트로 싼 exec 는 글자로만 뽑음(실행 · 평가하지 않음) · 앞 프로세스 후속 조회(write_stdin)는 새 일이 아니라 None
# p: custom_tool_call · function_call 내용
def sub_tool(p):
    name = str(p.get("name") or "")
    if p.get("type") == "custom_tool_call" and name == "exec":
        # 스크립트 글 · 그 안의 도구 이름들
        code = str(p.get("input") or "")
        used = [x for x in re.findall(r"tools\.(\w+)", code) if x != "write_stdin"]
        if not used:
            return None
        cmds = re.findall(r"""\bcmd["']?\s*:\s*(["'`])((?:\\.|(?!\1).)*)\1""", code, re.S)
        return cmds[-1][1].replace('\\"', '"').replace("\\n", " ") if used[-1] == "exec_command" and cmds else used[-1]
    if name == "write_stdin":
        return None
    if name == "exec_command":
        try:
            return str(json.loads(p.get("arguments") or "{}").get("cmd") or name)
        except (ValueError, AttributeError):
            return name
    return name or None


# 글의 첫 줄(빈 줄 건너뜀)
# text: 글
def first_text(text):
    return next((x.strip() for x in str(text or "").splitlines() if x.strip()), "")


# 서브 하나의 상태 — 이어 읽을 때 유지
class SubState:
    def __init__(self):
        # 읽은 바이트 · 남은 반쪽 줄 · 열린 턴 id · 일함 여부 · 중단 이유 · 지시 · 도구 · 혼잣말 · 마지막 결과 · 마지막 기록 시각
        self.offset = 0
        self.rest = b""
        self.turn = None
        self.work = False
        self.why = None
        self.order = self.tool = self.note = self.result = ""
        self.at = ""

    # 줄 하나 반영 — 일함 · 쉼은 턴 시작 · 끝 줄만 바꾼다(끝난 뒤 늦게 오는 도구 줄은 일함으로 안 돌림)
    # o: 줄 사전
    def feed(self, o):
        # 줄 종류 · 내용 · 하위 종류
        kind, p = o.get("type"), o.get("payload")
        if not isinstance(p, dict):
            return
        sub = p.get("type")
        if kind == "event_msg" and sub == "task_started":
            self.turn, self.work, self.why = p.get("turn_id"), True, None
            self.order = self.tool = self.note = ""
        elif kind == "event_msg" and sub in ("task_complete", "turn_aborted"):
            if self.turn and p.get("turn_id") not in (None, self.turn):
                return
            self.turn, self.work = None, False
            self.result = first_text(p.get("last_agent_message"))
            # 오류 칸
            err = p.get("error") if isinstance(p.get("error"), dict) else None
            if err:
                self.why = first_text(err.get("message") or err.get("codex_error_info") or "오류")
            elif sub == "turn_aborted":
                self.why = f"턴 중단됨({p['reason']})" if p.get("reason") else "턴 중단됨"
        elif kind == "response_item" and sub == "agent_message":
            # 머리 «Message Type: … Payload:» 뒤 본문 — 암호화면 비어 있음 · FINAL_ANSWER 는 지시가 아니라 보고
            head, mark, body = join_text(p.get("content")).partition("Payload:\n")
            if mark and "FINAL_ANSWER" not in head and first_text(body):
                self.order = first_text(body)
        elif kind == "response_item" and sub == "message":
            text = join_text(p.get("content"))
            if p.get("role") == "user" and text.strip() and not injected(text):
                self.order = first_text(text)
            elif p.get("role") == "assistant" and p.get("phase") == "commentary" and text.strip():
                self.note = first_text(text)
        elif kind == "response_item" and sub in ("custom_tool_call", "function_call"):
            self.tool = sub_tool(p) or self.tool
        else:
            return
        self.at = stamp(o.get("timestamp"))[0] or self.at

    # 화면 한 줄 내용
    # head: 서브 머리
    def row(self, head):
        if self.work:
            text = self.order or self.tool or self.note or "턴 실행 중"
        else:
            text = self.result or self.why or "대기"
        return {"id": head["id"], "name": head["name"], "nickname": head["nickname"], "state": "work" if self.work else "rest",
                "stopped": bool(self.why) and not self.work, "why": self.why, "text": short(text, SUB_TEXT), "at": self.at}


# GET /api/hub/subagents — 그 세션의 서브 줄 · 일하는 서브가 위 · 그 안은 생긴 순서 · 서브가 없거나 등록이 없으면 빈 목록
# root: 작업 폴더 / nick: 닉네임
def subagents(root, nick):
    # 닉네임 · 부모 thread · 줄 목록
    n = norm_nick(nick)
    reg = sessions(root).get(n) or {}
    thread = None if reg.get("kind") == "claude" else reg.get("thread")
    out = []
    with _SUB_LOCK:
        for head in sorted(sub_index().get(thread, []), key=lambda h: h["path"]) if thread else []:
            # 이어 읽기 상태
            st = _SUB_STATE.setdefault(head["path"], SubState())
            try:
                size = os.stat(head["path"]).st_size
                if size < st.offset:
                    # 파일이 바뀜 — 처음부터
                    st.__init__()
                read_new(head["path"], size, st, SUB_KEYS)
            except OSError:
                continue
            out.append(st.row(head))
    out.sort(key=lambda r: r["state"] != "work")
    return {"nick": n, "label": label(n), "thread": thread, "subs": out, "working": sum(r["state"] == "work" for r in out)}


# queue 실행 명령 — (인자 목록 앞부분, 못 찾은 이유)
def codex_cmd():
    if "cmd" in _CODEX:
        return _CODEX["cmd"], _CODEX["why"]
    # 결과 · 이유
    cmd, why = None, None
    env = os.environ.get("DEVVIEW_CODEX")
    if env:
        cmd = json.loads(env) if env.startswith("[") else [env]
        if cmd[0].endswith(".py"):
            cmd = [sys.executable, *cmd]
    elif os.name == "nt":
        # 윈도우 — codex.cmd 를 직접 부르면 cmd.exe 가 글 속 % · " · & 를 다시 풀어서 그 옆 node + codex.js 로
        exe = shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex")
        if not exe:
            why = "codex 실행 파일 없음(PATH)"
        elif exe.lower().endswith(".exe"):
            cmd = [exe]
        else:
            # npm 설치 폴더
            d = Path(exe).parent
            js = d / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            node = str(d / "node.exe") if (d / "node.exe").is_file() else shutil.which("node")
            if js.is_file() and node:
                cmd = [node, str(js)]
            else:
                why = f"codex.cmd 만 찾음({exe}) — cmd.exe 를 거치면 글 속 기호가 풀려 안 씀"
    else:
        # 리눅스 — /usr/bin/codex(노드 스크립트 · 실행 권한)를 바로
        exe = shutil.which("codex")
        if exe:
            cmd = [exe]
        else:
            why = "codex 실행 파일 없음(PATH)"
    _CODEX.update(cmd=cmd, why=why)
    return cmd, why


# codex queue 실행 — 성공이면 출력 끝 줄, 실패면 HubError
# thread: 세션 id / text: 글
def run_queue(thread, text):
    # 실행 명령 · 이유
    cmd, why = codex_cmd()
    if not cmd:
        raise HubError(503, f"queue 불가 — {why}")
    # 글이 «-» 로 시작해도 옵션으로 읽히지 않게 = 로 붙임 · 셸 없이 인자 목록
    args = [*cmd, "queue", "--thread", thread, f"--message={text}"]
    # 윈도우 — 창 없이(pythonw 로 뜬 devview 에서 콘솔 창이 깜빡이지 않게)
    extra = {"creationflags": 0x08000000} if os.name == "nt" else {}
    try:
        # 실행 결과
        r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=QUEUE_SEC, **extra)
    except subprocess.TimeoutExpired:
        raise HubError(504, f"queue 응답 없음({QUEUE_SEC}초) — Codex 데몬 연결 확인") from None
    except OSError as e:
        raise HubError(503, f"queue 실행 실패 — {e}") from None
    # 출력 글(끝 줄)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    last = next((x.strip() for x in reversed(out.splitlines()) if x.strip()), "")
    if r.returncode != 0:
        raise HubError(502, f"queue 실패(종료코드 {r.returncode}) — {last[:300] or '출력 없음'}")
    return last[:300]


# 보낼 대상 등록 — 없거나 thread 가 없으면 HubError
# root: 작업 폴더 / nick: 닉네임
def target(root, nick):
    # 닉네임 · 등록
    n = norm_nick(nick)
    reg = sessions(root).get(n)
    if not reg:
        raise HubError(409, f"{label(n)} 미연결 — 세션이 $codex-hub 로 등록해야 보낼 수 있음")
    if reg.get("kind") == "claude":
        return n, reg
    if not reg.get("thread"):
        raise HubError(409, f"{label(n)} thread 없음 — 그 세션에서 CODEX_THREAD_ID 가 비어 있었음")
    return n, reg


# POST /api/hub/queue — 직접 입력
# root: 작업 폴더 / body: {nick, text}
def send(root, body):
    # 대상 · 글
    n, reg = target(root, body.get("nick"))
    text = str(body.get("text") or "")
    if not text.strip():
        raise HubError(400, "보낼 글 없음")
    if len(text) > TEXT_MAX:
        raise HubError(413, f"글이 너무 김({len(text)}자 · {TEXT_MAX}자 이내)")
    return {"ok": True, "nick": n, "label": label(n), "out": deliver(reg, text)}


# 보내기 — Claude = tmux 붙여넣기 · Codex = 앱 서버로 바로(steer · start) → 안 되면 codex queue(턴 끝 뒤)
# reg: 받는 세션 등록 / text: 글
def deliver(reg, text):
    if reg.get("kind") == "claude":
        return tmux_send(reg, text)
    try:
        how = steer.send(reg["thread"], text)
    except steer.SteerError:
        return f"큐(턴 끝 뒤) · {run_queue(reg['thread'], text)}"
    return "턴 중 바로 전달" if how == "steer" else "바로 전달"


# 새 요청 id — m월일-시분초-16진 4자리
def new_rid():
    return f"m{time.strftime('%m%d-%H%M%S')}-{secrets.token_hex(2)}"


# 파일 종류 → 2ND 답 자리(md · code · form)
# path: 파일 경로 / readonly: 옛 판 보기 등 고칠 수 없는 문서
def answer_kind(path, readonly=False):
    # 파일 이름 · 확장자
    name = Path(str(path)).name.lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else name
    if readonly:
        return "form"
    if ext in DOC_EXT:
        return "md"
    if ext in CODE_EXT:
        return "code"
    return "form"


# 고른 노드 목록 다듬기 — [{id, kind, graph, title}]
# nodes: 화면이 보낸 목록
def clean_nodes(nodes):
    # 결과
    out = []
    for x in nodes or []:
        if isinstance(x, dict) and isinstance(x.get("id"), str) and x["id"]:
            out.append({"id": x["id"][:120], "kind": str(x.get("kind") or "")[:20], "graph": str(x.get("graph") or "")[:10],
                        "title": str(x.get("title") or "")[:200]})
    return out[:50]


# 질문 노드 즉시 등록 — 유저 이름(role user)으로 · 대상 노드마다 선 · 반환 질문 id
# ft: flowtree server 모듈 / ws: flowtree 작업 공간 / text: 질문 제목 / targets: 대상 id 목록 / view: feature · adr · code
def add_question(ft, ws, text, targets, view):
    if ft is None or ws is None:
        raise HubError(503, "flowtree 없음 — 질문 노드를 못 만듦")
    if not ws.tree_path.is_file():
        raise HubError(409, f"그래프 파일 없음 — {ws.tree_path}")
    # 쓰기 통로(flowtree_store)
    store = ft.flowtree_store
    # 대상 — 트리 노드 · 화면 노드(mod: · fn: · ext:)만(유저 노드는 질문 선 불가)
    tree = store.read_json(ws.tree_path, {}) or {}
    ids = set(store.node_map(tree))
    tg = [t for t in targets if t in ids or t.startswith(store.SCREEN_PREFIX)]
    try:
        # 실행 결과
        res = store.apply(ws.tree_path, "user", "ask", text=text, target=tg[0] if tg else None,
                          view=view if view in ("feature", "adr", "code") else "feature", targets=tg[1:])
    except store.StoreError as e:
        raise HubError(400, f"질문 노드 실패 — {e}") from None
    return res["id"], tg


# 책 스티커 선택 채우기 — 화면은 {note, doc(책 html 경로)} 만 보냄 → notes.json(책 폴더) 의 스티커 글 · 자리 · 블록
#   이미 notes_file 이 있으면(페이지 서버 note_magic) 그대로
# root: 작업 폴더 / sel: 선택
def book_sel(root, sel):
    if sel.get("notes_file") or not sel.get("note") or not sel.get("doc"):
        return sel
    # 책 html → 책 폴더(dist 의 부모) · notes.json
    doc = str(sel["doc"]).replace("\\", "/")
    nf = (Path(root) / doc).parent.parent / "notes.json"
    data = read_json(nf, []) or []
    nt = next((x for x in data if isinstance(x, dict) and x.get("id") == sel["note"]), None)
    if nt is None:
        raise HubError(404, f"스티커 없음: {sel['note']} ({nf.name})")
    m = re.search(r"b=([^\s|]+)", str(nt.get("ctx") or ""))
    return {**sel, "notes_file": str(nf.relative_to(Path(root))).replace("\\", "/"), "book": nf.parent.name,
            "ctx": str(nt.get("ctx") or "")[:300], "block": m.group(1) if m else "", "text": str(nt.get("text") or "")}


# MAIN 지시의 대상 — 보기의 선택(코드 줄 · 글자 · 표 칸 · Git · 책 스티커) · 없으면 None
# view: 보기 / sel: 선택 / resolve: 상대 경로 → 실제 경로
def ref_of(view, sel, resolve=None):
    if view == "code" and sel.get("file"):
        absp = None
        if resolve:
            try:
                absp = str(resolve(str(sel["file"])))
            except Exception:  # noqa: BLE001 — 경로 밖이면 상대 경로만
                absp = None
        return {"kind": "code", "file": str(sel["file"]), "abs": absp, "range": sel.get("range"),
                "text": str(sel.get("text") or "")[:4000], "table": sel.get("table") if isinstance(sel.get("table"), dict) else None}
    if view == "git" and (sel.get("commit") or sel.get("git_file")):
        return {"kind": "git", "commit": str(sel.get("commit") or "")[:40], "git_file": str(sel.get("git_file") or "")[:500],
                "subject": str(sel.get("subject") or "")[:200]}
    if view == "book" and sel.get("note"):
        return {"kind": "note", **{k: str(sel.get(k) or "")[:2000] for k in ("note", "doc", "book", "block", "notes_file", "text")}}
    return None


# 대상 한 줄 글 — magic_text · magic.py 가 같이 씀
# r: ref_of 결과
def ref_text(r):
    if not r:
        return ""
    if r["kind"] == "code":
        g = r.get("range") or {}
        tb = r.get("table") or {}
        return (f"파일 {r['file']}" + (f" {g.get('start_line')}–{g.get('end_line')}줄" if g.get("start_line") else "")
                + (f" · 표 행 {tb.get('line')} 열 {tb.get('col')}" if tb else "")
                + (f" · 고른 글자 «{short(r.get('text'), 120)}»" if str(r.get("text") or "").strip() else ""))
    if r["kind"] == "git":
        return "Git " + " · ".join(x for x in (r.get("commit", "")[:10], r.get("git_file", ""),
                                               f"«{short(r.get('subject'), 60)}»" if r.get("subject") else "") if x)
    if r["kind"] == "note":
        return f"책 ‹{r.get('book')}› 스티커 {r.get('note')} «{short(r.get('text'), 120)}»" + (f" (블록 {r['block']})" if r.get("block") else "")
    return ""


# 2ND 그래프 — 고른 노드 중 답 자리가 될 질문 · 설문 노드(질문 노드 먼저 · 닫힌 질문 제외) · 반환 사전 또는 None
#   {"id", "kind", "ask"(질문 노드 = 제목 · 설문 노드 = 메모 · 빈 글이면 입력창), "targets"(질문 선 대상 · 설문은 붙은 작업 + 함께 고른 노드)}
# ft · ws: flowtree 모듈 · 작업 공간 / nodes: 고른 노드 목록(clean_nodes)
def own_node(ft, ws, nodes):
    if ft is None or ws is None or not nodes or not ws.tree_path.is_file():
        return None
    store = ft.flowtree_store
    tree = store.read_json(ws.tree_path, {}) or {}
    nm = store.node_map(tree)
    # 고른 id · 트리 기준 종류
    ids = [x["id"] for x in nodes]
    q = next((i for i in ids if (nm.get(i) or {}).get("kind") == "question" and not nm[i].get("closed")), None)
    s = next((i for i in ids if (nm.get(i) or {}).get("kind") == "survey"), None) if q is None else None
    if q is None and s is None:
        return None
    nid = q or s
    nd = nm[nid]
    # 대상 — 질문 선(질문 노드) · 붙은 작업(설문 노드) + 함께 고른 다른 노드
    base = [e.get("target") for e in tree.get("edges", []) if e.get("kind") == "asks" and e.get("source") == nid] if q else \
        ([nd["parent"]] if nd.get("parent") else [])
    tg = list(dict.fromkeys([t for t in base + [i for i in ids if i != nid] if t]))
    ask = str(nd.get("title") or "") if q else store.survey_vote(nd)["memo"]
    return {"id": nid, "kind": nd["kind"], "ask": ask.strip(), "title": str(store.eff(nd, "title") or ""), "targets": tg,
            "rev": int(tree.get("rev") or 0), "answers": [a for a in nd.get("answers") or [] if isinstance(a, dict)]}


# 고른 노드 중 열린 질문 노드 id 목록(트리 기준 · 고른 순서)
# ft · ws: flowtree 모듈 · 작업 공간 / nodes: 고른 노드 목록
def open_questions(ft, ws, nodes):
    if ft is None or ws is None or not nodes or not ws.tree_path.is_file():
        return []
    nm = ft.flowtree_store.node_map(ft.flowtree_store.read_json(ws.tree_path, {}) or {})
    return [x["id"] for x in nodes if (nm.get(x["id"]) or {}).get("kind") == "question" and not nm[x["id"]].get("closed")]


# 그 노드(질문 · 설문)에 보낸 요청 중 아직 답이 안 달린 것 — 요청 id 또는 None
#   요청 target.rev = 보낼 때의 그래프 판 번호 · 그 뒤 판(seq)의 답이 있으면 답 달림
# root: 작업 폴더 / own: own_node 결과
def pending_request(root, own):
    best = None
    for f in sorted((Path(root) / HUB / "requests").glob("m*.json")):
        r = read_json(f, {}) or {}
        t = r.get("target") or {}
        if t.get("question") != own["id"] or not t.get("own") or not isinstance(t.get("rev"), int) or r.get("failed"):
            continue
        if not any(int(a.get("seq") or 0) > t["rev"] for a in own["answers"]):
            best = r.get("id") or f.stem
    return best


# MAIN — 설문 노드 상태: none(답 없음) · hold(보류) · acked(이미 반영 — 마지막 답보다 반영 기록이 새것) · ok(결정 · 반영 전)
# store: flowtree_store / nd: 설문 노드
def survey_state(store, nd):
    v = store.survey_vote(nd)
    if v["hold"]:
        return "hold"
    if v["pick"] is None and not v["memo"]:
        return "none"
    if v["seq"] <= max((int(a.get("seq") or 0) for a in nd.get("acks") or []), default=0):
        return "acked"
    return "ok"


# MAIN — 설문 노드에 유저 답이 있나(선택 · 기타 · 보류 · 메모 중 하나)
# store: flowtree_store / nd: 설문 노드
def survey_answered(store, nd):
    v = store.survey_vote(nd)
    return v["pick"] is not None or v["hold"] or bool(v["memo"])


# 설문 노드 결정 글 — «‹선택지 라벨›» · 기타 · 보류 · 선택 없음
# store: flowtree_store / nd: 설문 노드
def survey_choice(store, nd):
    v = store.survey_vote(nd)
    opts = nd.get("options") or []
    if v["hold"]:
        return "보류"
    if v["pick"] == store.PICK_OTHER:
        return "기타"
    if v["pick"] is not None and 0 <= v["pick"] < len(opts):
        o = opts[v["pick"]]
        return f"{v['pick'] + 1}. {o.get('label', '')}" + (f" — {short(o.get('text'), 80)}" if o.get("text") else "")
    return "선택 없음"


# 한 줄로 줄이기
# s: 글 / n: 최대 글자
def short(s, n=120):
    # 한 줄 글
    t = " ".join(str(s or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


# 마법봉 queue 글 — 첫 글자 🪄 + 지시 본문(유저 지시로 기록에 남게) + 끝 줄 «$역할-magic 요청id»
#   끝 줄 $스킬도 Codex 가 스킬로 부른다(2026-11-03 WSL codex 0.163 실측 — <skill> 주입 확인)
#   Claude 세션은 $ 대신 / 가 스킬 호출이라 끝 줄 «/역할-magic 요청id»
# n: 역할 / rid: 요청 id / req: 요청 내용 / ft · ws: flowtree 모듈 · 작업 공간 / claude: Claude 세션이면 True
def magic_text(n, rid, req, ft=None, ws=None, claude=False):
    # 트리 노드(요약 · 섹션 앵커 · 이름 칸)
    nodes = {}
    if ft is not None and ws is not None and ws.tree_path.is_file():
        nodes = ft.flowtree_store.node_map(ft.flowtree_store.read_json(ws.tree_path, {}) or {})
    # 본문 줄
    body = []
    t = req.get("target") or {}
    if t.get("kind") == "survey":
        # 설문 제출 — MAIN = 확정 문항(결정 문서 반영 · 커밋 → 작업) · 2ND = 질문 문항(답)
        items = t.get("items") or []
        head = f"설문 ‹{short(t.get('title'), 60)}›({t.get('survey')})"
        body.append(f"{head} 확정 {len(items)}개 — 결정 문서에 반영 · 커밋하고 작업 시작해 줘" if n == "main"
                    else f"{head} 질문 {len(items)}개 — 답해 줘")
        for it in items[:20]:
            body.append(f"- [{it.get('id') or '-'}] {short(it.get('question'), 80)} → {short(it.get('text'), 160)}")
        if len(items) > 20:
            body.append(f"- 외 {len(items) - 20}개(magic.py show)")
        if t.get("extra"):
            body.append(f"추가 지시: {short(t['extra'], 300)}")
    elif n == "main":
        for x in req.get("nodes") or []:
            # 트리 노드 · 섹션 앵커 · 요약 · 이름 칸
            nd = nodes.get(x["id"]) or {}
            title = nd.get("title") or x.get("title") or x["id"]
            # 종류 — 트리 기준(화면이 보낸 종류만 믿지 않음) · MAIN 이 서브에게 나눈다
            kind = nd.get("kind") or x.get("kind")
            if kind == "verify":
                body.append(f"검증 노드 ‹{short(title, 60)}›({x['id']}) 확인해 줘" + (f" — {short(nd['summary'], 80)}" if nd.get("summary") else ""))
                continue
            if kind == "question":
                body.append(f"질문 노드 ‹{short(title, 60)}›({x['id']}) 답해 줘")
                continue
            if kind == "survey" and nd and survey_state(ft.flowtree_store, nd) == "ok":
                # 설문 노드 — 유저 답(선택 · 메모)을 결정으로 보고 반영 → 붙은 작업 시작(답 없는 설문은 magic() 이 미리 뺌)
                fs = ft.flowtree_store
                memo = fs.survey_vote(nd)["memo"]
                par = nodes.get(nd.get("parent")) or {}
                body.append(f"설문 ‹{short(fs.eff(nd, 'title') or title, 60)}›({x['id']}) 결정: ‹{survey_choice(fs, nd)}›"
                            + (f" · 메모 {short(memo, 160)}" if memo else "")
                            + (f" — 반영하고 이어진 작업 ‹{short(par.get('title') or nd['parent'], 40)}›({nd['parent']}) 시작" if nd.get("parent")
                               else " — 반영하고 이어진 작업 시작"))
                continue
            if kind != "task":
                body.append(f"맥락: ‹{short(title, 60)}›({x['id']})")
                continue
            anchor = str((nd.get("doc") or {}).get("anchor") or "") if isinstance(nd.get("doc"), dict) else ""
            line = f"{'섹션 ' + anchor + ' ' if anchor else ''}‹{short(title, 60)}›({x['id']}) 구현해 줘"
            if nd.get("summary"):
                line += f" — 요약: {short(nd['summary'], 80)}"
            # 함수 표(파일 · 함수 — 옛 names 도 행으로) · 이름 바뀜(유저가 고쳐 아직 코드에 반영 안 된 이름)
            fs = ft.flowtree_store if ft is not None else None
            rows = [r for r in fs.func_rows(nd) if not r.get("del")] if fs is not None and hasattr(fs, "func_rows") else []
            if rows:
                line += f" · 함수: {' · '.join(fs.func_label(r) for r in rows[:8])}" + (f" 외 {len(rows) - 8}" if len(rows) > 8 else "")
            body.append(line)
            for r in rows:
                if fs.func_pending(r):
                    body.append(f"이름 바뀜: {fs.func_change(r)} — 코드 · 시험 · 문서도 새 이름으로 바꾸고 funcs-ack {x['id']}")
        if req.get("instruction"):
            # 지시 붙은 마법봉(Alt+E) — 대상(노드 · 보기의 선택) + 지시 글
            if t.get("ref"):
                body.append(f"대상: {ref_text(t['ref'])}")
            elif not req.get("nodes"):
                body.append(f"대상 없음(보기 {req.get('view') or '-'})")
            body.append(f"지시: {short(req['instruction'], 1000)}")
    else:
        # 대상 한 줄
        if t.get("kind") == "note" and t.get("thread"):
            # 꼬리 질문 — 원 질문 · 앞 답(마지막 꼬리 답 또는 원 답) · 꼬리 질문 · 스티커 id + 꼬리 id
            prev = [x for x in t.get("prev") or [] if x.get("a")]
            body.append(f"책 ‹{short(t.get('book') or t.get('doc'), 40)}› 스티커 꼬리 질문"
                        f" (스티커 {t.get('note')} · 꼬리 {t['thread']}" + (f" · 블록 {t['block']}" if t.get("block") else "") + ")")
            body.append(f"원 질문: {short(t.get('orig_q'), 200)}")
            body.append(f"앞 답: {short(prev[-1]['a'] if prev else t.get('orig_a'), 300)}")
            body.append(f"꼬리 질문: {short(req.get('question'), 300)}")
        elif t.get("kind") == "note":
            where = f"책 ‹{short(t.get('book') or t.get('doc'), 40)}› 스티커 질문"
            body.append(f"{where}: {short(req.get('question'), 300)}" + (f" (블록 {t['block']})" if t.get("block") else ""))
            body.append(f"스티커 {t.get('note')} — 답에 짧은 제목(--title · 20자 안팎)도 달 것")
        else:
            if t.get("kind") == "node":
                tg = [f"‹{short((nodes.get(i) or {}).get('title') or i, 40)}›({i})" for i in t.get("targets") or []]
                where = "노드 " + " · ".join(tg) if tg else ("Git " + " · ".join(x for x in (str(t.get("commit") or "")[:10], str(t.get("git_file") or "")) if x)
                                                             if t.get("commit") or t.get("git_file") else "")
                if t.get("own"):
                    # 고른 질문 · 설문 노드 자체가 답 자리(새 질문 노드 없음) — «(질문 노드 ‹…›(q…) 안에 답 · 대상: …)»
                    own = f"{'설문' if t['own'] == 'survey' else '질문'} 노드 ‹{short(t.get('own_title') or t['question'], 40)}›({t['question']}) 안에 답"
                    body.append(f"질문: {short(req.get('question'), 300)} ({own}" + (f" · 대상: {where})" if where else ")"))
            elif t.get("kind") == "chat":
                where = f"없음(보기 {req.get('view') or '-'}) — 답은 대화로"
            else:
                r = t.get("range") or {}
                where = f"{t.get('file')}" + (f" {r.get('start_line')}–{r.get('end_line')}줄" if r.get("start_line") else "")
            if not t.get("own"):
                body.append(f"질문: {short(req.get('question'), 300)}" + (f" (대상: {where})" if where else ""))
        ins = req.get("instruction")
        if ins and ins == req.get("question"):
            # 지시 글이 곧 질문 — «질문:» 을 «지시:» 로
            body = [x.replace("질문: ", "지시: ", 1) if x.startswith("질문: ") else x for x in body]
        elif ins:
            body.append(f"지시: {short(ins, 1000)}")
    return "🪄 " + "\n".join(body or ["(대상 없음)"]) + f"\n{'/' if claude else '$'}{MAGIC[n]} {rid}"


# 책 스티커 → 2ND 마법봉 요청 — 페이지 서버가 notes.json 의 스티커를 읽어 부름(클라이언트는 id 만 보냄)
# root: 작업 폴더 / note: 스티커 항목 / notes_file: notes.json 경로 / doc: 책 html 상대 경로 / tid: 꼬리 질문 id(없으면 원 질문)
def note_magic(root, note, notes_file, doc, tid=None, instruction=""):
    # 블록 ID — ctx 끝의 «b=…»
    m = re.search(r"b=([^\s|]+)", str(note.get("ctx") or ""))
    try:
        rel = str(Path(notes_file).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except ValueError:
        rel = str(notes_file)
    # 책 이름 — notes.json 이 든 폴더
    book = Path(notes_file).parent.name
    sel = {"note": note.get("id"), "notes_file": rel, "doc": doc, "book": book, "ctx": str(note.get("ctx") or "")[:300],
           "block": m.group(1) if m else ""}
    question = str(note.get("text") or "")
    if tid:
        # 꼬리 질문 — 질문 = 꼬리 글 · 맥락 = 원 질문 · 원 답 · 앞 꼬리(문답)
        th = [t for t in note.get("thread") or [] if isinstance(t, dict)]
        cur = next((t for t in th if t.get("id") == tid), None)
        if cur is None:
            raise HubError(404, f"꼬리 질문 없음: {tid}")
        sel["thread"] = tid
        sel["orig_q"] = question
        sel["orig_a"] = str(note.get("answer") or "")
        sel["prev"] = [{"id": t.get("id"), "q": str(t.get("q") or ""), "a": str(t.get("a") or "")} for t in th[:th.index(cur)]]
        question = str(cur.get("q") or "")
    return magic(root, {"nick": "2nd", "view": "book", "selection": sel, "question": question, "instruction": instruction})


# POST /api/hub/magic — 요청 파일 → (2ND 질문 노드) → queue «🪄 지시 본문 + $역할-magic 요청id»
# root: 작업 폴더 / body: {nick, view, selection, question} / ft · ws: flowtree 모듈 · 작업 공간 / resolve: 상대 경로 → 실제 경로
def magic(root, body, ft=None, ws=None, resolve=None):
    # 대상 · 역할
    n, reg = target(root, body.get("nick"))
    if n not in MAGIC:
        raise HubError(400, f"{label(n)} 는 마법봉 없음(MAIN · 2ND 만)")
    # 보기 · 선택 · 질문
    view = str(body.get("view") or "")
    sel = body.get("selection") if isinstance(body.get("selection"), dict) else {}
    question = str(body.get("question") or "").strip()
    # 지시 글(Alt+E · Alt+R — 허브 입력창으로 붙인 글) · 책 스티커 선택이면 notes.json 에서 스티커 정보 채움
    instruction = str(body.get("instruction") or "").strip()[:TEXT_MAX // 2]
    if view == "book":
        sel = book_sel(root, sel)
    nodes = clean_nodes(sel.get("nodes"))
    # 요청 내용
    rid = new_rid()
    req = {"id": rid, "skill": MAGIC[n], "nick": n, "role": n, "at": now_text(), "view": view, "question": question,
           "nodes": nodes, "graph_view": str(sel.get("graph_view") or ""), "root": str(Path(root).resolve()),
           "tree": str(ws.tree_path) if ws is not None else None,
           "flowtree": str(Path(ft.__file__).resolve().parent) if ft is not None else None, "target": None,
           "instruction": instruction}
    # 알림 덧붙임
    note = ""
    if view == "survey" and isinstance(sel.get("survey"), dict):
        # 설문 제출(survey.py submit) — 문항 목록 · 결과 위치(답 자리 = MAIN 은 결정 문서 · 2ND 는 설명 폼)
        sv = sel.get("survey") if isinstance(sel.get("survey"), dict) else {}
        items = [{"id": str(x.get("id") or "")[:40], "question": str(x.get("question") or "")[:500], "kind": str(x.get("kind") or "")[:10],
                  "text": str(x.get("text") or "")[:2000]} for x in (sel.get("items") or []) if isinstance(x, dict)][:100]
        if not sv.get("id") or not items:
            raise HubError(400, "설문 id · 문항 없음")
        req["target"] = {"kind": "survey", "survey": str(sv["id"])[:40], "title": str(sv.get("title") or "")[:200],
                         "project": str(sv.get("project") or "")[:80], "dir": str(sv.get("dir") or "")[:500],
                         "items": items, "extra": str(sel.get("extra") or "")[:2000]}
    elif n == "main":
        # 답 없는 설문 노드는 뺀다(유저 답 = 결정으로 보내므로) — 같이 고른 다른 노드는 그대로
        # 뺄 설문 — 답 없음 · 보류 · 이미 반영(지시 글이 있으면 빼지 않고 맥락으로 · 빈 틀 설문은 맥락으로 그대로 — MAIN 이 채움)
        skipped, skip_note = [], ""
        if nodes and not instruction and ft is not None and ws is not None and ws.tree_path.is_file():
            fs = ft.flowtree_store
            nm = fs.node_map(fs.read_json(ws.tree_path, {}) or {})
            groups = {"none": [], "hold": [], "acked": []}
            for x in nodes:
                nd = nm.get(x["id"]) or {}
                if nd.get("kind") == "survey" and not nd.get("frame"):
                    st = survey_state(fs, nd)
                    if st in groups:
                        groups[st].append(x["id"])
            skipped = [i for g in groups.values() for i in g]
            skip_note = " · ".join(f"{name} {' · '.join(groups[k])}" for k, name in (("none", "답 없음"), ("hold", "보류 설문"),
                                                                                   ("acked", "이미 반영한 설문")) if groups[k])
            nodes = [x for x in nodes if x["id"] not in skipped]
            req["nodes"] = nodes
            req["skipped"] = skipped
            req["skip_note"] = skip_note
            if skipped:
                note = f"{skip_note} 뺌 · "
        if not nodes and not instruction:
            raise HubError(400, f"보낼 노드 없음 — {skip_note}" if skipped
                           else "노드를 고르지 않음 — 그래프에서 노드를 고른 뒤(Ctrl+클릭 여럿)")
        # 지시 글이 있으면 노드 없이도 — 그 보기의 대상(코드 줄 · Git · 스티커)을 같이 싣는다
        req["target"] = {"kind": "work", "ref": ref_of(view, sel, resolve) if instruction else None}
    else:
        # 질문 노드 여럿(입력창 글 없음) — 질문마다 요청을 따로(각각 그 노드 안에 답) · 함께 고른 다른 노드는 대상
        qs = open_questions(ft, ws, nodes) if view == "graph" and not question else []
        if len(qs) > 1:
            others = [x for x in nodes if x["id"] not in qs]
            outs, errs = [], []
            for q in qs:
                try:
                    outs.append(magic(root, {**body, "selection": {**sel, "nodes": [x for x in nodes if x["id"] == q] + others}}, ft, ws, resolve))
                except HubError as e:
                    errs.append(f"{q} {e}")
            if not outs:
                raise HubError(409, " · ".join(errs))
            return {"ok": True, "id": outs[-1]["id"], "ids": [o["id"] for o in outs], "nick": n, "label": label(n), "skipped": [],
                    "msg": f"질문 {len(outs)}개 각각 {label(n)} 에 보냄" + (f" · 못 보냄: {' · '.join(errs)}" if errs else "")}
        # 그래프에서 고른 질문 · 설문 노드 — 답 자리 = 그 노드(질문 = 질문 노드 제목 · 설문 메모 · 입력창 글)
        own = own_node(ft, ws, nodes) if view == "graph" else None
        if own and own["kind"] == "survey" and not question:
            question = own["ask"]
        elif own and own["kind"] == "question" and not question:
            question = own["ask"]
        elif own and own["kind"] == "question":
            own = None   # 입력창 글 + 질문 노드 — 새 질문(옛 동작)
        if not question and view == "book":
            question = str(sel.get("text") or "").strip()   # 스티커 글이 질문 · 지시는 따로
        if not question and instruction:
            question = instruction   # 질문할 대상 글이 없으면 지시 글이 곧 질문
        if view == "graph" and not question:
            # 질문할 글 없음(작업 노드만 · 메모 빈 설문) — 화면이 입력창을 연다
            return {"ok": False, "need_input": True, "nick": n, "label": label(n),
                    "msg": f"설문 {own['id']} 메모 없음 — 질문 입력" if own else "질문 입력"}
        if not question:
            raise HubError(400, "질문 없음")
        req["question"] = question
        if own:
            # 답 대기 중 같은 노드 재전송 막기(스티커 409 처럼) — 답이 달린 뒤 다시 보내면 새 답 덧붙임
            wait = pending_request(root, own)
            if wait:
                raise HubError(409, f"이미 보냄({wait}) — {own['id']} 답 대기 중")
            req["target"] = {"kind": "node", "question": own["id"], "targets": own["targets"], "own": own["kind"],
                             "own_title": own["title"], "ask": question, "rev": own["rev"]}
            note = f"{'설문' if own['kind'] == 'survey' else '질문'} {own['id']} 에 답 · "
        elif view == "book" and sel.get("note"):
            # 책 스티커 — 답 자리 = 그 스티커 answer 칸(질문 노드는 안 만듦 · 책 질문으로 그래프가 차지 않게)
            if not sel.get("note") or not sel.get("notes_file"):
                raise HubError(400, "스티커 id · notes.json 없음")
            req["target"] = {"kind": "note", **{k: str(sel.get(k) or "")[:300] for k in ("note", "notes_file", "doc", "book", "ctx", "block")}}
            if sel.get("thread"):
                # 꼬리 질문 — 답 자리 = 그 꼬리의 a 칸 · 맥락(원 질문 · 원 답 · 앞 꼬리)
                req["target"].update({"thread": str(sel["thread"])[:20], "orig_q": str(sel.get("orig_q") or "")[:2000],
                                      "orig_a": str(sel.get("orig_a") or "")[:4000],
                                      "prev": [{k: str(x.get(k) or "")[:2000] for k in ("id", "q", "a")}
                                               for x in (sel.get("prev") or []) if isinstance(x, dict)][-20:]})
        elif view == "code" and sel.get("file"):
            # 열린 파일 — 상대 경로 · 실제 경로 · 답 자리
            rel = str(sel["file"])
            kind = answer_kind(rel, bool(sel.get("readonly")) or sel.get("doc_kind") in ("pdf", "sheet", "word", "image", "binary", "large"))
            absp = None
            if resolve:
                try:
                    absp = str(resolve(rel))
                except Exception:  # noqa: BLE001 — 경로 밖이면 상대 경로만
                    absp = None
            req["target"] = {"kind": kind, "file": rel, "abs": absp, "range": sel.get("range"), "text": str(sel.get("text") or "")[:4000],
                             "table": sel.get("table") if isinstance(sel.get("table"), dict) else None}
        elif instruction and view != "graph" and not (view == "git" and (sel.get("commit") or sel.get("git_file"))):
            # 지시 붙은 2ND(Alt+R) · 그래프 밖 · 대상 없음 — 노드를 만들지 않고 지시 글만(답 = 2ND 대화)
            req["target"] = {"kind": "chat"}
        else:
            # 그래프 · Git · 설문 · 앱 — 질문 노드(그래프에서 고른 노드는 대상 선 · 그 밖은 섬)
            title = question
            tg = [x["id"] for x in nodes] if view == "graph" else []
            if view == "git" and (sel.get("commit") or sel.get("git_file")):
                # 대상 표시 — 제목 앞 [커밋 · 파일]
                ref = " · ".join(x for x in (str(sel.get("commit") or "")[:10], str(sel.get("git_file") or "")) if x)
                title = f"[{ref}] {question}"
            qid, linked = add_question(ft, ws, title[:500], tg, req["graph_view"] if view == "graph" else "feature")
            req["target"] = {"kind": "node", "question": qid, "targets": linked, "commit": sel.get("commit"),
                             "git_file": sel.get("git_file"), "subject": sel.get("subject")}
            note = f"질문 {qid} 등록 · "
    # queue 글 — 요청 파일에도(기록과 같은 글)
    claude = reg.get("kind") == "claude"
    text = magic_text(n, rid, req, ft, ws, claude)
    req["message"] = text
    write_json(Path(root) / HUB / "requests" / f"{rid}.json", req)
    # queue(Claude 는 tmux)
    try:
        out = deliver(reg, text)
    except HubError as e:
        # 못 보낸 요청 — 답 대기(재전송 막기)로 치지 않게 표시
        req["failed"] = str(e)[:300]
        write_json(Path(root) / HUB / "requests" / f"{rid}.json", req)
        raise HubError(e.status, f"{note}요청 {rid} 저장 · {e}") from None
    return {"ok": True, "id": rid, "nick": n, "label": label(n), "question": (req["target"] or {}).get("question"),
            "thread": reg.get("thread"), "msg": f"{note}{label(n)} 에 {'/' if claude else '$'}{MAGIC[n]} {rid} · {str(out).split(' · ')[0]}", "out": out,
            "skipped": req.get("skipped") or [], "skip_note": req.get("skip_note") or ""}
