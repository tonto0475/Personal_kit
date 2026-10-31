#!/usr/bin/env python3
# 표 폼 시험 — 임시 폴더 · 빈 포트의 따로 띄운 서버로 등록 → 화면(X · △ · O 칸 · 행마다 메모 줄) → 제출 → 결과
#   python3 .agents/skills/survey/test_table_form.py
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

TOOL = Path(__file__).resolve().with_name("survey.py")
FAILS = []


def check(name: str, ok: bool) -> None:
    print(("  통과 " if ok else "  실패 ") + name, flush=True)
    if not ok:
        FAILS.append(name)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="sv_table_"))
    env = dict(os.environ, SURVEY_REGISTRY=str(tmp / "stores.json"))
    spec = {"title": "표 폼 시험", "columns": ["절", "동작"],
            "rows": [["0", "라이브러리 **확인**"], {"id": "1-1", "cells": ["1-1", "문서 세트"]}, ["2", "설정"]]}
    (tmp / "q.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOL), "--dir", str(tmp / "sv"), "new", str(tmp / "q.json"), "--project", "t"],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    out = json.loads(r.stdout)
    sid = out["id"]
    saved = json.loads(Path(out["file"]).read_text(encoding="utf-8"))
    check("등록 — 표 모드 · 머리 칸 · 행 3개", saved["mode"] == "table" and saved["columns"] == ["절", "동작"]
          and [q["id"] for q in saved["questions"]] == ["1", "1-1", "3"])
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(TOOL), "--dir", str(tmp / "sv"), "serve", "--host", "127.0.0.1",
                            "--port", str(port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}/"
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "api/state", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        st = json.loads(urllib.request.urlopen(base + "api/state").read())
        q = "?" + urllib.parse.urlencode({"s": st["newest"]["s"], "p": "t", "id": sid})
        page = urllib.request.urlopen(base + q).read().decode("utf-8")
        check("화면 — 표 · X · △ · O 머리", "class='grid'" in page and all(f">{m}</th>" in page for m in ("X", "△", "O")))
        check("화면 — 행마다 메모 줄 3개", page.count("class='mrow'") == 3 and "name='q3_memo'" in page)
        check("화면 — 칸 글 굵게", "<b>확인</b>" in page)
        form = urllib.parse.urlencode({"q1": "O", "q2": "△", "q2_memo": "나중에", "extra": "끝", "_act": "submit"}).encode()
        urllib.request.urlopen(urllib.request.Request(base + q, data=form, method="POST")).read()
        res = json.loads(subprocess.run([sys.executable, str(TOOL), "--dir", str(tmp / "sv"), "result", sid],
                                        capture_output=True, text=True, encoding="utf-8", env=env).stdout)
        a = res["answers"]
        check("결과 — O 대상 · △ 보류(메모) · 미선택", [(x["choice"], x["kind"], x["label"]) for x in a]
              == [("O", "target", "대상"), ("△", "hold", "보류"), ("", "none", "미선택")]
              and a[1]["memo"] == "나중에" and a[1]["text"] == "보류 — 나중에" and res["extra"] == "끝")
        done = urllib.request.urlopen(base + q).read().decode("utf-8")
        check("기록 보기 — 고른 칸 체크 · 읽기 전용", "value='O' checked disabled" in done and "readonly" in done)
    finally:
        srv.kill()
        srv.wait(5)
    print("결과: " + ("모두 통과" if not FAILS else f"실패 {len(FAILS)}개"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
