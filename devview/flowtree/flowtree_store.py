# flowtree 공용 쓰기 통로 — tree.json 에 쓰는 길은 이것 하나(화면 server.py · 명령 flowtree.py 공용)
"""
쓰기 순서: 잠금 파일(tree.json.lock) 잡기 → 다시 읽기 → 고치기 → 임시 파일 → os.replace → 판 번호(rev) +1
  잠금: 리눅스 fcntl.flock · 윈도우 msvcrt.locking — 프로세스가 죽으면 운영체제가 풀어 줌(오래된 잠금이 남지 않음)
역할별로 쓸 수 있는 명령만 허용(OP_ROLES) — 남의 칸은 거부(StoreError)
  main: 작업 노드 · 작업 사건(start · hold · block · done) · 검증 노드 만들기
  2nd : 질문에 답변 준비 중 · 답 덧붙이기
  insp: 검증 중 · 보류 · 결과(runs) 덧붙이기
  user: 화면 — 질문 만들기 · 고치기 · 닫기 · 지우기(답 없을 때) · 질문 선 잇기 · 끊기
        · 설문 답(vote) · 작업 · 검증 고치기(edit) · 함수 표 칸(funcs) · 검증 항목 추가(check-add)
  main 추가: 설문 만들기(survey-add) · 설문 반영 기록(survey-ack) · 분석 결과 불러오기(import-analysis) · 지급 파일 노드(file-add)
        · 함수 표(add --func · funcs-set — 유저가 고친 칸은 못 덮음) · 이름 바뀜 반영 기록(funcs-ack) · 코드에서 설명 읽기(funcs-scan)
  user 추가: 화면 노드 추가 단추(node-add — 작업 · 검증 · 설문을 hand_off 그래프 맨 위에 · by user)
유저 칸(edit · 함수 표의 유저 칸(funcs[].user) · votes)은 에이전트 명령이 쓰지 않고, 에이전트 칸(제목 · 사건 · 결과 · 답)은 유저 명령이 덮지 않는다
  유저가 고친 제목 · 요약 · 설명은 edit 칸에 따로 두고 보여 줄 때만 위에 덮는다(eff) — 원래 글은 그대로
기록(작업 사건 events · 답 answers · 검증 결과 runs)은 덧붙이기만 — 이력 보존
상태는 저장하지 않고 기록에서 계산(status) — 화면(web/src/model.js workStatus)과 같은 규칙
기록마다 seq = 그 쓰기의 판 번호 — 기록 순서 · 화면 «확인한 기록 번호»(tree.user.json seen) 비교에 씀
노드마다 graph 칸(task 과제 파악 · hand_off 구현 진행 · 옛 이름 adr 도 읽음). 칸이 없으면 graph_of 규칙(부모를 따름 · 맨 위는 task)
  옛 tree.json 의 섹션 후보 · chosen · confirmed · from(ho- · adr- 복사본) 칸은 읽기만 하고 무시한다(지우지 않음)
파이썬 3.10 이상 · 표준 라이브러리만
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
from pathlib import Path

# tree.json 형식 번호(작업 · 검증 · 질문 노드가 있는 판)
FORMAT = 2
# 요약 · 결론 최대 글자 수
SUMMARY_MAX = 60
# 착수 후 이 초가 넘도록 완료가 없으면 «주황»(늦음)
LATE_SEC = 300
# 잠금 기다리는 최대 초
LOCK_WAIT_SEC = 15
# 화면 스위치 총 개수(Main + 섹션0 · 섹션1 …) — 이 값 하나로 화면(meta.screens)과 --section 범위가 같이 바뀜
SCREENS = 10
# 섹션 틀 — 작업 노드 수(세로로 이음) · 작업마다 왼쪽 설문 수 · 오른쪽 검증 수(두 줄) — 아직 안 깐 섹션에만 적용
FRAME_TASKS = 4
FRAME_SURVEYS = 2
FRAME_VERIFIES = 4
# 틀 처음 위치 간격 — 작업 세로 · 설문 x · 검증 x · 설문 · 검증 세로 줄 간격
FRAME_DY, FRAME_SX, FRAME_VX, FRAME_VH = 640, 360, 340, 144
# 역할 이름 목록
ROLES = ("main", "2nd", "insp", "user")
# 일 노드 종류 → 이름
WORK_KINDS = {"task": "작업", "verify": "검증", "question": "질문", "survey": "설문"}
# 작업 사건 → 이름
TASK_EVENTS = {"start": "착수", "hold": "보류", "block": "이상", "done": "완료"}
# 명령 → 쓸 수 있는 역할
OP_ROLES = {
    "add": "main", "start": "main", "hold": "main", "block": "main", "done": "main", "verify-add": "main",
    "answer-start": "2nd", "answer": "2nd",
    "verify-start": "insp", "verify-hold": "insp", "run": "insp",
    "ask": "user", "ask-edit": "user", "ask-close": "user", "ask-del": "user", "link": "user", "unlink": "user",
    "survey-add": "main", "survey-ack": "main", "import-analysis": "main", "file-add": "main",
    "funcs-set": "main", "funcs-ack": "main", "funcs-scan": "main", "section-set": "main", "fill": "main",
    "node-add": "user", "node-del": "user", "mark": "user",
    "vote": "user", "edit": "user", "funcs": "user", "check-add": "user",
}
# 유저가 고칠 수 있는 노드 종류(edit) — 작업 · 검증 · 설문(질문 칸)
EDITABLE_KINDS = ("task", "verify", "survey")
# edit 로 고치는 칸
EDIT_FIELDS = ("title", "summary", "text", "script")
# 분류 다섯(bookkit 계약 CATS 와 같은 순서)
CATS = ("화면", "시스템", "알고리즘", "파이프라인", "문서")
# 불러온 노드 제목 최대 글자(넘으면 줄이고 전문은 설명에)
IMPORT_TITLE_MAX = 18
# «안 줌» 표시(vote · edit 인자) — None 과 구분
KEEP = object()
# 질문 선 대상으로 받는 화면 노드 id 접두어(코드 모듈 · 함수 · 외부 라이브러리)
SCREEN_PREFIX = ("mod:", "fn:", "ext:")
# 구현 진행 그래프 이름(개편 2026-11-03 — 옛 이름 «adr»)
HAND_OFF = "hand_off"
# 그래프 이름 목록
GRAPHS = ("task", HAND_OFF)
# 옛 그래프 이름 → 지금 이름(읽을 때 받기 · 명령 인자도 받음)
OLD_GRAPHS = {"adr": HAND_OFF}
# 화면 노드 추가 단추로 만드는 종류(node-add) → id 접두어
USER_ADD_KINDS = {"task": "t", "verify": "v", "survey": "s"}
# 두 그래프에 함께 보이는 종류(모듈 열)
SHARED_KINDS = {"module"}
# 상태 → 이름(종류별로 다른 «미완» 은 TODO_LABEL)
STATUS_LABEL = {
    "doing": "착수", "late": "착수 5분 넘음", "hold": "보류", "block": "이상", "done": "완료",
    "checking": "검증 중", "pass": "정상", "fail": "비정상", "answering": "답변 준비 중", "answered": "답변 완료",
    "picked": "선택됨", "held": "보류",
}
# 종류 → 처음 상태 이름
TODO_LABEL = {"task": "미완", "verify": "미검증", "question": "미답변", "survey": "미응답"}
# 결과 상태(유저가 확인하기 전 점멸) 목록 — 설문 선택됨 · 보류는 유저가 만든 결과라 점멸 없음
RESULT_STATES = {"hold", "block", "done", "pass", "fail", "answered"}


# 거부 · 실패 — 원인 한 줄
class StoreError(Exception):
    pass


# 지금 시각 — (글자, 초)
def now_stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S"), int(time.time())


# 빈 그래프
def empty_tree():
    return {"version": FORMAT, "rev": 0, "title": "", "nodes": [], "edges": []}


# JSON 읽기 — 윈도우에서 다른 프로세스가 os.replace 하는 순간이면 PermissionError → 잠깐 쉬고 다시
# path: 파일 경로 / default: 없을 때 값
def read_json(path, default=None):
    # 파일 경로
    p = Path(path)
    for _ in range(80):
        try:
            if not p.exists():
                return default
            return json.loads(p.read_text(encoding="utf-8"))
        # 교체 중 — 다시
        except PermissionError:
            time.sleep(0.025)
    return json.loads(p.read_text(encoding="utf-8"))


# 임시 파일에 쓰고 교체 — 읽는 쪽이 파일을 열고 있으면 윈도우가 교체를 막으므로 잠깐 쉬고 다시
# path: 대상 파일 / data: 내용
def write_json(path, data):
    # 대상 경로 — 폴더가 없으면 만듦(빈 그래프로 시작한 뒤 첫 저장)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 임시 파일 경로 — 프로세스마다 다른 이름
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for _ in range(120):
        try:
            os.replace(tmp, path)
            return
        # 읽는 중 — 다시
        except PermissionError:
            time.sleep(0.025)
    os.replace(tmp, path)


# 잠금 — tree.json 옆 잠금 파일을 잡고 있는 동안만 쓰기
# tree_path: tree.json 경로
@contextlib.contextmanager
def locked(tree_path):
    # 잠금 파일 경로
    lp = Path(str(tree_path) + ".lock")
    lp.parent.mkdir(parents=True, exist_ok=True)
    # 잠금 파일
    f = open(lp, "a+b")
    # 기다림 끝 시각
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
            # 다른 쓰기 중
            except OSError:
                if time.time() > end:
                    raise StoreError(f"잠금 대기 {LOCK_WAIT_SEC}초 초과: {lp}") from None
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
        # 잡지 못한 채 끝남
        except OSError:
            pass
        f.close()


# 틀 깔기 — 아직 안 깐 섹션에만 한 번(tree.framed 기록 · 유저가 옮기거나 지운 노드는 다시 안 깖)
#   빈 틀 노드 = frame 칸 true · pos0 = 섹션 화면 처음 위치 · 선은 tree.edges(sh · th = 손잡이)
# tree: 그래프 / rev: 판 번호
def lay_frames(tree, rev):
    # 깐 섹션 · 시각
    done = set(tree.get("framed") or [])
    at, _ = now_stamp()
    for s in range(SCREENS - 1):
        if s in done:
            continue
        # 앞 작업 id
        prev = None
        for k in range(FRAME_TASKS):
            # 작업 id · 세로 위치
            tid, y = f"s{s}-t{k + 1}", k * FRAME_DY
            # 틀 노드 공통 칸
            base = {"graph": HAND_OFF, "title": "", "screen": s, "frame": True, "seq": rev, "at": at, "by": "main"}
            tree["nodes"].append({"id": tid, "kind": "task", **base, "pos0": [0, y], "events": []})
            if prev:
                tree["edges"].append({"id": f"fe-{tid}", "source": prev, "target": tid, "kind": "flow"})
            prev = tid
            # 설문 — 왼쪽 세로 줄 · 하나하나 작업에 직접(병렬)
            for i in range(FRAME_SURVEYS):
                # 설문 id
                sid = f"{tid}-s{i + 1}"
                tree["nodes"].append({"id": sid, "kind": "survey", **base, "parent": tid,
                                      "pos0": [-FRAME_SX, y + int((i - (FRAME_SURVEYS - 1) / 2) * FRAME_VH)],
                                      "options": [], "votes": [], "acks": []})
                tree["edges"].append({"id": f"fe-{sid}", "source": sid, "target": tid, "kind": "flow", "sh": "r", "th": "l"})
            # 검증 — 오른쪽 세로 줄 · 하나하나 작업에서 직접(병렬)
            for j in range(FRAME_VERIFIES):
                # 검증 id
                vid = f"{tid}-v{j + 1}"
                tree["nodes"].append({"id": vid, "kind": "verify", **base, "parent": tid, "events": [], "runs": [],
                                      "pos0": [FRAME_VX, y + int((j - (FRAME_VERIFIES - 1) / 2) * FRAME_VH)]})
                tree["edges"].append({"id": f"fe-{vid}", "source": tid, "target": vid, "kind": "flow", "sh": "r", "th": "l"})
        done.add(s)
    tree["framed"] = sorted(done)


# 내용이 들어온 틀 노드 → 일반 노드(frame 칸을 뗌)
# tree: 그래프
def unframe(tree):
    for n in tree["nodes"]:
        if isinstance(n, dict) and n.get("frame") and any(n.get(k) for k in (
                "title", "summary", "text", "script", "edit", "funcs", "options", "doc", "events", "runs", "votes")):
            del n["frame"]


# 그래프 파일이 없거나 틀이 덜 깔렸으면 깖(새 작업 폴더에서 화면을 처음 열어도 틀이 보이게)
# tree_path: tree.json 경로
def ensure_frames(tree_path):
    # 지금 그래프
    tree = read_json(tree_path, None)
    if not Path(tree_path).exists() or (isinstance(tree, dict) and not set(range(SCREENS - 1)) <= set(tree.get("framed") or [])):
        mutate(tree_path, lambda t, rev: None)


# 잠금 → 다시 읽기 → fn(그래프, 새 판 번호) → 교체 → 판 번호 +1. fn 의 반환값을 돌려줌
# tree_path: tree.json 경로 / fn: 고치는 함수
def mutate(tree_path, fn):
    # 대상 경로
    path = Path(tree_path)
    with locked(path):
        # 지금 그래프
        tree = read_json(path, None)
        if tree is None:
            tree = empty_tree()
        if not isinstance(tree, dict) or not isinstance(tree.get("nodes", []), list):
            raise StoreError(f"tree.json 형식 오류: {path}")
        tree.setdefault("nodes", [])
        tree.setdefault("edges", [])
        # 새 판 번호
        rev = int(tree.get("rev") or 0) + 1
        lay_frames(tree, rev)
        # 고친 결과
        res = fn(tree, rev)
        unframe(tree)
        tree["rev"] = rev
        write_json(path, tree)
        return res


# 명령 하나 실행 — 역할 확인 → 잠금 쓰기. 반환 {id?, msg}
# tree_path: tree.json 경로 / role: 역할 / op: 명령 / args: 명령 인자
def apply(tree_path, role, op, **args):
    if role not in ROLES:
        raise StoreError(f"모르는 역할 «{role}» — {' · '.join(ROLES)}")
    # 이 명령을 쓸 수 있는 역할
    need = OP_ROLES.get(op)
    if need is None:
        raise StoreError(f"모르는 명령 «{op}»")
    if need != role:
        raise StoreError(f"«{op}» 는 {need} 명령 — 지금 역할 {role}")
    return mutate(tree_path, lambda tree, rev: OPS[op](tree, rev, role, **args))


# ======= 명령 본체 — (그래프, 판 번호, 역할, 인자) → {id?, msg} =======
# id → 노드 사전
# tree: 그래프
def node_map(tree):
    return {n.get("id"): n for n in tree.get("nodes", []) if isinstance(n, dict) and n.get("id")}


# 노드 찾기 — 없거나 종류가 다르면 거부
# tree: 그래프 / nid: 노드 id / kind: 바라는 종류(없으면 아무거나)
def need_node(tree, nid, kind=None):
    # 노드
    n = node_map(tree).get(nid)
    if n is None:
        raise StoreError(f"없는 id «{nid}»")
    if kind and n.get("kind") != kind:
        raise StoreError(f"«{nid}» 는 {WORK_KINDS.get(n.get('kind'), n.get('kind'))} — {WORK_KINDS[kind]} 아님")
    return n


# 다음 id — 접두어 + (가장 큰 번호 + 1). 노드 · 선 id 를 함께 봄
# tree: 그래프 / prefix: 접두어(t · v · q · a)
def next_id(tree, prefix):
    # 쓰인 id 집합
    ids = {str(n.get("id")) for n in tree["nodes"] if isinstance(n, dict)} | {str(e.get("id")) for e in tree["edges"] if isinstance(e, dict)}
    # 같은 접두어 번호 목록
    nums = [int(m.group(1)) for i in ids for m in [re.fullmatch(re.escape(prefix) + r"(\d+)", i)] if m]
    return f"{prefix}{max(nums, default=0) + 1}"


# 기록 한 칸 — seq · 시각 · 쓴 역할 + 내용(빈 칸 제외)
# rev: 판 번호 / role: 역할 / kw: 내용
def record(rev, role, **kw):
    # 시각 글자 · 초
    at, ts = now_stamp()
    return {"seq": rev, "at": at, "ts": ts, "by": role, **{k: v for k, v in kw.items() if v not in (None, "")}}


# 빈 글자 거부
# v: 값 / what: 이름
def need_text(v, what):
    # 앞뒤 공백 뺀 값
    v = str(v or "").strip()
    if not v:
        raise StoreError(f"{what} 없음")
    return v


# 60자 넘으면 거부
# s: 글자 / what: 이름
def check_short(s, what):
    if len(s) > SUMMARY_MAX:
        raise StoreError(f"{what} {len(s)}자 — {SUMMARY_MAX}자 이내")


# 연결 문서 글자(«경로#앵커») → {path, anchor}
# s: 글자
def parse_doc(s):
    # 경로 · 앵커
    path, _, anchor = str(s).partition("#")
    if not path.strip():
        raise StoreError("문서 경로 없음 — «경로#앵커»")
    return {"path": path.strip(), "anchor": anchor.strip()} if anchor.strip() else {"path": path.strip()}


# 섹션 값 다듬기 → 번호 · 없음 · «-» 은 None(칸 없음). 칸 이름은 screen(section 은 묶음 노드가 이미 씀)
# v: 섹션 값
def norm_section(v):
    if v in (None, "", "-"):
        return None
    try:
        # 번호
        s = int(v)
    except (TypeError, ValueError):
        s = -1
    if not 0 <= s <= SCREENS - 2:
        raise StoreError(f"섹션 «{v}» — 0 ~ {SCREENS - 2}")
    return s


# 그래프 이름 다듬기 — 옛 이름(adr)은 지금 이름(hand_off)으로 · 그 밖은 그대로
# g: 그래프 이름
def norm_graph(g):
    return OLD_GRAPHS.get(g, g)


# 노드가 속한 그래프 — graph 칸 > 질문은 놓인 화면(hand_off · adr · code 면 hand_off) > 모듈은 둘 다(both) > 부모를 따름 > 맨 위는 task
# nodes: id → 노드 / n: 노드
def graph_of(nodes, n):
    # 거슬러 올라가며 본 id(순환 막기)
    seen = set()
    while n is not None:
        if norm_graph(n.get("graph")) in GRAPHS:
            return norm_graph(n["graph"])
        if n.get("kind") == "question":
            return HAND_OFF if n.get("view") in ("adr", HAND_OFF, "code") else "task"
        if n.get("kind") in SHARED_KINDS:
            return "both"
        if n.get("id") in seen:
            break
        seen.add(n.get("id"))
        n = nodes.get(n.get("parent"))
    return "task"


# 이름 목록 다듬기 — 글자면 줄바꿈 · 쉼표 · « · » 로 나눔 · 빈 칸 · 중복 제외
# names: 이름 목록 또는 글자
def clean_names(names):
    if isinstance(names, str):
        names = re.split(r"\n|,| · ", names)
    # 새 이름 목록
    out = []
    for x in names or []:
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
    return out


# 유저가 이름 칸을 고친 적 있나(고친 기록 중 names · user)
# n: 작업 노드
def names_by_user(n):
    return any(e.get("field") == "names" and e.get("by") == "user" for e in n.get("edits") or [])


# MAIN — 작업 노드 만들기
# parent: 부모 id(«-» 면 맨 위) / title: 제목 / summary: 요약 / text: 설명 / doc: «경로#앵커»
# graph: task · hand_off(옛 adr 도 받음 · 없으면 부모 그래프 · 맨 위면 hand_off) / names: 옛 이름 칸 «파일.py · 함수» → 함수 표 행 / funcs: 함수 표 행(«파일 | 함수 | 설명 | ⭐»)
# section: 섹션 번호(없으면 칸 없음)
def op_add(tree, rev, role, parent, title, summary="", text="", doc=None, graph=None, names=None, funcs=None, section=None):
    title = need_text(title, "제목")
    section = norm_section(section)
    graph = norm_graph(graph)
    # 요약
    summary = str(summary or "").strip()
    check_short(summary, "요약")
    if graph not in (None, "") and graph not in GRAPHS:
        raise StoreError(f"그래프 «{graph}» — task · hand_off")
    # 부모 그래프
    pg = None
    if parent not in (None, "", "-"):
        pg = graph_of(node_map(tree), need_node(tree, parent))
        if graph and pg not in (graph, "both"):
            raise StoreError(f"부모 «{parent}» 는 {pg} 그래프 — --graph {graph} 와 다름")
    graph = graph or (pg if pg in GRAPHS else HAND_OFF)
    # 새 id
    nid = next_id(tree, "t")
    # 새 노드
    node = {"id": nid, "kind": "task", "graph": graph, "title": title}
    if parent not in (None, "", "-"):
        node["parent"] = parent
    if summary:
        node["summary"] = summary
    if text:
        node["text"] = str(text)
    if doc:
        node["doc"] = parse_doc(doc)
    if section is not None:
        node["screen"] = section
    # 함수 표 처음 값 — 옛 이름 칸(--names) 행 + 행(--func)
    first = names_to_rows(names) + [parse_func_row(x) for x in funcs or []]
    if first:
        node["funcs"] = [dict(v, id=f"f{i}", by=role, code={"file": v["file"], "name": v["name"]}) for i, v in enumerate(first, 1)]
    at, _ = now_stamp()
    node.update({"seq": rev, "at": at, "by": role, "events": []})
    tree["nodes"].append(node)
    return {"id": nid, "msg": f"{nid} 추가"}


# MAIN — 작업 사건 하나 덧붙이기(start · hold · block · done)
# t: 사건 종류 / task: 작업 id / note: 사유 · 필요한 것
def op_event(tree, rev, role, t, task, note=""):
    # 작업 노드
    n = need_node(tree, task, "task")
    if t in ("hold", "block"):
        note = need_text(note, "사유" if t == "hold" else "유저에게 필요한 것")
    n.setdefault("events", []).append(record(rev, role, t=t, note=note))
    return {"id": task, "msg": f"{task} {TASK_EVENTS[t]}"}


# MAIN — 검증 노드 만들기(대상 노드 밑)
# target: 대상 id / what: 확인할 것
def op_verify_add(tree, rev, role, target, what, section=None):
    section = norm_section(section)
    # 대상 노드
    tn = need_node(tree, target)
    if tn.get("kind") in ("question", "verify"):
        raise StoreError(f"«{target}» 는 {WORK_KINDS[tn['kind']]} — 검증 대상 아님")
    what = need_text(what, "확인할 것")
    # 대상 그래프(모듈이면 hand_off)
    g = graph_of(node_map(tree), tn)
    # 새 id
    nid = next_id(tree, "v")
    at, _ = now_stamp()
    tree["nodes"].append({"id": nid, "kind": "verify", "graph": g if g in GRAPHS else HAND_OFF, "parent": target, "title": what,
                          "seq": rev, "at": at, "by": role, "events": [], "runs": [],
                          **({} if section is None else {"screen": section})})
    return {"id": nid, "msg": f"{nid} 추가"}


# 2ND — 답변 준비 중
# question: 질문 id
def op_answer_start(tree, rev, role, question):
    # 질문 노드
    n = need_node(tree, question, "question")
    if n.get("closed"):
        raise StoreError(f"«{question}» 는 닫힌 질문")
    n.setdefault("events", []).append(record(rev, role, t="start"))
    return {"id": question, "msg": f"{question} 답변 준비 중"}


# 2ND — 답 덧붙이기(질문 노드 · 설문 노드 — 설문은 «질문 · 답» 칸: 물은 글 ask 를 같이 남김 · 유저 답 votes 는 안 건드림)
# question: 질문 · 설문 id / short: 결론 한 줄(60자) / text: 본문 / ask: 설문 노드에 물은 글(메모 · 입력창 글)
def op_answer(tree, rev, role, question, short, text="", ask=""):
    # 질문 · 설문 노드
    n = need_node(tree, question)
    if n.get("kind") not in ("question", "survey"):
        raise StoreError(f"«{question}» 는 {WORK_KINDS.get(n.get('kind'), n.get('kind'))} — 질문 · 설문 아님")
    short = need_text(short, "결론(--short)")
    check_short(short, "결론(--short)")
    rec = record(rev, role, short=short, text=str(text or "").strip())
    if n["kind"] == "survey":
        rec["q"] = need_text(ask, "물은 글")
    n.setdefault("answers", []).append(rec)
    return {"id": question, "msg": f"{question} 답변 완료"}


# INSP — 검증 사건(start · hold)
# t: 사건 종류 / verify: 검증 id / note: 사유
def op_verify_event(tree, rev, role, t, verify, note=""):
    # 검증 노드
    n = need_node(tree, verify, "verify")
    if t == "hold":
        note = need_text(note, "사유")
    n.setdefault("events", []).append(record(rev, role, t=t, note=note))
    return {"id": verify, "msg": f"{verify} {'검증 중' if t == 'start' else '보류'}"}


# INSP — 검증 결과 덧붙이기
# verify: 검증 id / result: pass · fail / note: 근거(시험 경로 · 명령)
def op_run(tree, rev, role, verify, result, note):
    # 검증 노드
    n = need_node(tree, verify, "verify")
    if result not in ("pass", "fail"):
        raise StoreError(f"결과 «{result}» — pass · fail")
    note = need_text(note, "근거")
    n.setdefault("runs", []).append(record(rev, role, result=result, note=note))
    return {"id": verify, "msg": f"{verify} {'정상' if result == 'pass' else '비정상'}"}


# 질문 선 하나 잇기(같은 선이 있으면 그대로)
# tree: 그래프 / q: 질문 id / target: 대상 id(트리 노드 · 화면 노드)
def _link(tree, q, target):
    target = need_text(target, "대상")
    if target == q:
        raise StoreError("질문을 자기 자신에 이을 수 없음")
    if target not in node_map(tree) and not target.startswith(SCREEN_PREFIX):
        raise StoreError(f"없는 id «{target}»")
    if any(e.get("kind") == "asks" and e.get("source") == q and e.get("target") == target for e in tree["edges"]):
        return
    tree["edges"].append({"id": next_id(tree, "a"), "source": q, "target": target, "kind": "asks"})


# USER — 질문 만들기(대상이 있으면 선도)
# text: 질문 / target: 대상 id(없으면 섬) / view: 놓인 화면(feature · hand_off · code — 옛 adr 도 받음)
# targets: 더 이을 대상 id 목록(devview 허브 2ND 마법봉 — 여럿 고른 노드를 한 번의 쓰기로) / section: 섹션 번호(없으면 칸 없음)
def op_ask(tree, rev, role, text, target=None, view="feature", targets=None, section=None):
    text = need_text(text, "질문")
    section = norm_section(section)
    # 새 id
    nid = next_id(tree, "q")
    at, _ = now_stamp()
    # 새 노드
    node = {"id": nid, "kind": "question", "title": text, "seq": rev, "asked": rev, "at": at, "by": role,
            "events": [], "answers": []}
    if view and view != "feature":
        node["view"] = view
    if section is not None:
        node["screen"] = section
    tree["nodes"].append(node)
    if target:
        _link(tree, nid, target)
    # 더 이을 대상 하나
    for t in targets or []:
        _link(tree, nid, t)
    return {"id": nid, "msg": f"{nid} 추가"}


# USER — 질문 고치기(다시 묻는 것 — 이후 답이 없으면 미답변)
# question: 질문 id / text: 새 질문
def op_ask_edit(tree, rev, role, question, text):
    # 질문 노드
    n = need_node(tree, question, "question")
    n["title"] = need_text(text, "질문")
    n["asked"] = rev
    return {"id": question, "msg": f"{question} 고침"}


# USER — 질문 닫기 · 다시 열기
# question: 질문 id / closed: 닫힘 여부
def op_ask_close(tree, rev, role, question, closed=True):
    # 질문 노드
    n = need_node(tree, question, "question")
    n["closed"] = bool(closed)
    return {"id": question, "msg": f"{question} {'닫힘' if closed else '다시 열림'}"}


# USER — 질문 지우기(답이 없을 때만 — 답이 있으면 닫기)
# question: 질문 id
def op_ask_del(tree, rev, role, question):
    # 질문 노드
    n = need_node(tree, question, "question")
    if n.get("answers"):
        raise StoreError(f"«{question}» 는 답이 달린 질문 — 지우지 말고 닫기")
    tree["nodes"] = [x for x in tree["nodes"] if x is not n]
    tree["edges"] = [e for e in tree["edges"] if not (e.get("kind") == "asks" and e.get("source") == question)]
    return {"id": question, "msg": f"{question} 지움"}


# USER — 질문 선 잇기
# question: 질문 id / target: 대상 id
def op_link(tree, rev, role, question, target):
    need_node(tree, question, "question")
    _link(tree, question, target)
    return {"id": question, "msg": f"{question} → {target} 이음"}


# USER — 질문 선 끊기
# question: 질문 id / target: 대상 id
def op_unlink(tree, rev, role, question, target):
    # 남길 선
    keep = [e for e in tree["edges"] if not (e.get("kind") == "asks" and e.get("source") == question and e.get("target") == target)]
    if len(keep) == len(tree["edges"]):
        raise StoreError(f"없는 질문 선 «{question} → {target}»")
    tree["edges"] = keep
    return {"id": question, "msg": f"{question} → {target} 끊음"}


# ======= 설문 · 유저 편집 · 섹션 후보 · 분석 결과 불러오기 =======
# 유저 칸이 덮인 보기용 값 — edit 칸(유저가 고친 제목 · 요약 · 설명)이 있으면 그것
# n: 노드 / key: title · summary · text
def eff(n, key):
    # 유저가 고친 값
    v = (n.get("edit") or {}).get(key)
    return v if v not in (None, "") else n.get(key, "")


# 선택지 글자 «라벨|풀이|장점;…|단점;…» 또는 사전 → {label, text, pros, cons}
# o: 글자 · 사전
def parse_option(o):
    if isinstance(o, dict):
        # 라벨
        label = need_text(o.get("label"), "선택지 라벨")
        return {"label": label, "text": str(o.get("text") or "").strip(),
                "pros": [str(x).strip() for x in o.get("pros") or [] if str(x).strip()],
                "cons": [str(x).strip() for x in o.get("cons") or [] if str(x).strip()]}
    # 칸 넷
    parts = (str(o).split("|") + ["", "", ""])[:4]
    return {"label": need_text(parts[0], "선택지 라벨"), "text": parts[1].strip(),
            "pros": [x.strip() for x in parts[2].split(";") if x.strip()],
            "cons": [x.strip() for x in parts[3].split(";") if x.strip()]}


# 설문 노드 내용 채우기(새로 · 다시 불러오기 공용) — 유저 답(votes) · 반영 기록(acks)은 건드리지 않음
# node: 노드 / question: 질문 / options: 선택지 목록 / recommend: 추천 번호(0부터 · 없으면 None) / why: 추천 이유 / detail: 배경
def fill_survey(node, question, options, recommend=None, why="", detail=""):
    # 선택지
    opts = [parse_option(o) for o in options or []]
    if not opts:
        raise StoreError("선택지 없음 — --option 하나 이상")
    if recommend not in (None, ""):
        recommend = int(recommend)
        if not 0 <= recommend < len(opts):
            raise StoreError(f"추천 번호 {recommend + 1} — 선택지 1~{len(opts)}")
    else:
        recommend = None
    node["title"] = need_text(question, "질문")
    node["options"] = opts
    node["recommend"] = recommend
    for key, val in (("why", why), ("detail", detail)):
        if str(val or "").strip():
            node[key] = str(val).strip()
        else:
            node.pop(key, None)


# MAIN — 설문 노드 만들기(대상 밑 · «-» 면 그 그래프 맨 위)
# target: 대상 id / question: 질문 / options: 선택지 / recommend: 추천(0부터) / why: 추천 이유 / detail: 배경 · 메커니즘 / graph: task · hand_off(옛 adr 도 받음)
def op_survey_add(tree, rev, role, target, question, options, recommend=None, why="", detail="", graph=None, section=None):
    graph = norm_graph(graph)
    section = norm_section(section)
    if graph not in (None, "") and graph not in GRAPHS:
        raise StoreError(f"그래프 «{graph}» — task · hand_off")
    # 대상 그래프
    pg = None
    if target not in (None, "", "-"):
        # 대상 노드
        tn = need_node(tree, target)
        if tn.get("kind") in ("question", "survey"):
            raise StoreError(f"«{target}» 는 {WORK_KINDS[tn['kind']]} — 설문 대상 아님(질문은 선으로 잇는 노드)")
        pg = graph_of(node_map(tree), tn)
        if graph and pg not in (graph, "both"):
            raise StoreError(f"대상 «{target}» 는 {pg} 그래프 — --graph {graph} 와 다름")
    # 새 id · 노드
    nid = next_id(tree, "s")
    at, _ = now_stamp()
    node = {"id": nid, "kind": "survey", "graph": graph or (pg if pg in GRAPHS else "task")}
    if target not in (None, "", "-"):
        node["parent"] = target
    if section is not None:
        node["screen"] = section
    fill_survey(node, question, options, recommend, why, detail)
    node.update({"seq": rev, "at": at, "by": role, "votes": [], "acks": []})
    tree["nodes"].append(node)
    return {"id": nid, "msg": f"{nid} 추가"}


# 설문의 지금 유저 답 — {pick, memo, hold, seq}
# n: 설문 노드
def survey_vote(n):
    # 마지막 답
    last = (n.get("votes") or [None])[-1] or {}
    return {"pick": last.get("pick"), "memo": last.get("memo", ""), "hold": bool(last.get("hold")), "seq": last.get("seq", 0)}


# 설문 반영이 필요한가 — 마지막 답(선택 · 보류)이 마지막 반영 기록보다 새것
# n: 설문 노드
def survey_pending(n):
    # 지금 답
    v = survey_vote(n)
    if v["pick"] is None and not v["hold"]:
        return False
    return v["seq"] > max((a.get("seq", 0) for a in n.get("acks") or []), default=0)


# 설문 «기타» 선택 번호(내용은 메모 칸)
PICK_OTHER = -1


# USER — 설문 답(선택 · 메모 · 보류). 안 준 칸은 지난 값 그대로 · 선택하면 보류 풀림
# survey: 설문 id / pick: 선택 번호(0부터 · -1 = 기타 · None = 해제) / memo: 메모 / hold: 보류
def op_vote(tree, rev, role, survey, pick=KEEP, memo=KEEP, hold=KEEP):
    # 설문 노드 · 지금 답
    n = need_node(tree, survey, "survey")
    cur = survey_vote(n)
    if pick is not KEEP:
        if pick is not None:
            pick = int(pick)
            if pick != PICK_OTHER and not 0 <= pick < len(n.get("options") or []):
                raise StoreError(f"선택 번호 {pick + 1} — 선택지 1~{len(n.get('options') or [])}")
        cur["pick"] = pick
        if hold is KEEP and pick is not None:
            cur["hold"] = False
    if memo is not KEEP:
        cur["memo"] = str(memo or "").strip()
    if hold is not KEEP:
        cur["hold"] = bool(hold)
    # 기록(선택 해제는 pick None 그대로 남김)
    rec = record(rev, role)
    rec.update({"pick": cur["pick"], "memo": cur["memo"], "hold": cur["hold"]})
    n.setdefault("votes", []).append(rec)
    # 결과 글자
    what = "보류" if cur["hold"] else "기타" if cur["pick"] == PICK_OTHER else (f"선택 {cur['pick'] + 1}" if cur["pick"] is not None else "미응답")
    return {"id": survey, "msg": f"{survey} {what}"}


# MAIN — 설문 결정을 반영했다는 기록
# survey: 설문 id / note: 무엇을 했나
def op_survey_ack(tree, rev, role, survey, note=""):
    # 설문 노드
    n = need_node(tree, survey, "survey")
    if not n.get("votes"):
        raise StoreError(f"«{survey}» 는 아직 유저 답 없음")
    n.setdefault("acks", []).append(record(rev, role, note=str(note or "").strip()))
    return {"id": survey, "msg": f"{survey} 반영 기록"}


# 유저 고침 기록 한 줄 덧붙이기
# n: 노드 / rev: 판 번호 / role: 역할 / field: 칸 / old · new: 전 · 후 값
def add_edit(n, rev, role, field, old, new):
    # 기록
    rec = record(rev, role, field=field)
    rec.update({"old": old, "new": new})
    n.setdefault("edits", []).append(rec)


# USER — 작업 · 검증 · 섹션 후보의 제목 · 요약 · 설명 고치기(edit 칸 · 원래 글은 그대로). 빈 글자 = 고침 지움(원래 글로)
# node: 노드 id / title · summary · text: 새 값(안 주면 그대로)
def op_edit(tree, rev, role, node, title=KEEP, summary=KEEP, text=KEEP, script=KEEP):
    # 노드
    n = need_node(tree, node)
    if n.get("kind") not in EDITABLE_KINDS:
        raise StoreError(f"«{node}» ({n.get('kind')}) 는 고칠 수 없음 — 작업 · 검증 · 설문만")
    # 유저 고침 칸 · 바꾼 칸 수
    ed = dict(n.get("edit") or {})
    changed = 0
    for key, val in (("title", title), ("summary", summary), ("text", text), ("script", script)):
        if val is KEEP:
            continue
        val = str(val or "").strip()
        if key == "summary":
            check_short(val, "요약")
        # 지금 보이는 값
        old = eff(n, key)
        # 원래 글과 같으면 고침 지움
        new_val = "" if val == str(n.get(key) or "") else val
        if (ed.get(key) or "") == new_val:
            continue
        if new_val:
            ed[key] = new_val
        else:
            ed.pop(key, None)
        add_edit(n, rev, role, key, old, val or str(n.get(key) or ""))
        changed += 1
    if ed:
        n["edit"] = ed
    else:
        n.pop("edit", None)
    return {"id": node, "msg": f"{node} 고침 {changed}"}


# ======= 함수 표(funcs) — 작업 노드의 «파일 · 함수 · 설명 · 핵심(⭐)» 행 목록 =======
#   행: {id: f1…, by: 만든 역할, file · name · desc · core: 에이전트 칸(원문), user: {유저가 고친 칸},
#        code: {file, name}(코드에 있다고 확인된 이름 — funcs-set · funcs-ack 가 씀), del: 유저가 지움(에이전트 행)}
#   보이는 값 = 유저 칸 > 에이전트 칸(func_val) · 에이전트 명령은 user 칸을 쓰지 않고, 유저 명령은 에이전트 칸을 쓰지 않음
#   이름 바뀜 = 보이는 (파일, 함수) 가 code 와 다름(유저가 고침 · 유저가 새 행) → MAIN inbox · funcs-ack 로 닫음
#   옛 tree.json 의 names(글자 목록)는 읽을 때 행으로 올리고(func_rows) 처음 쓸 때 funcs 로 옮긴다(ensure_funcs)
# 행 칸 이름
FUNC_KEYS = ("file", "name", "desc", "core")
# 파일 이름처럼 보이는 글자(경로 구분자 · 확장자)
FILE_LIKE = re.compile(r"[/\\]|\.[A-Za-z][A-Za-z0-9]{0,4}$")
# 핵심 표시로 받는 글자
CORE_MARKS = {"⭐", "★", "*", "core", "y", "yes", "1", "true", "o", "핵심"}


# 옛 이름 목록 → 행 값 목록 — 파일 글자 뒤의 이름은 그 파일의 함수 · 함수가 없는 파일은 파일만인 행
# names: 이름 목록 또는 글자
def names_to_rows(names):
    # 결과 · 지금 파일 · 함수 없이 남은 파일
    rows, cur, alone = [], "", False
    for x in clean_names(names):
        if FILE_LIKE.search(x):
            if alone:
                rows.append({"file": cur, "name": "", "desc": "", "core": False})
            cur, alone = x, True
        else:
            rows.append({"file": cur, "name": x, "desc": "", "core": False})
            alone = False
    if alone:
        rows.append({"file": cur, "name": "", "desc": "", "core": False})
    return rows


# 행 글자 «파일 | 함수 | 설명 | ⭐» · 목록 · 사전 → {file, name, desc, core}
# x: 행
def parse_func_row(x):
    if isinstance(x, dict):
        parts = [x.get("file", ""), x.get("name", ""), x.get("desc", ""), x.get("core", False)]
    elif isinstance(x, (list, tuple)):
        parts = (list(x) + ["", "", "", False])[:4]
    else:
        # 칸 — 넷 넘으면 가운데를 설명으로(설명 안 «|»)
        cells = str(x).split("|")
        parts = (cells + ["", "", ""])[:3] + [False] if len(cells) < 4 else [cells[0], cells[1], "|".join(cells[2:-1]), cells[-1]]
    # 핵심 여부
    core = parts[3] if isinstance(parts[3], bool) else str(parts[3] or "").strip().lower() in CORE_MARKS
    row = {"file": str(parts[0] or "").strip(), "name": str(parts[1] or "").strip(), "desc": str(parts[2] or "").strip(), "core": core}
    if not row["file"] and not row["name"]:
        raise StoreError(f"함수 표 행 «{x}» — 파일 · 함수 둘 다 비었음(«파일 | 함수 | 설명 | ⭐»)")
    return row


# 노드의 함수 표 행 — funcs 칸, 없으면 옛 names 를 행으로(저장은 안 함 · 유저가 고친 names 면 유저 칸으로)
# n: 작업 노드
def func_rows(n):
    if isinstance(n.get("funcs"), list):
        return n["funcs"]
    # 옛 칸을 유저가 고쳤나
    by_user = names_by_user(n)
    # 결과
    rows = []
    for i, v in enumerate(names_to_rows(n.get("names") or []), 1):
        r = {"id": f"f{i}", "by": "user" if by_user else "main", "code": {"file": v["file"], "name": v["name"]}}
        if by_user:
            r["user"] = {k: v[k] for k in ("file", "name") if v[k]}
        else:
            r.update(v)
        rows.append(r)
    return rows


# 쓰기 전 — 옛 names 를 funcs 로 옮기고(names 칸 지움) 행 목록을 돌려줌
# n: 작업 노드
def ensure_funcs(n):
    # 행 목록
    rows = func_rows(n)
    n["funcs"] = rows
    n.pop("names", None)
    return rows


# 행 칸의 보이는 값 — 유저 칸 > 에이전트 칸
# r: 행 / k: 칸 이름
def func_val(r, k):
    # 유저 칸
    u = r.get("user") or {}
    if k in u:
        return u[k]
    return bool(r.get(k)) if k == "core" else str(r.get(k) or "")


# 행 이름 글자 «파일 · 함수»
# r: 행 / code: True 면 code 칸(코드에 있는 이름)
def func_label(r, code=False):
    # 파일 · 함수
    f, nm = ((r.get("code") or {}).get("file", ""), (r.get("code") or {}).get("name", "")) if code else (func_val(r, "file"), func_val(r, "name"))
    return " · ".join(x for x in (f, nm) if x) or "(빈 행)"


# 이름 바뀜인가 — 지우지 않은 행의 보이는 (파일, 함수) 가 코드에 있다고 확인된 이름과 다름
# r: 행
def func_pending(r):
    if r.get("del"):
        return False
    # 코드 이름
    c = r.get("code")
    return c is None or (c.get("file", ""), c.get("name", "")) != (func_val(r, "file"), func_val(r, "name"))


# 이름 바뀜 글자 «옛 → 새»(새 행이면 «새 행 → 새»)
# r: 행
def func_change(r):
    return f"{func_label(r, code=True) if r.get('code') is not None else '새 행'} → {func_label(r)}"


# 노드의 이름 바뀜 행 목록
# n: 작업 노드
def funcs_pending(n):
    return [r for r in func_rows(n) if func_pending(r)]


# 다음 행 id
# rows: 행 목록
def next_func_id(rows):
    # 쓰인 번호
    nums = [int(m.group(1)) for r in rows for m in [re.fullmatch(r"f(\d+)", str(r.get("id")))] if m]
    return f"f{max(nums, default=0) + 1}"


# 이름 바꾸기 작업 설명(키트 CODE_RULE 9-1 — 파일 · 정의 · 부르는 곳 · import · 테스트 전부)
# tid: 원래 작업 id / changes: «옛 → 새» 목록
def rename_text(tid, changes):
    return (f"{tid} 의 함수 표 이름을 유저가 바꿈 — 그래프 글자만 바꾸고 끝내지 않는다\n"
            + "\n".join(changes) + "\n"
            "1. 파일 이름 바꾸기 2. 함수 · 클래스 정의 이름 3. 부르는 곳 전부 4. import 줄 5. 테스트 이름 · 내용 6. 시험 다시 돌리기\n"
            f"끝나면 MAIN 이 funcs-ack {tid}")


# 완료된 작업의 이름 바뀜 → «이름 바꾸기» 작업(열린 것이 있으면 내용만 갱신). 반환 작업 id(바뀜 없으면 None)
# tree: 그래프 / rev: 판 번호 / role: 역할 / n: 원래 작업 노드
def rename_task(tree, rev, role, n):
    # 바뀜 글자
    changes = [func_change(r) for r in funcs_pending(n)]
    if not changes:
        return None
    nodes = node_map(tree)
    # 요약(60자)
    summary = " · ".join(changes)
    if len(summary) > SUMMARY_MAX:
        summary = summary[:SUMMARY_MAX - 1] + "…"
    # 아직 안 끝난 이름 바꾸기 작업
    open_t = next((x for x in tree["nodes"] if x.get("auto") == "rename" and x.get("rename_of") == n["id"]
                   and status(x, nodes)["status"] != "done"), None)
    if open_t is not None:
        open_t.update(summary=summary, text=rename_text(n["id"], changes))
        return open_t["id"]
    rid = next_id(tree, "t")
    at, _ = now_stamp()
    # 원래 작업 그래프
    tg = graph_of(nodes, n)
    tree["nodes"].append({"id": rid, "kind": "task", "graph": tg if tg in GRAPHS else HAND_OFF,
                          "parent": n["id"], "title": f"이름 바꾸기 — {eff(n, 'title')}", "summary": summary,
                          "text": rename_text(n["id"], changes), "auto": "rename", "rename_of": n["id"],
                          "seq": rev, "at": at, "by": role, "events": []})
    return rid


# MAIN — 함수 표 쓰기(코드에 있는 이름 · 한 줄 설명 · 핵심). 보낸 목록 = 지금 코드의 함수 표
#   맞추기: 보이는 이름 > 에이전트 원문 이름 > 코드 이름이 같은 행(함수 없는 행은 파일) · 맞은 행은 에이전트 칸 · code 갱신(유저 칸은 그대로)
#   목록에 없는 에이전트 행은 지움 — 유저 칸이 있는 행 · 유저가 만든 행은 남김 · 유저가 지운 행은 되살리지 않음
# task: 작업 id / rows: 행 목록(«파일 | 함수 | 설명 | ⭐» · 사전 · 목록)
def op_funcs_set(tree, rev, role, task, rows):
    # 작업 노드 · 새 행 값 · 지금 행
    n = need_node(tree, task, "task")
    new = [parse_func_row(x) for x in rows or []]
    cur = ensure_funcs(n)
    # 바꾸기 전 모습(같으면 기록 안 함)
    before = json.dumps(cur, ensure_ascii=False, sort_keys=True)
    old_labels = [func_label(r) for r in cur if not r.get("del")]
    # 맞은 행 · 셈
    used, cnt = set(), {"new": 0, "upd": 0, "del_kept": 0}

    # 새 행 값에 맞는 지금 행
    # v: 새 행 값
    def find(v):
        # 맞추는 규칙(앞이 우선)
        rules = ((lambda r: func_val(r, "name") == v["name"]), (lambda r: r.get("name") == v["name"]),
                 (lambda r: (r.get("code") or {}).get("name") == v["name"])) if v["name"] else \
                ((lambda r: not func_val(r, "name") and func_val(r, "file") == v["file"]),)
        for rule in rules:
            for r in cur:
                if id(r) not in used and rule(r):
                    return r
        return None
    for v in new:
        r = find(v)
        if r is None:
            r = dict(v, id=next_func_id(cur), by=role)
            cur.append(r)
            cnt["new"] += 1
        else:
            r.update(v)
            cnt["upd"] += 1
            if r.get("del"):
                cnt["del_kept"] += 1
        r["code"] = {"file": v["file"], "name": v["name"]}
        used.add(id(r))
    # 목록에 없는 행 — 유저 칸 · 유저 행은 남김
    keep, gone, kept_user = [], 0, 0
    for r in cur:
        if id(r) in used:
            keep.append(r)
        elif r.get("del"):
            gone += 1
        elif r.get("by") == "user" or r.get("user"):
            keep.append(r)
            kept_user += 1
        else:
            gone += 1
    n["funcs"] = keep
    if not keep:
        n.pop("funcs", None)
    if json.dumps(keep, ensure_ascii=False, sort_keys=True) == before:
        return {"id": task, "msg": f"{task} 함수 표 그대로"}
    add_edit(n, rev, role, "funcs", old_labels, [func_label(r) for r in keep if not r.get("del")])
    # 결과 글자
    extra = [f"새 {cnt['new']}", f"갱신 {cnt['upd']}", f"지움 {gone}"]
    if kept_user:
        extra.append(f"유저 칸 있어 남김 {kept_user}")
    if cnt["del_kept"]:
        extra.append(f"유저가 지운 행 {cnt['del_kept']}(되살리지 않음)")
    # 남은 이름 바뀜
    pend = funcs_pending(n)
    if pend:
        extra.append(f"이름 바뀜 {len(pend)} — {' · '.join(func_change(r) for r in pend[:3])}")
    return {"id": task, "msg": f"{task} 함수 표 {sum(1 for r in keep if not r.get('del'))}행({' · '.join(extra)})"}


# MAIN — 유저가 바꾼 이름(· 새 행)을 코드 · 시험 · 문서에 반영했다는 기록 → 이름 바뀜 닫힘(code = 보이는 이름)
# task: 작업 id / note: 무엇을 했나
def op_funcs_ack(tree, rev, role, task, note=""):
    # 작업 노드 · 이름 바뀜 행
    n = need_node(tree, task, "task")
    pend = funcs_pending(n)
    if not pend:
        raise StoreError(f"«{task}» 는 이름 바뀜 없음")
    ensure_funcs(n)
    pend = funcs_pending(n)
    # 바뀜 글자
    changes = [func_change(r) for r in pend]
    for r in pend:
        r["code"] = {"file": func_val(r, "file"), "name": func_val(r, "name")}
    n.setdefault("func_acks", []).append(record(rev, role, note=str(note or "").strip(), changes=changes))
    return {"id": task, "msg": f"{task} 이름 반영 {len(changes)} — {' · '.join(changes[:3])}"}


# MAIN — 코드에서 읽은 함수 설명을 에이전트 설명 칸에(비었을 때만 · 유저 칸은 그대로). 찾기는 명령 쪽(flowtree.py)이 함
# task: 작업 id / found: {«파일::함수»: 바로 위 주석 한 줄(없으면 "")} — 코드에 없는 이름은 열쇠가 없음
def op_funcs_scan(tree, rev, role, task, found):
    # 작업 노드
    n = need_node(tree, task, "task")
    rows = ensure_funcs(n)
    # 채운 행 · 코드에 없는 행
    filled, missing = [], []
    for r in rows:
        if r.get("del") or not func_val(r, "name"):
            continue
        # 찾기 열쇠
        key = f"{func_val(r, 'file')}::{func_val(r, 'name')}"
        if key not in found:
            missing.append(func_label(r))
        elif found[key] and not r.get("desc"):
            r["desc"] = found[key]
            filled.append(r["id"])
    if filled:
        add_edit(n, rev, role, "funcs", [], [f"{i} 설명(코드 주석)" for i in filled])
    return {"id": task, "msg": f"{task} 설명 채움 {len(filled)}" + (f" · 코드에 없는 이름 {len(missing)} — {' · '.join(missing[:5])}" if missing else "")}


# USER — 함수 표 칸 고치기 · 행 추가 · 지우기(화면 자세히 창). done 뒤에 파일 · 함수 이름이 바뀌면 «이름 바꾸기» 작업
#   row 없음 = 새 행(cells) / delete = 지우기(에이전트 행은 del 표시 — 다시 만들지 않게 · 유저 행은 뺌) / 그 밖 = 칸 고치기(유저 칸)
#   에이전트 원문과 같은 값으로 고치면 유저 칸을 지움(원문으로)
# task: 작업 id / row: 행 id / cells: {file · name · desc · core 중 고칠 칸} / delete: 지우기
def op_funcs(tree, rev, role, task, row="", cells=None, delete=False):
    # 작업 노드 · 지금 상태(바꾸기 전) · 행
    n = need_node(tree, task, "task")
    done = status(n, node_map(tree))["status"] == "done"
    rows = ensure_funcs(n)
    cells = dict(cells or {})
    bad = set(cells) - set(FUNC_KEYS)
    if bad:
        raise StoreError(f"함수 표 칸 «{' · '.join(sorted(bad))}» — {' · '.join(FUNC_KEYS)}")
    for k in cells:
        cells[k] = bool(cells[k]) if k == "core" else str(cells[k] or "").strip()
    if not row:
        if delete:
            raise StoreError("지울 행 id 없음")
        if not cells.get("file") and not cells.get("name"):
            raise StoreError("새 행 — 파일 · 함수 둘 다 비었음")
        r = {"id": next_func_id(rows), "by": role, "user": {k: v for k, v in cells.items() if v not in ("", False)}}
        rows.append(r)
        add_edit(n, rev, role, f"funcs:{r['id']}", "", func_label(r))
        msg = f"{task} 함수 {r['id']} 추가"
    else:
        r = next((x for x in rows if x.get("id") == row and not x.get("del")), None)
        if r is None:
            raise StoreError(f"«{task}» 함수 표에 없는 행 «{row}»")
        if delete:
            add_edit(n, rev, role, f"funcs:{row}", func_label(r), "(지움)")
            if r.get("by") == "user":
                rows.remove(r)
            else:
                r["del"] = True
            return {"id": task, "msg": f"{task} 함수 {row} 지움"}
        # 유저 칸 · 바꾼 칸
        u = dict(r.get("user") or {})
        changed = []
        for k, v in cells.items():
            old = func_val(r, k)
            if v == old:
                continue
            # 에이전트 원문
            orig = bool(r.get(k)) if k == "core" else str(r.get(k) or "")
            if v == orig and r.get("by") != "user":
                u.pop(k, None)
            else:
                u[k] = v
            changed.append((k, old, v))
        if not changed:
            return {"id": task, "msg": f"{task} 함수 {row} 그대로"}
        if not (u.get("file", r.get("file")) or u.get("name", r.get("name"))):
            raise StoreError("파일 · 함수 둘 다 빈 행 — 지우기로")
        if u:
            r["user"] = u
        else:
            r.pop("user", None)
        for k, old, v in changed:
            add_edit(n, rev, role, f"funcs:{row}:{k}", old, v)
        msg = f"{task} 함수 {row} 고침 {len(changed)}"
    if func_pending(r):
        msg += f" · 이름 바뀜 {func_change(r)}"
        if done:
            rid = rename_task(tree, rev, role, n)
            return {"id": rid, "msg": f"{msg} · 완료 뒤라 {rid} 이름 바꾸기 작업"}
    return {"id": task, "msg": msg}


# USER — 화면 노드 추가 단추(작업 · 검증 · 설문) — hand_off 그래프 맨 위에 새 노드 · 만든 사람 user
#   작업은 MAIN 이 start · done 으로 진행 · 검증은 INSP 가 결과 · 설문은 유저가 고를 선택지가 아직 없음(MAIN 이 반영)
# kind: task · verify · survey / title: 제목 / summary: 요약(60자 이내) / section: 만든 화면의 섹션 번호(Main 이면 없음)
def op_node_add(tree, rev, role, kind, title, summary="", section=None):
    if kind not in USER_ADD_KINDS:
        raise StoreError(f"종류 «{kind}» — {' · '.join(USER_ADD_KINDS)}")
    title = need_text(title, "제목")
    section = norm_section(section)
    # 요약
    summary = str(summary or "").strip()
    check_short(summary, "요약")
    # 새 id · 노드
    nid = next_id(tree, USER_ADD_KINDS[kind])
    at, _ = now_stamp()
    node = {"id": nid, "kind": kind, "graph": HAND_OFF, "title": title}
    if summary:
        node["summary"] = summary
    if section is not None:
        node["screen"] = section
    node.update({"seq": rev, "at": at, "by": role})
    # 종류별 기록 칸(덧붙이기만 하는 칸 — 처음은 빈 목록)
    if kind == "task":
        node["events"] = []
    elif kind == "verify":
        node.update({"events": [], "runs": []})
    else:
        node.update({"options": [], "votes": [], "acks": []})
    tree["nodes"].append(node)
    return {"id": nid, "msg": f"{nid} 추가"}


# MAIN — 틀 노드 채우기(준 칸만 · 에이전트 칸 — 유저 칸은 안 덮음). 채워지면 일반 노드
# node: 작업 · 검증 · 설문 id / title: 제목(설문은 질문) / summary: 요약 / text: 설명 / doc: «경로#앵커» / funcs: 함수 표 행 / script: 검증 스크립트 경로
# options · recommend · why · detail: 설문 선택지 · 추천(0부터) · 추천 이유 · 배경
def op_fill(tree, rev, role, node, title=None, summary=None, text=None, doc=None, funcs=None, script=None,
            options=None, recommend=None, why="", detail=""):
    # 노드 · 종류
    n = need_node(tree, node)
    kind = n.get("kind")
    if kind not in EDITABLE_KINDS:
        raise StoreError(f"«{node}» ({kind}) 는 채울 수 없음 — 작업 · 검증 · 설문만")
    if options and kind != "survey":
        raise StoreError(f"«{node}» 는 {WORK_KINDS[kind]} — --option 은 설문만")
    if script and kind != "verify":
        raise StoreError(f"«{node}» 는 {WORK_KINDS[kind]} — --script 는 검증만")
    if funcs and kind != "task":
        raise StoreError(f"«{node}» 는 {WORK_KINDS[kind]} — --func 는 작업만")
    if not (title or n.get("title") or (n.get("edit") or {}).get("title")):
        raise StoreError(f"«{node}» 제목 없음 — --title")
    if summary is not None:
        check_short(str(summary).strip(), "요약")
    if options:
        fill_survey(n, title or n.get("title"), options, recommend, why, detail)
    elif title:
        n["title"] = need_text(title, "제목")
    for key, val in (("summary", summary), ("text", text), ("script", script)):
        if val is not None:
            n[key] = str(val).strip()
    if doc:
        n["doc"] = parse_doc(doc)
    if funcs:
        op_funcs_set(tree, rev, role, node, funcs)
    n["by"] = role
    return {"id": node, "msg": f"{node} 채움"}


# MAIN — 노드의 섹션 바꾸기 — «-» 면 칸을 지움(Main 만) · 칸 없는 아래 노드 · 이어진 질문은 화면에서 이 값을 따름
# node: 노드 id / section: 섹션 번호 · «-»
def op_section_set(tree, rev, role, node, section):
    # 노드 · 섹션
    n = need_node(tree, node)
    s = norm_section(section)
    if s is None:
        n.pop("screen", None)
    else:
        n["screen"] = s
    return {"id": node, "msg": f"{node} → {'Main' if s is None else f'섹션{s}'}"}


# USER — 노드 지우기(그래프 화면 Delete 키 · 메뉴) — 질문은 ask-del · 맨 위 · 공용(모듈)은 거부
#   아래 노드가 있으면 거부(통째로 날리지 않게 — 아래부터 지운다) · 그 노드에 걸린 선(질문 선 포함)은 함께 지움 · 질문 노드는 남음
# node: 노드 id
def op_node_del(tree, rev, role, node):
    # 지울 노드 · 종류
    n = need_node(tree, node)
    kind = n.get("kind")
    if kind == "question":
        raise StoreError(f"«{node}» 는 질문 — 질문 지우기(ask-del)로")
    if kind == "root" or kind in SHARED_KINDS:
        raise StoreError(f"«{node}» 는 {kind} — 못 지움")
    # 아래 노드 — 빈 틀 노드는 같이 지움
    under = [x for x in tree["nodes"] if isinstance(x, dict) and x.get("parent") == node]
    kids = [x.get("id") for x in under if not x.get("frame")]
    if kids:
        raise StoreError(f"«{node}» 아래 노드 {len(kids)}개({' · '.join(map(str, kids[:3]))}) — 아래부터 지우기")
    # 지울 id
    gone = {node, *(x.get("id") for x in under)}
    tree["nodes"] = [x for x in tree["nodes"] if x.get("id") not in gone]
    tree["edges"] = [e for e in tree["edges"] if e.get("source") not in gone and e.get("target") not in gone]
    return {"id": node, "msg": f"{node} 지움"}


# 출처 id 로 노드 찾아 갱신 · 없으면 새로(다시 불러와도 두 번 생기지 않게). 유저 칸 · 기록은 그대로
# tree: 그래프 / rev: 판 번호 / role: 역할 / src: 출처 id / prefix: 새 id 접두어 / fields: 채울 칸 / stats: {new, upd} 셈
def upsert(tree, rev, role, src, prefix, fields, stats):
    # 같은 출처 노드
    n = next((x for x in tree["nodes"] if isinstance(x, dict) and x.get("src") == src), None)
    if n is None:
        at, _ = now_stamp()
        n = {"id": next_id(tree, prefix), "src": src, "seq": rev, "at": at, "by": role}
        tree["nodes"].append(n)
        stats["new"] += 1
    else:
        stats["upd"] += 1
    for k, v in fields.items():
        if v in (None, "", []):
            n.pop(k, None)
        else:
            n[k] = v
    return n


# 긴 글 → 노드 제목(넘으면 줄임)
# s: 글자 / limit: 최대 글자
def short_title(s, limit=IMPORT_TITLE_MAX):
    # 굵게 표시 · 숫자 자리 지운 글의 첫 줄
    s = (re.sub(r"\*\*|\{F\[['\"][^'\"]+['\"]\]\}", "", str(s or "")).strip().splitlines() or [""])[0].strip()
    return s if len(s) <= limit else s[:limit - 1] + "…"


# 60자 요약
# s: 글자
def short_summary(s):
    # 한 줄
    s = re.sub(r"\*\*", "", str(s or "")).strip().replace("\n", " ")
    return s if len(s) <= SUMMARY_MAX else s[:SUMMARY_MAX - 1] + "…"


# 분류 값(5개 밖이면 버림)
# v: 값
def cat_of(v):
    return v if v in CATS else None


# MAIN — 분석 결과(reqs.json · facts.json)를 Task 그래프 노드로. 같은 출처 id 면 갱신
#   bookkit 계약(contract · readme · hidden · silent · questions / files · traps · defects · facts)과 임시 형식(reqs · hidden · questions / facts) 둘 다
# reqs: reqs.json 내용(없으면 None) / facts: facts.json 내용(없으면 None)
def op_import_analysis(tree, rev, role, reqs=None, facts=None):
    if not reqs and not facts:
        raise StoreError("분석 결과 없음 — reqs.json · facts.json")
    reqs = reqs or {}
    facts = facts or {}
    # 셈
    stats = {"new": 0, "upd": 0}
    # 맨 위(Task 그래프) — 없으면 만듦
    root = next((n for n in tree["nodes"] if n.get("kind") == "root"), None)
    if root is None:
        root = upsert(tree, rev, role, "import:root", "i", {"kind": "root", "graph": "task",
                                                             "title": short_title(reqs.get("task") or facts.get("task") or "과제 파악")}, stats)

    # 묶음 하나(맨 위 밑)
    # key: 출처 열쇠 / title: 제목 / section: 구역
    def group(key, title, section):
        return upsert(tree, rev, role, f"import:g:{key}", "i", {"kind": "group", "graph": "task", "parent": root["id"],
                                                                 "title": title, "section": section}, stats)

    # 묶음 캐시(필요할 때만 만듦)
    groups = {}

    # 묶음 얻기
    # key: 열쇠 / title · section: 처음 만들 때 제목 · 구역
    def g(key, title, section):
        if key not in groups:
            groups[key] = group(key, title, section)
        return groups[key]["id"]

    # 항목 id 가 없는 곳(칸[순번]) — 출처 열쇠는 id 만 쓴다(순번이면 항목이 끼거나 빠질 때 다른 노드와 섞인다)
    missing = [f"{sec}[{i}]" for src, secs in ((reqs, ("readme", "reqs", "hidden", "silent", "questions")),
                                                (facts, ("traps", "defects", "facts")))
               for sec in secs for i, x in enumerate(src.get(sec) or []) if isinstance(x, dict) and not x.get("id")]
    if missing:
        raise StoreError(f"항목 id 없음 {len(missing)}곳 — {', '.join(missing[:8])}{' …' if len(missing) > 8 else ''}"
                         " (bookkit/contracts/check_contract.py <폴더> --add-ids 로 채운다)")

    # 항목 출처 열쇠 — 항목 id(Q1 · H3 …)
    # sec: 칸 이름 / i: 순번(쓰지 않음 — 부르는 쪽 모양 유지) / item: 항목
    def key_of(sec, i, item):
        return f"{sec}:{item['id']}"

    # 설문 하나(유저 답은 그대로) 또는 선택지 없으면 질문 노드
    # src: 출처 / parent: 부모 / q: 질문 / options: 선택지 / rec: 추천 번호 / why: 이유 / detail: 배경 / cat: 분류
    def survey_or_question(src, parent, q, options, rec, why, detail, cat):
        if options:
            # 설문 노드(새로 · 갱신)
            n = upsert(tree, rev, role, src, "s", {"kind": "survey", "graph": "task", "parent": parent, "cat": cat}, stats)
            n.setdefault("votes", [])
            n.setdefault("acks", [])
            fill_survey(n, q, options, rec, why, detail)
            return n
        n = upsert(tree, rev, role, src, "q", {"kind": "question", "title": need_text(q, "질문"), "cat": cat}, stats)
        n.setdefault("asked", rev)
        n.setdefault("events", [])
        n.setdefault("answers", [])
        return n

    # ── 요구(README) — 계약 readme · 임시 reqs
    for i, r in enumerate(reqs.get("readme") or reqs.get("reqs") or []):
        if not isinstance(r, dict) or not r.get("text"):
            continue
        # 본문
        body = "\n".join(x for x in (r.get("text"), f"묶음: {r['group']}" if r.get("group") else "",
                                     f"만들 것: {r['make']}" if r.get("make") else "", f"출처: {r['source']}" if r.get("source") else "") if x)
        upsert(tree, rev, role, "reqs:" + key_of("readme", i, r), "i", {
            "kind": "req", "graph": "task", "parent": g("req", "요구", "req"), "title": short_title(r.get("make") or r["text"]),
            "summary": short_summary(r["text"]), "text": body, "cat": cat_of(r.get("cat"))}, stats)
    # ── 숨은 요구 — 선택지가 있으면 그 밑에 설문
    for i, h in enumerate(reqs.get("hidden") or []):
        if not isinstance(h, dict) or not h.get("text"):
            continue
        # 본문
        body = "\n".join(x for x in (h.get("text"), f"위치: {h['where']}" if h.get("where") else "",
                                     f"이유: {h['why']}" if h.get("why") else "", f"만들 것: {h['make']}" if h.get("make") else "") if x)
        # 요구 노드
        n = upsert(tree, rev, role, "reqs:" + key_of("hidden", i, h), "i", {
            "kind": "req", "graph": "task", "parent": g("hidden", "숨은 요구", "req"), "hidden": True,
            "title": short_title(h.get("make") or h["text"]), "summary": short_summary(h["text"]), "text": body,
            "cat": cat_of(h.get("cat"))}, stats)
        if h.get("options"):
            survey_or_question("reqs:" + key_of("hidden", i, h) + ":survey", n["id"], h["text"], h["options"],
                               h.get("recommend"), h.get("why", ""), body, cat_of(h.get("cat")))
    # ── 명시 안 된 것(계약 silent) — 기본값 하나짜리 설문
    for i, s in enumerate(reqs.get("silent") or []):
        if not isinstance(s, dict) or not s.get("title"):
            continue
        survey_or_question("reqs:" + key_of("silent", i, s), g("ask", "담당자 질문 · 설문", "req"), s["title"],
                           [{"label": "기본값대로", "text": s.get("default", "")}], 0, s.get("why", ""),
                           "\n".join(x for x in (s.get("why"), f"기본값: {s['default']}" if s.get("default") else "") if x),
                           cat_of(s.get("cat")))
    # ── 담당자 질문 — 선택지(임시 options · 계약 rec/opp)가 있으면 설문, 없으면 질문 노드
    for i, q in enumerate(reqs.get("questions") or []):
        if not isinstance(q, dict) or not q.get("q"):
            continue
        # 선택지
        opts = q.get("options") or []
        # 추천 번호
        rec = q.get("recommend")
        if not opts and (q.get("rec") or q.get("opp")):
            opts = [o for o in ({"label": "추천안", "text": q.get("rec", "")} if q.get("rec") else None,
                                {"label": "다른 안", "text": q.get("opp", "")} if q.get("opp") else None) if o]
            rec = 0 if q.get("rec") else None
        elif isinstance(rec, str):
            # 추천 = 선택지 라벨 글자
            labels = [o.get("label") if isinstance(o, dict) else str(o).split("|")[0] for o in opts]
            rec = labels.index(rec) if rec in labels else None
        survey_or_question("reqs:" + key_of("questions", i, q), g("ask", "담당자 질문 · 설문", "req"), q["q"], opts, rec,
                           q.get("why", ""), q.get("why", ""), cat_of(q.get("cat")))

    # ── 파일 노드 — 이미 있는 파일 노드(제목 · 경로 끝이 같은 것)가 있으면 그것에 잇고, 없으면 만듦
    # name: 파일 이름 / extra: 새로 만들 때 칸
    def file_node(name, extra=None):
        name = str(name or "").strip()
        if not name:
            return g("files", "파일 · 함정", "files")
        if name in files_seen and not extra:
            return files_seen[name]
        for n in tree["nodes"]:
            if n.get("kind") == "file" and not n.get("src") and (n.get("title") == name or str(n.get("path") or "").endswith(name)):
                return n["id"]
        files_seen[name] = upsert(tree, rev, role, f"facts:file:{name}", "i", {"kind": "file", "graph": "task", "parent": g("files", "파일 · 함정", "files"),
                                                                              "title": name, **(extra or {})}, stats)["id"]
        return files_seen[name]
    # 파일 이름 → 노드 id(이번 불러오기에서 이미 다룬 것)
    files_seen = {}
    for f in facts.get("files") or []:
        if isinstance(f, dict) and f.get("name"):
            file_node(f["name"], {"summary": short_summary(f.get("desc")), "size": f"{f['rows']}행" if f.get("rows") is not None else None})
    # ── 함정(계약 traps · defects · 임시 facts 의 file 있는 항목) → 원본 파일 노드 밑 함정 노드
    # src: 출처 / item: 항목 / what: 무엇
    def trap(src, item, what):
        # 줄 번호 글자
        lines = item.get("lines") or ([item["line"]] if item.get("line") is not None else [])
        # 본문
        body = "\n".join(x for x in (re.sub(r"\*\*", "", what),
                                     f"줄: {', '.join(str(x) for x in lines)}" if lines else "",
                                     f"개수: {item['count']}" if item.get("count") is not None else "",
                                     f"원본: {item['raw']}" if isinstance(item.get("raw"), str) else "",
                                     f"잘못 · 정상: {item['bad']} → {item['good']}" if item.get("bad") else "",
                                     f"고치기: {re.sub(r'[*]{2}', '', str(item['fix']))}" if item.get("fix") else "") if x)
        upsert(tree, rev, role, src, "i", {"kind": "trap", "graph": "task", "parent": file_node(item.get("file")),
                                           "title": short_title(what), "summary": short_summary(what), "text": body,
                                           "cat": cat_of(item.get("cat"))}, stats)
    for i, t in enumerate(facts.get("traps") or []):
        if isinstance(t, dict) and t.get("what"):
            trap("facts:" + key_of("traps", i, t), t, t["what"])
    for i, d in enumerate(facts.get("defects") or []):
        if isinstance(d, dict) and d.get("what"):
            trap("facts:" + key_of("defects", i, d), d, d["what"])
    for i, f in enumerate(facts.get("facts") or []):
        if not isinstance(f, dict):
            continue
        if f.get("file") and f.get("what"):
            trap("facts:" + key_of("facts", i, f), f, f["what"])
        elif f.get("title"):
            # 자료 사실(계약 facts)
            body = "\n".join(x for x in (f.get("title"), f"영향: {re.sub(r'[*]{2}', '', str(f['effect']))}" if f.get("effect") else "",
                                         f"할 일: {f['do']}" if f.get("do") else "") if x)
            upsert(tree, rev, role, "facts:" + key_of("facts", i, f), "i", {
                "kind": "detail", "graph": "task", "parent": g("facts", "자료 사실", "req"), "title": short_title(f["title"]),
                "summary": short_summary(f["title"]), "text": body, "cat": cat_of(f.get("cat"))}, stats)
    return {"id": "", "msg": f"불러옴: 새 {stats['new']} · 갱신 {stats['upd']}"}


# MAIN — 지급 파일 노드 만들기(Main 화면 · 과제 파악을 시작할 때). import-analysis 와 같은 맨 위 · 묶음을 쓰고, 뒤에 불러와도 경로 끝이 같으면 이 노드에 잇는다
# files: 프로젝트 루트 기준 파일 경로 목록
def op_file_add(tree, rev, role, files=None):
    if not files:
        raise StoreError("파일 없음")
    # 셈 · 맨 위
    stats = {"new": 0, "upd": 0}
    root = next((n for n in tree["nodes"] if n.get("kind") == "root"), None)
    if root is None:
        root = upsert(tree, rev, role, "import:root", "i", {"kind": "root", "graph": "task", "title": "과제 파악"}, stats)
    # 묶음 · 이미 있는 경로
    group = upsert(tree, rev, role, "import:g:files", "i", {"kind": "group", "graph": "task", "parent": root["id"],
                                                            "title": "파일 · 함정", "section": "files"}, stats)
    have = {n.get("path") for n in tree["nodes"] if n.get("kind") == "file"}
    # 새로 만든 수
    made = 0
    for p in files:
        if p in have:
            continue
        at, _ = now_stamp()
        tree["nodes"].append({"id": next_id(tree, "i"), "kind": "file", "graph": "task", "parent": group["id"],
                              "title": p.rsplit("/", 1)[-1], "path": p, "seq": rev, "at": at, "by": role})
        made += 1
    return {"id": "", "msg": f"파일 노드: 새 {made} · 이미 있음 {len(files) - made}"}


# 명령 → 본체
OPS = {
    "add": op_add,
    "start": lambda tree, rev, role, task: op_event(tree, rev, role, "start", task),
    "hold": lambda tree, rev, role, task, note="": op_event(tree, rev, role, "hold", task, note),
    "block": lambda tree, rev, role, task, note="": op_event(tree, rev, role, "block", task, note),
    "done": lambda tree, rev, role, task: op_event(tree, rev, role, "done", task),
    "verify-add": op_verify_add,
    "answer-start": op_answer_start,
    "answer": op_answer,
    "verify-start": lambda tree, rev, role, verify: op_verify_event(tree, rev, role, "start", verify),
    "verify-hold": lambda tree, rev, role, verify, note="": op_verify_event(tree, rev, role, "hold", verify, note),
    "run": op_run,
    "mark": lambda tree, rev, role, verify, result: op_run(tree, rev, role, verify, result, "유저 표시"),
    "ask": op_ask, "ask-edit": op_ask_edit, "ask-close": op_ask_close, "ask-del": op_ask_del,
    "link": op_link, "unlink": op_unlink,
    "survey-add": op_survey_add, "survey-ack": op_survey_ack,
    "import-analysis": op_import_analysis,
    "file-add": op_file_add,
    "vote": op_vote, "edit": op_edit, "funcs": op_funcs, "check-add": op_verify_add,
    "funcs-set": op_funcs_set, "funcs-ack": op_funcs_ack, "funcs-scan": op_funcs_scan, "node-add": op_node_add, "node-del": op_node_del,
    "section-set": op_section_set, "fill": op_fill,
}


# ======= 상태 계산(저장하지 않음) — 화면 model.js workStatus 와 같은 규칙 =======
# 마지막 완료 사건의 seq(없으면 0)
# n: 작업 노드
def last_done_seq(n):
    return max((e.get("seq", 0) for e in n.get("events") or [] if e.get("t") == "done"), default=0)


# 일 노드 상태 — {status, label, result_seq(결과 기록 번호 · 진행 중 · 미완은 0), since(지금 상태가 된 초), stale, last(마지막 기록)}
# n: 노드 / nodes: id → 노드 / now: 지금 초(없으면 지금)
def status(n, nodes, now=None):
    # 지금 초
    now = time.time() if now is None else now
    # 종류
    kind = n.get("kind")
    # 결과 사전
    out = {"status": "todo", "label": TODO_LABEL.get(kind, ""), "result_seq": 0, "since": 0, "stale": False, "last": None}
    if kind == "task":
        # 마지막 사건
        last = (n.get("events") or [None])[-1]
        if last:
            # 사건 → 상태
            st = {"start": "doing", "hold": "hold", "block": "block", "done": "done"}.get(last.get("t"), "todo")
            if st == "doing" and now - (last.get("ts") or now) > LATE_SEC:
                st = "late"
            out.update(status=st, since=last.get("ts", 0), last=last)
    elif kind == "verify":
        # 사건 · 결과 전체(seq 순)
        recs = sorted([dict(e, _k="ev") for e in n.get("events") or []] + [dict(r, _k="run") for r in n.get("runs") or []],
                      key=lambda r: r.get("seq", 0))
        if recs:
            # 마지막 기록
            last = recs[-1]
            st = (last.get("result") if last["_k"] == "run" else {"start": "checking", "hold": "hold"}.get(last.get("t"))) or "todo"
            # 대상 작업
            tn = nodes.get(n.get("parent"))
            if last["_k"] == "run" and tn and tn.get("kind") == "task" and last_done_seq(tn) > last.get("seq", 0):
                out.update(stale=True, last=last)
            else:
                out.update(status=st, since=last.get("ts", 0), last=last)
    elif kind == "survey":
        # 마지막 유저 답(선택 · 메모 · 보류)
        last = (n.get("votes") or [None])[-1]
        if last:
            st = "held" if last.get("hold") else "picked" if last.get("pick") is not None else "todo"
            out.update(status=st, since=last.get("ts", 0), last=last)
    elif kind == "question":
        # 물은 seq · 기록 전체
        recs = [{"_k": "ask", "seq": n.get("asked") or n.get("seq") or 0}]
        recs += [dict(e, _k="ev") for e in n.get("events") or []] + [dict(a, _k="ans") for a in n.get("answers") or []]
        # 마지막 기록(같은 seq 면 뒤에 넣은 것)
        last = sorted(recs, key=lambda r: r.get("seq", 0))[-1]
        if last["_k"] == "ev":
            out.update(status="answering", since=last.get("ts", 0), last=last)
        elif last["_k"] == "ans":
            out.update(status="answered", since=last.get("ts", 0), last=last)
    if out["status"] != "todo":
        out["label"] = STATUS_LABEL[out["status"]]
    if out["status"] in RESULT_STATES and out["last"]:
        out["result_seq"] = out["last"].get("seq", 0)
    return out


# ======= 옛 형식(1) → 새 형식(2) 옮기기 =======
# 옛 tree.json answers · verified 와 tree.user.json questions 를 질문 · 검증 노드로. 접힘(collapsed) · 추가 화면(views)은 버림
# tree: tree.json 내용 / user: tree.user.json 내용 → (새 tree, 새 user, 옮긴 개수 사전)
def migrate(tree, user):
    tree = json.loads(json.dumps(tree or empty_tree()))
    user = json.loads(json.dumps(user or {}))
    tree.setdefault("nodes", [])
    tree.setdefault("edges", [])
    # 새 판 번호
    rev = int(tree.get("rev") or 0) + 1
    # 옛 답 사전
    answers = tree.pop("answers", None) or {}
    # 옛 검증 결과 사전
    verified = tree.pop("verified", None) or {}
    # 옮긴 개수
    counts = {"questions": 0, "answers": 0, "verifies": 0}
    # 트리 노드 id 집합
    ids = set(node_map(tree))
    at, ts = now_stamp()
    # 옛 질문 하나
    for q in user.pop("questions", None) or []:
        if not isinstance(q, dict) or not q.get("text"):
            continue
        # 새 id(옛 id 가 비었거나 겹치면 새로)
        qid = q.get("id") if q.get("id") and q["id"] not in ids else next_id(tree, "q")
        # 옛 답
        a = answers.get(q.get("id"))
        # 새 질문 노드
        node = {"id": qid, "kind": "question", "title": q["text"], "seq": rev, "asked": rev, "at": q.get("at") or at,
                "by": "user", "events": [], "answers": []}
        if q.get("closed"):
            node["closed"] = True
        if a and a.get("text"):
            # 결론 한 줄 — 첫 문장(60자까지)
            short = re.split(r"(?<=[.!?])\s", a["text"].strip())[0][:SUMMARY_MAX]
            node["answers"].append({"seq": rev, "at": at, "ts": ts, "by": a.get("by") or "2nd", "short": short, "text": a["text"]})
            counts["answers"] += 1
        tree["nodes"].append(node)
        ids.add(qid)
        if q.get("target"):
            tree["edges"].append({"id": next_id(tree, "a"), "source": qid, "target": q["target"], "kind": "asks"})
        counts["questions"] += 1
    # 옛 검증 대상 · 결과
    for target, res in verified.items():
        if target not in ids or not isinstance(res, dict):
            continue
        # 새 id
        vid = next_id(tree, "v")
        # 근거 글자
        note = " · ".join(x for x in (res.get("script"), res.get("note"), res.get("commit")) if x) or "옛 기록"
        tree["nodes"].append({
            "id": vid, "kind": "verify", "parent": target, "title": res.get("script") or "검증(옛 기록)", "seq": rev, "at": at,
            "by": "main", "events": [],
            "runs": [{"seq": rev, "at": at, "ts": ts, "by": res.get("by") or "insp",
                      "result": "pass" if res.get("status") == "pass" else "fail", "note": note}],
        })
        ids.add(vid)
        counts["verifies"] += 1
    user.pop("collapsed", None)
    # 추가 화면(구현 모듈 · 아이디어)은 2026-11-01 삭제 — 남은 칸 버림
    tree.pop("views", None)
    # 옮긴 화면 위치 — 추가 화면(v:…) 위치는 버림
    user["positions"] = {k: v for k, v in (user.get("positions") or {}).items() if not str(k).startswith("v:")}
    tree["version"] = FORMAT
    tree["rev"] = rev
    return tree, user, counts
