#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""precheck — 사전 체험 왕복 점검: 시험 재료 준비 · 자동 판정 · precheck.md 쓰기(표준 라이브러리 + 키트 도구)

  python3 precheck.py prepare [--kit 키트] [--root 루트] [--py 파이썬] [--port 8701]   run 시작 · ReadyStart.md · 시험 재료 · 시작 명령
  python3 precheck.py ping                     MAIN 에 codex queue 한 번(유저 터미널 탭에서)
  python3 precheck.py sub-worktree             검증 서브가 자기 샌드박스에서 — worktree + xdist 실측
  python3 precheck.py sub-skill '제목 줄'       서브가 insp SKILL.md 에서 읽은 첫 «## » 줄을 대조
  python3 precheck.py sub-task 노드id          구현 서브의 시험 작업(run 폴더에 표식 파일 하나)
  python3 precheck.py mark ID 결과 [--note 글]  유저 체크 · 세션이 본 결과(자동 판정이 통과면 자동이 이긴다)
  python3 precheck.py check [--final]          전체 판정 → precheck.md 갱신(--final = ReadyStart 상태 한 줄도)

- 자동 설치 · 자동 수리를 하지 않는다 · 하나 실패해도 멈추지 않고 그 항목에 기대는 것만 «선행 실패로 차단» 으로 적는다
- 증거 = 세션 기록(~/.codex/sessions) · 허브 요청 · 답 자리 파일 · HTTP. 모델의 말만으로 통과시키지 않는다
- 파일: <키트>/.codex-hub/precheck/<run>/(git 제외) · 결과 <키트>/precheck.md(run 별 절을 덧붙임 · 같은 run 은 그 절만 바꿈)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# 이 파일 폴더 · 형제 스킬 폴더(.agents/skills · skills_src · ~/.codex/skills 어디든 같은 모양)
HERE = Path(__file__).resolve().parent
SK = HERE.parent
# 결과 값
PASS, FAIL, BLOCK, UNSURE, LIMIT, SKIP, NOTRUN = "통과", "실패", "선행 실패로 차단", "미확인", "제한 내 미완료", "제외", "미실행"
RESULTS = (PASS, FAIL, BLOCK, UNSURE, LIMIT, SKIP, NOTRUN)
# 이번 점검이 기대는 스킬(실제 운영 지시가 ~/.codex/skills/… 로 부르는 것)
NEED_SKILLS = ("codex-hub", "main-magic", "2nd-magic", "survey", "insp")
# 결과 파일 이름 · run 절 표시
REPORT = "precheck.md"
MARK_A, MARK_B = "<!-- precheck-run:{} -->", "<!-- /precheck-run:{} -->"
# 시험 세션 강도 — 본선 high · medium 과 다르다(결과에 적는다)
TEST_EFFORT = "low"
# 명령 하나가 응답 없이 멈췄을 때만 끊는 상한(초) · HTTP 상한
CMD_WAIT = 180
NET_WAIT = 5
# 항목 — (ID, 이름, 치명, 선행 항목, 입력 · 기대값)
ITEMS = [
    ("R1", "ReadyStart.md 생성 · 명령 옵션", True, (), "세션 명령 2줄 · 모델 · V2 · wait · 상한 8"),
    ("P1", "스킬 경로 ~/.codex/skills", True, (), "운영 지시가 부르는 스킬 5개 경로"),
    ("P2", "압축 훅 경로(compact 미시험)", False, (), "~/.codex/hooks.json 있음"),
    ("H0", "main · 2nd 등록 충돌", True, (), "시작 때 쓰는 중인 등록 없음"),
    ("H1", "허브 스킬 연결 — MAIN", True, (), "등록 thread · 작업 폴더 · 세션 기록 일치"),
    ("H2", "허브 스킬 연결 — 2ND", True, (), "등록 thread · 작업 폴더 · 세션 기록 일치"),
    ("V1", "Codex 판 · 적용 설정", True, ("H1", "H2"), "판 · 모델 · 강도 low · V2 · 시작 인자"),
    ("Q1", "코덱스 큐 실제 수신(MAIN)", True, ("H1",), "입력에 Q1 표식 · 답에 ACK-Q1"),
    ("T1", "대화 탭 전달(MAIN)", True, ("H1", "D1"), "입력에 T1 표식 · 답에 ACK-T1"),
    ("S8", "서브 8개 생성", True, ("H1",), "서로 다른 ID 8개 · READY 표식 8개"),
    ("L8", "서브 8개 로드 유지", True, ("S8",), "list_agents 2회 · 8개 살아 있음 · 내려감 없음"),
    ("C1", "서브 간 대화(A → B)", True, ("H1",), "send 뒤 B 새 턴 없음 · followup 뒤 B 표식"),
    ("F1", "idle 서브 followup 재시작", True, ("H1",), "같은 B ID · 완료 턴 증가 · 새 표식"),
    ("C2", "메인 서브 간 대화", True, ("H1",), "MAIN → A followup · A → MAIN send · 표식 수신"),
    ("W1", "부모 긴 wait 로 서브 표식 받기", True, ("H1",), "followup 뒤 wait_agent · B 표식 수신"),
    ("K1", "서브가 실제 스킬 파일 읽기", True, ("H1",), "insp SKILL.md 첫 «## » 줄 일치"),
    ("WT", "검증 서브 worktree", True, (), "서브 샌드박스에서 add · HEAD 일치 · 시험 · remove"),
    ("XD", "xdist -n 2", False, (), "작업자 2 · 시험 2개 통과"),
    ("D1", "devview 주소 · page_port · 트리", True, (), "/api/info 의 키트 · 트리 일치 · page_port 있음"),
    ("N1", "종 알림", False, ("D1",), "/api/notify 에 run 표식"),
    ("SV1", "설문 제출 → 마법봉 전달", True, ("D1",), "result route MAIN · 2ND ok + 요청 id"),
    ("SV2", "설문 확정 → MAIN 수신", True, ("SV1", "H1"), "요청 id 수신 · ACK-SV"),
    ("SV3", "설문 질문 → 2ND 답 · 설명 폼", True, ("SV1", "H2"), "요청 id 수신 · 설명 폼 등록"),
    ("ST1", "스티커 → 2ND 답 자리", True, ("D1", "H2"), "magic_rid 수신 · 그 스티커 answer 에 ST 표식 · 질문 노드 없음"),
    ("G1", "그래프 쓰기(devview 트리)", True, (), "시험 노드 3개 읽기 재확인"),
    ("G2", "그래프 틀 frames · fill · check", True, (), "종료코드 0 · 지정 id 제목 일치"),
    ("M1", "그래프 마법봉 → MAIN 전달", True, ("G1", "H1", "D1"), "세 노드 요청 · 요청 id 수신"),
    ("M2", "작업 노드 처리", True, ("M1",), "done · 서브 표식 파일"),
    ("M3", "검증 노드 처리", True, ("M1",), "run pass"),
    ("M4", "질문 노드 처리", True, ("M1",), "answer 있음 · run 표식"),
    ("E1", "환경 점검 envcheck", False, (), "요약 줄 · 실패가 A6 · B3 · B4 뿐(체험과 같음)"),
    ("E2", "책 재료 — pandas · playwright · 크롬", False, (), "import 둘 · 헤드리스 크롬 실행"),
    ("E3", "파일 노드 file-add", False, (), "키트 AGENTS.md 파일 노드 생성"),
    ("E4", "세션끼리 글(hub send)", False, ("H1", "H2"), "2ND 입력에 @main · 표식 · ACK-E4"),
    ("E5", "책 실제 빌드(양식 · 그 기계 파이썬)", False, (), "new_book · build_book --stage 1 · html 생성"),
    ("U1", "유저 · 외부 Browser 로 devview", True, (), "화면 본문 보임"),
    ("U2", "유저 · 대화 탭에서 MAIN 에 전송", True, (), "대화 탭에 답 보임"),
    ("U3", "유저 · 시험 설문 제출", True, (), "첫 문항 확정 · 둘째 질문"),
    ("U4", "유저 · 시험 책 스티커 마법봉", True, (), "Book 탭(같은 주소 /pg/) 책 화면 · 답 보임"),
    ("U5", "유저 · 그래프 세 노드 마법봉", True, (), "Ctrl 선택 한 번(안 되면 나눠서 · 사실대로)"),
    ("U6", "유저 · 종 · 답 표식 화면 확인", False, (), "API 와 화면 구분"),
    ("U7", "유저 · CSV 표 · 파일 노드 열기", False, (), "CSV 가 표로 뜸 · 그래프 Main 파일 노드에서 ` 로 열림"),
    ("U8", "유저 · 단축키", False, (), "Alt+Q/W · Alt+E/R · Alt+` · 0~8 · Alt+Z/X/C/V 가 Browser 에 안 뺏김"),
    ("U9", "유저 · 서브 패널", False, (), "대화 탭 서브 목록 8개 · 창 끌기"),
    ("U10", "유저 · 터미널 끊김", False, (), "체험 내내 안 끊김 · 끊기면 시각"),
    ("U11", "유저 · 그래프 화면 스위치", False, (), "Main · 섹션0 ~ 8 전환 · 새로고침 뒤 유지"),
    ("U12", "유저 · Main 에 보이는 것", False, (), "작업 · 파일 · 섬 질문 · 검증 · 설문 · 섹션 질문 · 빈 틀 없음"),
    ("U13", "유저 · 섹션 틀", False, (), "빈 노드 28개 · 작업 4 세로 · 왼쪽 설문 2 · 오른쪽 검증 4"),
    ("U14", "유저 · 자유 배치", False, (), "끈 위치 유지 · 화면마다 따로"),
    ("U15", "유저 · 노드 추가 단추", False, (), "네 종류 생성 · Esc 취소"),
    ("U16", "유저 · 줌 단계", False, (), "점 → 카드 → 상세 → 펼침"),
    ("U17", "유저 · 자세히 · 함수 표", False, (), "` 로 자세히 · 행 추가 · 칸 고침 저장"),
    ("U18", "유저 · 그래프 설문 노드", False, (), "선택 · 해제 · 메모 · 보류"),
    ("U19", "유저 · 책 다른 방식으로 열기", False, (), "책 · 스티커 · 🪄 · 쪽 넘김"),
    ("U24", "유저 · 책 PORT 8801 맨 위", False, (), "최근 책이 바로 뜸 · 쪽 넘김 · 스티커 · 🪄"),
    ("U20", "유저 · 질문 노드 Alt+W", False, (), "입력창 없이 전송 · 답이 그 노드 안"),
    ("U21", "유저 · 설문 노드 Alt+Q · Alt+W", False, (), "Q = MAIN 이 답으로 받음 · W = 메모가 질문 · 답이 설문 노드 안"),
    ("U22", "유저 · 종 알림 색", False, (), "질문 노랑 · 작업 초록 · 검증 보라 · 설문 핑크 · 북키트 파랑 · 나머지 회색"),
    ("U23", "유저 · 진행 표시 색", False, (), "진행 중 노랑 회전 · 완료 초록 점멸"),
]
ITEM_IDS = [x[0] for x in ITEMS]


