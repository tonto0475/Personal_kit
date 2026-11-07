# tree.json 점검 — 형식 · 연결 · 결정 · 코드 대조(tree.auto.json) · 유저 선택 충돌(tree.user.json)
"""
문제만 출력(성공은 개수 한 줄). error 가 하나라도 있으면 종료코드 1
파일 셋 · 쓰는 쪽
- tree.json       flowtree.py · 화면이 flowtree_store 로만 씀(노드 · 선 · 작업 · 검증 · 질문 노드와 그 기록)
- tree.auto.json  scan_code.py 가 씀(코드에서 감지한 모듈 · import · 호출)
- tree.user.json  화면(유저)이 씀(토글 · 선택 · 검증 방법 · 유저 선 · 배치 · 확인 기록)
노드 연결 문서 doc: {path(프로젝트 루트 기준), anchor} — 파일 · 앵커가 있는지만 점검(제목 글자로 찾지 않음)
  anchor «1-2» = 그 번호로 시작하는 제목 줄(hand_off 절) · «^이름» = 옵시디언 블록 id(줄 끝) · 없으면 파일만
파이썬 3.10 이상 · 표준 라이브러리만
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 노드 종류 → 뜻
NODE_KINDS = {
    "root": "맨 위", "group": "묶음", "file": "초기 파일", "req": "필수 요구", "detail": "세부 주의",
    "optional": "곁가지", "dont": "안 만들 것", "decision": "결정", "option": "선택지",
    "module": "모듈", "stack": "기술 스택",
    "task": "작업", "verify": "검증", "question": "질문", "survey": "설문",
    "section": "섹션 후보", "trap": "함정",
}
# 일 노드 종류(작업 · 검증 · 질문 — flowtree.py · 화면이 만듦) — 부모 없이도 됨(검증 제외) · 제목 길이 안 봄(검증 · 질문)
WORK_KINDS = {"task", "verify", "question", "survey"}
# 선 종류 → 뜻
EDGE_KINDS = {
    "implements": "구현", "flow": "동작 흐름", "requires": "필요", "conflicts": "충돌", "calls": "설계상 호출",
    "asks": "질문",
}
# 질문 선 대상으로 받는 화면 노드 id 접두어(코드 모듈 · 함수 · 외부 라이브러리)
SCREEN_PREFIX = ("mod:", "fn:", "ext:")
# 요약 최대 글자(작업)
SUMMARY_MAX = 60
# 그래프 이름(task 과제 파악 · hand_off 구현 진행 — 개편 2026-11-03)
GRAPHS = ("task", "hand_off")
# 옛 그래프 이름 → 지금 이름(옛 tree.json 도 오류 없이 읽음)
OLD_GRAPHS = {"adr": "hand_off"}


# 노드의 graph 칸 — 옛 이름(adr)은 지금 이름으로
# n: 노드
def gr(n):
    return OLD_GRAPHS.get(n.get("graph"), n.get("graph"))


# 제목 길이 경고 기준(글자) — 카드 두 줄 안
TITLE_MAX = 18
# 검증 방법 값
VERIFY_VALUES = {"test", "manual", "none"}


# JSON 파일 읽기. 없으면 기본값
# path: 파일 경로 / default: 없을 때 값
def load_json(path, default=None):
    # 파일 경로
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


# 노드 켜짐 판정 — 곁가지는 유저 토글, 선택지는 결정의 선택(유저 > 담당자 결정), 안 만들 것은 꺼짐
# node: 노드 / nodes: id → 노드 / picks: 유저 선택
def is_on(node, nodes, picks):
    # 노드 종류
    kind = node.get("kind")
    if kind == "optional":
        return picks.get(node["id"]) is True
    if kind == "dont":
        return False
    if kind == "option":
        # 소속 결정
        dec = nodes.get(node.get("parent"))
        return bool(dec) and decision_pick(dec, picks) == node["id"]
    return True


# 결정의 현재 선택 — 유저 선택 > 담당자 결정(decided) > 없음
# dec: 결정 노드 / picks: 유저 선택
def decision_pick(dec, picks):
    # 유저 선택값
    p = picks.get(dec["id"])
    if isinstance(p, str):
        return p
    return (dec.get("decided") or {}).get("pick")


# 문서 앵커 찾기 — 줄 번호(1부터) 또는 None
#   «^이름» = 옵시디언 블록 id(줄 끝 « ^이름») · 그 밖 = 절 번호(«1-2» → «## 1-2 · …» · «### 1-2. …» 같은 제목 줄)
#   제목 글자로는 찾지 않는다(글자를 고쳐도 연결이 안 끊기게)
# text: 문서 전체 글 / anchor: 앵커 값
def find_anchor(text, anchor):
    # 앵커 앞뒤 공백 뺀 값
    a = str(anchor or "").strip()
    if not a:
        return None
    if a.startswith("^"):
        # 블록 id 줄 — 줄 끝(뒤 공백 허용) · 앞은 줄 처음이거나 공백
        pat = re.compile(r"(?:^|\s)" + re.escape(a) + r"\s*$")
    else:
        # 절 번호 제목 — 번호 뒤에 숫자 · 하이픈이 이어지면 다른 절(1-2 ≠ 1-20 · 1-2-1)
        pat = re.compile(r"^#{1,6}\s+" + re.escape(a) + r"(?![0-9-])")
    # 줄 번호 · 줄 글
    for i, line in enumerate(text.splitlines(), 1):
        if pat.search(line):
            return i
    return None


# 노드의 연결 문서 칸 → (경로, 앵커) 또는 None
#   doc: {path, anchor} · 파일 노드는 path 칸만 있어도 됨(앵커 없이 파일 열기)
# n: 트리 노드
def doc_ref(n):
    # 연결 문서 칸
    d = n.get("doc")
    if isinstance(d, dict) and d.get("path"):
        return str(d["path"]), d.get("anchor")
    if isinstance(d, str) and d:
        return d, None
    if n.get("kind") == "file" and n.get("path"):
        return str(n["path"]), None
    return None


# 연결 문서 풀이 — 노드 id → {path, anchor, line, error}. 프로젝트 루트 밖 · 없는 파일 · 없는 앵커는 error 칸
# tree: tree.json 내용 / root: 프로젝트 루트(devview 작업 폴더)
def resolve_docs(tree, root):
    # 프로젝트 루트(절대 경로)
    base = Path(root).resolve()
    # 결과 사전
    out = {}
    # 파일 경로 → 글(같은 문서를 여러 노드가 가리킬 때 한 번만 읽기)
    texts = {}
    for n in tree.get("nodes", []):
        # 노드의 연결 문서
        ref = doc_ref(n) if isinstance(n, dict) else None
        if not ref or not n.get("id"):
            continue
        # 경로 · 앵커
        rel, anchor = ref
        # 결과 한 칸
        item = {"path": rel.replace("\\", "/").strip("/"), "anchor": anchor, "line": None, "error": None}
        out[n["id"]] = item
        # 실제 파일 경로
        p = (base / item["path"]).resolve()
        if p != base and base not in p.parents:
            item["error"] = f"프로젝트 밖 경로: {rel}"
            continue
        if not p.is_file():
            item["error"] = f"파일 없음: {item['path']}"
            continue
        if anchor in (None, ""):
            continue
        if p not in texts:
            try:
                texts[p] = p.read_text(encoding="utf-8", errors="replace")
            # 읽기 실패(권한 등)
            except OSError as err:
                texts[p] = None
                item["error"] = f"읽기 실패: {item['path']} — {err}"
                continue
        if texts[p] is None:
            item["error"] = f"읽기 실패: {item['path']}"
            continue
        item["line"] = find_anchor(texts[p], anchor)
        if item["line"] is None:
            item["error"] = f"앵커 없음: {item['path']} «{anchor}»"
    return out


# 점검 — 문제 목록 반환. 문제 = {level, code, target, msg}
# tree: tree.json 내용 / auto: tree.auto.json 내용 / user: tree.user.json 내용
# root: 프로젝트 루트 — 주면 노드 연결 문서(doc) 파일 · 앵커가 있는지도 점검(None 이면 건너뜀)
def check(tree, auto=None, user=None, root=None):
    # 문제 목록
    out = []

    # 문제 추가
    # level: error · warn · info / code: 문제 코드 / target: 대상 id / msg: 설명
    def add(level, code, target, msg):
        out.append({"level": level, "code": code, "target": target, "msg": msg})

    # 노드 목록
    node_list = tree.get("nodes", [])
    # id → 노드
    nodes = {}
    # 노드 하나
    for n in node_list:
        # 노드 id
        nid = n.get("id")
        if not nid:
            add("error", "no-id", None, f"id 없는 노드: {n.get('title', '?')}")
            continue
        if nid in nodes:
            add("error", "dup-id", nid, f"id 중복: {nid}")
        nodes[nid] = n
        # 빈 틀 노드 — 채워지기 전에는 점검 안 함
        if n.get("frame"):
            continue
        if n.get("kind") not in NODE_KINDS:
            add("error", "bad-kind", nid, f"모르는 종류 «{n.get('kind')}»")
        if not n.get("title") and not n.get("pos0"):
            add("error", "no-title", nid, "제목 없음")
        elif len(n.get("title") or "") > TITLE_MAX and n.get("kind") not in ("verify", "question", "survey") and not n.get("auto"):
            add("warn", "title-long", nid, f"제목 {len(n['title'])}자 — {TITLE_MAX}자 안으로(카드 두 줄)")

        if n.get("kind") == "task" and len(str(n.get("summary") or "")) > SUMMARY_MAX:
            add("warn", "summary-long", nid, f"요약 {len(n['summary'])}자 — {SUMMARY_MAX}자 안으로")
        # 기록 칸 하나 — 목록이어야 함
        for key in ("events", "runs", "answers", "votes", "acks", "edits"):
            if key in n and not isinstance(n[key], list):
                add("error", "record-bad", nid, f"«{key}» 는 목록이어야 함")
        if n.get("kind") == "survey":
            # 선택지 목록
            opts = n.get("options")
            if not isinstance(opts, list) or not opts:
                # 유저가 노드 추가 단추로 만든 설문 — 선택지는 아직 없음(경고만)
                if (n.get("by") == "user" or n.get("pos0")) and isinstance(opts, list):
                    add("warn", "survey-options", nid, "설문 선택지 없음 — 유저가 만든 설문")
                else:
                    add("error", "survey-options", nid, "설문 선택지 없음")
            elif n.get("recommend") is not None and not (isinstance(n["recommend"], int) and 0 <= n["recommend"] < len(opts)):
                add("error", "survey-recommend", nid, f"추천 번호 «{n['recommend']}» 가 선택지 밖")

    # 맨 위 노드 목록
    roots = [n for n in nodes.values() if n.get("kind") == "root"]
    # 일 노드만 있는 그래프(맨 위 없이 작업부터 시작)는 root 없어도 됨
    only_work = all(n.get("kind") in WORK_KINDS for n in nodes.values())
    if len(roots) > 1 or (not roots and not only_work):
        add("error", "root-count", None, f"root 노드 {len(roots)}개 — 1개여야 함")
    # 부모 · 순환 점검
    for nid, n in nodes.items():
        if n.get("kind") == "root":
            continue
        # 질문은 부모 없음(선으로 대상을 이음) · 작업 · 검증 · 설문 · hand_off 그래프 노드는 맨 위(부모 없음)도 됨
        if n.get("kind") == "question" or (not n.get("parent") and (n.get("kind") in ("task", "verify", "survey") or gr(n) == "hand_off")):
            continue
        # 부모 id
        parent = n.get("parent")
        if parent not in nodes:
            add("error", "missing-parent", nid, f"부모 «{parent}» 없음")
            continue
        # 거슬러 올라가며 본 id
        seen = {nid}
        # 현재 위치
        cur = parent
        while cur in nodes and nodes[cur].get("kind") != "root":
            if cur in seen:
                add("error", "parent-cycle", nid, "부모를 따라가면 제자리로 돌아옴")
                break
            seen.add(cur)
            cur = nodes[cur].get("parent")

    # 그래프 칸 점검(옛 from · chosen · confirmed 칸은 무시)
    for nid, n in nodes.items():
        if "graph" in n and gr(n) not in GRAPHS:
            add("error", "graph-bad", nid, f"그래프 «{n['graph']}» — task · hand_off")
        if n.get("kind") == "file" and gr(n) == "hand_off":
            add("error", "graph-file-hand-off", nid, "파일 노드는 Task 그래프에만")
        # 부모
        par = nodes.get(n.get("parent"))
        if par and gr(n) in GRAPHS and gr(par) in GRAPHS and gr(par) != gr(n):
            add("error", "graph-parent", nid, f"부모 «{par['id']}» 는 {par['graph']} 그래프 — 이 노드는 {n['graph']}")

    # 자식 목록
    children = {}
    # 노드 하나
    for nid, n in nodes.items():
        if n.get("parent") in nodes:
            children.setdefault(n["parent"], []).append(nid)

    # 결정 · 선택지 점검
    for nid, n in nodes.items():
        if n.get("kind") == "decision":
            # 선택지 id 목록
            opts = [c for c in children.get(nid, []) if nodes[c].get("kind") == "option"]
            if len(opts) < 2:
                add("error", "decision-options", nid, f"선택지 {len(opts)}개 — 2개 이상")
            if n.get("recommend") and n["recommend"] not in opts:
                add("error", "recommend-not-option", nid, f"추천 «{n['recommend']}» 이 이 결정의 선택지가 아님")
            # 담당자 결정
            dec = (n.get("decided") or {}).get("pick")
            if dec and dec not in opts:
                add("error", "decided-not-option", nid, f"담당자 결정 «{dec}» 이 선택지가 아님")
            if n.get("cost") not in ("high", "low"):
                add("warn", "cost-missing", nid, "비용(cost: high · low) 없음 — 비싼 결정인지 표시")
            if n.get("cost") == "high" and not n.get("due"):
                add("warn", "due-missing", nid, "비싼 결정인데 «언제까지(due)» 없음")
        if n.get("kind") == "option" and nodes.get(n.get("parent"), {}).get("kind") != "decision":
            add("error", "option-outside", nid, "선택지가 결정 밑에 있지 않음")

    # 선 점검
    for i, e in enumerate(tree.get("edges", [])):
        # 선 이름(출력용)
        label = f"선 {i + 1} ({e.get('source')} → {e.get('target')})"
        if e.get("kind") not in EDGE_KINDS:
            add("error", "edge-bad-kind", e.get("source"), f"{label}: 모르는 종류 «{e.get('kind')}»")
        if e.get("kind") == "asks":
            if nodes.get(e.get("source"), {}).get("kind") != "question":
                add("error", "asks-not-question", e.get("source"), f"{label}: 질문 선의 출발이 질문 노드가 아님")
            if e.get("target") not in nodes and not str(e.get("target") or "").startswith(SCREEN_PREFIX):
                add("error", "edge-missing-node", e.get("source"), f"{label}: target «{e.get('target')}» 없음")
            continue
        # 끝점 하나
        for end in ("source", "target"):
            if e.get(end) not in nodes:
                add("error", "edge-missing-node", e.get("source"), f"{label}: {end} «{e.get(end)}» 없음")
        if e.get("kind") == "implements" and nodes.get(e.get("target"), {}).get("kind") != "module":
            add("error", "implements-not-module", e.get("source"), f"{label}: 구현 선의 도착이 모듈이 아님")

    # 코드 대조(스캔 결과가 있을 때)
    if auto is not None:
        # 코드에서 찾은 모듈 이름
        code_mods = {m["name"] for m in auto.get("modules", [])}
        # 트리 모듈의 code 값
        tree_codes = set()
        # 노드 하나
        for nid, n in nodes.items():
            if n.get("kind") != "module":
                continue
            if not n.get("code"):
                add("warn", "module-no-code", nid, "모듈에 code(점 이름) 없음 — 코드와 못 이음")
                continue
            tree_codes.add(n["code"])
            if n["code"] not in code_mods:
                add("warn", "module-not-in-code", nid, f"코드에 없음: {n['code']}")
        # 코드에만 있는 모듈 하나
        for name in sorted(code_mods - tree_codes):
            add("info", "module-untracked", name, f"트리에 없는 모듈: {name}")
        # 위반 하나
        for v in auto.get("violations", []):
            add("error", "layer-violation", v["source"], f"층 규칙 위반 {v['rule']} — {v['source']} → {v['target']} ({v['file']}:{v['line']})")
        # 파싱 실패 하나
        for err in auto.get("errors", []):
            add("warn", "scan-error", err["file"], f"코드 파싱 실패 {err['file']} — {err['error']}")

    # 유저 선택 대조
    if user is not None:
        # 유저 선택
        picks = user.get("picks", {})
        # 선택 하나
        for nid, val in picks.items():
            if nid not in nodes:
                add("warn", "pick-missing-node", nid, f"선택한 노드 «{nid}» 가 트리에 없음")
                continue
            # 노드 종류
            kind = nodes[nid].get("kind")
            if kind == "decision" and not (isinstance(val, str) and val in children.get(nid, [])):
                add("warn", "pick-bad-option", nid, f"결정 선택값 «{val}» 이 선택지가 아님")
            if kind == "optional" and not isinstance(val, bool):
                add("warn", "pick-bad-toggle", nid, "곁가지 선택값은 참 · 거짓")
        # 비싼 결정 미결정
        for nid, n in nodes.items():
            if n.get("kind") == "decision" and n.get("cost") == "high" and not decision_pick(n, picks):
                add("warn", "decision-open", nid, f"미결정(비쌈) «{n['title']}» — {n.get('due') or '언제까지 미정'}")
        # 트리 선 하나 — 필요 · 충돌
        for e in tree.get("edges", []):
            # 출발 · 도착 노드
            s, t = nodes.get(e.get("source")), nodes.get(e.get("target"))
            if not s or not t:
                continue
            if e.get("kind") == "conflicts" and is_on(s, nodes, picks) and is_on(t, nodes, picks):
                add("error", "conflict-on", s["id"], f"충돌: «{s['title']}» 과 «{t['title']}» 이 둘 다 켜짐 — {e.get('label', '')}")
            if e.get("kind") == "requires" and is_on(s, nodes, picks) and not is_on(t, nodes, picks):
                add("warn", "requires-off", s["id"], f"«{s['title']}» 은 «{t['title']}» 이 필요 — 지금 꺼짐 · 미정")
        # 검증 방법 하나
        for target, val in user.get("verify", {}).items():
            if val not in VERIFY_VALUES:
                add("warn", "verify-bad", target, f"검증 방법 «{val}» — test · manual · none")
        # 유저 노드 id 집합(복사 · 붙여넣기로 만든 🚹 노드)
        unode_ids = set()
        # 유저 노드 하나
        for un in user.get("nodes", []):
            if not isinstance(un, dict) or not un.get("id"):
                add("warn", "user-node-bad", None, "id 없는 유저 노드")
                continue
            if un["id"] in nodes or un["id"] in unode_ids:
                add("warn", "user-node-dup", un["id"], f"유저 노드 id 중복: {un['id']}")
            unode_ids.add(un["id"])
            if not un.get("title"):
                add("warn", "user-node-no-title", un["id"], "유저 노드 제목 없음")
        # 유저 선 하나
        for e in user.get("edges", []):
            # 끝점 하나
            for end in ("source", "target"):
                # 끝점 id
                v = e.get(end)
                if v not in nodes and v not in unode_ids and not str(v or "").startswith(("mod:", "ext:")):
                    add("warn", "user-edge-missing", e.get("id"), f"유저 선 «{e.get('id')}» 의 {end} «{v}» 없음")
    # 질문 노드 하나 — 닫히지 않았고 답이 없으면 참고
    for nid, n in nodes.items():
        if n.get("kind") == "question" and not n.get("closed") and not n.get("answers"):
            add("info", "question-open", nid, f"답 없는 질문: {str(n.get('title', ''))[:40]}")
    if root is not None:
        # 노드 id · 연결 문서 풀이
        for nid, item in resolve_docs(tree, root).items():
            if item["error"]:
                add("error", "doc-anchor-missing" if item["error"].startswith("앵커") else "doc-missing", nid, item["error"])
    return out


# 명령줄 — 문제만 출력 + 요약 한 줄
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    # 명령줄 해석기
    ap = argparse.ArgumentParser(description="tree.json 점검(형식 · 연결 · 결정 · 코드 대조 · 유저 선택)")
    ap.add_argument("tree", help="tree.json 경로 — 옆의 tree.auto.json · tree.user.json 도 읽음")
    ap.add_argument("--info", action="store_true", help="info 단계(답 없는 질문 · 트리에 없는 모듈)도 출력")
    ap.add_argument("--root", default=".", help="프로젝트 루트 — 노드 doc 경로의 기준(기본 현재 폴더)")
    # 해석 결과
    args = ap.parse_args(argv)
    # tree.json 경로
    tree_path = Path(args.tree)
    # 점검 결과
    probs = check(load_json(tree_path, {}), load_json(tree_path.with_name("tree.auto.json")),
                  load_json(tree_path.with_name("tree.user.json")), root=args.root)
    # 단계 → 표시
    mark = {"error": "🔴", "warn": "🟠", "info": "·"}
    # 문제 하나
    for p in probs:
        if p["level"] == "info" and not args.info:
            continue
        print(f"{mark[p['level']]} {p['code']} {p['target'] or ''} — {p['msg']}")
    # 단계별 개수
    counts = {lv: sum(1 for p in probs if p["level"] == lv) for lv in mark}
    print(f"점검: 오류 {counts['error']} · 경고 {counts['warn']} · 참고 {counts['info']}")
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
