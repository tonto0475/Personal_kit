# Codex 턴 중 끼어들기(steer) — 전용 앱 서버 소켓으로 글을 바로 넣는다 · 표준 라이브러리만
#   왜: codex queue 는 턴이 끝나야 들어간다 → MAIN 이 서브를 기다리는 동안 마법봉 · 질문 · 지시가 큐에 쌓였다(2026-11-05 대회 병목)
#   전제: ReadyStart 0번 줄이 띄운 앱 서버 + --remote TUI(내장 앱 서버 세션은 외부에서 steer 못 함 — thread not found)
#   보내는 순서: 소켓 접속 → thread/read 로 진행 중 턴 → 있으면 turn/steer · 없으면 turn/start($스킬이 주입되는 길)
#   실패 = SteerError → 부르는 쪽이 codex queue 로 물러난다
from __future__ import annotations

import base64
import json
import os
import re
import socket
import struct
import time
from pathlib import Path
from urllib.parse import urlsplit

# 앱 서버 소켓(readystart.py 의 SOCK_REL 과 같게) · 시험은 CODEX_HUB_SOCK
SOCK_REL = ".codex/rs/app.sock"
# Windows는 Unix 소켓 대신 loopback 전용 TCP. CODEX_HUB_SOCK으로 같은 주소를 지정할 수 있다.
WIN_SOCK = "ws://127.0.0.1:18702"
# 응답 기다리는 상한(초)
WAIT_SEC = 6
# 마법봉 끝 줄 — «$main-magic 요청id»
MAGIC_LINE = re.compile(r"^[$/]([a-z0-9-]+-magic) (\S+)$")


class SteerError(Exception):
    pass


# 소켓 경로
def sock_path():
    return os.environ.get("CODEX_HUB_SOCK") or (WIN_SOCK if os.name == "nt" else str(Path.home() / SOCK_REL))


# 주소를 검증한다. 인증 없는 TCP가 외부에 연결되지 않도록 숫자 loopback만 허용한다.
# path: 기존 Unix 경로 또는 ws://127.0.0.1:포트 → (TCP 여부, connect 인자, Host)
def 접속주소(path):
    path = os.fspath(path)
    if "://" not in path:
        return False, path, "localhost"
    try:
        u = urlsplit(path)
        if u.scheme == "wss":
            raise SteerError("wss는 지원하지 않음 — loopback ws만 허용")
        if (u.scheme != "ws" or u.hostname != "127.0.0.1" or u.username is not None
                or u.password is not None or u.path not in ("", "/") or u.query or u.fragment
                or u.port is None or not 1 <= u.port <= 65535):
            raise SteerError("TCP 주소는 ws://127.0.0.1:포트만 허용")
        return True, ("127.0.0.1", u.port), f"127.0.0.1:{u.port}"
    except ValueError:
        raise SteerError("올바르지 않은 앱 서버 주소") from None


# 턴 중 글 — 턴 중에는 $스킬이 주입되지 않아(0.163 실측) 끝 줄을 «스킬 파일을 읽어라» 로 바꾼다
# text: 쉬는 때 글
def midturn_text(text):
    head, _, last = text.rpartition("\n")
    m = MAGIC_LINE.match(last.strip())
    if not m:
        return text
    return (f"{head}\n먼저 ~/.codex/skills/{m.group(1)}/SKILL.md 를 읽고 그대로 따른다 · 요청 id {m.group(2)}"
            " · 서브가 남아 있으면 처리 뒤 다시 wait_agent")


