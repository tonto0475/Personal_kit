#!/usr/bin/env python3
"""devview 알림 종 — 알림 등록(세션 · 서브가 한 줄로) · 저장 · 자동 수집(devview 서버). 표준 라이브러리만 · 파이썬 3.8+

    py -3 devview/notify.py add --kind done --title "t3 완료" --to graph:t3
    python3 devview/notify.py add --kind decide --title "결정 필요" --body "A/B 중 고르기" --to survey:<설문id>
    python3 devview/notify.py list [--unread]

저장: <키트>/.codex-hub/notify.jsonl — 덧붙이기만(잠금 파일 notify.jsonl.lock) · 서버가 꺼져 있어도 쓰기만 하면 다음에 읽음
  한 줄 = {"op":"add", id, ts, at, kind, level, title, body, to, src[, key][, node]} 또는 {"op":"read", ts, ids:[...]}
  node = 그래프 자동 수집의 노드 종류(task · verify · question · survey) — 종 목록 색(notify.js) · 옛 기록엔 없음
  키트 찾기: --kit → 환경변수 DEVVIEW_KIT → 지금 폴더에서 위로 .codex-hub/notify.jsonl 이 있는 곳
             → 지금 폴더/kit(AGENTS.md 있음) → 지금 폴더
--to: graph:<노드id> · book:<책>[:<스티커id>[:<꼬리id>]](스티커 없으면 그 책 마지막 판) · survey:<설문id> · hub:<닉> · file:<경로>[:<줄>] · view:<보기>
자동 수집(서버 Collector): tree.json 기록(작업 완료 · 이상 · 보류 / 검증 정상 · 비정상 / 질문 답 / 설문 반영)
  · 책 notes.json 답(answer · thread[].a) · 설문 도구 새 설문 · 전달 실패 · 허브 세션 입력 · 승인 대기
  처음 보는 출처는 기준점만 잡고(지금 기록은 알림 안 함) 그 뒤 새 기록만 알림 — 본 기록 열쇠는 notify_seen.json
"""
import argparse
import contextlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

# 저장 폴더 · 파일 이름(키트 안 — 허브와 같은 폴더라 .gitignore · Codex 샌드박스 쓰기 허용이 그대로)
DIR = ".codex-hub"
FEED = "notify.jsonl"
SEEN = "notify_seen.json"
# 종류 → 화면 이름
KINDS = {"done": "완료", "block": "이상", "hold": "보류", "pass": "정상", "fail": "비정상", "answer": "답변",
         "note": "책 답", "survey": "설문", "survey-ack": "설문 반영", "route-fail": "전달 실패", "hub": "세션 대기",
         "decide": "결정 필요", "magic": "마법봉", "queue-fail": "큐 전달 실패", "report": "서브 보고", "book": "책 새 판", "info": "알림"}
# 빨강(🔴)으로 보이는 종류
BAD = {"block", "fail", "route-fail", "queue-fail"}
# 제목 · 본문 최대 길이
TITLE_MAX = 200
BODY_MAX = 2000
# 잠금 기다리는 최대 초
LOCK_WAIT_SEC = 10


class NotifyError(Exception):
    pass


# ======= 경로 =======
# 키트 폴더 정하기
# given: --kit 값 / start: 찾기 시작 폴더(기본 지금 폴더)
def find_kit(given=None, start=None):
    if given:
        return Path(given).expanduser().resolve()
    if os.environ.get("DEVVIEW_KIT"):
        return Path(os.environ["DEVVIEW_KIT"]).expanduser().resolve()
    here = Path(start or os.getcwd()).resolve()
    for d in (here, *here.parents):
        if (d / DIR / FEED).is_file():
            return d
    if (here / "kit" / "AGENTS.md").is_file():
        return here / "kit"
    return here


def feed_path(kit):
    return Path(kit) / DIR / FEED


# ======= 잠금 · 쓰기 =======
# 잠금 — 알림 파일 옆 잠금 파일을 잡고 있는 동안만 쓰기(프로세스가 죽으면 운영체제가 풀어 줌)
# path: 알림 파일 경로
@contextlib.contextmanager
def locked(path):
    lp = Path(str(path) + ".lock")
    lp.parent.mkdir(parents=True, exist_ok=True)
    f = open(lp, "a+b")
    end = time.time() + LOCK_WAIT_SEC
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() > end:
                    raise NotifyError(f"잠금 대기 {LOCK_WAIT_SEC}초 초과: {lp}") from None
                time.sleep(0.01)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


