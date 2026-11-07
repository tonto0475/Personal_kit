#!/usr/bin/env python3
# 시험용 임시 앱 — 과제 앱이 아직 없을 때 devview 앱 탭(Ctrl+Space) · Browser 도구로 «다른 포트가 보이나» 를 확인
#   python3 kit/scripts/demo_app/serve.py [--port 3000]      (0.0.0.0 · 표준 라이브러리만 · Ctrl+C 로 끝)
# 화면: 큰 글씨 «앱 탭 시험 — PORT 3000 OK» · 띄운 시각 · 누를 때마다 늘어나는 단추(화면이 살아 있나) · /health = ok
from __future__ import annotations

import argparse
import html
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 띄운 시각 — 화면에 보여서 «새로 띄운 서버인가» 를 가른다
STARTED = time.strftime("%H:%M:%S")


def page(port: int) -> bytes:
    return f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>demo {port}</title>
<style>body{{margin:0;font:20px/1.6 sans-serif;background:#10241a;color:#e8f5e9;display:flex;align-items:center;justify-content:center;height:100vh}}
main{{text-align:center}} h1{{font-size:40px;margin:0 0 8px;color:#81c995}} button{{font-size:20px;padding:8px 20px;border-radius:8px;border:0;cursor:pointer}}</style>
</head><body><main><h1 id='ok'>앱 탭 시험 — PORT {port} OK</h1>
<p>띄운 시각 {html.escape(STARTED)} · 이 화면이 보이면 devview 앱 탭(또는 Browser 도구)이 이 포트를 그린다</p>
<button id='b' onclick="this.textContent='누름 '+(++window.n)">누름 0</button><script>window.n=0</script>
</main></body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok" if self.path.startswith("/health") else page(self.server.server_port)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain" if self.path.startswith("/health") else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="시험용 임시 앱")
    ap.add_argument("--port", type=int, default=3000)
    port = ap.parse_args().port
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as e:
        print(f"포트 {port} 못 씀 — {e} (이미 떠 있으면 그대로 쓴다)")
        return 1
    print(f"시험 앱 0.0.0.0:{port} — devview 앱 탭(Ctrl+Space) PORT {port} · 끝내기 Ctrl+C", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