# Unix 소켓 또는 loopback TCP 위 WebSocket — 앱 서버가 쓰는 만큼만
class Socket:
    # path: 소켓 경로
    def __init__(self, path):
        tcp, address, host = 접속주소(path)
        if not tcp and not hasattr(socket, "AF_UNIX"):
            raise SteerError("유닉스 소켓 없음")
        self.s = socket.socket(socket.AF_INET if tcp else socket.AF_UNIX)
        self.s.settimeout(WAIT_SEC)
        self.buf = b""
        try:
            self.s.connect(address)
            key = base64.b64encode(os.urandom(16)).decode()
            self.s.sendall((f"GET / HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            while b"\r\n\r\n" not in self.buf:
                chunk = self.s.recv(4096)
                if not chunk:
                    raise SteerError("핸드셰이크 중 끊김")
                self.buf += chunk
        except (OSError, SteerError) as e:
            self.s.close()
            raise SteerError(f"소켓 접속 실패 — {e}") from None
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            self.s.close()
            raise SteerError("핸드셰이크 거부")

    # 프레임 하나 쓰기(클라이언트는 마스킹)
    # data: 내용 / op: 프레임 종류
    def write(self, data, op=1):
        n = len(data)
        head = bytes([0x80 | op])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.s.sendall(head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))

    # 바이트 n 개
    def need(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise SteerError("앱 서버가 끊음")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    # 글 프레임 하나 읽기 — 핑은 답하고 넘긴다
    def read(self):
        acc = b""
        while True:
            a, b = self.need(2)
            n = b & 127
            if n == 126:
                n = struct.unpack(">H", self.need(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self.need(8))[0]
            data = self.need(n)
            op = a & 15
            if op == 9:
                self.write(data, 10)
                continue
            if op == 8:
                raise SteerError("앱 서버가 닫음")
            acc += data
            if a & 0x80:
                return acc.decode("utf-8", "replace")

    def close(self):
        self.s.close()


# 요청 하나 → 결과(오류면 SteerError) · 사이에 오는 알림은 버린다
# ws: 연결 / rid: 요청 번호 / method: 명령 / params: 인자
def call(ws, rid, method, params):
    ws.write(json.dumps({"id": rid, "method": method, "params": params}, ensure_ascii=False).encode("utf-8"))
    end = time.time() + WAIT_SEC
    while time.time() < end:
        o = json.loads(ws.read())
        if o.get("id") == rid and ("result" in o or "error" in o):
            if "error" in o:
                raise SteerError(f"{method} — {str((o['error'] or {}).get('message'))[:200]}")
            return o["result"] or {}
    raise SteerError(f"{method} 응답 없음")


# 진행 중 턴 id — 없으면 None
# ws: 연결 / thread: 세션 id
def active_turn(ws, thread):
    r = call(ws, 2, "thread/read", {"threadId": thread, "includeTurns": True})
    turns = (r.get("thread") or {}).get("turns") or []
    return next((t.get("id") for t in reversed(turns) if str(t.get("status")).lower().startswith("in")), None)


# 글 보내기 → "steer"(턴 중 바로) · "start"(쉬는 때 새 턴) · 실패면 SteerError
# thread: 세션 id / text: 쉬는 때 글 / path: 소켓(없으면 기본)
def send(thread, text, path=None):
    path = path or sock_path()
    tcp, _, _ = 접속주소(path)
    if not tcp and not os.path.exists(path):
        raise SteerError("앱 서버 소켓 없음")
    ws = Socket(path)
    try:
        call(ws, 1, "initialize", {"clientInfo": {"name": "devview", "title": "devview", "version": "1"},
                                   "capabilities": {"experimentalApi": True}})
        ws.write(json.dumps({"method": "initialized"}).encode())
        turn = active_turn(ws, thread)
        if turn:
            try:
                call(ws, 3, "turn/steer", {"threadId": thread, "expectedTurnId": turn, "input": items(midturn_text(text))})
                return "steer"
            except SteerError as e:
                # 읽은 뒤 턴이 끝남 — 쉬는 때로
                if "no active turn" not in str(e) and "expected" not in str(e).lower():
                    raise
        call(ws, 4, "turn/start", {"threadId": thread, "input": items(text)})
        return "start"
    except (OSError, ValueError) as e:
        raise SteerError(str(e)[:200]) from None
    finally:
        ws.close()


# 입력 항목
# text: 글
def items(text):
    return [{"type": "text", "text": text, "text_elements": []}]
