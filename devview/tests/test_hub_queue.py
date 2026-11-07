"""허브 큐 보기 — ~/.codex/queue_1.sqlite 대기 글이 배지 · 펼침으로 보이나(임시 세계 · 헤드리스)

    py -3 devview/tests/test_hub_queue.py      종료코드 0 = 통과
"""
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_hub as th  # noqa: E402


# 시험 큐 파일 — Codex 0.163 표 그대로
# home: CODEX_HOME / thread: 세션 thread
def make_queue(home, thread):
    con = sqlite3.connect(Path(home) / "queue_1.sqlite")
    con.execute("create table queued_items (id text primary key not null, thread_id text not null, payload_json text not null,"
                " queue_order integer not null, created_at_ms integer not null, updated_at_ms integer not null)")
    now = int(time.time() * 1000)
    for i, t in enumerate(("🪄 첫 글 큐 시험", "둘째 글")):
        con.execute("insert into queued_items values (?,?,?,?,?,?)", (f"q{i}", thread, json.dumps({"input": [{"type": "text", "text": t}]}), i, now, now))
    con.commit()
    con.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix="dv_hubq_"))
    proc = None
    ok = True
    try:
        w = th.make_world(tmp)
        proc, base = th.start(w)
        code, d = th.http(base + "/api/hub")
        row = next(r for r in d["rows"] if r.get("thread"))
        assert row["queue"] == [], row["queue"]
        make_queue(w["home"], row["thread"])
        code, d = th.http(base + "/api/hub")
        row = next(r for r in d["rows"] if r["nick"] == row["nick"])
        texts = [x["text"] for x in row["queue"]]
        print("API", texts)
        ok &= texts == ["🪄 첫 글 큐 시험", "둘째 글"]
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            page = br.new_page(viewport={"width": 1500, "height": 900})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base + "/")
            page.wait_for_selector("html[data-ready='1']", timeout=30000)
            page.wait_for_selector(".dv-hub-q", timeout=8000)
            badge = page.locator(".dv-hub-q").first.inner_text()
            page.locator(".dv-hub-q").first.click()
            page.wait_for_selector(".dv-hub-queue:not([hidden])", timeout=4000)
            body = page.inner_text(".dv-hub-queue")
            print("화면", badge, "|", body.replace("\n", " / ")[:120], "| 오류", errs[:2])
            ok &= badge == "큐 2" and "첫 글 큐 시험" in body and "둘째 글" in body and not errs
            br.close()
    finally:
        if proc:
            proc.terminate()
        shutil.rmtree(tmp, ignore_errors=True)
    print("결과:", "통과" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
