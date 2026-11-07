# -*- coding: utf-8 -*-
r"""책 스티커 꼬리 질문 API 시험(브라우저 없음) — 페이지 서버 …/api/notes 의 thread 경로 · 꼬리 단위 409 · 옛 형식 notes.json

    py -3 devview/tests/test_note_thread.py          → PASS / FAIL

- 임시 작업 폴더(시험 notes.json · .codex-hub 2ND 등록) · 가짜 codex(받은 인자를 파일에 적음) · 실제 ~/.codex · 8701 무관
- 키트(같은 폴더 위에 bookkit/notes.py · .agents/skills/codex-hub/magic.py 가 있으면)는 notes.py answer --thread · magic.py show · answer-note 까지,
  없으면(로컬 devview) 답은 notes.json 을 직접 고쳐 흉내 낸다
- devview 는 빈 포트(페이지 서버 = +100)에 띄우고 끝나면 그 프로세스만 끈다
"""
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# devview.py · 키트(있으면) · 키트 도구
DEVVIEW = HERE.parent / "devview.py"
KIT = HERE.parents[1]
NOTES_PY = KIT / "bookkit" / "notes.py"
MAGIC = KIT / ".agents" / "skills" / "codex-hub" / "magic.py"
HAS_KIT = NOTES_PY.is_file() and MAGIC.is_file()
NAME = "_nt"


