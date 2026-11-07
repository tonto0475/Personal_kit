#!/usr/bin/env python3
"""Codex 세션 상태 — ~/.codex/sessions/**/rollout-*.jsonl 을 읽어 세션마다 상태 · 맥락 % 를 계산(표준 라이브러리만)

    python3 codex_sessions.py [--limit 20] [--home ~/.codex]      목록을 JSON 으로 출력
    devview: GET /api/codex/sessions[?limit=N&thread=<id>]

판정은 기록된 이벤트로만 한다. 확실하지 않은 판정은 sure=false · basis 에 «추정» 을 적는다
- 작업 중   task_started 뒤에 그 턴의 task_complete · turn_aborted 가 아직 없음
- 대기     마지막 턴이 task_complete · turn_aborted 로 끝남(턴 기록이 없으면 대기 · 추정)
- 설문     작업 중인데 아직 결과가 안 온 명령이 «survey.py wait <id>»(추정 — 명령 글자로 판정)
           · request_user_input 도구 호출이 결과 없이 열려 있음
- 권한 요청 승인 요청 이벤트(이름에 approval 이 든 event_msg · request_permissions · elicitation_request)가
           마지막 의미 있는 이벤트 — 이 PC 기록(2026-11-01)에는 이런 이벤트가 없어 가짜 조각으로만 시험함
- 연결     마지막 기록이 ALIVE_SEC 안(추정 — 쉬는 세션은 아무것도 안 써서 기록만으로는 살아 있는지 모름)
맥락 % = 마지막 token_count 의 last_token_usage.total_tokens ÷ model_context_window
세션 id = session_meta.payload.id — 파일 이름 끝 · thread_id 와 같은 값(Codex 안의 CODEX_THREAD_ID)
🔴 대화 본문은 읽어도 내보내지 않는다(명령 글자는 설문 판정에만 메모리에서 씀)
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

# 연결로 볼 마지막 기록 뒤 시간(초)
ALIVE_SEC = 600
# 작업 중인데 이만큼 기록이 없으면 멈췄을 수 있다고 표시(초)
STALE_SEC = 1800
# 큰 파일은 끝에서 이만큼만 읽음(바이트) — 상태는 끝 부분 이벤트로 정해짐
TAIL_BYTES = 4 * 1024 * 1024
# 목록 기본 개수
DEFAULT_LIMIT = 30
# 상태 키 → 표시 이름
STATE_LABELS = {"working": "작업 중", "idle": "대기", "survey": "설문", "approval": "권한 요청"}
# 승인 요청으로 보는 event_msg 종류(이름에 approval 이 든 것도 포함)
APPROVAL_TYPES = {"request_permissions", "elicitation_request", "exec_approval_request", "apply_patch_approval_request"}
# 승인 요청 대기를 풀지 않는 이벤트(진행 신호가 아님)
PASSIVE_TYPES = {"token_count", "token_usage_record", "world_state", "thread_settings_applied", "turn_context"}
# 설문 대기 명령 — survey.py wait <설문 id>
SURVEY_WAIT = re.compile(r"survey(?:\.py)?['\"]?\s+wait\s+['\"]?([0-9A-Za-z_-]+)")
# 설문 저장 폴더 목록 파일(설문 도구와 같은 곳)
SURVEY_REGISTRY = Path(os.environ.get("SURVEY_REGISTRY") or (Path.home() / ".devview" / "survey_stores.json"))
# (경로, 수정 시각, 크기) → 계산 결과 — 안 바뀐 파일은 다시 안 읽음
_CACHE = {}


# Codex 홈 폴더 — CODEX_HOME 환경변수 > ~/.codex
# home: 직접 지정(없으면 None)
def codex_home(home=None):
    return Path(home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser()


# ISO 시각 글자 → 에포크 초(못 읽으면 None)
# s: «2026-11-01T04:31:08.131Z» 모양
def parse_ts(s):
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# 에포크 초 → 지역 시각 글자(YYYY-MM-DD HH:MM:SS)
# t: 에포크 초
def local_ts(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else None


# 파일 앞 첫 줄 · 끝 부분 줄 목록 읽기
# path: rollout 파일
def read_lines(path):
    # 파일 크기
    size = path.stat().st_size
    with open(path, "rb") as f:
        # 첫 줄(session_meta)
        first = f.readline()
        if size <= TAIL_BYTES:
            # 나머지 전부
            rest = f.read()
        else:
            f.seek(size - TAIL_BYTES)
            rest = f.read()
            rest = rest[rest.find(b"\n") + 1:]   # 잘린 첫 줄 버림
    return first, rest.splitlines()


# JSON 한 줄 → 사전(깨진 줄은 None)
# raw: 줄 바이트
def load_line(raw):
    try:
        o = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None
    return o if isinstance(o, dict) else None


# 설문 답 상태 — 설문 저장 폴더에서 <id>.result.json 을 찾음 → answered · pending · unknown
# sid: 설문 id
def survey_status(sid):
    try:
        # 등록된 저장 폴더 목록
        stores = json.loads(SURVEY_REGISTRY.read_text(encoding="utf-8")) if SURVEY_REGISTRY.exists() else []
    except (OSError, ValueError):
        stores = []
    # 설문 파일을 찾았는지
    found = False
    for s in stores:
        # 저장 폴더
        base = Path(s)
        # 바로 아래 · 프로젝트 폴더 아래
        for folder in [base] + ([p for p in base.iterdir() if p.is_dir()] if base.is_dir() else []):
            if (folder / f"{sid}.result.json").exists():
                return "answered"
            if (folder / f"{sid}.json").exists():
                found = True
    return "pending" if found else "unknown"


# 세션 하나 계산 — 상태 · 맥락 · 시각 · 폴더 · id
# path: rollout 파일 / now: 지금(에포크 초)
def parse_session(path, now=None):
    now = now or time.time()
    # 처음 줄 · 나머지 줄
    first, lines = read_lines(path)
    # 세션 머리 칸
    meta = (load_line(first) or {}).get("payload") or {}
    # 계산 중인 값들
    cwd = meta.get("cwd")
    model = policy = None
    window = None
    last_usage = None
    turn_open = False
    turn_end = None
    started_at = None
    last_ts = parse_ts((load_line(first) or {}).get("timestamp"))
    # 결과 없이 열린 도구 호출: call_id → {name, survey, at}
    open_calls = {}
    # 대기 중인 승인 요청
    approval = None
    # 생각 강도(마지막 turn_context · 설정 적용 기록) · 마지막으로 끝난 턴 {id, at, error} — 허브 행 테두리(점멸 · 오류)용
    effort = None
    last_done = None
    for raw in lines:
        # 이벤트 하나
        o = load_line(raw)
        if not o:
            continue
        # 줄 종류 · 내용
        kind, p = o.get("type"), o.get("payload")
        if not isinstance(p, dict):
            p = {}
        # 내용 종류(event_msg · response_item 의 하위 종류)
        sub = p.get("type") if isinstance(p.get("type"), str) else None
        # 이 이벤트 시각
        ts = parse_ts(o.get("timestamp"))
        if ts:
            last_ts = ts if last_ts is None else max(last_ts, ts)
        # 승인 요청 이벤트인가
        is_approval = kind == "event_msg" and sub and (sub in APPROVAL_TYPES or "approval" in sub)
        if is_approval:
            approval = {"type": sub, "at": ts, "call_id": p.get("call_id")}
            continue
        if approval and kind not in PASSIVE_TYPES and sub not in PASSIVE_TYPES:
            approval = None
        if kind == "session_meta":
            meta = p
            cwd = p.get("cwd") or cwd
        elif kind == "turn_context":
            cwd = p.get("cwd") or cwd
            model = p.get("model") or model
            policy = p.get("approval_policy") or policy
            # 협업 모드 설정 칸 — 기본값으로 띄운 세션은 둘 다 null
            cm = p.get("collaboration_mode") if isinstance(p.get("collaboration_mode"), dict) else {}
            effort = p.get("effort") or (cm.get("settings") or {}).get("reasoning_effort") or effort
        elif kind == "event_msg" and sub == "thread_settings_applied":
            effort = (p.get("thread_settings") or {}).get("reasoning_effort") or effort
        elif kind == "event_msg" and sub == "task_started":
            turn_open, turn_end = True, None
            open_calls.clear()
            window = p.get("model_context_window") or window
            started_at = ts
        elif kind == "event_msg" and sub in ("task_complete", "turn_aborted"):
            turn_open, turn_end = False, sub
            open_calls.clear()
            # 오류 — task_complete.error.message(없는 모델 · API 거부 등 · 2026-11-02 WSL 0.163 실측)
            err = p.get("error") if isinstance(p.get("error"), dict) else None
            last_done = {"id": p.get("turn_id") or f"t{ts}", "at": local_ts(ts), "kind": sub,
                         "error": (err.get("message") or err.get("codex_error_info") or "오류") if err else None}
        elif kind == "event_msg" and sub == "token_count":
            # 토큰 집계 칸
            info = p.get("info") or {}
            if info.get("last_token_usage"):
                last_usage = info["last_token_usage"]
            window = info.get("model_context_window") or window
        elif kind == "token_usage_record" and p.get("usage") and last_usage is None:
            last_usage = p["usage"]
        elif kind == "response_item" and sub in ("custom_tool_call", "function_call", "local_shell_call"):
            # 도구 이름 · 입력 글자(설문 판정에만 · 내보내지 않음)
            name = p.get("name") or sub
            text = p.get("input") or p.get("arguments") or ""
            if not isinstance(text, str):
                text = json.dumps(text, ensure_ascii=False)
            # 설문 id(설문 대기 명령일 때)
            m = SURVEY_WAIT.search(text)
            open_calls[p.get("call_id") or f"#{len(open_calls)}"] = {"name": name, "survey": m.group(1) if m else None,
                                                                     "at": ts}
        elif kind == "response_item" and sub in ("custom_tool_call_output", "function_call_output",
                                                  "local_shell_call_output"):
            open_calls.pop(p.get("call_id"), None)

    # 판정
    # 마지막 기록 뒤 지난 초
    age = (now - last_ts) if last_ts else None
    # 설문 대기 중인 호출 · 질문 도구 호출
    survey_call = next((c for c in open_calls.values() if c["survey"]), None)
    ask_call = next((c for c in open_calls.values() if c["name"] in ("request_user_input", "request_user_input_async")),
                    None)
    survey_id = survey_call["survey"] if survey_call else None
    if approval:
        state, sure, basis = "approval", True, f"승인 요청 이벤트 «{approval['type']}» 뒤 진행 기록 없음"
    elif turn_open and survey_call:
        state, sure, basis = "survey", False, f"열린 명령이 설문 대기(survey wait {survey_id}) — 추정(명령 글자로 판정)"
    elif turn_open and ask_call:
        state, sure, basis = "survey", True, f"{ask_call['name']} 도구 호출이 결과 없이 열려 있음"
    elif turn_open:
        if age is not None and age > STALE_SEC:
            state, sure, basis = "working", False, f"task_started 뒤 끝 기록 없음 · 마지막 기록 {int(age // 60)}분 전 — 멈췄을 수 있음(추정)"
        else:
            state, sure, basis = "working", True, "task_started 뒤 task_complete · turn_aborted 없음"
    elif turn_end:
        state, sure, basis = "idle", True, f"마지막 턴이 {turn_end} 로 끝남"
    else:
        state, sure, basis = "idle", False, "턴 기록 없음 — 추정"
    # 맥락 사용량 · 창 · 비율
    used = (last_usage or {}).get("total_tokens")
    if used is None and last_usage:
        used = (last_usage.get("input_tokens") or 0) + (last_usage.get("output_tokens") or 0)
    pct = round(used / window * 100, 1) if used is not None and window else None
    # 세션 id
    sid = meta.get("id")
    return {
        "id": sid, "session_id": meta.get("session_id"), "id_in_file_name": bool(sid) and sid in path.name,
        "file": str(path), "cwd": cwd, "model": model, "approval_policy": policy, "cli_version": meta.get("cli_version"),
        "state": state, "state_label": STATE_LABELS[state], "sure": sure, "basis": basis,
        "connected": age is not None and age <= ALIVE_SEC, "connected_basis": f"마지막 기록 뒤 {ALIVE_SEC}초 안 — 추정",
        "last_event_at": local_ts(last_ts), "last_event_age_sec": round(age, 1) if age is not None else None,
        "turn_started_at": local_ts(started_at), "open_calls": len(open_calls),
        "survey_id": survey_id, "survey_status": survey_status(survey_id) if survey_id else None,
        "context": {"used": used, "window": window, "pct": pct,
                    "basis": "last_token_usage.total_tokens ÷ model_context_window"},
        "effort": effort, "last_done": last_done,
    }


# 세션 목록 — 마지막 기록이 최근인 순
# home: Codex 홈(없으면 기본) / limit: 최대 개수 / thread: 이 id 만 / now: 지금(시험용)
def list_sessions(home=None, limit=DEFAULT_LIMIT, thread=None, now=None):
    # 세션 폴더
    base = codex_home(home) / "sessions"
    if not base.is_dir():
        return {"home": str(codex_home(home)), "sessions": [], "error": f"세션 폴더 없음: {base}"}
    now = now or time.time()
    # (수정 시각, 파일) — 최근 것부터
    files = []
    for f in base.rglob("rollout-*.jsonl"):
        try:
            files.append((f.stat().st_mtime, f))
        except OSError:
            continue
    files.sort(reverse=True)
    if thread:
        files = [x for x in files if thread in x[1].name]
    # 결과 목록
    out = []
    for _, f in files[:max(1, int(limit or DEFAULT_LIMIT))]:
        try:
            st = f.stat()
            # 캐시 키
            key = (str(f), st.st_mtime_ns, st.st_size)
            res = _CACHE.get(key)
            if res is None or res.get("_now_bucket") != int(now // 30):
                res = parse_session(f, now)
                res["_now_bucket"] = int(now // 30)   # 나이 · 연결 판정이 시간에 따라 바뀌니 30초마다 다시
                _CACHE[key] = res
            out.append({k: v for k, v in res.items() if not k.startswith("_")})
        # 읽는 중 지워짐 · 권한
        except OSError as e:
            out.append({"file": str(f), "error": str(e)})
    if len(_CACHE) > 500:
        _CACHE.clear()
    return {"home": str(codex_home(home)), "sessions": out, "t": now}


# 명령줄 — 목록 JSON 출력
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    # 명령줄 해석기
    ap = argparse.ArgumentParser(description="Codex 세션 상태 · 맥락 % (rollout 기록 기반)")
    ap.add_argument("--home", default=None, help="Codex 홈(기본 CODEX_HOME 또는 ~/.codex)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--thread", default=None, help="이 세션 id 만")
    # 해석 결과
    a = ap.parse_args(argv)
    print(json.dumps(list_sessions(a.home, a.limit, a.thread), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