# 줄 하나 출력(단계마다 진행 한 줄)
def say(text):
    print(text, flush=True)


# 명령 실행 — (종료코드, 출력). 없는 명령은 127 · 무언 정지만 상한으로 끊는다(124)
def run_cmd(args, cwd=None, env=None, wait=CMD_WAIT):
    try:
        p = subprocess.run([str(a) for a in args], cwd=cwd and str(cwd), env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=wait)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"실행 파일 없음: {args[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"응답 없음: {' '.join(str(a) for a in args[:3])}"


# 끝 줄 하나(증거 칸용)
def last_line(out, n=160):
    line = next((x.strip() for x in reversed((out or "").splitlines()) if x.strip()), "")
    return line[:n]


# JSON 읽기(없거나 깨지면 기본값)
def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# JSON 쓰기 — 임시 파일 → 교체
def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# 키트 = AGENTS.md 와 docs/ 가 있는 곳
def is_kit(p):
    return (p / "AGENTS.md").is_file() and (p / "docs").is_dir()


# 키트 찾기 — --kit → 지금 폴더 → 지금 폴더/kit → 이 파일 위 → None
def find_kit(given=None):
    if given:
        return Path(given).resolve()
    cwd = Path.cwd().resolve()
    for p in (cwd, cwd / "kit", *HERE.parents):
        if is_kit(p):
            return p
    return None


