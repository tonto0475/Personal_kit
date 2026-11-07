"""턴 중 끼어들기(devview/steer.py) — 가짜 앱 서버로 보내는 순서 · 물러나기 판단

    python3 -m pytest -q devview/tests/test_steer.py      (Unix와 loopback TCP · Windows도 TCP 시험)
"""
import json
import os
import socket
import struct
import sys
import tempfile
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import steer  # noqa: E402

unix = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="유닉스 소켓 없음")


# 가짜 앱 서버 — 받은 명령을 기록 · turn 이 있으면 진행 중
class Fake:
    # turn: 진행 중 턴 id / steer_err: turn/steer 오류 글
    def __init__(self, turn=None, steer_err=None, tcp=False):
        self.turn, self.steer_err, self.got = turn, steer_err, []
        self.root = Path(tempfile.mkdtemp(prefix="st"))
        self.path = str(self.root / "a.sock")
        self.srv = socket.socket(socket.AF_INET if tcp else socket.AF_UNIX)
        self.srv.bind(("127.0.0.1", 0) if tcp else self.path)
        if tcp:
            self.path = f"ws://127.0.0.1:{self.srv.getsockname()[1]}"
        self.conn = None
        self.head = b""
        self.srv.listen(1)
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def frame(self, c):
        def take(n):
            data = b""
            while len(data) < n:
                chunk = c.recv(n - len(data))
                if not chunk:
                    raise EOFError
                data += chunk
            return data
        _, b = take(2)
        n = b & 127
        if n == 126:
            n = struct.unpack(">H", take(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", take(8))[0]
        mask, data = take(4), take(n)
        return bytes(x ^ mask[i % 4] for i, x in enumerate(data))

    def reply(self, c, o):
        d = json.dumps(o).encode()
        c.sendall(bytes([0x81]) + (bytes([len(d)]) if len(d) < 126 else bytes([126]) + struct.pack(">H", len(d)) if len(d) < 65536 else bytes([127]) + struct.pack(">Q", len(d))) + d)

    def run(self):
        try:
            c, _ = self.srv.accept()
        except OSError:
            return
        self.conn = c
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += c.recv(4096)
        self.head = buf
        c.sendall(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
        try:
            while True:
                o = json.loads(self.frame(c))
                self.got.append(o)
                if "id" not in o:
                    continue
                m = o["method"]
                self.reply(c, {"method": "note/any", "params": {}})   # 사이 알림은 버려야 한다
                if m == "thread/read":
                    turns = [{"id": "old", "status": "completed"}] + ([{"id": self.turn, "status": "inProgress"}] if self.turn else [])
                    self.reply(c, {"id": o["id"], "result": {"thread": {"turns": turns}}})
                elif m == "turn/steer" and self.steer_err:
                    self.reply(c, {"id": o["id"], "error": {"code": -32600, "message": self.steer_err}})
                else:
                    self.reply(c, {"id": o["id"], "result": {}})
        except (OSError, IndexError, ValueError, EOFError):
            pass

    def close(self):
        if self.conn:
            try:
                self.conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.conn.close()
        self.srv.close()
        self.worker.join(2)
        if not self.path.startswith("ws://"):
            Path(self.path).unlink(missing_ok=True)
        self.root.rmdir()


@pytest.fixture(params=["unix", "tcp"])
def fake(request):
    if request.param == "unix" and not hasattr(socket, "AF_UNIX"):
        pytest.skip("유닉스 소켓 없음")
    made = []
    def create(**kwargs):
        f = Fake(tcp=request.param == "tcp", **kwargs)
        made.append(f)
        return f
    yield create
    for f in made:
        f.close()


def names(f):
    return [o["method"] for o in f.got]


def test_midturn_text_replaces_magic_line():
    t = steer.midturn_text("🪄 지시\n$main-magic m1106-1")
    assert "$main-magic" not in t and "~/.codex/skills/main-magic/SKILL.md" in t and "m1106-1" in t and "wait_agent" in t
    assert steer.midturn_text("그냥 글") == "그냥 글"
    assert steer.midturn_text("두 줄\n그냥 글") == "두 줄\n그냥 글"


def test_no_socket_is_error():
    with pytest.raises(steer.SteerError):
        steer.send("t", "글", "/없는/경로.sock")


def test_busy_goes_steer_with_read_line(fake):
    f = fake(turn="t9")
    assert steer.send("th", "🪄 지시\n$main-magic m1", f.path) == "steer"
    o = next(x for x in f.got if x["method"] == "turn/steer")
    assert o["params"]["expectedTurnId"] == "t9" and "SKILL.md" in o["params"]["input"][0]["text"]
    assert "turn/start" not in names(f)


def test_idle_goes_start_with_skill_line(fake):
    f = fake()
    assert steer.send("th", "🪄 지시\n$main-magic m1", f.path) == "start"
    o = next(x for x in f.got if x["method"] == "turn/start")
    assert o["params"]["input"][0]["text"].endswith("$main-magic m1")


def test_turn_just_ended_falls_to_start(fake):
    f = fake(turn="t9", steer_err="no active turn to steer")
    assert steer.send("th", "글", f.path) == "start"


def test_other_error_raises_for_queue(fake):
    f = fake(turn="t9", steer_err="thread not found")
    with pytest.raises(steer.SteerError):
        steer.send("th", "글", f.path)


@pytest.mark.parametrize("url", [
    "ws://0.0.0.0:18702", "ws://localhost:18702", "ws://127.0.0.2:18702",
    "ws://192.168.1.2:18702", "ws://example.com:18702", "wss://127.0.0.1:18702",
    "http://127.0.0.1:18702", "ws://test:dummy@127.0.0.1:18702",
    "ws://127.0.0.1:18702/path", "ws://127.0.0.1:18702/?x=1",
    "ws://127.0.0.1:18702/#x", "ws://127.0.0.1:0", "ws://127.0.0.1:65536",
    "ws://127.0.0.1", "ws://[::1]:18702", "ws://[broken"
])
def test_tcp_unsafe_address_rejected_before_connect(url, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("거절할 주소에 소켓을 만들었음")
    monkeypatch.setattr(steer.socket, "socket", forbidden)
    with pytest.raises(steer.SteerError):
        steer.send("th", "글", url)


def test_platform_defaults_and_env_override(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(steer, "os", SimpleNamespace(name="nt", environ={}))
    assert steer.sock_path() == "ws://127.0.0.1:18702"
    monkeypatch.setattr(steer, "os", SimpleNamespace(name="posix", environ={}))
    assert steer.sock_path() == str(Path.home() / steer.SOCK_REL)
    monkeypatch.setattr(steer, "os", SimpleNamespace(name="nt", environ={"CODEX_HUB_SOCK": "ws://127.0.0.1:19999"}))
    assert steer.sock_path() == "ws://127.0.0.1:19999"


def test_tcp_large_unicode_input_and_host_header():
    f = Fake(turn="t9", tcp=True)
    try:
        text = "한글" * 20000
        assert steer.send("th", text, f.path) == "steer"
        sent = next(x for x in f.got if x["method"] == "turn/steer")
        assert sent["params"]["input"][0]["text"] == text
        assert f"Host: {f.path[5:]}".encode() in f.head
    finally:
        f.close()


def test_tcp_refused_is_steer_error():
    reserved = socket.socket(socket.AF_INET)
    reserved.bind(("127.0.0.1", 0))
    try:
        url = f"ws://127.0.0.1:{reserved.getsockname()[1]}"
        with pytest.raises(steer.SteerError):
            steer.send("th", "글", url)
    finally:
        reserved.close()
