"""답변 스트리밍 시험. python3 devview/tests/test_stream.py / py -3 ... --ui
표준 라이브러리 가짜 Unix WebSocket + API. --ui는 설치된 Playwright로 빈 포트의 시험 서버만 연다.
"""
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stream
import codex_hub


def 기다림(fn, limit=6):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        if fn():
            return True
        time.sleep(.02)
    return bool(fn())


def 정리(root):
    root = Path(root).resolve()
    assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
    for parent, dirs, files in os.walk(root, topdown=False):
        for name in files:
            Path(parent, name).unlink(missing_ok=True)
        for name in dirs:
            p = Path(parent, name)
            p.unlink() if p.is_symlink() else p.rmdir()
    root.rmdir()


def 항목(method='item/started', text='', phase='final_answer', iid='m1', thread='t1', turn='turn1', kind='agentMessage'):
    p = {'threadId': thread, 'turnId': turn}
    if method.endswith('/delta'):
        p.update(itemId=iid, delta=text)
    else:
        p['item'] = {'id': iid, 'type': kind, 'text': text, 'phase': phase}
    return {'method': method, 'params': p}


class 가짜서버:
    def __init__(self, states=None, reject=False, tcp=False):
        self.root = Path(tempfile.mkdtemp(prefix='dvstream_'))
        self.path = str(self.root / 'app.sock')
        self.states = states or {'t1': 'active'}
        self.reject = reject
        self.got = []
        self.connections = []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.sock = socket.socket(socket.AF_INET if tcp else socket.AF_UNIX)
        self.sock.bind(('127.0.0.1', 0) if tcp else self.path)
        if tcp:
            self.path = f'ws://127.0.0.1:{self.sock.getsockname()[1]}'
        self.sock.listen()
        self.sock.settimeout(.1)
        self.worker = threading.Thread(target=self.실행, daemon=True)
        self.worker.start()

    def 프레임(self, c):
        def take(n):
            data = b''
            while len(data) < n:
                chunk = c.recv(n-len(data))
                if not chunk:
                    raise EOFError
                data += chunk
            return data
        _, b = take(2)
        n = b & 127
        if n == 126:
            n = struct.unpack('>H', take(2))[0]
        elif n == 127:
            n = struct.unpack('>Q', take(8))[0]
        mask = take(4)
        data = take(n)
        return json.loads(bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def 전송(self, obj, c=None):
        data = json.dumps(obj, ensure_ascii=False).encode()
        frame = b'\x81' + (bytes([len(data)]) if len(data) < 126 else b'\x7e' + struct.pack('>H', len(data)) if len(data) < 65536 else b'\x7f' + struct.pack('>Q', len(data))) + data
        with self.lock:
            (c or self.connections[-1]).sendall(frame)

    def 실행(self):
        while not self.stop.is_set():
            try:
                c, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.connections.append(c)
            try:
                data = b''
                while b'\r\n\r\n' not in data:
                    data += c.recv(4096)
                c.sendall(b'HTTP/1.1 101 Switching Protocols\r\n\r\n')
                while not self.stop.is_set():
                    obj = self.프레임(c)
                    self.got.append(obj)
                    if 'id' not in obj:
                        continue
                    method = obj['method']
                    p = obj.get('params') or {}
                    result = {}
                    if method == 'thread/read':
                        result = {'thread': {'id': p['threadId'], 'status': {'type': self.states.get(p['threadId'], 'notLoaded')}}}
                    if self.reject and method == 'thread/resume':
                        self.전송({'id': obj['id'], 'error': {'message': 'unsupported'}}, c)
                    else:
                        self.전송({'id': obj['id'], 'result': result}, c)
            except (OSError, EOFError, ValueError):
                pass
            finally:
                c.close()

    def 횟수(self, method):
        return sum(x.get('method') == method for x in self.got)

    def 끊기(self):
        c = self.connections[-1]
        c.shutdown(socket.SHUT_RDWR)
        c.close()

    def 닫기(self):
        self.stop.set()
        for c in self.connections:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            c.close()
        self.sock.close()
        self.worker.join(2)
        정리(self.root)


class 메모리시험(unittest.TestCase):
    def setUp(self):
        self.c = stream.수집기('/no-devview-stream-socket')
        # 순수 상태 시험은 작업 스레드를 만들지 않는다.
        self.c.roots = {'test': {'t1'}}

    def test_delta_accumulates_and_completed_replaces(self):
        self.c.반영(항목())
        self.c.반영(항목('item/agentMessage/delta', '안'))
        self.c.반영(항목('item/agentMessage/delta', '녕'))
        self.assertEqual(self.c.목록('t1', [])[0]['text'], '안녕')
        self.c.반영(항목('item/completed', '정본'))
        self.c.반영(항목('item/agentMessage/delta', '늦은 조각'))
        self.assertEqual(self.c.목록('t1', [])[0]['text'], '정본')

    def test_commentary_is_note(self):
        self.c.반영(항목(text='진행', phase='commentary'))
        self.assertEqual(self.c.목록('t1', [])[0]['role'], 'note')

    def test_other_threads_reasoning_tools_tokens_ignored(self):
        for obj in [항목(text='다른 세션', thread='child'), 항목(text='생각', kind='reasoning'),
                    항목(text='명령', kind='commandExecution'), {'method': 'thread/tokenUsage/updated', 'params': {'threadId': 't1'}}]:
            self.c.반영(obj)
        self.assertEqual(self.c.목록('t1', []), [])

    def test_unknown_delta_does_not_show_suffix(self):
        self.c.반영(항목('item/agentMessage/delta', '뒷부분'))
        self.assertEqual(self.c.목록('t1', []), [])

    def test_duplicate_start_preserves_text(self):
        self.c.반영(항목(text='기존'))
        self.c.반영(항목())
        self.assertEqual(self.c.목록('t1', [])[0]['text'], '기존')

    def test_rollout_replaces_final_even_if_text_differs(self):
        self.c.반영(항목(text='부분 답'))
        self.assertEqual(self.c.목록('t1', [{'turn': 'turn1', 'role': 'assistant', 'text': '완성 답'}]), [])

    def test_note_dedup_does_not_hide_other_notes_same_turn(self):
        self.c.반영(항목(text='첫 진행', phase='commentary'))
        self.c.반영(항목(text='둘째 진행', phase='commentary', iid='m2'))
        out = self.c.목록('t1', [{'turn': 'turn1', 'role': 'note', 'text': '첫 진행\n'}])
        self.assertEqual([x['text'] for x in out], ['둘째 진행'])

    def test_abort_rollout_removes_unfinished_partial(self):
        self.c.반영(항목(text='부분 답'))
        self.assertEqual(self.c.목록('t1', [{'turn': 'turn1', 'role': 'error', 'text': '턴 중단됨'}]), [])

    def test_claude_api_has_no_socket_live(self):
        reg = {'main': {'thread': 'claude1', 'kind': 'claude'}}
        with (patch.object(codex_hub, 'sessions', return_value=reg),
              patch.object(codex_hub, 'claude_transcript', return_value=(Path('fake'), 'claude1', None)),
              patch.object(codex_hub, 'chat_items', return_value=[]), patch.object(stream, '등록'), patch.object(stream, '목록') as live):
            self.assertEqual(codex_hub.chat('/test', 'main')['live'], [])
            live.assert_not_called()

    def test_closed_or_notloaded_forgets_subscription_and_partial(self):
        for obj in [{'method': 'thread/closed', 'params': {'threadId': 't1'}},
                    {'method': 'thread/status/changed', 'params': {'threadId': 't1', 'status': {'type': 'notLoaded'}}}]:
            self.c.attached.add('t1')
            self.c.반영(항목(text='부분 답'))
            self.c.반영(obj)
            self.assertNotIn('t1', self.c.attached)
            self.assertEqual(self.c.목록('t1', []), [])

    def test_turn_and_item_ids_separate_same_text(self):
        self.c.반영(항목(text='답'))
        self.c.반영(항목(text='답', turn='turn2'))
        self.assertEqual(len(self.c.목록('t1', [])), 2)

    def test_unregister_removes_memory(self):
        self.c.반영(항목(text='답'))
        self.c.등록('test', [])
        self.assertEqual(self.c.목록('t1', []), [])

    def test_remote_address_does_not_start_worker(self):
        blocked = stream.수집기('ws://example.com:18702')
        blocked.등록('test', ['t1'])
        self.assertIsNone(blocked.worker)

    def test_windows_without_unix_is_quiet(self):
        with patch.object(stream, 'socket', __import__('types').SimpleNamespace()):
            self.c.등록('test', ['t1'])
            self.assertIsNone(self.c.worker)

    def test_api_live_has_separate_cursor(self):
        reg = {'main': {'thread': 't1'}}
        self.c.반영(항목(text='부분 답'))
        recorded = [{'turn': 'turn1', 'role': 'user', 'text': '질문'}]
        with (patch.object(codex_hub, 'sessions', return_value=reg), patch.object(codex_hub, 'rollout_for', return_value=Path('fake')),
             patch.object(codex_hub, 'chat_items', return_value=recorded), patch.object(stream, '등록'), patch.object(stream, '목록', side_effect=self.c.목록)):
            a = codex_hub.chat('/test', 'main', 1)
            self.assertEqual(a['total'], 1)
            self.assertEqual(a['items'], [])
            self.assertEqual(a['live'][0]['text'], '부분 답')
            recorded.append({'turn': 'turn1', 'role': 'assistant', 'text': '완성 답'})
            b = codex_hub.chat('/test', 'main', 1)
            self.assertEqual([x['text'] for x in b['items']], ['완성 답'])
            self.assertEqual(b['live'], [])


@unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'Windows에는 AF_UNIX 없음')
class 소켓시험(unittest.TestCase):
    tcp = False

    def setUp(self):
        self.f = 가짜서버({'t1': 'active', 'idle': 'idle', 'gone': 'notLoaded'}, tcp=self.tcp)
        self.c = stream.수집기(self.f.path)
        self.c.등록('test', ['t1', 'idle', 'gone'])
        self.assertTrue(기다림(lambda: self.f.횟수('thread/resume') == 1))

    def tearDown(self):
        self.c.중지()
        self.f.닫기()

    def test_only_active_registered_thread_resumed_without_overrides(self):
        resumes = [x['params'] for x in self.f.got if x['method'] == 'thread/resume']
        self.assertEqual(resumes, [{'threadId': 't1'}])
        self.assertFalse(any(x['method'] in ('turn/start', 'turn/steer') for x in self.f.got))

    def test_real_frames_stream_until_rollout_catches_up(self):
        self.f.전송(항목())
        self.f.전송(항목('item/agentMessage/delta', '첫 글'))
        self.assertTrue(기다림(lambda: self.c.목록('t1', []) and self.c.목록('t1', [])[0]['text'] == '첫 글'))
        self.f.전송(항목('item/completed', '완성 글'))
        self.assertTrue(기다림(lambda: self.c.목록('t1', [])[0]['text'] == '완성 글'))
        self.assertEqual(self.c.목록('t1', [{'turn': 'turn1', 'role': 'assistant', 'text': '완성 글'}]), [])

    def test_reconnect_reinitializes_and_streams_next_message(self):
        self.f.끊기()
        self.assertTrue(기다림(lambda: self.f.횟수('thread/resume') == 2))
        self.assertEqual(self.f.횟수('initialize'), 2)
        self.f.전송(항목(text='재접속 답'))
        self.assertTrue(기다림(lambda: bool(self.c.목록('t1', []))))
        self.assertEqual(self.c.목록('t1', [])[0]['text'], '재접속 답')

    def test_disconnect_clears_partial_before_reconnect(self):
        self.f.전송(항목(text='끊기기 전 부분 답'))
        self.assertTrue(기다림(lambda: bool(self.c.목록('t1', []))))
        self.f.reject = True
        self.f.끊기()
        self.assertTrue(기다림(lambda: not self.c.목록('t1', [])))
        self.assertTrue(기다림(lambda: self.f.횟수('thread/resume') == 2))
        self.assertEqual(self.c.목록('t1', []), [])

    def test_unloaded_thread_rejoins_after_becoming_active(self):
        self.f.states['t1'] = 'notLoaded'
        self.f.전송({'method': 'thread/status/changed', 'params': {'threadId': 't1', 'status': {'type': 'notLoaded'}}})
        self.assertTrue(기다림(lambda: 't1' not in self.c.attached))
        self.f.states['t1'] = 'active'
        self.assertTrue(기다림(lambda: self.f.횟수('thread/resume') == 2))

    def test_unregister_unsubscribes(self):
        self.c.등록('test', [])
        self.assertTrue(기다림(lambda: self.f.횟수('thread/unsubscribe') == 1))

    def test_unknown_server_method_is_ignored(self):
        self.f.전송({'method': 'server/newThing', 'params': {'threadId': 't1'}})
        self.f.전송(항목(text='정상'))
        self.assertTrue(기다림(lambda: bool(self.c.목록('t1', []))))

    def test_unsupported_resume_keeps_worker_alive(self):
        self.f.reject = True
        self.f.끊기()
        self.assertTrue(기다림(lambda: self.f.횟수('thread/resume') == 2))
        self.assertTrue(self.c.worker.is_alive())
        self.assertEqual(self.c.목록('t1', []), [])

    def test_stop_closes_own_connection(self):
        self.c.중지()
        self.assertFalse(self.c.worker.is_alive())