# 형제 도구를 모듈로 불러오기(readystart 는 불러와도 쓰기가 없다)
def load_tool(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# flowtree_store 불러오기 — 키트 것
def load_store(kit):
    d = str(Path(kit) / "devview" / "flowtree")
    if d not in sys.path:
        sys.path.insert(0, d)
    import flowtree_store  # noqa: PLC0415 — 키트 경로를 안 뒤에만 찾을 수 있다
    return flowtree_store


# Codex 홈 — CODEX_HOME > ~/.codex
def codex_home():
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser()


# 표식 — run 하나에 고유
def tok(kind, run):
    return f"{kind}-{run}"


# ======= 세션 기록(rollout) 읽기 =======
# 줄의 글자 모으기 — content 목록의 text 칸(암호화된 칸은 건너뜀)
def join_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(str(c.get("text")) for c in content or [] if isinstance(c, dict) and c.get("text"))


# 기록 시각 → 초
def stamp(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# 세션 기록 하나 — 대화 · 도구 호출 · 턴 · 설정 · 사용량만 뽑는다
class Rollout:
    def __init__(self, path):
        self.path = Path(path)
        self.id = self.parent = self.agent_path = self.version = self.cwd = None
        self.events = []
        self.settings = {}
        self.usage = {}
        self.load()

    # 파일 읽기 — 깨진 줄은 건너뜀(쓰는 중인 끝 줄)
    def load(self):
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict) and isinstance(o.get("payload"), dict):
                self.feed(o, o["payload"], stamp(o.get("timestamp")))

    # 줄 하나 반영
    def feed(self, o, p, t):
        kind, sub = o.get("type"), p.get("type")
        if kind == "session_meta":
            spawn = ((p.get("source") or {}).get("subagent") or {}).get("thread_spawn") or {} if isinstance(p.get("source"), dict) else {}
            self.id, self.cwd, self.version = p.get("id"), p.get("cwd"), p.get("cli_version")
            self.parent = p.get("parent_thread_id") or spawn.get("parent_thread_id")
            self.agent_path = spawn.get("agent_path")
        elif kind == "turn_context":
            self.settings.update({k: p[k] for k in ("model", "effort", "multi_agent_version", "approval_policy") if p.get(k) is not None})
        elif kind == "event_msg" and sub == "thread_settings_applied":
            ts = p.get("thread_settings") or {}
            self.settings.update({k: ts[k] for k in ("model", "service_tier") if ts.get(k) is not None})
            if ts.get("reasoning_effort"):
                self.settings["effort"] = ts["reasoning_effort"]
        elif kind == "event_msg" and sub == "task_started":
            self.add("turn", t)
        elif kind == "event_msg" and sub in ("task_complete", "turn_aborted"):
            self.add("say", t, text=p.get("last_agent_message") or "")
        elif kind == "event_msg" and sub == "item_completed" and (p.get("item") or {}).get("type") == "UserMessage":
            self.add("user", t, text=join_text(p["item"].get("content")))
        elif kind == "event_msg" and sub == "token_count":
            self.usage = ((p.get("info") or {}).get("total_token_usage")) or self.usage
        elif kind == "response_item" and sub == "message" and p.get("role") in ("user", "assistant"):
            self.add("user" if p["role"] == "user" else "say", t, text=join_text(p.get("content")))
        elif kind == "response_item" and sub == "function_call":
            try:
                args = json.loads(p.get("arguments") or "{}")
            except ValueError:
                args = {}
            self.add("call", t, name=p.get("name"), args=args if isinstance(args, dict) else {}, id=p.get("call_id"))
        elif kind == "response_item" and sub == "function_call_output":
            self.add("out", t, text=str(p.get("output") or ""), id=p.get("call_id"))
        elif kind == "response_item" and sub == "agent_message":
            self.add("agent", t, text=join_text(p.get("content")), author=p.get("author"), recipient=p.get("recipient"))

    # 사건 추가
    def add(self, k, t, **kw):
        self.events.append({"k": k, "t": t, **kw})

    # 종류 고르기 · 글자에 표식이 있는 사건
    def of(self, *kinds):
        return [e for e in self.events if e["k"] in kinds]

    def has(self, marker, *kinds):
        return [e for e in self.of(*kinds) if marker in str(e.get("text") or "")]

    # 입력에 표식이 왔나 · 답에 표식이 나왔나
    def got(self, marker):
        return bool(self.has(marker, "user"))

    def said(self, marker):
        return bool(self.has(marker, "say"))

    # 도구 호출(이름 일부로) · 대상이 맞는 것만
    def calls(self, word, targets=None):
        return [e for e in self.of("call") if word in str(e.get("name")) and (targets is None or str(e["args"].get("target")) in targets)]


# 세션 기록 파일 — thread 끝 이름으로
def find_rollout(thread):
    base = codex_home() / "sessions"
    if not thread or not base.is_dir():
        return None
    hits = sorted(base.rglob(f"rollout-*{thread}.jsonl"))
    return Rollout(hits[-1]) if hits else None


# 이 부모의 서브 기록 — 시작 뒤 바뀐 파일의 첫 줄만 먼저 본다
def find_children(parent, since):
    base = codex_home() / "sessions"
    out = []
    if not parent or not base.is_dir():
        return out
    for p in base.rglob("rollout-*.jsonl"):
        try:
            if p.stat().st_mtime < since - 60:
                continue
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                head = f.readline()
        except OSError:
            continue
        if parent in head and f"{parent}.jsonl" not in p.name:
            r = Rollout(p)
            if r.parent == parent:
                out.append(r)
    return out


# ======= run 폴더 · 상태 =======
# run 하나의 폴더 · 상태 · 판정 재료
class Run:
    def __init__(self, kit, run):
        self.kit, self.run = Path(kit), run
        self.dir = self.kit / ".codex-hub" / "precheck" / run
        self.ev = self.dir / "evidence"
        self.st = read_json(self.dir / "state.json", {}) or {}
        self._sessions = None

    # 상태 저장
    def save(self):
        write_json(self.dir / "state.json", self.st)

    # 도우미가 남긴 증거 · 유저 체크
    def evidence(self, name):
        return read_json(self.ev / f"{name}.json")

    def put_evidence(self, name, data):
        write_json(self.ev / f"{name}.json", {**data, "at": time.strftime("%Y-%m-%d %H:%M:%S")})

    # 허브 등록
    def reg(self, nick):
        return read_json(self.kit / ".codex-hub" / "sessions" / f"{nick}.json")

    # 이 run 뒤 등록만(앞선 세션의 등록은 시험 세션이 아니다)
    def live_reg(self, nick):
        reg = self.reg(nick)
        return reg if reg and str(reg.get("registered_at") or "") >= self.st.get("started", "") else None

    # MAIN · 2ND · 서브 기록(한 번만 읽음)
    def sessions(self):
        if self._sessions is None:
            main, second = (self.live_reg(n) or {} for n in ("main", "2nd"))
            m = find_rollout(main.get("thread"))
            kids = find_children(main.get("thread"), self.st.get("started_ts", 0))
            subs = {}
            for k in kids:
                n = re.search(r"/c([1-8])$", str(k.agent_path or ""))
                hit = int(n.group(1)) if n else next((i for i in range(1, 9) if k.said(tok(f"READY-c{i}", self.run))), None)
                if hit:
                    subs[hit] = k
            self._sessions = {"main": m, "2nd": find_rollout(second.get("thread")), "kids": kids, "subs": subs}
        return self._sessions


# 지금 run 찾기
def current_run(kit, given=None):
    run = given
    if not run:
        try:
            run = (Path(kit) / ".codex-hub" / "precheck" / "current.txt").read_text(encoding="utf-8").strip()
        except OSError:
            run = ""
    return Run(kit, run) if run and (Path(kit) / ".codex-hub" / "precheck" / run / "state.json").is_file() else None


# ======= prepare =======
# 한 단계 실행 — 실패해도 이어 간다 · 결과를 상태에 남긴다
def step(R, name, fn):
    try:
        msg = fn()
        R.st["seed"][name] = {"ok": True, "msg": str(msg or "")}
        say(f"  🟢 {name} — {msg}")
    except Exception as e:  # noqa: BLE001 — 재료 하나가 실패해도 나머지는 준비한다
        R.st["seed"][name] = {"ok": False, "msg": f"{type(e).__name__}: {e}"[:300]}
        say(f"  🔴 {name} — {R.st['seed'][name]['msg']}")


# ReadyStart.md — 없으면 정본 함수로 쓴다 · 있으면(준비 상태 줄이 있을 수 있어) 그대로 둔다
def seed_ready(R, rs):
    path = R.kit / rs.NAME
    if path.is_file():
        return f"이미 있음 · 그대로 둠: {path}"
    rc, out = run_cmd([sys.executable, SK / "ready-start" / "readystart.py", "write", "--kit", R.kit, "--root", R.st["root"]])
    if rc != 0:
        raise RuntimeError(last_line(out))
    return str(path)


# 시험 세션 시작 명령 — ReadyStart 와 같은 옵션 · 강도 low · 시작 메시지만 precheck 대기 지시
def seed_start(R, rs):
    lines = []
    for role, section in (("MAIN", "MAIN"), ("2ND", "2ND")):
        msg = f"{HERE / 'SKILL.md'} 를 읽고 «{section}» 절대로 한다 · run {R.run} · 도구 {HERE / 'precheck.py'}"
        lines += [f"# {role}", rs.remote_line(R.kit, TEST_EFFORT, msg), ""]
    path = R.dir / "start.sh.txt"
    path.write_text("\n".join(["# 앱 서버(devview 보다 먼저 · 대회와 같음)", rs.server_line(Path(R.st["root"])), "", *lines]), encoding="utf-8")
    R.st["start_lines"] = [x for x in lines if x.startswith("codex ")]
    return str(path)


# 시험 설문 — 질문 파일은 run 폴더에 · 등록은 키트 docs/surveys/precheck
def seed_survey(R):
    run = R.run
    spec = {"title": f"[precheck {run}] 시험 설문 — 결정 문서 반영 · 커밋 금지", "questions": [
        {"id": "PC #1", "question": f"[시험 {run}] 첫 문항 — 선택지를 고른다", "context": "확정 문항이 MAIN 으로 가는지 본다.",
         "options": [{"label": "(추천) 확정 A", "detail": "시험용"}, {"label": "확정 B", "detail": "시험용"}]},
        {"id": "PC #2", "question": f"[시험 {run}] 둘째 문항 — «질문» 단추를 누르고 메모에 아무 글자", "context": "질문 문항이 2ND 로 가는지 본다.",
         "options": [{"label": "(추천) 쓰지 않음", "detail": "«질문» 단추를 쓴다"}, {"label": "쓰지 않음 2", "detail": "«질문» 단추를 쓴다"}]}]}
    qf = R.dir / "survey_questions.json"
    write_json(qf, spec)
    rc, out = run_cmd([sys.executable, SK / "survey" / "survey.py", "--dir", R.kit / "docs" / "surveys", "new", qf, "--project", "precheck"])
    if rc != 0:
        raise RuntimeError(last_line(out))
    res = json.loads(out.strip().splitlines()[-1])
    R.st["survey"] = {"id": res["id"], "project": res["project"], "file": res["file"]}
    return f"설문 {res['id']} · {res['file']}"


# 시험 노드 셋 — devview 가 읽는 트리에 · 제목에 run 표시
def seed_nodes(R):
    store = load_store(R.kit)
    tp, tag = Path(R.st["tree"]), f"[precheck {R.run}]"
    tp.parent.mkdir(parents=True, exist_ok=True)
    task = store.apply(tp, "main", "add", parent="-", title=f"{tag} 시험 작업", summary="시험 노드 · 지워도 됨", graph="hand_off", section="1")["id"]
    ver = store.apply(tp, "main", "verify-add", target=task, what=f"{tag} 시험 검증")["id"]
    ask = store.apply(tp, "user", "ask", text=f"{tag} 시험 질문 — run 표식을 답한다", target=task, view="adr")["id"]
    R.st["nodes"] = {"task": task, "verify": ver, "question": ask}
    # 유저 눈 확인용 설문 노드(U18 · 마법봉 대상 아님)
    R.st["survey_node"] = store.apply(tp, "main", "survey-add", target=task, question=f"{tag} 시험 설문 — 고르고 해제해 본다", section="1", why="시험 추천 이유",
                                      detail="그래프 설문 노드가 눌리는지 본다.", recommend=0, options=["(추천) 시험 가", "시험 나"])["id"]
    return f"작업 {task} · 검증 {ver} · 질문 {ask} · 설문 {R.st['survey_node']} · {tp}"


# 그래프 틀 시험 — run 폴더의 사본 트리로(운영 틀을 쓰지 않는다)
def seed_frames(R):
    tp = R.dir / "tree" / "tree.json"
    tp.parent.mkdir(parents=True, exist_ok=True)
    ft = R.kit / "devview" / "flowtree" / "flowtree.py"
    base = [sys.executable, ft]
    tail = ["--tree", tp, "--root", R.kit, "--role", "main"]
    rc, out = run_cmd([*base, "frames", *tail])
    ids = out.split()
    first = next((x for x in ids if re.fullmatch(r"s\d+-t\d+", x)), None)
    res = {"frames_rc": rc, "frames": len(ids), "id": first}
    if first:
        res["fill_rc"], fo = run_cmd([*base, "fill", first, "--title", tok("G2", R.run), *tail])
        res["check_rc"], co = run_cmd([*base, "check", *tail])
        res["out"] = last_line(fo + "\n" + co)
    R.st["g2"] = {**res, "tree": str(tp)}
    return f"틀 {len(ids)}개 · fill {first} · 트리 {tp}"


# 시험 책 — 예시 책 html 사본 + 미리 붙인 스티커 하나(git 제외 폴더 bookkit/books/)
def seed_book(R):
    src = R.kit / "bookkit" / "book_example" / "task09" / "task09_kit.html"
    # 이름 앞에 «_» 를 붙이지 않는다 — Book 탭 목록이 «_» 책을 뺀다(11-05 체험에서 시험 책이 목록에 없었다)
    book = R.kit / "bookkit" / "books" / f"precheck_{R.run}"
    (book / "dist").mkdir(parents=True, exist_ok=True)
    html = src.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'id="bkmeta">\{"doc":\s*"([^"]+)"', html)
    b = re.search(r'data-id="([^"]+)"', html)
    if not m or not b:
        raise RuntimeError("예시 책에서 문서 이름 · 블록 id 못 찾음")
    # 예시 책은 마법봉 전 판 런타임이라 사본의 css · js 만 지금 엔진 것으로 바꾼다(엔진 build 와 같은 자리)
    assets = R.kit / "bookkit" / "engine" / "book" / "assets"
    s0 = html.index("<style>") + len("<style>")
    s1 = html.index("</style>", s0)
    j0 = html.index("<script>", m.end()) + len("<script>")
    j1 = html.rindex("</script>")
    html = (html[:s0] + (assets / "book.css").read_text(encoding="utf-8") + html[s1:j0]
            + (assets / "book.js").read_text(encoding="utf-8") + html[j1:])
    (book / "dist" / src.name).write_text(html, encoding="utf-8")
    nid = secrets.token_hex(4)
    note = {"id": nid, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "doc": m.group(1), "slide": 1, "x": 0.1, "y": 0.02, "w": 0.3, "h": 0.1,
            "ctx": f"precheck | b={b.group(1)}", "text": f"[precheck {R.run}] 시험 스티커 — 이 run 표식을 답한다"}
    write_json(book / "notes.json", [note])
    R.st["note"] = {"id": nid, "book": str(book), "file": str(book / "notes.json"), "rel": f"bookkit/books/{book.name}/dist/{src.name}#note={nid}"}
    return f"스티커 {nid} · {book}"


# 종 알림 한 줄
def seed_notify(R):
    rc, out = run_cmd([sys.executable, R.kit / "devview" / "notify.py", "--kit", R.kit, "add", "--kind", "info", "--title", tok("N1", R.run)])
    if rc != 0:
        raise RuntimeError(last_line(out))
    return tok("N1", R.run)


# 시작 전 main · 2nd 등록 — 덮어쓰면 안 되는 세션이 있나 보려고 남긴다
def seed_conflict(R):
    found = {}
    for nick in ("main", "2nd"):
        reg = R.reg(nick)
        if reg:
            found[nick] = {"thread": reg.get("thread"), "registered_at": reg.get("registered_at")}
    R.st["conflict"] = found
    return f"🟠 등록 있음 {', '.join(found)} — 쓰는 세션이면 멈추고 유저가 정한다" if found else "등록 없음"


# 기대 파이썬 — 키트 .venv → 지금 파이썬
def pick_py(kit, given):
    if given:
        return given
    for p in (kit / ".venv" / "bin" / "python", kit / ".venv" / "Scripts" / "python.exe"):
        if p.is_file():
            return str(p)
    return sys.executable


# devview 작업 폴더 예상 — dv 와 같은 규칙(부모가 과제 루트면 부모)
def guess_page_prefix(kit):
    up = kit.parent
    return f"{kit.name}/" if (up / "README.md").is_file() or (up / ".git").exists() or (up / "uploads").is_dir() else ""


