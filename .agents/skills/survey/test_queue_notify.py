#!/usr/bin/env python3
# 설문 완료 알림 시험 — 등록한 세션(CODEX_THREAD_ID)에 제출 · 취소 때 codex queue 가 불리는지
#   가짜 codex(받은 인자를 파일에 적음)를 PATH 앞에 두고 실제 서버로 등록 → 제출 → 취소
#   python3 .agents/skills/survey/test_queue_notify.py
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("survey.py")
# 실패 목록
FAILS = []


# 확인 하나 — 통과/실패 출력, 실패는 목록에 모음
def check(name: str, ok: bool) -> None:
    print(("  통과 " if ok else "  실패 ") + name, flush=True)
    if not ok:
        FAILS.append(name)


# 비어 있는 포트 하나
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# 가짜 codex 가 적은 인자 줄 — 생길 때까지 잠깐 봄(따로 띄운 프로세스라서). 없으면 None
def read_args(path: Path):
    for _ in range(50):
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path.read_text(encoding="utf-8").splitlines()
        time.sleep(0.1)
    return None


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if os.name == "nt":
        print("건너뜀 — 리눅스(키트 환경)에서 돌린다", flush=True)
        return 0
    # 임시 폴더 · 가짜 codex
    tmp = Path(tempfile.mkdtemp(prefix="survey_queue_"))
    (tmp / "bin").mkdir()
    fake = tmp / "bin" / "codex"
    fake.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$FAKE_OUT"\n', encoding="utf-8")
    fake.chmod(0o755)
    out = tmp / "args.txt"
    # 공통 환경 — 등록 목록은 임시 폴더 · 가짜 codex 를 먼저
    env = dict(os.environ, SURVEY_REGISTRY=str(tmp / "_registry.json"), FAKE_OUT=str(out),
               PATH=f"{tmp / 'bin'}:{os.environ.get('PATH', '')}")
    env.pop("SURVEY_NO_QUEUE", None)
    qfile = tmp / "q.json"
    qfile.write_text(json.dumps({"title": "알림 시험", "questions": [{"question": "고를 것", "options": ["A", "B"]}]},
                                ensure_ascii=False), encoding="utf-8")

    # 등록 — 세션 id 는 환경변수로(Codex 안과 같게)
    def new(thread_env: str = "", *extra):
        e = dict(env, CODEX_THREAD_ID=thread_env) if thread_env else {k: v for k, v in env.items() if k != "CODEX_THREAD_ID"}
        r = subprocess.run([sys.executable, str(TOOL), "--dir", str(tmp / "store"), "new", str(qfile), "--project", "시험", *extra],
                           capture_output=True, text=True, encoding="utf-8", timeout=30, env=e)
        return json.loads(r.stdout)

    port = free_port()
    server = subprocess.Popen([sys.executable, str(TOOL), "--dir", str(tmp / "store"), "serve", "--port", str(port)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", env=env)
    try:
        server.stdout.readline()
        base = f"http://127.0.0.1:{port}"

        def post(info, form):
            data = urllib.parse.urlencode(form).encode("utf-8")
            with urllib.request.urlopen(base + "/" + info["path"].lstrip("/"), data=data, timeout=10) as resp:
                return resp.status

        print("① 제출 → 완료 알림", flush=True)
        a = new("11111111-2222-3333-4444-555555555555")
        saved = json.loads(Path(a["file"]).read_text(encoding="utf-8"))
        check("등록 파일에 세션 id", saved.get("thread") == "11111111-2222-3333-4444-555555555555")
        check("next 안내에 «---설문 완료»", "---설문 완료" in a.get("next", ""))
        post(a, {"q1": "A", "_act": "submit"})
        args = read_args(out)
        check("codex queue --thread <세션> 으로 불림", args is not None and args[:3] == ["queue", "--thread",
                                                                                    "11111111-2222-3333-4444-555555555555"])
        check("메시지 = --message=@설문 ---설문 완료 · id · 제목 → result id",
              args is not None and len(args) == 4 and args[3].startswith(f"--message=@설문 ---설문 완료 · {a['id']} · 알림 시험")
              and args[3].endswith(f"result {a['id']}"))

        print("② 취소 → 취소 알림 · --thread 인자가 환경변수보다 먼저", flush=True)
        out.unlink()
        b = new("aaaa", "--thread", "bbbb")
        post(b, {"_act": "cancel"})
        args = read_args(out)
        check("--thread 인자 우선", args is not None and args[2] == "bbbb")
        check("취소 메시지", args is not None and args[3].startswith(f"--message=@설문 ---설문 취소 · {b['id']}"))

        print("③ 세션 id 없음 → 안 부름", flush=True)
        out.unlink()
        c = new("")
        post(c, {"q1": "B", "_act": "submit"})
        check("세션 없이 등록한 설문은 알림 없음", read_args(out) is None)
    finally:
        server.terminate()
        server.wait(timeout=10)

    print(f"\n결과: 실패 {len(FAILS)}", flush=True)
    for f in FAILS:
        print("  - " + f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