# 줄 덧붙이기 — 잠금 안에서 한 번에(줄이 섞이지 않게)
# kit: 키트 / recs: 기록 목록
def append(kit, recs):
    p = feed_path(kit)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs).encode("utf-8")
    with locked(p):
        with open(p, "ab") as f:
            f.write(data)
            f.flush()


def new_id():
    return f"{int(time.time() * 1000):x}{os.urandom(3).hex()}"


def short(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


# 알림 한 칸 만들기
# kind: 종류 / title: 제목 / body: 본문 / to: 이동 대상 dict / src: 출처 / key: 자동 수집 열쇠 / at: 기록 시각 글자
# node: 그래프 노드 종류(자동 수집만)
def make(kind, title, body="", to=None, src="script", key=None, at=None, node=None):
    kind = str(kind or "info").strip()
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", kind):
        raise NotifyError(f"종류 «{kind}» — 영어 소문자 · 숫자 · - (예: {' · '.join(KINDS)})")
    title = str(title or "").strip()
    if not title:
        raise NotifyError("제목(--title) 없음")
    rec = {"op": "add", "id": new_id(), "ts": round(time.time(), 3), "at": at or time.strftime("%Y-%m-%d %H:%M:%S"),
           "kind": kind, "level": "bad" if kind in BAD else "", "title": title[:TITLE_MAX],
           "body": str(body or "").strip()[:BODY_MAX], "to": to or {}, "src": src}
    if key:
        rec["key"] = key
    if node:
        rec["node"] = str(node)
    return rec


# 알림 등록 — 반환: 기록
def add(kit, kind, title, body="", to=None, src="script"):
    rec = make(kind, title, body, to, src)
    append(kit, [rec])
    return rec


# 읽음 기록
def mark_read(kit, ids):
    ids = [str(i) for i in ids if i]
    if ids:
        append(kit, [{"op": "read", "ts": round(time.time(), 3), "ids": ids}])
    return len(ids)


# --to 글 → 이동 대상
# s: «graph:t3» 등
def parse_to(s):
    s = str(s or "").strip()
    if not s:
        return {}
    kind, _, rest = s.partition(":")
    if kind == "graph" and rest:
        return {"view": "graph", "node": rest}
    if kind == "book" and rest:
        parts = rest.split(":")
        if not parts[0]:
            raise NotifyError("book 은 book:<책>[:<스티커id>[:<꼬리id>]]")
        to = {"view": "book", "book": parts[0]}
        if len(parts) > 1 and parts[1]:
            to["note"] = parts[1]
        if len(parts) > 2 and parts[2]:
            to["t"] = parts[2]
        return to
    if kind == "survey" and rest:
        return {"view": "survey", "id": rest}
    if kind == "hub" and rest:
        return {"view": "chat", "nick": rest}
    if kind == "file" and rest:
        m = re.fullmatch(r"(.+?):(\d+)", rest)
        return {"view": "code", "path": m.group(1), "line": int(m.group(2))} if m else {"view": "code", "path": rest}
    if kind == "view" and rest:
        return {"view": rest}
    raise NotifyError(f"--to «{s}» — graph:<id> · book:<책>[:<스티커>] · survey:<id> · hub:<닉> · file:<경로>[:<줄>] · view:<보기>")


# ======= 읽기(서버) — 덧붙인 만큼만 이어 읽음 =======
class Feed:
    def __init__(self, kit):
        self.path = feed_path(kit)
        self.lock = threading.Lock()
        self.pos = 0
        self.items = {}       # id → 알림(넣은 순서)
        self.read = set()

    # 새 줄 읽기 — 줄 끝(\n)까지 온 것만 · 파일이 줄었으면(지움) 처음부터
    def refresh(self):
        with self.lock:
            try:
                size = self.path.stat().st_size
            except OSError:
                self.pos, self.items, self.read = 0, {}, set()
                return
            if size < self.pos:
                self.pos, self.items, self.read = 0, {}, set()
            if size == self.pos:
                return
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read(size - self.pos)
            end = data.rfind(b"\n")
            if end < 0:
                return
            self.pos += end + 1
            for line in data[:end].split(b"\n"):
                try:
                    r = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(r, dict):
                    continue
                if r.get("op") == "add" and r.get("id"):
                    self.items[str(r["id"])] = r
                elif r.get("op") == "read":
                    self.read.update(str(i) for i in r.get("ids") or [])

    # 화면용 — 최근 것이 위 · 안 읽은 개수는 전체 기준
    # limit: 최대 개수
    def view(self, limit=300):
        self.refresh()
        with self.lock:
            items = list(self.items.values())
            unread = [r["id"] for r in items if r["id"] not in self.read]
            out = [dict({k: v for k, v in r.items() if k not in ("op", "key")}, read=r["id"] in self.read)
                   for r in items[::-1][:limit]]
        return {"items": out, "unread": len(unread), "total": len(items), "unread_ids": unread}


# ======= 자동 수집 =======
def read_json(path):
    p = Path(path)
    for _ in range(40):
        try:
            if not p.is_file():
                return None
            return json.loads(p.read_text(encoding="utf-8"))
        except PermissionError:
            time.sleep(0.025)       # 윈도우 — 다른 프로세스가 os.replace 하는 순간
        except (OSError, ValueError):
            return None
    return None


# 그래프 노드 → 이동 대상(섹션 칸 screen 이 있으면 같이)
def node_to(n):
    to = {"view": "graph", "node": n["id"]}
    if n.get("screen") is not None:
        to["screen"] = n["screen"]
    if n.get("graph"):
        to["graph"] = n["graph"]
    return to


# tree.json → [(열쇠, 알림 칸 dict | None)] — 기록(events · runs · answers · acks)마다
def tree_events(tree):
    out = []
    for n in (tree or {}).get("nodes") or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nid, kind = str(n["id"]), n.get("kind")
        name = f"{nid} · {short(n.get('title') or '', 80)}".rstrip(" ·")
        if kind == "task":
            for e in n.get("events") or []:
                t = e.get("t") if isinstance(e, dict) else None
                if t in ("done", "block", "hold"):
                    out.append((f"tree:{nid}:ev:{e.get('seq')}:{t}:{e.get('ts')}",
                                dict(kind=t, title=name, body=e.get("note", ""), to=node_to(n), at=e.get("at"), node=kind)))
        elif kind == "verify":
            for r in n.get("runs") or []:
                if isinstance(r, dict) and r.get("result") in ("pass", "fail"):
                    out.append((f"tree:{nid}:run:{r.get('seq')}:{r.get('ts')}",
                                dict(kind=r["result"], title=name, body=r.get("note", ""), to=node_to(n), at=r.get("at"), node=kind)))
        elif kind == "question":
            for a in n.get("answers") or []:
                if isinstance(a, dict):
                    out.append((f"tree:{nid}:ans:{a.get('seq')}:{a.get('ts')}",
                                dict(kind="answer", title=name, body=a.get("short", ""), to=node_to(n), at=a.get("at"), node=kind)))
        elif kind == "survey":
            for a in n.get("acks") or []:
                if isinstance(a, dict):
                    out.append((f"tree:{nid}:ack:{a.get('seq')}:{a.get('ts')}",
                                dict(kind="survey-ack", title=name, body=a.get("note", ""), to=node_to(n), at=a.get("at"), node=kind)))
    return out


# notes.json(책 하나) → [(열쇠, 알림 칸)] — 답(answer) · 꼬리 질문 답(thread[].a)
# notes: 목록 / book: 책 폴더 이름
def notes_events(notes, book):
    out = []
    for n in notes if isinstance(notes, list) else []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nid = str(n["id"])
        label = short(n.get("title") or n.get("text") or nid, 60)
        if n.get("answer"):
            out.append((f"notes:{book}:{nid}:a:{n.get('answer_ts') or ''}",
                        dict(kind="note", title=f"{book} · {label}", body=short(n["answer"], 300),
                             to={"view": "book", "book": book, "note": nid}, at=n.get("answer_ts"))))
        for t in n.get("thread") or []:
            if isinstance(t, dict) and t.get("a") and t.get("id"):
                out.append((f"notes:{book}:{nid}:t:{t['id']}:{t.get('a_ts') or ''}",
                            dict(kind="note", title=f"{book} · 꼬리 · {short(t.get('q') or label, 60)}", body=short(t["a"], 300),
                                 to={"view": "book", "book": book, "note": nid, "t": str(t["id"])}, at=t.get("a_ts"))))
    return out


# 허브 행 목록(codex_hub.rows) → [(열쇠, 알림 칸)] — 입력 · 승인 대기로 바뀐 세션
def hub_events(res):
    out = []
    for r in (res or {}).get("rows") or []:
        st = r.get("state")
        if not r.get("registered") or st not in ("survey", "approval"):
            continue
        mark = r.get("last_event_at") or (r.get("done") or {}).get("id") or r.get("status_at") or ""
        out.append((f"hub:{r.get('nick')}:{st}:{mark}",
                    dict(kind="hub", title=f"{r.get('label') or r.get('nick')} {'입력 대기' if st == 'survey' else '승인 대기'}",
                         body=r.get("status") or "", to={"view": "chat", "nick": r.get("nick")})))
    return out


# 설문 도구(survey.py 모듈) → [(열쇠, 알림 칸 | None)] — 새 설문(답할 차례만 알림) · 전달 실패
# mod: survey 모듈 / cache: 결과 파일 읽기 캐시(경로 → (수정 시각, 결과))
def survey_events(mod, cache):
    out = []
    for key, st, pr, s in mod.all_surveys():
        sid = s["id"]
        to = {"view": "survey", "s": key, "p": pr, "id": sid}
        out.append((f"survey:new:{key}:{pr}:{sid}",
                    dict(kind="survey", title=f"새 설문 · {short(s.get('title'), 80)}", to=to) if s.get("state") == "pending" else None))
        if s.get("state") == "pending":
            continue
        try:
            rf = mod.result_file(mod.project_dir(st, pr), sid)
            mt = rf.stat().st_mtime_ns
        except (OSError, AttributeError):
            continue
        hit = cache.get(str(rf))
        if not hit or hit[0] != mt:
            hit = (mt, read_json(rf) or {})
            cache[str(rf)] = hit
        for i, r in enumerate(hit[1].get("route") or []):
            if isinstance(r, dict) and not r.get("ok"):
                out.append((f"survey:route:{key}:{pr}:{sid}:{i}:{r.get('to')}",
                            dict(kind="route-fail", title=f"설문 전달 실패 · {r.get('to')} · {short(s.get('title'), 60)}",
                                 body=str(r.get("error") or ""), to=to)))
    return out


class Collector:
    """devview 서버 안 자동 수집 — tick() 한 번 = 출처마다 새 기록을 알림으로 덧붙임
    kit: 키트 / tree_path: () → tree.json 경로 | None / survey: survey 모듈 | None / hub: codex_hub 모듈 | None
    book_path: (책 폴더 이름) → 작업 폴더 기준 html 경로 | None"""

    def __init__(self, kit, tree_path=None, survey=None, hub=None, book_path=None):
        self.kit = Path(kit)
        self.tree_path = tree_path
        self.survey = survey
        self.hub = hub
        self.book_path = book_path
        self.seen_path = self.kit / DIR / SEEN
        seen = read_json(self.seen_path) or {}
        self.sources = set(seen.get("sources") or [])
        self.keys = set(seen.get("keys") or [])
        self.n = 0
        self.cache = {}
        self.stamps = {}      # 출처 → 파일 지문(바뀌지 않았으면 건너뜀)
        self.errors = {}

    # 출처 목록 — 이름 → (지문, 사건 계산 함수) · 지문이 같으면 계산 안 함(None = 늘 계산)
    def sources_now(self):
        out = {}
        tp = self.tree_path() if self.tree_path else None
        if tp and Path(tp).is_file():
            out["tree"] = (self.stamp(tp), lambda: tree_events(read_json(tp)))
        for p in sorted((self.kit / "bookkit" / "books").glob("*/notes.json")):
            book = p.parent.name
            out[f"notes:{book}"] = (self.stamp(p), lambda p=p, book=book: notes_events(read_json(p), book))
        if self.survey is not None and self.n % 2 == 0:
            out["survey"] = (None, lambda: survey_events(self.survey, self.cache))
        if self.hub is not None and self.n % 2 == 0:
            out["hub"] = (None, lambda: hub_events(self.hub.rows(self.kit)))
        return out

    @staticmethod
    def stamp(p):
        try:
            st = Path(p).stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    # 한 번 훑기 — 반환: 새 알림 목록
    def tick(self):
        new, changed = [], False
        for name, (stamp, fn) in self.sources_now().items():
            if stamp is not None and self.stamps.get(name) == stamp:
                continue
            try:
                evs = fn()
            except Exception as e:          # 출처 하나가 깨져도 나머지는 계속
                self.errors[name] = f"{type(e).__name__}: {e}"
                continue
            self.errors.pop(name, None)
            self.stamps[name] = stamp
            first = name not in self.sources
            if first:
                self.sources.add(name)
                changed = True
            for key, rec in evs:
                if key in self.keys:
                    continue
                self.keys.add(key)
                changed = True
                if first or rec is None:
                    continue                 # 처음 보는 출처 = 기준점만
                to = rec.get("to") or {}
                if to.get("view") == "book" and self.book_path and not to.get("path"):
                    try:
                        to["path"] = self.book_path(to["book"]) or ""
                    except Exception:
                        pass
                new.append(make(rec["kind"], rec["title"], rec.get("body", ""), to, src=name.split(":")[0], key=key,
                                at=rec.get("at"), node=rec.get("node")))
        self.n += 1
        if new:
            append(self.kit, new)
        if changed:
            self.save()
        return new

    def save(self):
        p = self.seen_path
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"sources": sorted(self.sources), "keys": sorted(self.keys)}, ensure_ascii=False), encoding="utf-8")
        for _ in range(40):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:
                time.sleep(0.025)
        os.replace(tmp, p)

    # 뒤에서 계속 돌기
    # every: 간격 초 / log: (글) → None
    def start(self, every=1.5, log=None):
        def loop():
            while True:
                try:
                    self.tick()
                except Exception as e:
                    if log:
                        log(f"수집 실패: {type(e).__name__}: {e}")
                time.sleep(every)
        threading.Thread(target=loop, name="notify", daemon=True).start()