# prepare — run 시작
def cmd_prepare(a):
    kit = find_kit(a.kit)
    if kit is None or not is_kit(kit):
        print("키트 못 찾음 — --kit <키트 폴더>", file=sys.stderr)
        return 2
    rs = load_tool(SK / "ready-start" / "readystart.py", "readystart_for_precheck")
    _, root = rs.locate(str(kit), a.root)
    run = f"pc{time.strftime('%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    R = Run(kit, run)
    R.dir.mkdir(parents=True, exist_ok=True)
    R.st = {"run": run, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "started_ts": time.time(), "kit": str(kit), "root": str(root),
            "py": pick_py(kit, a.py), "port": a.port, "tree": str(kit / "docs" / "flowtree" / "tree.json"), "seed": {},
            "tz": time.strftime("%Z")}
    say(f"precheck run {run} · 키트 {kit} · 루트 {root}")
    step(R, "등록 충돌", lambda: seed_conflict(R))
    step(R, "ReadyStart", lambda: seed_ready(R, rs))
    step(R, "시작 명령", lambda: seed_start(R, rs))
    step(R, "시험 설문", lambda: seed_survey(R))
    step(R, "시험 노드", lambda: seed_nodes(R))
    step(R, "그래프 틀", lambda: seed_frames(R))
    step(R, "시험 책", lambda: seed_book(R))
    step(R, "종 알림", lambda: seed_notify(R))
    R.save()
    (kit / ".codex-hub" / "precheck" / "current.txt").write_text(run + "\n", encoding="utf-8")
    write_report(R, judge_all(R))
    note = R.st.get("note") or {}
    say("")
    say(f"0) devview: bash {kit / 'devview' / 'dv'}")
    say(f"1) 2) 세션 시작 명령(줄마다 새 탭): {R.dir / 'start.sh.txt'}")
    say(f"대화 탭에서 MAIN 에 보낼 글: [precheck {run}] {tok('T1', run)} 받았으면 {tok('ACK-T1', run)} 한 줄만 답해 줘")
    say(f"시험 책 주소(devview 같은 주소 · Book 탭 — 2026-11-05 다른 포트는 대회 브라우저에서 막힘): /pg/{guess_page_prefix(kit)}{note.get('rel', '-')}")
    say(f"결과: {kit / REPORT}")
    return 0


# ping — MAIN 에 queue 한 번
def cmd_ping(R, a):
    reg = R.live_reg("main")
    if not reg or not reg.get("thread"):
        print("MAIN 등록 없음 — 시험 세션이 먼저 허브에 붙어야 함", file=sys.stderr)
        R.put_evidence("q1", {"rc": None, "out": "MAIN 등록 없음"})
        return 1
    run = R.run
    msg = f"[precheck {run}] {tok('Q1', run)} 받았으면 {tok('ACK-Q1', run)} 한 줄만 답해 줘"
    rc, out = run_cmd(["codex", "queue", "--thread", reg["thread"], f"--message={msg}"], wait=60)
    R.put_evidence("q1", {"rc": rc, "out": last_line(out)})
    say(f"queue 종료코드 {rc} · {last_line(out)} — 접수일 뿐이다 · 판정은 check 가 세션 기록으로")
    return 0 if rc == 0 else 1


# ======= 서브가 부르는 도우미 =======
# 시험 파일 — 작업자 수 · 작업자 이름을 파일로 남긴다
XD_TEST = '''import os
from pathlib import Path


def rec(name):
    Path(os.environ["PRECHECK_XD_DIR"], name).write_text(os.environ.get("PYTEST_XDIST_WORKER", "none"), encoding="utf-8")
    assert os.environ.get("PYTEST_XDIST_WORKER_COUNT") == "2"


def test_a():
    rec("a")


def test_b():
    rec("b")
'''


# worktree + xdist — 부른 서브의 샌드박스에서 돈다 · 하나 실패해도 다음 칸은 본다
def cmd_sub_worktree(R, a):
    root, py = R.st["root"], R.st["py"]
    wt = R.dir / "worktree"
    rc, head = run_cmd(["git", "-C", root, "rev-parse", "HEAD"])
    seed = None
    if rc != 0:
        # 체험은 ready-start 를 안 돌려 커밋이 없다 — 시험용 빈 커밋(이것도 서브 샌드박스의 .git 쓰기 시험이다)
        seed, sout = run_cmd(["git", "-C", root, "-c", "user.name=precheck", "-c", "user.email=precheck@local", "commit", "--allow-empty", "-q", "-m", f"precheck {R.run} 시험 커밋"])
        say(f"시험 빈 커밋 종료코드 {seed} · {last_line(sout)}")
        rc, head = run_cmd(["git", "-C", root, "rev-parse", "HEAD"])
    head = head.strip() if rc == 0 else ""
    res = {"head": head, "path": str(wt), "py": py, "cwd": os.getcwd(), "thread": os.environ.get("CODEX_THREAD_ID", ""), "seed_commit": seed}
    if not head:
        res.update(add_rc=rc, out="HEAD 없음 — 커밋이 있는 저장소가 아님")
    else:
        res["add_rc"], out = run_cmd(["git", "-C", root, "worktree", "add", "--detach", wt, head])
        res["out"] = last_line(out)
        if res["add_rc"] == 0:
            rc2, h2 = run_cmd(["git", "-C", wt, "rev-parse", "HEAD"])
            res["head_ok"] = rc2 == 0 and h2.strip() == head
            res["separate"] = wt.resolve() != Path(root).resolve()
            res["py_rc"], _ = run_cmd([py, "-c", "import sys"], cwd=wt)
    R.put_evidence("worktree", res)
    say(f"worktree add 종료코드 {res['add_rc']} · {res.get('out', '')}")
    # xdist — 설치하지 않는다 · 없으면 그 사실만 남긴다
    xd = R.dir / "xdist"
    xd.mkdir(exist_ok=True)
    (xd / "test_precheck_xd.py").write_text(XD_TEST, encoding="utf-8")
    env = {**os.environ, "PRECHECK_XD_DIR": str(xd)}
    rc, out = run_cmd([py, "-m", "pytest", xd / "test_precheck_xd.py", "-q", "-n", "2", "-p", "no:cacheprovider"],
                      cwd=wt if wt.is_dir() else xd, env=env)
    workers = sorted({(xd / n).read_text(encoding="utf-8") for n in ("a", "b") if (xd / n).is_file()})
    R.put_evidence("xdist", {"rc": rc, "workers": workers, "out": last_line(out), "py": py})
    say(f"xdist 종료코드 {rc} · 작업자 {workers} · {last_line(out)}")
    # 깨끗한 시험 worktree 만 정확한 경로로 지운다(강제 없음)
    if wt.is_dir():
        rc, out = run_cmd(["git", "-C", root, "worktree", "remove", wt])
        R.put_evidence("worktree", {**res, "remove_rc": rc, "remove_out": last_line(out)})
        say(f"worktree remove 종료코드 {rc}")
    return 0


# 스킬 파일 — 설치 경로 먼저
def insp_skill():
    for p in (codex_home() / "skills" / "insp" / "SKILL.md", SK / "insp" / "SKILL.md"):
        if p.is_file():
            return p
    return None


# 서브가 읽어 온 줄 대조 — 부모 지시문에 답을 넣지 않으려고 스크립트가 맞춘다
def cmd_sub_skill(R, a):
    p = insp_skill()
    want = next((x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.startswith("## ")), None) if p else None
    ok = bool(want) and a.line.strip() == want
    R.put_evidence("skill", {"ok": ok, "path": str(p) if p else "", "got": a.line.strip()[:120], "thread": os.environ.get("CODEX_THREAD_ID", "")})
    say("일치" if ok else "불일치")
    return 0 if ok else 1


# 환경 점검 — 샌드박스 밖에서 돌려야 소켓 칸이 맞다 · 설치하지 않는다
def cmd_sub_env(R, a):
    tool = R.kit / "scripts" / "envcheck" / "envcheck.py"
    if not tool.is_file():
        R.put_evidence("env", {"rc": None, "summary": "", "out": f"없음: {tool}"})
        say("envcheck 없음")
        return 1
    rc, out = run_cmd([R.st["py"], tool, "--no-install"], cwd=R.kit)
    lines = out.strip().splitlines()
    R.put_evidence("env", {"rc": rc, "summary": next((x for x in reversed(lines) if x.startswith("요약:")), ""), "out": "\n".join(lines[-40:])})
    say(last_line(out))
    return 0


# 책 재료 — 라이브러리 · 헤드리스 크롬 · 설치하지 않는다
def cmd_sub_book(R, a):
    py = R.st["py"]
    res_ = {}
    for name in ("pandas", "playwright"):
        rc, out = run_cmd([py, "-c", f"import {name}; print(getattr({name}, '__version__', 'ok'))"], cwd=R.kit)
        res_[name] = {"rc": rc, "out": last_line(out)}
    rc, out = run_cmd([py, "-c", "from playwright.sync_api import sync_playwright as s\nwith s() as p:\n    p.chromium.launch(headless=True).close()\nprint('ok')"], cwd=R.kit)
    res_["chrome"] = {"rc": rc, "out": last_line(out)}
    R.put_evidence("book", res_)
    say(" · ".join(f"{k} {v['rc']}" for k, v in res_.items()))
    # 양식 그대로 실제 빌드 — 대회 파이썬 · pandas 판에서 도는지 · 브라우저 없음 건너뛰기 · Book 목록에 뜨는 책
    name = f"precheckb_{R.run}"
    book = R.kit / "bookkit" / "books" / name
    rc1, o1 = run_cmd([py, R.kit / "bookkit" / "new_book.py", name, "--task", R.st["root"]], cwd=R.kit)
    rc2, o2 = run_cmd([py, R.kit / "bookkit" / "engine" / "build_book.py", book, "--stage", "1"], cwd=R.kit) if rc1 == 0 else (None, "")
    html = sorted(str(x) for x in (book / "dist").glob("*.html")) if (book / "dist").is_dir() else []
    R.put_evidence("bookbuild", {"new_rc": rc1, "build_rc": rc2, "out": last_line(o2 or o1), "html": html, "book": str(book)})
    say(f"책 빌드 new {rc1} · build {rc2} · html {len(html)}")
    return 0


# 파일 노드 — 키트 AGENTS.md 하나로 file-add 를 실제 그래프에 돌린다
def cmd_sub_file(R, a):
    rc, out = run_cmd([R.st["py"], R.kit / "devview" / "flowtree" / "flowtree.py", "--role", "main", "--tree", R.st["tree"], "--root", R.kit, "file-add", "AGENTS.md"], cwd=R.kit)
    tree = read_json(Path(R.st["tree"]), {}) or {}
    node = next((n["id"] for n in tree.get("nodes", []) if n.get("kind") == "file" and n.get("path") == "AGENTS.md"), "")
    R.put_evidence("filenode", {"rc": rc, "out": last_line(out), "node": node})
    say(f"file-add 종료코드 {rc} · {last_line(out)}")
    return 0


