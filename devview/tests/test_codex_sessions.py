"""codex_sessions 판정 시험 — 가짜 rollout jsonl 조각(임시 폴더)으로 상태별 · 맥락 % · id · 목록

    py -3 tests/test_codex_sessions.py        결과 PASS/FAIL (실제 ~/.codex 무관)

이벤트 모양은 이 PC 의 실제 rollout(2026-11-01)에서 칸 이름만 본떴다 — session_meta · task_started(model_context_window)
· token_count(info.last_token_usage · model_context_window) · task_complete · turn_aborted · custom_tool_call(_output)
· function_call(_output) · token_usage_record. 승인 요청 이벤트는 실제 기록에 없어 Codex 이벤트 이름(exec_approval_request)으로 가정
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import codex_sessions as cs  # noqa: E402

# 결과 목록
RESULTS = []
# 기준 시각(에포크 초) — 가짜 이벤트 시각의 출발점
T0 = 1_793_000_000.0


# 결과 한 줄
# name: 항목 / ok: 통과 / detail: 덧붙임
def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail)[:240] if detail else ''}", flush=True)


# 에포크 초 → rollout 시각 글자(UTC · Z)
# t: 에포크 초
def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int((t % 1) * 1000):03d}Z"


# 이벤트 한 줄
# t: 시각 / kind: 줄 종류 / payload: 내용
def ev(t, kind, payload):
    return {"timestamp": iso(t), "type": kind, "payload": payload}


# 가짜 세션 파일 쓰기 — 반환 경로
# base: sessions 폴더 / sid: 세션 id / events: 머리 뒤 이벤트 목록 / t: 머리 시각
def write_session(base, sid, events, t=T0):
    # 파일 경로(날짜 폴더 · rollout-시각-id.jsonl)
    p = base / "2026" / "11" / "01" / f"rollout-2026-11-01T10-00-00-{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    # 머리 줄
    head = ev(t, "session_meta", {"id": sid, "session_id": sid, "cwd": "/work/proj", "cli_version": "0.99.0",
                                  "base_instructions": {"text": "지시문"}})
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [head] + events) + "\n", encoding="utf-8")
    return p


# 턴 시작 · 토큰 집계 묶음
# t: 시각 / used: 마지막 사용 토큰 / window: 맥락 창
def turn_start(t, used=250, window=1000):
    return [
        ev(t, "turn_context", {"turn_id": "u1", "cwd": "/work/proj", "model": "gpt-x", "approval_policy": "on-request"}),
        ev(t, "event_msg", {"type": "task_started", "turn_id": "u1", "model_context_window": window}),
        ev(t + 1, "response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "비밀본문 12345"}]}),
        ev(t + 2, "event_msg", {"type": "token_count", "info": {
            "total_token_usage": {"total_tokens": used * 3}, "last_token_usage": {"input_tokens": used - 50, "output_tokens": 50,
                                                                                  "total_tokens": used},
            "model_context_window": window}}),
    ]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="cx_"))
    base = tmp / "sessions"
    now = T0 + 100
    # 설문 저장 폴더 · 등록 목록(가짜)
    store = tmp / "surveys"
    (store / "proj").mkdir(parents=True)
    (store / "proj" / "20261101-120000.json").write_text("{}", encoding="utf-8")
    (store / "proj" / "20261101-130000.json").write_text("{}", encoding="utf-8")
    (store / "proj" / "20261101-130000.result.json").write_text("{}", encoding="utf-8")
    reg = tmp / "survey_stores.json"
    reg.write_text(json.dumps([str(store)]), encoding="utf-8")
    cs.SURVEY_REGISTRY = reg

    # 1. 작업 중 · 맥락 %
    p = write_session(base, "aaaa-working", turn_start(T0 + 10))
    r = cs.parse_session(p, now)
    check("작업 중(task_started 뒤 끝 없음)", r["state"] == "working" and r["sure"] and r["state_label"] == "작업 중", r["basis"])
    check("맥락 % = last total ÷ 창", r["context"]["used"] == 250 and r["context"]["window"] == 1000 and r["context"]["pct"] == 25.0, r["context"])
    check("세션 id · 파일 이름 · 작업 폴더 · 모델", r["id"] == "aaaa-working" and r["id_in_file_name"] and r["cwd"] == "/work/proj"
          and r["model"] == "gpt-x", (r["id"], r["cwd"], r["model"]))
    check("연결(최근 기록 · 추정)", r["connected"] and "추정" in r["connected_basis"], r["last_event_age_sec"])
    check("대화 본문을 내보내지 않음", "비밀본문" not in json.dumps(r, ensure_ascii=False) and "지시문" not in json.dumps(r, ensure_ascii=False))

    # 2. 대기 — task_complete
    p = write_session(base, "bbbb-idle", turn_start(T0 + 10) + [
        ev(T0 + 20, "event_msg", {"type": "task_complete", "turn_id": "u1", "last_agent_message": "비밀본문"})])
    r = cs.parse_session(p, now)
    check("대기(task_complete)", r["state"] == "idle" and r["sure"] and "task_complete" in r["basis"], r["basis"])
    check("대기여도 맥락 % 유지", r["context"]["pct"] == 25.0, r["context"])

    # 3. 대기 — turn_aborted
    p = write_session(base, "cccc-abort", turn_start(T0 + 10) + [ev(T0 + 15, "event_msg", {"type": "turn_aborted", "turn_id": "u1"})])
    r = cs.parse_session(p, now)
    check("대기(turn_aborted)", r["state"] == "idle" and "turn_aborted" in r["basis"], r["basis"])

    # 4. 설문 — 열린 명령이 survey wait(답 안 옴)
    p = write_session(base, "dddd-survey", turn_start(T0 + 10) + [
        ev(T0 + 30, "response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c1",
                                      "input": "python3 .agents/skills/survey/survey.py wait 20261101-120000"})])
    r = cs.parse_session(p, now)
    check("설문(survey wait 열림 · 추정)", r["state"] == "survey" and not r["sure"] and "추정" in r["basis"]
          and r["survey_id"] == "20261101-120000", (r["state"], r["basis"]))
    check("설문 등록 대조 — 답 대기(pending)", r["survey_status"] == "pending", r["survey_status"])
    check("열린 호출 수", r["open_calls"] == 1, r["open_calls"])

    # 5. 설문 — 답이 이미 있음(answered) · 결과가 오면 작업 중으로
    p = write_session(base, "eeee-survey2", turn_start(T0 + 10) + [
        ev(T0 + 30, "response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c1",
                                      "input": "python3 ~/.codex/skills/survey/survey.py wait 20261101-130000"})])
    r = cs.parse_session(p, now)
    check("설문 등록 대조 — 답 있음(answered)", r["state"] == "survey" and r["survey_status"] == "answered", r["survey_status"])
    p = write_session(base, "eeee-survey3", turn_start(T0 + 10) + [
        ev(T0 + 30, "response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c1",
                                      "input": "python3 survey.py wait 20261101-130000"}),
        ev(T0 + 40, "response_item", {"type": "custom_tool_call_output", "call_id": "c1", "output": [{"type": "text", "text": "{}"}]})])
    r = cs.parse_session(p, now)
    check("설문 명령 결과 도착 → 작업 중", r["state"] == "working" and r["open_calls"] == 0, r["state"])

    # 6. 설문 — request_user_input 도구 열림(확실)
    p = write_session(base, "ffff-ask", turn_start(T0 + 10) + [
        ev(T0 + 30, "response_item", {"type": "function_call", "name": "request_user_input", "call_id": "f1", "arguments": "{}"})])
    r = cs.parse_session(p, now)
    check("설문(request_user_input 열림)", r["state"] == "survey" and r["sure"], r["basis"])

    # 7. 권한 요청 — 승인 요청 이벤트가 마지막(토큰 집계는 진행 신호 아님)
    approval = [ev(T0 + 30, "response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c9", "input": "rm x"}),
                ev(T0 + 31, "event_msg", {"type": "exec_approval_request", "call_id": "c9"}),
                ev(T0 + 32, "event_msg", {"type": "token_count", "info": None})]
    p = write_session(base, "gggg-approval", turn_start(T0 + 10) + approval)
    r = cs.parse_session(p, now)
    check("권한 요청(승인 요청 이벤트)", r["state"] == "approval" and r["sure"] and r["state_label"] == "권한 요청", r["basis"])
    p = write_session(base, "gggg-approval2", turn_start(T0 + 10) + approval + [
        ev(T0 + 40, "response_item", {"type": "custom_tool_call_output", "call_id": "c9", "output": []})])
    r = cs.parse_session(p, now)
    check("승인 뒤 진행 기록 → 작업 중", r["state"] == "working", r["state"])

    # 8. 멈춘 작업 — 작업 중인데 오래 기록 없음(추정)
    p = write_session(base, "hhhh-stale", turn_start(T0 + 10))
    r = cs.parse_session(p, T0 + 10 + cs.STALE_SEC + 600)
    check("오래 기록 없는 작업 중 → 추정 · 연결 아님", r["state"] == "working" and not r["sure"] and "추정" in r["basis"]
          and not r["connected"], r["basis"])

    # 9. 턴 기록 없음 → 대기(추정)
    p = write_session(base, "iiii-empty", [])
    r = cs.parse_session(p, now)
    check("턴 기록 없음 → 대기(추정)", r["state"] == "idle" and not r["sure"] and r["context"]["pct"] is None, r["basis"])

    # 10. token_count 없이 token_usage_record 만 — 창은 task_started 값
    p = write_session(base, "jjjj-record", [
        ev(T0 + 10, "event_msg", {"type": "task_started", "turn_id": "u1", "model_context_window": 2000}),
        ev(T0 + 11, "token_usage_record", {"usage": {"input_tokens": 400, "output_tokens": 100, "total_tokens": 500}})])
    r = cs.parse_session(p, now)
    check("token_usage_record 로 맥락 %", r["context"]["pct"] == 25.0, r["context"])

    # 11. 큰 파일 — 끝 부분만 읽어도 머리(id) · 상태 · 맥락 유지
    old_tail = cs.TAIL_BYTES
    cs.TAIL_BYTES = 3000
    pad = [ev(T0 + 5, "response_item", {"type": "reasoning", "encrypted_content": "x" * 400}) for _ in range(40)]
    p = write_session(base, "kkkk-big", pad + turn_start(T0 + 10, used=600, window=1200))
    r = cs.parse_session(p, now)
    cs.TAIL_BYTES = old_tail
    check("큰 파일 끝만 읽기 — id · 상태 · %", r["id"] == "kkkk-big" and r["state"] == "working" and r["context"]["pct"] == 50.0,
          (r["id"], r["state"], r["context"]["pct"], p.stat().st_size))

    # 12. 목록 — 최근 순 · 개수 · id 거르기
    res = cs.list_sessions(home=tmp, limit=3, now=now)
    check("목록 개수 제한", len(res["sessions"]) == 3, len(res["sessions"]))
    res = cs.list_sessions(home=tmp, thread="dddd-survey", now=now)
    check("id 로 거르기", [s["id"] for s in res["sessions"]] == ["dddd-survey"], [s["id"] for s in res["sessions"]])
    res = cs.list_sessions(home=tmp / "없음", now=now)
    check("세션 폴더 없음 → 빈 목록 · 오류 글자", res["sessions"] == [] and "세션 폴더 없음" in res["error"], res.get("error"))

    shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"결과: {len(RESULTS) - len(bad)}/{len(RESULTS)} 통과" + (f" · 실패 {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