# ======= 명령 =======
def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        if st is not None and hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="devview 알림 종 — 알림 등록 · 목록")
    ap.add_argument("--kit", default=None, help="키트 폴더(기본: 위로 찾기 → 지금 폴더)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("add", help="알림 등록")
    a1.add_argument("--kind", default="info", help=" · ".join(f"{k}({v})" for k, v in KINDS.items()))
    a1.add_argument("--title", required=True)
    a1.add_argument("--body", default="")
    a1.add_argument("--to", default="", help="graph:<id> · book:<책>[:<스티커>[:<꼬리>]] · survey:<id> · hub:<닉> · file:<경로>[:<줄>] · view:<보기>")
    a1.add_argument("--kit", dest="kit2", default=None, help=argparse.SUPPRESS)
    a2 = sub.add_parser("list", help="알림 목록(최근 것이 위)")
    a2.add_argument("--unread", action="store_true")
    a2.add_argument("-n", type=int, default=20)
    a = ap.parse_args(argv)
    kit = find_kit(getattr(a, "kit2", None) or a.kit)
    try:
        if a.cmd == "add":
            rec = add(kit, a.kind, a.title, a.body, parse_to(a.to))
            print(f"알림 {rec['id']} → {feed_path(kit)}")
        else:
            v = Feed(kit).view(limit=100000)
            rows = [r for r in v["items"] if not (a.unread and r["read"])][:a.n]
            print(f"알림 {v['total']} · 안 읽음 {v['unread']} — {feed_path(kit)}")
            for r in rows:
                print(f"{'  ' if r['read'] else '* '}{r['at'][5:16]} [{KINDS.get(r['kind'], r['kind'])}] {r['title']}")
    except NotifyError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