# 구현 서브의 시험 작업 — run 폴더에 표식 파일 하나
def cmd_sub_task(R, a):
    R.put_evidence(f"task_{a.node}", {"node": a.node, "marker": tok("M2", R.run), "thread": os.environ.get("CODEX_THREAD_ID", "")})
    say(tok("M2", R.run))
    return 0


# mark — 유저 체크 · 세션이 본 결과
def cmd_mark(R, a):
    if a.id not in ITEM_IDS:
        print(f"모르는 항목 {a.id} — {' · '.join(ITEM_IDS)}", file=sys.stderr)
        return 2
    if a.result not in RESULTS:
        print(f"결과는 {' / '.join(RESULTS)} 중 하나", file=sys.stderr)
        return 2
    R.put_evidence(f"mark_{a.id}", {"result": a.result, "note": a.note or ""})
    say(f"{a.id} {a.result}")
    return 0


# ======= 판정 =======
# 결과 하나
def res(result, actual="", proof="", nxt=""):
    return {"result": result, "actual": actual, "proof": proof, "next": nxt}


# HTTP GET → json · 실패 None
def get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=NET_WAIT) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None


# ReadyStart 명령 줄 검사
def j_r1(R):
    rs = load_tool(SK / "ready-start" / "readystart.py", "readystart_for_precheck")
    path = R.kit / rs.NAME
    if not path.is_file():
        return res(FAIL, "파일 없음", str(path), R.st.get("seed", {}).get("ReadyStart", {}).get("msg", ""))
    lines = [x for x in path.read_text(encoding="utf-8").splitlines() if x.startswith("codex -C")]
    need = [f"-m {rs.MODEL}", "--add-dir", "--approve-for-me", *rs.EXTRA]
    miss = [n for ln in lines for n in need if n not in ln]
    # 앱 서버 세션 줄 — 서브 상한은 서버 줄(0번)에 있어야 먹는다
    body = path.read_text(encoding="utf-8")
    remote = [x for x in body.splitlines() if x.startswith("codex --remote")]
    miss += [n for ln in remote for n in ("--approve-for-me", *rs.EXTRA) if n not in ln]
    if len(remote) != len(rs.ROLES) or "agents.max_concurrent_threads_per_session=8" not in next((x for x in body.splitlines() if "app-server" in x), ""):
        miss.append("앱 서버 줄 · --remote 줄")
    if len(lines) != len(rs.ROLES) or miss or str(R.kit) not in "".join(x.replace("'", "") for x in lines):
        return res(FAIL, f"명령 {len(lines)}줄 · 빠짐 {miss[:3]}", str(path), "readystart.py write 다시")
    return res(PASS, f"명령 {len(lines)}줄 · 옵션 일치 · 시험 세션은 강도 {TEST_EFFORT} · 시작 메시지만 다름", str(path))


# 스킬 경로
def j_p1(R):
    base = codex_home() / "skills"
    miss = [n for n in NEED_SKILLS if not (base / n / "SKILL.md").is_file()]
    if not base.is_dir() or miss:
        return res(FAIL, f"없음: {' · '.join(miss)}", str(base), "$스킬 · 운영 지시의 ~/.codex/skills/… 가 실패한다 — install.sh 또는 ready-start 로 준비(자동 설치 안 함)")
    return res(PASS, f"스킬 {len(NEED_SKILLS)}개 있음", str(base))


# 훅 경로 — 압축 실작동은 시험하지 않는다
def j_p2(R):
    p = codex_home() / "hooks.json"
    return res(PASS, "경로 있음 · compact 미시험", str(p)) if p.is_file() else res(UNSURE, "없음 · ready-start 안 돌렸으면 정상", str(p), "대회 때 ready-start 가 설치")


# 시작 때 등록 충돌
def j_h0(R):
    found = R.st.get("conflict")
    if found is None:
        return res(NOTRUN)
    if found:
        return res(UNSURE, f"시작 때 등록 있음: {json.dumps(found, ensure_ascii=False)[:160]}", "", "쓰던 세션이면 유저가 정한다 · 지난 시험의 남은 등록이면 무시")
    return res(PASS, "등록 없음")


# 허브 등록 — nick: main · 2nd
def j_hub(R, nick):
    reg = R.live_reg(nick)
    if not reg:
        return res(NOTRUN, "이번 run 뒤 등록 없음", "", f"그 세션에서 hub.py register --nick {nick}")
    roll = R.sessions()["main" if nick == "main" else "2nd"]
    same = Path(str(reg.get("cwd") or "")).resolve() == R.kit.resolve()
    actual = f"thread {str(reg.get('thread'))[:13]} · cwd {'일치' if same else reg.get('cwd')} · 세션 기록 {'있음' if roll else '없음'}"
    if reg.get("thread") and same and roll:
        return res(PASS, actual, str(roll.path))
    if reg.get("thread") and same:
        return res(UNSURE, actual, "", "세션 기록 경로 확인(CODEX_HOME)")
    return res(FAIL, actual, str(R.kit / ".codex-hub" / "sessions" / f"{nick}.json"), "ReadyStart 옵션(-C 키트)으로 띄웠나 확인")


# 프로세스 시작 인자(리눅스) — codex 이고 키트가 들어간 것
def proc_cmds(kit):
    out = []
    for p in Path("/proc").glob("[0-9]*/cmdline") if Path("/proc").is_dir() else []:
        try:
            s = p.read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "codex" in s and str(kit) in s and "precheck.py" not in s.split(" -c ")[0]:
            out.append(s)
    return out


# 판 · 설정
def j_v1(R):
    rs = load_tool(SK / "ready-start" / "readystart.py", "readystart_for_precheck")
    s = R.sessions()
    rc, ver = run_cmd(["codex", "--version"], wait=20)
    got = {k: (s[k].settings if s[k] else {}) for k in ("main", "2nd")}
    if not s["main"] and not s["2nd"]:
        return res(NOTRUN, f"판 {last_line(ver) if rc == 0 else '확인 불가'} · 세션 기록 없음")
    R.st["seen_settings"] = {"version": last_line(ver) if rc == 0 else "", **got, "main_cli": s["main"].version if s["main"] else "",
                             "cmds": len(proc_cmds(R.kit))}
    bad = [f"{k} {x}={v.get(x)}" for k, v in got.items() for x, want in (("model", rs.MODEL), ("effort", TEST_EFFORT)) if v and v.get(x) != want]
    cmds = proc_cmds(R.kit)
    miss = [e for e in rs.EXTRA if not any(e in c for c in cmds)] if cmds else None
    actual = f"판 {last_line(ver) if rc == 0 else '?'} · main {got['main']} · 2nd {got['2nd']}"[:300]
    if bad or miss:
        return res(FAIL, actual + f" · 다름 {bad} · 인자 빠짐 {miss}"[:200], "", "ReadyStart 와 시작 명령 대조")
    if miss is None:
        return res(UNSURE, actual + " · 시작 인자 못 읽음(/proc)", "", "V2 · wait · 상한은 시작 명령 값만 확인됨")
    return res(PASS, actual + " · 시작 인자 일치", str(s["main"].path if s["main"] else ""))


# 입력 · 답 표식 판정 — key: Q1 · T1
def j_echo(R, key, extra=""):
    m = R.sessions()["main"]
    mark, ack = tok(key, R.run), tok(f"ACK-{key}", R.run)
    if not m or not m.got(mark):
        return res(NOTRUN, extra + "입력에 표식 없음")
    if not m.said(ack):
        return res(FAIL, extra + "입력은 왔는데 답에 ACK 없음", str(m.path), "MAIN 턴 상태 확인")
    return res(PASS, extra + "입력 · 답 표식 일치", str(m.path))


# queue — 종료코드 + 실제 수신
def j_q1(R):
    e = R.evidence("q1") or {}
    r = j_echo(R, "Q1", f"queue 종료코드 {e.get('rc')} · ")
    if r["result"] == NOTRUN and e.get("rc") not in (None, 0):
        return res(FAIL, r["actual"] + f" · {e.get('out')}", "", "codex 데몬 · thread 확인")
    if r["result"] == NOTRUN and e.get("rc") == 0:
        return res(UNSURE, r["actual"] + " · 접수만 확인", "", "MAIN 이 턴 중이면 끝난 뒤 들어간다 — check 다시")
    return r


# 서브 8개
def j_s8(R):
    s = R.sessions()
    kids = {k.id for k in s["kids"]}
    ready = [n for n, k in s["subs"].items() if k.said(tok(f"READY-c{n}", R.run))]
    actual = f"ID {len(kids)}개 · READY {len(ready)}개({' '.join(f'c{n}' for n in sorted(ready))})"
    if len(kids) >= 8 and len(ready) == 8:
        return res(PASS, actual, str(s["main"].path))
    return res(FAIL if kids else NOTRUN, actual, "", "MAIN 의 spawn 오류 원문을 mark S8 로 남긴다" if kids else "")


# 로드 유지 — list_agents 출력만 본다(READY 로 대체하지 않음) · 출력 모양을 못 읽으면 미확인
def j_l8(R):
    s = R.sessions()
    m = s["main"]
    if not m:
        return res(NOTRUN)
    ids = [e.get("id") for e in m.calls("list_agents")]
    outs = [e["text"] for e in m.of("out") if e.get("id") in ids]
    if len(outs) < 2:
        return res(UNSURE, f"list_agents 출력 {len(outs)}회(2회 필요) · 상태 수집 불가면 미확인", "", "READY 8줄로 대체하지 않는다")
    down = [o for o in outs if re.search(r"notLoaded|not_loaded|unloaded", o)]
    paths = [len({n for n in range(1, 9) if re.search(rf"/c{n}\b", o)}) for o in outs]
    actual = f"관측 {len(outs)}회 · 경로 수 {paths} · 내려감 {len(down)}회"
    if down:
        return res(FAIL, actual, str(m.path), "상한 설정 확인")
    return res(PASS, actual, str(m.path)) if min(paths[-2:]) >= 8 else res(UNSURE, actual + " · 출력 모양 다름", str(m.path), "출력을 사람이 확인")


