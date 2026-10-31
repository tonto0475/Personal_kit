#!/usr/bin/env python3
# Codex 쪽 설문 흐름 시험 — SKILL 1 · 3절을 Codex 가 하는 순서 그대로 따라 한다(리눅스 · python3)
#   python3 .agents/skills/survey/test_codex_flow.py
#   ① 키트의 devview 를 임시 git 저장소에 띄움 → ② 설문 탭 연결 확인(curl 과 같은 요청)
#   → ③ 저장소 루트에서 new 로 등록(--open 없이) → ④ wait 를 백그라운드로(출력 없음 = 대기 중)
#   → ⑤ devview 화면 주소로 제출(유저 클릭 대신) → ⑥ wait 가 제출 직후 결과 json 으로 끝나는가 · 걸린 시간
#   → ⑦ devview 목록에서 완료로 바뀌었나 → 정리(devview 는 PID 로만 종료)
# 실제 ~/workspace · 8701 · 설문 목록 파일은 건드리지 않는다(임시 폴더 · 빈 포트 · 임시 목록 파일)
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
KIT = HERE.parents[2]
TOOL = HERE / "survey.py"
DEVVIEW = KIT / "devview" / "devview.py"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  {'통과' if ok else '실패'} {name}{' — ' + str(detail)[:200] if detail else ''}", flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(url, form=None):
    data = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
    req = urllib.request.Request(url, data=data, headers={"X-Devview": "1"} if form is not None else {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="sv_codex_"))
    env = {**os.environ, "SURVEY_REGISTRY": str(tmp / "stores.json")}
    ws = tmp / "workspace"
    ws.mkdir()
    subprocess.run(["git", "init", "-q", str(ws)], check=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    dv = subprocess.Popen([sys.executable, str(DEVVIEW), str(ws), "--host", "0.0.0.0", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    waiter = None
    try:
        print("① devview 띄우기 · ② 설문 탭 연결", flush=True)
        state = None
        for _ in range(50):
            try:
                state = json.loads(http(f"{base}/sv/api/state")[1])
                break
            except OSError:
                time.sleep(0.2)
        check("설문 연결된 devview(상태 json 에 seen_ago)", state is not None and "seen_ago" in state, state)

        print("③ 등록(저장소 루트에서 · --open 없이)", flush=True)
        r = subprocess.run([sys.executable, str(TOOL), "new", str(HERE / "sample_questions.json"), "--project", "sample"],
                           cwd=ws, capture_output=True, text=True, encoding="utf-8", env=env)
        info = json.loads(r.stdout) if r.returncode == 0 else {}
        sid = info.get("id", "")
        check("new → 설문 id", r.returncode == 0 and sid, r.stdout + r.stderr)
        check("저장 위치 = 저장소/docs/surveys/sample", (ws / "docs" / "surveys" / "sample" / f"{sid}.json").exists())
        state = json.loads(http(f"{base}/sv/api/state")[1])
        check("devview 가 새 대기 설문을 봄(화면이 2초 안에 넘어가는 근거)", (state.get("newest") or {}).get("id") == sid
              and state.get("pending") == 1, state)

        print("④ wait 백그라운드 · ⑤ devview 화면으로 제출", flush=True)
        waiter = subprocess.Popen([sys.executable, str(TOOL), "wait", sid], cwd=ws, stdout=subprocess.PIPE,
                                  text=True, encoding="utf-8", env=env)
        time.sleep(2)
        check("제출 전 wait 는 출력 없이 대기", waiter.poll() is None)
        page = http(f"{base}/sv/?p=sample&id={sid}")[1]
        check("devview 설문 화면이 그 설문을 그림", "<form" in page and "name='q1'" in page)
        t0 = time.time()
        status, done = http(f"{base}/sv/survey/{sid}", {"q1": "(추천) 1초", "q1_memo": "시험 메모", "_act": "submit"})
        check("제출 → 완료 기록 화면", status == 200 and "완료" in done)

        print("⑥ wait 종료 · ⑦ 완료 목록", flush=True)
        out, _ = waiter.communicate(timeout=15)
        took = time.time() - t0
        res = json.loads(out) if out.strip() else {}
        check("wait 가 결과 json 으로 종료(종료코드 0)", waiter.returncode == 0 and res.get("action") == "accept", out[:120])
        check("결과에 고른 답 · 메모", res.get("answers", [{}])[0].get("choice") == "(추천) 1초"
              and res["answers"][0].get("memo") == "시험 메모")
        check("제출 → wait 종료 2초 이내", took < 2, f"{took:.2f}초")
        state = json.loads(http(f"{base}/sv/api/state")[1])
        check("devview 대기 0 · 완료로 바뀜", state.get("pending") == 0, state)
    finally:
        if waiter and waiter.poll() is None:
            waiter.kill()
        dv.terminate()
        dv.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    fails = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} 통과" + (f" · 실패: {fails}" if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