def free_port():
    """페이지 서버(+100)까지 비어 있는 포트"""
    for _ in range(200):
        p = random.randint(20000, 40000)
        try:
            with socket.socket() as s, socket.socket() as t:
                s.bind(("127.0.0.1", p))
                t.bind(("127.0.0.1", p + 100))
            return p
        except OSError:
            pass
    raise RuntimeError("빈 포트 없음")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fails = []

    # 단언 하나
    def check(ok, what, detail=""):
        print(("  ok   " if ok else "  FAIL ") + what + (f" | {str(detail)[:300]}" if detail and not ok else ""), flush=True)
        if not ok:
            fails.append(what)

    tmp = Path(tempfile.mkdtemp(prefix="note_thread_"))
    root = tmp / "proj"
    book = root / "bookkit" / "books" / NAME
    (book / "dist").mkdir(parents=True)
    nf = book / "notes.json"
    # 옛 형식(title · thread 없음) — 답 없는 a1 · 답 있는 b2
    old = [{"id": "a1a1a1a1", "ts": "2026-11-01 10:00:00", "doc": NAME, "slide": 3, "x": 0.1, "y": 0.1, "w": 0, "h": 0,
            "ctx": "p3 | 3장 | b=s3-Q1", "text": "DB 트랜잭션은 왜 묶나?"},
           {"id": "b2b2b2b2", "ts": "2026-11-01 10:01:00", "doc": NAME, "slide": 5, "x": 0.1, "y": 0.1, "w": 0, "h": 0,
            "ctx": "p5 | 4장 | b=s4-Q2", "text": "API 시험은 무엇부터?", "answer": "상태 코드부터 본다.", "answer_ts": "2026-11-01 11:00:00"}]
    nf.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    if HAS_KIT:
        shutil.copy(NOTES_PY, root / "bookkit" / "notes.py")
    hub = root / ".codex-hub"
    (hub / "sessions").mkdir(parents=True)
    (hub / "sessions" / "2nd.json").write_text(json.dumps({"nick": "2nd", "thread": "019a-2nd", "registered_at": "2026-11-03 00:00:00"}), encoding="utf-8")
    log = tmp / "queue.jsonl"
    fake = tmp / "fake_codex.py"
    fake.write_text("import json, os, sys\nargs = sys.argv[1:]\n"
                    "open(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8').write(json.dumps(args, ensure_ascii=False) + '\\n')\n"
                    "print('Queued message m-1.')\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    port = free_port()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(tmp / "codex"), DEVVIEW_CODEX=str(fake), FAKE_CODEX_LOG=str(log),
               HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    dv = subprocess.Popen([sys.executable, str(DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    api = f"http://127.0.0.1:{port + 100}/bookkit/books/{NAME}/dist/api/notes"

    # 요청 하나 → (상태 코드, json)
    def call(method, path="", body=None):
        data = json.dumps(body).encode() if body is not None else (b"{}" if method == "POST" else None)
        req = urllib.request.Request(api + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    # 가짜 codex 가 받은 메시지(--message= 뒤) 목록
    def queued():
        return [json.loads(x)[-1] for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []

    def disk():
        return {n["id"]: n for n in json.loads(nf.read_text(encoding="utf-8"))}

    # 2ND 답 흉내 — 키트면 notes.py · 아니면 notes.json 직접
    def answer(nid, text, thread=None, title=None):
        if HAS_KIT:
            cmd = [sys.executable, str(root / "bookkit" / "notes.py"), "answer", nid, text, "--book", str(book)]
            cmd += (["--thread", thread] if thread else []) + (["--title", title] if title else [])
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            return r.returncode == 0, r.stdout + r.stderr
        notes = json.loads(nf.read_text(encoding="utf-8"))
        for n in notes:
            if n["id"] == nid:
                if thread:
                    next(t for t in n["thread"] if t["id"] == thread).update(a=text, a_ts="2026-11-04 00:00:00")
                else:
                    n.update(answer=text, answer_ts="2026-11-04 00:00:00")
                if title:
                    n["title"] = title
        nf.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
        return True, ""

    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(api + f"?doc={NAME}", timeout=1).read(10)
                break
            except OSError:
                time.sleep(0.2)
        print(f"대상 devview = {DEVVIEW} · 키트 도구 {'있음' if HAS_KIT else '없음(직접 흉내)'}")
        code, lst = call("GET", f"?doc={NAME}")
        check(code == 200 and [n["id"] for n in lst] == ["a1a1a1a1", "b2b2b2b2"] and "thread" not in lst[1], "옛 형식 notes.json — 그대로 읽힘", lst)

        # 꼬리 질문 — 답 없는 원 질문에는 409 · 빈 글 400 · 없는 스티커 404
        code, d = call("POST", "/a1a1a1a1/thread", {"q": "x"})
        check(code == 409, "답 없는 스티커에 꼬리 질문 = 409", (code, d))
        check(call("POST", "/b2b2b2b2/thread", {"q": "  "})[0] == 400, "빈 꼬리 질문 = 400")
        check(call("POST", "/zzzz/thread", {"q": "x"})[0] == 404, "없는 스티커 꼬리 = 404")
        code, d = call("POST", "/b2b2b2b2/thread", {"q": "201 과 200 은 어떻게 갈라?"})
        check(code == 201 and d["thread"] == [{"id": "t1", "q": "201 과 200 은 어떻게 갈라?", "ts": d["thread"][0]["ts"]}],
              "꼬리 질문 등록 — 201 · thread[t1] {id, q, ts}", (code, d))
        check(disk()["b2b2b2b2"]["answer"] == "상태 코드부터 본다." and disk()["b2b2b2b2"]["thread"][0]["id"] == "t1", "notes.json — 원 답 그대로 · thread 추가")

        # 꼬리 마법봉 → 가짜 codex 메시지에 스티커 id + 꼬리 id + 원 질문 · 앞 답 · 꼬리 질문
        code, d = call("POST", "/b2b2b2b2/thread/t1/magic")
        rid1 = d.get("rid") if isinstance(d, dict) else None
        msg = queued()[-1] if queued() else ""
        check(code == 200 and rid1, "꼬리 t1 마법봉 = 200 · rid", (code, d))
        check(disk()["b2b2b2b2"]["thread"][0].get("magic_rid") == rid1 and not disk()["b2b2b2b2"].get("magic_rid"),
              "notes.json — thread[t1].magic_rid (원 질문 magic_rid 는 그대로 없음)", disk()["b2b2b2b2"])
        check("스티커 b2b2b2b2 · 꼬리 t1" in msg and "원 질문: API 시험은 무엇부터?" in msg and "앞 답: 상태 코드부터 본다." in msg
              and "꼬리 질문: 201 과 200 은 어떻게 갈라?" in msg and msg.endswith(f"$2nd-magic {rid1}"), "queue 글 — 스티커 id + 꼬리 id · 원 질문 · 앞 답 · 꼬리 질문", msg)
        req = json.loads((hub / "requests" / f"{rid1}.json").read_text(encoding="utf-8"))
        t = req["target"]
        check(t["kind"] == "note" and t["note"] == "b2b2b2b2" and t["thread"] == "t1" and t["orig_a"] == "상태 코드부터 본다."
              and req["question"] == "201 과 200 은 어떻게 갈라?", "요청 파일 — 답 자리 note · thread t1 · 맥락", t)

        # 꼬리 단위 409 — t1 답 전 재요청 409 · 다른 꼬리 t2 는 따로 200 · 원 질문(답 있음) 마법봉도 따로 200
        n_q = len(queued())
        code, d = call("POST", "/b2b2b2b2/thread/t1/magic")
        check(code == 409 and len(queued()) == n_q, "t1 답 전 다시 = 409 · queue 안 함", (code, d))
        code, d = call("POST", "/b2b2b2b2/thread", {"q": "204 는?"})
        check(code == 201 and [x["id"] for x in d["thread"]] == ["t1", "t2"], "꼬리 t2 등록 — 같은 스티커 안 고유 id", d)
        code, d = call("POST", "/b2b2b2b2/thread/t2/magic")
        rid2 = d.get("rid") if isinstance(d, dict) else None
        check(code == 200 and rid2 and rid2 != rid1, "t1 대기 중에도 t2 마법봉 = 200(꼬리 단위 판정)", (code, d))
        check(call("POST", "/b2b2b2b2/thread/t9/magic")[0] == 404, "없는 꼬리 마법봉 = 404")
        code, d = call("POST", "/a1a1a1a1/magic")
        check(code == 200, "답 없는 원 질문 마법봉 = 200", (code, d))
        check(call("POST", "/a1a1a1a1/magic")[0] == 409, "원 질문 답 전 다시 = 409(원 질문 단위)")
        rid_a = d.get("rid")
        m_a = queued()[-1]
        check("스티커 질문: DB 트랜잭션은 왜 묶나?" in m_a and "스티커 a1a1a1a1 — 답에 짧은 제목(--title" in m_a, "원 질문 queue 글 — 스티커 id · 짧은 제목 지시", m_a)

        # 답 달기 — 원 질문 + 제목 · 꼬리 t1(키트면 magic.py answer-note) · t2(notes.py --thread)
        if HAS_KIT:
            menv = dict(os.environ, CODEX_HUB_DIR=str(hub), CODEX_THREAD_ID="019a-2nd", PYTHONUTF8="1")
            r = subprocess.run([sys.executable, str(MAGIC), "show", rid1], cwd=root, env=menv, capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0 and "꼬리 질문 t1" in r.stdout and "원 질문: API 시험은 무엇부터?" in r.stdout and f"answer-note {rid1}" in r.stdout,
                  "magic.py show(꼬리) — 원 질문 · 꼬리 · 답 자리", r.stdout + r.stderr)
            r = subprocess.run([sys.executable, str(MAGIC), "show", rid_a], cwd=root, env=menv, capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0 and "--title" in r.stdout, "magic.py show(원 질문) — 답 자리에 --title", r.stdout + r.stderr)
            r = subprocess.run([sys.executable, str(MAGIC), "answer-note", rid1, "200 은 읽기 성공, 201 은 새로 만듦."], cwd=root, env=menv,
                               capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0 and "답 달음 [b2b2b2b2 · t1]" in r.stdout, "magic.py answer-note(꼬리) → notes.py --thread", r.stdout + r.stderr)
            r = subprocess.run([sys.executable, str(MAGIC), "answer-note", rid_a, "한 단위로 성공 · 실패하게 묶는다.", "--title", "DB 트랜잭션"], cwd=root,
                               env=menv, capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0, "magic.py answer-note --title(원 질문)", r.stdout + r.stderr)
        else:
            answer("b2b2b2b2", "200 은 읽기 성공, 201 은 새로 만듦.", thread="t1")
            answer("a1a1a1a1", "한 단위로 성공 · 실패하게 묶는다.", title="DB 트랜잭션")
        ok, out = answer("b2b2b2b2", "본문 없음.", thread="t2")
        check(ok, "꼬리 t2 답", out)
        b2, a1 = disk()["b2b2b2b2"], disk()["a1a1a1a1"]
        check(b2["thread"][0].get("a", "").startswith("200 은") and b2["thread"][0].get("a_ts") and b2["thread"][1].get("a") == "본문 없음."
              and b2["answer"] == "상태 코드부터 본다.", "notes.json — t1 · t2 에 a · a_ts · 원 답 그대로", b2)
        check(a1.get("answer", "").startswith("한 단위") and a1.get("title") == "DB 트랜잭션", "notes.json — 원 질문 답 + title", a1)
        if HAS_KIT:
            r = subprocess.run([sys.executable, str(root / "bookkit" / "notes.py"), "answer", "b2b2b2b2", "x", "--thread", "t9", "--book", str(book)],
                               capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 1 and "t9" in r.stdout, "notes.py answer --thread 없는 꼬리 = 실패", r.stdout)
            r = subprocess.run([sys.executable, str(root / "bookkit" / "notes.py"), "list", "--book", str(book)], capture_output=True, text=True, encoding="utf-8")
            check("답할 스티커 없음" in r.stdout, "모두 답한 뒤 list = 답할 스티커 없음", r.stdout)
        # 답 달린 뒤 — 꼬리 t1 다시 마법봉 = 200(답 달림 → 재요청 허용)
        code, d = call("POST", "/b2b2b2b2/thread/t1/magic")
        check(code == 200, "t1 답 달린 뒤 다시 마법봉 = 200", (code, d))
        # 옛 화면 경로(PATCH · DELETE)도 그대로
        check(call("PATCH", "/a1a1a1a1", {"x": 0.5})[0] == 200 and disk()["a1a1a1a1"]["x"] == 0.5 and disk()["a1a1a1a1"]["title"] == "DB 트랜잭션",
              "PATCH 자리 — title 보존")
        check(call("PATCH", "/b2b2b2b2/thread", {"x": 1})[0] == 404, "PATCH 하위 경로 = 404")
    finally:
        dv.terminate()
        try:
            dv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            dv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not fails else f"FAIL {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