# 사건 시각 뒤에 턴 시작이 있나
def turns_between(r, a, b):
    return [e for e in r.of("turn") if a < e["t"] <= b]


# 서브 대상 이름(경로 · ID)
def names(k):
    return {str(k.id), str(k.agent_path), str(k.agent_path).rsplit("/", 1)[-1]}


# 서브 간 대화 재료 — (A, B, A 의 send, A 의 followup)
def peer(R):
    subs = R.sessions()["subs"]
    A, B = subs.get(1), subs.get(2)
    if not A or not B:
        return A, B, None, None
    sends = A.calls("send_message", names(B))
    send = sends[0] if sends else None
    fol = [e for e in A.calls("followup_task", names(B)) if send and e["t"] >= send["t"]]
    return A, B, send, fol[0] if fol else None


# A → B
def j_c1(R):
    A, B, send, fol = peer(R)
    if not A or not B:
        return res(NOTRUN, "c1 · c2 기록 없음")
    if not send or not fol:
        return res(NOTRUN, f"A 의 send {'있음' if send else '없음'} · followup {'있음' if fol else '없음'}", str(A.path))
    early = turns_between(B, send["t"], fol["t"])
    if early:
        return res(FAIL, "send 만으로 B 새 턴 시작 — 실측과 다름", str(B.path), "지시 규칙(send · followup 구분) 재확인")
    if not B.said(tok("B-FOLLOW", R.run)):
        return res(FAIL, "followup 뒤 B 표식 없음", str(B.path), "주소 전체 경로 확인")
    return res(PASS, "send 뒤 B 턴 없음 · followup 뒤 B 표식", f"{A.path} · {B.path}")


# idle 재시작
def j_f1(R):
    A, B, send, fol = peer(R)
    if not B or not fol:
        return res(NOTRUN, "followup 기록 없음")
    after = [e for e in B.of("turn") if e["t"] >= fol["t"]]
    actual = f"B {str(B.id)[:13]} · 턴 {len(B.of('turn'))}개 · followup 뒤 {len(after)}개"
    return res(PASS, actual, str(B.path)) if after and B.said(tok("B-FOLLOW", R.run)) else res(FAIL, actual, str(B.path))


# MAIN ↔ A
def j_c2(R):
    s = R.sessions()
    m, A = s["main"], s["subs"].get(1)
    if not m or not A:
        return res(NOTRUN, "MAIN · c1 기록 없음")
    down = m.calls("followup_task", names(A))
    up = [e for e in A.calls("send_message") if str(e["args"].get("target")) in ("/root", str(m.id))]
    mark = tok("A-REPORT", R.run)
    seen = m.has(mark, "agent", "say", "user", "out")
    actual = f"MAIN → A followup {len(down)} · A → MAIN send {len(up)} · 표식 수신 {'있음' if seen else '없음'}"
    if not down:
        return res(NOTRUN, actual)
    return res(PASS, actual, str(m.path)) if up and seen else res(FAIL, actual, str(m.path))


# 긴 wait — 도착 순서는 보지 않는다(관문을 줄였다)
def j_w1(R):
    s = R.sessions()
    m, B = s["main"], s["subs"].get(2)
    tail = " · 미래 도착 순서 미확인"
    if not m or not B:
        return res(NOTRUN, "MAIN · c2 기록 없음")
    mark = tok("B-WAIT", R.run)
    fol = m.calls("followup_task", names(B))
    waits = [e for e in m.calls("wait") if any(e["t"] >= f["t"] for f in fol)]
    if not B.said(mark):
        return res(NOTRUN if not fol else FAIL, f"followup {len(fol)} · B 표식 없음", str(B.path))
    seen = [e for e in m.has(mark, "agent", "out", "say")]
    if not waits:
        return res(UNSURE, f"B 표식 있음 · wait_agent 호출 기록 없음{tail}", str(m.path), "세션 기록에 wait 이름이 다르면 mark W1")
    ok = [e for e in seen if e["t"] >= waits[0]["t"]]
    actual = f"wait {len(waits)}회 · timeout {waits[0]['args'].get('timeout_ms')} · B 표식 수신 {'있음' if ok else '없음'}{tail}"
    return res(PASS, actual, str(m.path)) if ok else res(FAIL, actual, str(m.path))


# 서브 샌드박스 도우미 결과
def j_k1(R):
    e = R.evidence("skill")
    if not e:
        return res(NOTRUN)
    return res(PASS if e.get("ok") else FAIL, f"{e.get('path')} · «{e.get('got')}»", str(R.ev / "skill.json"))


def j_wt(R):
    e = R.evidence("worktree")
    if not e:
        return res(NOTRUN)
    # 서브에서 불렀는지 — 외부 터미널 성공은 따로 표시
    who = "서브 샌드박스" if e.get("thread") else "외부 터미널(서브 아님)"
    actual = f"{who} · add {e.get('add_rc')} · HEAD {e.get('head_ok')} · 분리 {e.get('separate')} · 파이썬 {e.get('py_rc')} · remove {e.get('remove_rc')}"
    ok = e.get("add_rc") == 0 and e.get("head_ok") and e.get("separate") and e.get("py_rc") == 0
    if not ok:
        return res(FAIL, actual + f" · {e.get('out')}", str(R.ev / "worktree.json"), "검증관 worktree 운영 불가 — 권한 · ROOT .git 쓰기 확인")
    return res(PASS if e.get("thread") else UNSURE, actual, str(R.ev / "worktree.json"))


def j_xd(R):
    e = R.evidence("xdist")
    if not e:
        return res(NOTRUN)
    actual = f"종료코드 {e.get('rc')} · 작업자 {e.get('workers')} · {e.get('out')}"
    ok = e.get("rc") == 0 and e.get("workers") and all(str(w).startswith("gw") for w in e["workers"])
    return res(PASS, actual, str(R.ev / "xdist.json")) if ok else res(FAIL, actual, str(R.ev / "xdist.json"), "설치 필요 기록만(자동 설치 안 함) · -n auto 는 별도")


# devview — 끊기면(샌드박스일 수 있음) 앞선 관측을 쓴다
def j_d1(R):
    port = R.st.get("port", 8701)
    info = get_json(f"http://127.0.0.1:{port}/api/info")
    if info is None:
        old = R.st.get("d1")
        if old:
            return res(old["result"], old["actual"] + " · 앞선 관측", old["proof"])
        return res(UNSURE, f"127.0.0.1:{port} 응답 없음", "", "안 떴거나 샌드박스 안 실행 — 유저 터미널 탭에서 check")
    tree = (info.get("flowtree") or {}).get("tree")
    same_kit = Path(str(info.get("kit_abs"))).resolve() == R.kit.resolve()
    same_tree = bool(tree) and Path(tree).resolve() == Path(R.st["tree"]).resolve()
    actual = f"키트 {'일치' if same_kit else info.get('kit_abs')} · 트리 {'일치' if same_tree else tree} · page_port {info.get('page_port')}"
    ok = same_kit and same_tree and info.get("page_port")
    r = res(PASS if ok else FAIL, actual, f"http://127.0.0.1:{port}/api/info", "" if ok else "운영 트리 · 키트가 시험 재료와 다르면 8번 항목이 연결되지 않는다")
    R.st["d1"] = {k: r[k] for k in ("result", "actual", "proof")}
    R.st["page"] = {"root": info.get("root"), "page_port": info.get("page_port")}
    return r


# 종 — API 까지만(화면은 U6)
def j_n1(R):
    data = get_json(f"http://127.0.0.1:{R.st.get('port', 8701)}/api/notify")
    if data is None:
        old = R.st.get("n1")
        return res(*old) if old else res(UNSURE, "API 응답 없음", "", "유저 터미널 탭에서 check")
    ok = tok("N1", R.run) in json.dumps(data, ensure_ascii=False)
    r = res(PASS if ok else FAIL, f"/api/notify 에 표식 {'있음' if ok else '없음'}")
    R.st["n1"] = [r["result"], r["actual"]]
    return r


# 설문 결과 파일
def survey_result(R):
    sv = R.st.get("survey") or {}
    return read_json(Path(sv.get("file", "")).with_name(f"{sv.get('id')}.result.json")) if sv else None


# 전송 줄 고르기
def route_of(result, to):
    return next((x for x in (result or {}).get("route") or [] if x.get("to") == to), None)


def j_sv1(R):
    if not R.st.get("survey"):
        return res(FAIL, "설문 등록 실패", "", R.st.get("seed", {}).get("시험 설문", {}).get("msg", ""))
    r = survey_result(R)
    if not r:
        return res(NOTRUN, "제출 없음")
    a, b = route_of(r, "MAIN"), route_of(r, "2ND")
    actual = f"MAIN {a and (a.get('ok'), a.get('request') or a.get('error'))} · 2ND {b and (b.get('ok'), b.get('request') or b.get('error'))}"
    ok = a and b and a.get("ok") and b.get("ok") and a.get("request") and b.get("request")
    return res(PASS if ok else FAIL, actual[:240], R.st["survey"]["file"], "" if ok else "둘째 문항 «질문» 을 골랐나 · 세션 등록 확인")


def j_sv2(R):
    a = route_of(survey_result(R), "MAIN")
    m = R.sessions()["main"]
    if not a or not a.get("request") or not m:
        return res(NOTRUN)
    if not m.got(a["request"]):
        return res(UNSURE, f"요청 {a['request']} 접수 · 세션 입력에 아직 없음", "", "MAIN 턴 끝난 뒤 check 다시")
    ok = m.said(tok("ACK-SV", R.run))
    return res(PASS if ok else FAIL, f"요청 {a['request']} 수신 · ACK {'있음' if ok else '없음'}", str(m.path))