class TCP소켓시험(소켓시험):
    __unittest_skip__ = False
    tcp = True

    def test_large_unicode_delta(self):
        text = '큰 답변 한글 ' * 12000
        self.f.전송(항목())
        self.f.전송(항목('item/agentMessage/delta', text))
        self.assertTrue(기다림(lambda: self.c.목록('t1', []) and self.c.목록('t1', [])[0]['text'] == text))


def 화면시험():
    import test_hub as th
    from playwright.sync_api import sync_playwright
    root = Path(tempfile.mkdtemp(prefix='dvstream_ui_'))
    proc = None
    original = th.subprocess.run
    def run(args, *a, **kw):
        if args[0] == 'git':
            raise OSError('스트리밍 화면 시험에는 git fixture 불필요')
        return original(args, *a, **kw)
    try:
        with patch.object(th.subprocess, 'run', side_effect=run):
            w = th.make_world(root)
        proc, base = th.start(w, {'CODEX_HUB_SOCK': str(root/'absent.sock')})
        state = {'text': '첫 글', 'done': False}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            def respond(route):
                response = route.fetch()
                data = response.json()
                data['live'] = [] if state['done'] else [{'id': 'screen1', 'i': 'live:screen-turn:screen1', 'turn': 'screen-turn',
                                'role': 'assistant', 'text': state['text'], 'live': True, 'at': ''}]
                route.fulfill(response=response, json=data)
            page.route('**/api/hub/chat?*', respond)
            page.goto(base)
            page.locator('#chatTab').click()
            bubble = page.locator('[data-stream="screen1"]')
            bubble.wait_for()
            page.wait_for_function("document.querySelector('[data-stream=screen1]').textContent.includes('첫 글')")
            bubble.evaluate("e => e.dataset.preserved = 'yes'")
            state['text'] = '첫 글 다음 글'
            page.wait_for_function("document.querySelector('[data-stream=screen1]').textContent.includes('다음 글')")
            assert bubble.get_attribute('data-preserved') == 'yes', '본문 갱신이 기존 말풍선을 교체함'
            print('PASS 화면: 진행 중 본문 누적·같은 말풍선 유지')
            page.keyboard.press('Control+Shift+Comma')
            state['text'] += ' 접은 뒤 추가'
            page.wait_for_timeout(800)
            assert bubble.locator('.dv-cm-fold').count() == 1
            print('PASS 화면: 스트리밍 중 전체 접기·접힘 유지')
            # 같은 turn 정본을 실제 rollout에 추가하고 live를 치운다.
            path = w['rollouts']['main']
            events = [th.ev(time.time(), 'event_msg', {'type': 'task_started', 'turn_id': 'screen-turn'}),
                      th.ev(time.time(), 'response_item', {'type': 'message', 'role': 'assistant', 'phase': 'final_answer',
                                             'content': [{'type': 'output_text', 'text': '정본 화면 답'}]})]
            with path.open('a', encoding='utf-8') as f:
                for event in events:
                    f.write(json.dumps(event, ensure_ascii=False)+'\n')
            state['done'] = True
            page.wait_for_function("!document.querySelector('[data-stream=screen1]') && document.querySelector('.dv-chat-list').textContent.includes('정본 화면 답')")
            assert page.locator('.dv-msg.is-assistant').filter(has_text='정본 화면 답').count() == 1
            assert page.locator('.dv-msg.is-assistant').filter(has_text='정본 화면 답').locator('.dv-cm-fold').count() == 1
            print('PASS 화면: rollout 완성 답 하나로 교체·접힘 유지')
            assert not errors, errors
            print('PASS 화면: 브라우저 오류 없음')
            page.screenshot(path=str(root/'stream.png'))
            browser.close()
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(5)
            except __import__('subprocess').TimeoutExpired:
                proc.kill(); proc.wait()
        정리(root)


if __name__ == '__main__':
    ui = '--ui' in sys.argv
    if ui:
        sys.argv.remove('--ui')
    result = unittest.main(exit=False).result
    if ui and result.wasSuccessful():
        화면시험()
    sys.exit(0 if result.wasSuccessful() else 1)
