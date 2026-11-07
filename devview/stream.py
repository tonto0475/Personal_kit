from __future__ import annotations

# 등록된 실행 중 Codex 세션의 답변 조각만 읽는다. 소켓 없음/구판이면 rollout 표시를 유지한다.
# 0.163.0 실측: initialize/thread/read만으로는 delta 없음. 실행 중 thread/resume(threadId만)은
# TUI에 재합류하며 모델·강도·cwd·승인 설정을 유지한다. idle/notLoaded 세션을 깨우지 않는다.
import atexit
import json
import os
import select
import socket
import threading
import time

import steer

재시도 = 1.0
최대글자 = 2_000_000


class 수집기:
    def __init__(self, path=None):
        self.path = path
        self.lock = threading.RLock()
        self.roots = {}
        self.messages = {}
        self.worker = None
        self.stop = threading.Event()
        self.ws = None
        self.serial = 0
        self.attached = set()

    # root별 등록을 통째로 갱신한다. Claude와 등록되지 않은 서브는 구독하지 않는다.
    def 등록(self, root, threads):
        with self.lock:
            self.roots[str(root)] = set(threads)
            wanted = set().union(*self.roots.values())
            self.messages = {k: v for k, v in self.messages.items() if k in wanted}
            try:
                tcp, _, _ = steer.접속주소(self.path or steer.sock_path())
                supported = tcp or hasattr(socket, 'AF_UNIX')
            except steer.SteerError:
                supported = False
            if self.worker is None and wanted and supported:
                self.worker = threading.Thread(target=self.실행, name='devview-stream', daemon=True)
                self.worker.start()

    # rollout이 정본이다. 완료 기록으로 들어온 메시지는 조각 목록에서 제외한다.
    def 목록(self, thread, recorded):
        with self.lock:
            out = []
            for key, it in list(self.messages.get(thread, {}).items()):
                found = any(r.get('turn') == it['turn'] and
                            ((r.get('role') == 'error' and not it['done']) or
                             (r.get('role') == it['role'] and
                              (it['role'] == 'assistant' or str(r.get('text', '')).strip() == it['text'].strip())))
                            for r in recorded)
                if found:
                    del self.messages[thread][key]
                elif it['text']:
                    out.append({k: v for k, v in it.items() if k != 'done'})
            return out

    # agentMessage만 저장한다. reasoning·도구·토큰·다른 thread는 여기서 버린다.
    def 반영(self, obj):
        method, p = obj.get('method'), obj.get('params') or {}
        if not isinstance(p, dict):
            return
        thread, turn = p.get('threadId'), p.get('turnId')
        with self.lock:
            if thread not in set().union(*self.roots.values()):
                return
            if method == 'thread/closed' or (method == 'thread/status/changed' and (p.get('status') or {}).get('type') == 'notLoaded'):
                self.attached.discard(thread)
                self.messages.pop(thread, None)
                return
            if method not in ('item/started', 'item/completed', 'item/agentMessage/delta'):
                return
            item = p.get('item') or {}
            if method != 'item/agentMessage/delta' and item.get('type') != 'agentMessage':
                return
            iid = p.get('itemId') if method.endswith('/delta') else item.get('id')
            if not iid or not turn:
                return
            entries = self.messages.setdefault(thread, {})
            key = (turn, iid)
            existed = key in entries
            if key not in entries:
                if method.endswith('/delta'):
                    # 재접속 도중 시작을 놓친 항목의 뒷부분만 표시하지 않는다.
                    return
                phase = item.get('phase')
                if phase not in ('commentary', 'partial_answer', 'final_answer', None):
                    return
                entries[key] = {'id': iid, 'turn': turn, 'i': f'live:{turn}:{iid}',
                                'role': 'note' if phase in ('commentary', 'partial_answer') else 'assistant',
                                'text': '', 'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'live': True, 'done': False}
            it = entries[key]
            if method.endswith('/delta'):
                if not it['done'] and isinstance(p.get('delta'), str):
                    it['text'] = (it['text'] + p['delta'])[:최대글자]
            elif method == 'item/completed' or not existed:
                if isinstance(item.get('text'), str):
                    it['text'] = item['text'][:최대글자]
                it['done'] = method == 'item/completed'
            # API를 열지 않는 세션의 오래된 메시지가 무한히 쌓이지 않게 한다.
            while len(entries) > 256:
                del entries[next(iter(entries))]

    # 응답을 기다리는 중에도 delta를 처리한다.
    def 요청(self, ws, method, params):
        self.serial += 1
        rid = self.serial
        ws.write(json.dumps({'id': rid, 'method': method, 'params': params}).encode())
        end = time.monotonic() + steer.WAIT_SEC
        while not self.stop.is_set() and time.monotonic() < end:
            obj = json.loads(ws.read())
            if obj.get('id') == rid and ('result' in obj or 'error' in obj):
                if 'error' in obj:
                    raise steer.SteerError(method)
                return obj.get('result') or {}
            self.반영(obj)
        raise steer.SteerError('응답 대기 종료')

    def 실행(self):
        while not self.stop.is_set():
            ws = None
            try:
                path = self.path or steer.sock_path()
                tcp, _, _ = steer.접속주소(path)
                if not tcp and not os.path.exists(path):
                    self.stop.wait(재시도)
                    continue
                ws = steer.Socket(path)
                self.ws = ws
                self.요청(ws, 'initialize', {'clientInfo': {'name': 'devview_stream', 'version': '1'},
                                           'capabilities': {'experimentalApi': True}})
                ws.write(b'{"method":"initialized"}')
                self.attached = set()
                attached, retry = self.attached, {}
                scan = 0
                while not self.stop.is_set():
                    if time.monotonic() >= scan:
                        with self.lock:
                            wanted = set().union(*self.roots.values())
                        for thread in attached - wanted:
                            self.요청(ws, 'thread/unsubscribe', {'threadId': thread})
                            attached.discard(thread)
                        for thread in wanted - attached:
                            if retry.get(thread, 0) > time.monotonic():
                                continue
                            try:
                                state = self.요청(ws, 'thread/read', {'threadId': thread, 'includeTurns': False})
                                if (state.get('thread', {}).get('status') or {}).get('type') != 'active':
                                    continue
                                # 상태를 덮는 인자는 보내지 않는다. 실행 중 thread만 재합류한다.
                                resumed = self.요청(ws, 'thread/resume', {'threadId': thread})
                                attached.add(thread)
                                for turn in resumed.get('thread', {}).get('turns', []):
                                    if turn.get('status') != 'inProgress':
                                        continue
                                    for item in turn.get('items', []):
                                        # 재접속 시 서버가 돌려준 진행 중 본문으로 이어 받는다.
                                        with self.lock:
                                            prior = self.messages.get(thread, {}).get((turn['id'], item.get('id')))
                                            if prior and not prior['done'] and str(item.get('text', '')).startswith(prior['text']):
                                                prior['text'] = item['text'][:최대글자]
                                        self.반영({'method': 'item/started', 'params': {'threadId': thread,
                                                   'turnId': turn['id'], 'item': item}})
                            except steer.SteerError:
                                retry[thread] = time.monotonic() + 15
                        scan = time.monotonic() + 재시도
                    if select.select([ws.s], [], [], .2)[0] or ws.buf:
                        self.반영(json.loads(ws.read()))
            except (OSError, ValueError, steer.SteerError, TypeError, AttributeError):
                # 서버 재시작·연결 끊김·구판 프로토콜은 조용히 재접속한다.
                pass
            finally:
                # 연결 없는 동안 조각을 남기지 않는다. 완성 기록은 기존 rollout에서 보인다.
                with self.lock:
                    self.messages.clear()
                self.ws = None
                if ws:
                    ws.close()
            self.stop.wait(재시도)

    def 중지(self):
        self.stop.set()
        ws = self.ws
        if ws:
            try:
                ws.s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(2)


수집 = 수집기()
atexit.register(수집.중지)


def 등록(root, regs):
    수집.등록(root, [r['thread'] for r in regs.values() if r.get('thread') and r.get('kind') != 'claude'])


def 목록(thread, recorded):
    return 수집.목록(thread, recorded)