def j_sv3(R):
    b = route_of(survey_result(R), "2ND")
    s = R.sessions()["2nd"]
    if not b or not b.get("request") or not s:
        return res(NOTRUN)
    if not s.got(b["request"]):
        return res(UNSURE, f"요청 {b['request']} 접수 · 세션 입력에 아직 없음", "", "2ND 턴 끝난 뒤 check 다시")
    base = Path(os.environ.get("MAGIC_SURVEY_DIR") or "/tmp/sv")
    forms = [p for p in base.rglob("*.json") if b["request"] in p.read_text(encoding="utf-8", errors="replace")] if base.is_dir() else []
    return res(PASS if forms else FAIL, f"요청 {b['request']} 수신 · 설명 폼 {len(forms)}개", str(forms[0]) if forms else str(base),
               "" if forms else "answer-form 으로 답했나 — 채팅으로만 답하면 실패")


# 스티커
def j_st1(R):
    n = R.st.get("note")
    if not n:
        return res(FAIL, "시험 책 준비 실패", "", R.st.get("seed", {}).get("시험 책", {}).get("msg", ""))
    note = next((x for x in read_json(n["file"], []) or [] if x.get("id") == n["id"]), None)
    rid = (note or {}).get("magic_rid")
    if not rid:
        return res(NOTRUN, "마법봉 안 누름", n["file"])
    s = R.sessions()["2nd"]
    got = bool(s and s.got(rid))
    ans = tok("ST", R.run) in str(note.get("answer") or "")
    tree = read_json(R.st["tree"], {}) or {}
    stray = [x.get("id") for x in tree.get("nodes", []) if x.get("kind") == "question" and n["id"] in str(x.get("title"))]
    actual = f"요청 {rid} · 수신 {got} · answer 표식 {ans} · 질문 노드로 샌 것 {len(stray)}"
    if ans and got and not stray:
        return res(PASS, actual, n["file"])
    return res(UNSURE if not ans and not got else FAIL, actual, n["file"], "2ND 가 answer-note 로 답했나 — 채팅 답은 실패")


# 그래프 시험 노드
def tree_nodes(R):
    store = load_store(R.kit)
    tree = store.read_json(Path(R.st["tree"]), {}) or {}
    return store, store.node_map(tree)


def j_g1(R):
    ids = R.st.get("nodes")
    if not ids:
        return res(FAIL, "노드 준비 실패", "", R.st.get("seed", {}).get("시험 노드", {}).get("msg", ""))
    _, nodes = tree_nodes(R)
    tag = f"[precheck {R.run}]"
    ok = all(i in nodes and tag in str(nodes[i].get("title")) for i in ids.values())
    kinds = {k: nodes.get(i, {}).get("kind") for k, i in ids.items()}
    good = ok and kinds == {"task": "task", "verify": "verify", "question": "question"}
    return res(PASS if good else FAIL, f"읽기 재확인 {kinds}", R.st["tree"])


def j_g2(R):
    g = R.st.get("g2")
    if not g:
        return res(FAIL, "실행 안 됨", "", R.st.get("seed", {}).get("그래프 틀", {}).get("msg", ""))
    store = load_store(R.kit)
    node = store.node_map(store.read_json(Path(g["tree"]), {}) or {}).get(g.get("id")) or {}
    want = tok("G2", R.run)
    ok = g.get("frames_rc") == 0 and g.get("fill_rc") == 0 and g.get("check_rc") == 0 and node.get("title") == want and not node.get("frame")
    actual = f"frames {g.get('frames_rc')}({g.get('frames')}) · fill {g.get('fill_rc')} · check {g.get('check_rc')} · 제목 {'일치' if node.get('title') == want else node.get('title')}"
    return res(PASS if ok else FAIL, actual, g["tree"], "" if ok else str(g.get("out")))


# MAIN 마법봉 요청 — 시험 노드가 든 것만
def magic_requests(R):
    ids = set((R.st.get("nodes") or {}).values())
    out = []
    for p in sorted((R.kit / ".codex-hub" / "requests").glob("*.json")):
        q = read_json(p) or {}
        if q.get("role") == "main" and ids & {x.get("id") for x in q.get("nodes") or []}:
            out.append(q)
    return out


def j_m1(R):
    ids = set((R.st.get("nodes") or {}).values())
    reqs = magic_requests(R)
    if not reqs:
        return res(NOTRUN, "시험 노드 마법봉 요청 없음")
    covered = ids & {x.get("id") for q in reqs for x in q.get("nodes") or []}
    m = R.sessions()["main"]
    got = [q["id"] for q in reqs if m and m.got(q["id"])]
    actual = f"요청 {len(reqs)}개 · 노드 {len(covered)}/{len(ids)} · 수신 {len(got)}"
    same = all(Path(str(q.get("tree"))).resolve() == Path(R.st["tree"]).resolve() for q in reqs)
    if len(covered) == len(ids) and len(got) == len(reqs) and same:
        return res(PASS, actual + (" · 나눠 누름" if len(reqs) > 1 else " · 한 번에"), str(m.path))
    return res(UNSURE if not got else FAIL, actual + ("" if same else " · 요청 트리 다름"), "", "남은 노드를 마법봉으로 · MAIN 턴 끝난 뒤 check 다시")


def j_m234(R, kind):
    ids = R.st.get("nodes")
    if not ids:
        return res(NOTRUN)
    store, nodes = tree_nodes(R)
    n = nodes.get(ids[kind])
    if not n:
        return res(FAIL, "노드 없음", R.st["tree"])
    st = store.status(n, nodes, time.time())["status"]
    if kind == "task":
        ok, extra = st == "done" and R.evidence(f"task_{ids[kind]}") is not None, "표식 파일 " + ("있음" if R.evidence(f"task_{ids[kind]}") else "없음")
    elif kind == "verify":
        ok, extra = st == "pass", ""
    else:
        ok, extra = st == "answered" and R.run in json.dumps(n.get("answers"), ensure_ascii=False), "답에 run 표식"
    if st == "todo":
        return res(NOTRUN, "상태 todo")
    return res(PASS if ok else FAIL, f"{ids[kind]} {st} {extra}", R.st["tree"])


# 환경 점검 — 체험 때도 나온 번호만이면 통과
ENV_OK = {"A6", "B3", "B4"}


def j_e1(R):
    e = R.evidence("env")
    if not e:
        return res(NOTRUN)
    if not e.get("summary"):
        return res(FAIL, last_line(e.get("out") or "")[:200], "", "envcheck 를 샌드박스 밖에서 다시")
    nums = set(e["summary"].removeprefix("요약:").split()) - {"실패", "없음"}
    bad = sorted(nums - ENV_OK)
    return res(FAIL if bad else PASS, e["summary"], str(R.ev / "env.json"), f"envcheck README 3절 — {' '.join(bad)}" if bad else "")


def j_e2(R):
    e = R.evidence("book")
    if not e:
        return res(NOTRUN)
    e = {k: v for k, v in e.items() if isinstance(v, dict)}
    bad = [k for k, v in e.items() if v.get("rc") != 0]
    return res(FAIL if bad else PASS, " · ".join(f"{k} {v.get('out')}" for k, v in e.items())[:200], str(R.ev / "book.json"),
               f"없는 것 {' '.join(bad)} — 책 검사는 건너뛴다" if bad else "")


def j_e5(R):
    e = R.evidence("bookbuild")
    if not e:
        return res(NOTRUN)
    ok = e.get("build_rc") == 0 and e.get("html")
    return res(PASS if ok else FAIL, f"new {e.get('new_rc')} · build {e.get('build_rc')} · html {len(e.get('html') or [])} · {e.get('out')}"[:200],
               str(R.ev / "bookbuild.json"), "" if ok else "🔴 대회 때 책을 못 만든다 — 끝 줄 원인부터")


def j_e3(R):
    e = R.evidence("filenode")
    if not e:
        return res(NOTRUN)
    ok = e.get("rc") == 0 and e.get("node")
    return res(PASS if ok else FAIL, f"{e.get('node') or '노드 없음'} · {e.get('out')}"[:200], str(R.ev / "filenode.json"))


def j_e4(R):
    s = R.sessions()["2nd"]
    mark, ack = tok("E4", R.run), tok("ACK-E4", R.run)
    hits = s.has(mark, "user") if s else []
    if not hits:
        return res(NOTRUN, "2ND 입력에 표식 없음")
    if not any("@main" in str(e.get("text")) for e in hits):
        return res(FAIL, "표식은 왔는데 @main 꼬리표 없음", str(s.path), "hub.py send 확인")
    return res(PASS, "@main · 표식 · ACK 일치", str(s.path)) if s.said(ack) else res(FAIL, "입력은 왔는데 답에 ACK 없음", str(s.path))


# 판정 함수 표
JUDGES = {"R1": j_r1, "P1": j_p1, "P2": j_p2, "H0": j_h0, "H1": lambda R: j_hub(R, "main"), "H2": lambda R: j_hub(R, "2nd"), "V1": j_v1,
          "Q1": j_q1, "T1": lambda R: j_echo(R, "T1"), "S8": j_s8, "L8": j_l8, "C1": j_c1, "F1": j_f1, "C2": j_c2, "W1": j_w1, "K1": j_k1,
          "WT": j_wt, "XD": j_xd, "D1": j_d1, "N1": j_n1, "SV1": j_sv1, "SV2": j_sv2, "SV3": j_sv3, "ST1": j_st1, "G1": j_g1, "G2": j_g2,
          "M1": j_m1, "M2": lambda R: j_m234(R, "task"), "M3": lambda R: j_m234(R, "verify"), "M4": lambda R: j_m234(R, "question"),
          "E1": j_e1, "E2": j_e2, "E3": j_e3, "E4": j_e4, "E5": j_e5}


# 전체 판정 — 항목 하나의 예외가 다른 항목을 막지 않는다 · 자동 통과가 아니면 mark 가 이긴다 · 그다음 선행 차단
def judge_all(R):
    out = {}
    for iid, _, _, deps, _ in ITEMS:
        try:
            r = JUDGES[iid](R) if iid in JUDGES else res(NOTRUN)
            r["level"] = "자동 판정(기록)" if iid in JUDGES else "유저 눈 확인"
        except Exception as e:  # noqa: BLE001 — 판정 하나가 깨져도 나머지는 본다
            r = res(UNSURE, f"판정 오류 {type(e).__name__}: {e}"[:200], "", "수동 확인")
            r["level"] = "판정 오류"
        m = R.evidence(f"mark_{iid}")
        if m and r["result"] != PASS:
            r.update(result=m["result"], actual=(m.get("note") or r["actual"]), level="세션 · 유저 보고", proof=str(R.ev / f"mark_{iid}.json"))
        if r["result"] in (NOTRUN, UNSURE):
            bad = [d for d in deps if out.get(d, {}).get("result") in (FAIL, BLOCK)]
            if bad:
                r.update(result=BLOCK, actual=f"선행 {' · '.join(bad)} · {r['actual']}"[:200])
        r["at"] = time.strftime("%H:%M:%S")
        out[iid] = r
    return out


# 총 판정 — 치명 항목이 전부 통과 · 제외여야 통과
def verdict(results):
    crit = [results[i[0]]["result"] for i in ITEMS if i[2]]
    if all(x in (PASS, SKIP) for x in crit):
        return PASS
    return "일부 실패" if any(x in (FAIL, BLOCK) for x in crit) else "미완료"


# ======= precheck.md =======
# 표 칸 글
def cell(s):
    return " ".join(str(s or "-").split()).replace("|", "\\|") or "-"


# 사용량 표 — thread 별 누적값(더하지 않고 줄마다 그대로 · 서브 합산 여부는 미확인)
def usage_rows(R):
    s = R.sessions()
    rows = []
    for name, r in [("MAIN", s["main"]), ("2ND", s["2nd"]), *[(f"서브 {str(k.agent_path or k.id)}", k) for k in s["kids"]]]:
        if r and r.usage:
            u = r.usage
            rows.append(f"| {cell(name)} | {u.get('input_tokens')} | {u.get('cached_input_tokens')} | {u.get('output_tokens')} | {len(r.of('turn'))} |")
    return rows


# 남긴 것 목록
def left_rows(R):
    st, rows = R.st, []
    sv, nd, nt = st.get("survey") or {}, st.get("nodes") or {}, st.get("note") or {}
    rows.append(f"- run 폴더: {R.dir}")
    rows.append(f"- ReadyStart.md: {R.kit / 'ReadyStart.md'}(대회 명령 그대로 · git 제외)")
    if sv:
        rows.append(f"- 시험 설문: {sv.get('file')} · 같은 이름 .result.json")
    if nd:
        rows.append(f"- 시험 노드(제목 [precheck {R.run}]): {' · '.join(nd.values())} · 트리 {st.get('tree')} — 지우지 않았다")
    if nt:
        rows.append(f"- 시험 책 · 스티커: {nt.get('book')}(git 제외)")
    rows.append(f"- 종 알림: {tok('N1', R.run)} 한 줄(.codex-hub/notify.jsonl)")
    e = R.evidence("worktree") or {}
    if e.get("add_rc") == 0:
        rows.append(f"- 시험 worktree: {e.get('path')} · remove 종료코드 {e.get('remove_rc')}")
    if e.get("seed_commit") == 0:
        rows.append(f"- 시험 빈 커밋: {R.st.get('root')} 의 «precheck {R.run} 시험 커밋»(체험 기계에만)")
    bb = R.evidence("bookbuild") or {}
    if bb.get("book"):
        rows.append(f"- 빌드 시험 책: {bb['book']}(git 제외)")
    fn = R.evidence("filenode") or {}
    if fn.get("node"):
        rows.append(f"- 시험 파일 노드: {fn['node']}(AGENTS.md)")
    rows.append("- 시험 세션 · devview 는 이 도구가 닫지 않는다(유저 창)")
    return rows


# run 절 글
def render(R, results):
    st = R.st
    ss = st.get("seen_settings") or {}
    main, second = R.reg("main") or {}, R.reg("2nd") or {}
    page = st.get("page") or {}
    rows = [("시작 · 판정 시각 · 시간대", f"{st.get('started')} → {time.strftime('%Y-%m-%d %H:%M:%S')} · {st.get('tz')}"),
            ("키트 · git HEAD", f"{st.get('kit')} · {last_line(run_cmd(['git', '-C', st.get('kit'), 'rev-parse', '--short', 'HEAD'], wait=20)[1])}"),
            ("ROOT · 실제 PY", f"{st.get('root')} · {st.get('py')}"),
            ("Codex 판 · 기록 판", f"{ss.get('version') or '확인 불가'} · {ss.get('main_cli') or '확인 불가'}"),
            ("MAIN / 2ND thread", f"{main.get('thread') or '-'} / {second.get('thread') or '-'}"),
            ("적용 설정(기록)", f"main {ss.get('main') or '확인 불가'} · 2nd {ss.get('2nd') or '확인 불가'}"),
            ("본선과 다른 점", f"강도 {TEST_EFFORT}(본선 MAIN high · 2ND medium) · 시작 메시지만 precheck 대기 지시"),
            ("ReadyStart.md", str(st.get("seed", {}).get("ReadyStart", {}).get("msg") or "-")),
            ("envcheck · ready-start", f"{(R.evidence('env') or {}).get('summary') or '미실행'} · ready-start 미실행"),
            ("devview · page_port", f"{page.get('root') or '-'} · {page.get('page_port') or '-'}"),
            ("제외", "재시작 재연결(유저 지정) · 압축 훅 실작동")]
    out = [f"## run {R.run} — 총 판정 {verdict(results)}", "", "### 실행 정보", "", "| 필드 | 값 |", "|---|---|"]
    out += [f"| {cell(k)} | {cell(v)} |" for k, v in rows]
    out += ["", "### 항목별 결과", "", "| ID | 항목 | 결과 | 근거 수준 | 입력 · 기대값 | 실제 결과 | 판정 시각 | 증거 | 다음 조치 |", "|---|---|---|---|---|---|---|---|---|"]
    for iid, name, _, _, want in ITEMS:
        r = results[iid]
        out.append(f"| {iid} | {cell(name)} | {r['result']} | {cell(r.get('level'))} | {cell(want)} | {cell(r['actual'])} | {r['at']} | {cell(r['proof'])} | {cell(r['next'])} |")
    use = usage_rows(R)
    out += ["", "### 사용량(thread 별 누적 · 구독 차감 환산 미확인)", ""]
    out += (["| 세션 | input | cached_input | output | 턴 |", "|---|---|---|---|---|"] + use) if use else ["- 수집 값 없음"]
    env = (R.evidence("env") or {}).get("out")
    if env:
        out += ["", "### envcheck 출력", "", "```text", env, "```"]
    out += ["", "### 남긴 것", ""] + left_rows(R)
    return "\n".join(out)


# run 절 덧붙이기 — 같은 run 은 그 절만 바꾸고 다른 run 은 건드리지 않는다
def write_report(R, results):
    path = R.kit / REPORT
    a, b = MARK_A.format(R.run), MARK_B.format(R.run)
    body = f"{a}\n{render(R, results)}\n{b}\n"
    old = path.read_text(encoding="utf-8") if path.is_file() else "# precheck — 사전 체험 왕복 점검 결과\n\n"
    if a in old and b in old:
        new = old[:old.index(a)] + body + old[old.index(b) + len(b) + 1:]
    else:
        new = old.rstrip("\n") + "\n\n" + body
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, path)
    return path


# check — 판정 → 결과 파일
def cmd_check(R, a):
    say(f"precheck 판정 · run {R.run}")
    results = judge_all(R)
    for iid, name, *_ in ITEMS:
        r = results[iid]
        if r["result"] != PASS:
            say(f"  {iid} {r['result']} — {name} · {r['actual']}"[:200])
    R.save()
    path = write_report(R, results)
    n = sum(1 for r in results.values() if r["result"] == PASS)
    v = verdict(results)
    say(f"요약: {v} · 통과 {n}/{len(ITEMS)} · {path}")
    if a.final:
        rc, out = run_cmd([sys.executable, SK / "ready-start" / "readystart.py", "status", "precheck", f"{v} · 통과 {n}/{len(ITEMS)} · run {R.run}", "--kit", R.kit])
        say(f"ReadyStart 상태 한 줄 — 종료코드 {rc} {last_line(out)}")
    return 0


# 명령줄
def build_parser():
    ap = argparse.ArgumentParser(prog="precheck.py", description="사전 체험 왕복 점검")
    ap.add_argument("--kit", default=None, help="키트 폴더")
    ap.add_argument("--run", default=None, help="run id(기본 마지막 run)")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="명령")
    p = sub.add_parser("prepare", help="run 시작 · 재료 준비")
    p.add_argument("--root", default=None, help="과제 루트")
    p.add_argument("--py", default=None, help="검증에 쓸 파이썬")
    p.add_argument("--port", type=int, default=8701, help="devview 포트")
    sub.add_parser("ping", help="MAIN 에 codex queue 한 번")
    sub.add_parser("sub-worktree", help="worktree + xdist(서브에서)")
    sub.add_parser("sub-env", help="envcheck(서브에서 · 샌드박스 밖)")
    sub.add_parser("sub-book", help="책 재료 라이브러리 · 헤드리스 크롬(서브에서)")
    sub.add_parser("sub-file", help="file-add 파일 노드(서브에서)")
    p = sub.add_parser("sub-skill", help="스킬 파일 줄 대조")
    p.add_argument("line")
    p = sub.add_parser("sub-task", help="시험 작업 표식")
    p.add_argument("node")
    p = sub.add_parser("mark", help="유저 체크 · 세션 보고")
    p.add_argument("id")
    p.add_argument("result")
    p.add_argument("--note", default="")
    p = sub.add_parser("check", help="판정 · 결과 파일")
    p.add_argument("--final", action="store_true", help="ReadyStart 상태 한 줄도")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    a = build_parser().parse_args(argv)
    if a.cmd == "prepare":
        return cmd_prepare(a)
    kit = find_kit(a.kit)
    R = current_run(kit, a.run) if kit else None
    if R is None:
        print("run 없음 — 먼저 prepare", file=sys.stderr)
        return 2
    return {"ping": cmd_ping, "sub-worktree": cmd_sub_worktree, "sub-env": cmd_sub_env, "sub-book": cmd_sub_book, "sub-file": cmd_sub_file, "sub-skill": cmd_sub_skill, "sub-task": cmd_sub_task,
            "mark": cmd_mark, "check": cmd_check}[a.cmd](R, a)


if __name__ == "__main__":
    sys.exit(main())
