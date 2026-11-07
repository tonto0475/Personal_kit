# flowtree 명령 — Codex 세션(MAIN · 2ND · INSP)이 그래프(tree.json)를 읽고 쓰는 유일한 길
"""
사용: python3 flowtree.py --role <main|2nd|insp> <명령> …   (기본 그래프 = <현재 폴더>/docs/flowtree/tree.json · --tree 로 바꿈)
  MAIN : add <부모|-> "제목" --summary "…(60자)" [--text "설명"] [--doc 경로#앵커] [--graph task|hand_off] [--section N] [--func "파일 | 함수 | 설명 | ⭐"]…
         funcs-set <작업> --row "파일 | 함수 | 설명 | ⭐" …(여러 번) 또는 --json '[{"file","name","desc","core"}]'(@파일 도 됨)
           (함수 표 = 지금 코드 — 유저가 고친 칸은 못 덮음 · 목록에 없는 에이전트 행은 지움)
         funcs-ack <작업> ["무엇을 했나"](유저가 바꾼 이름을 코드 · 시험 · 문서에 반영함 → 이름 바뀜 닫힘)
         funcs-scan <작업>(표의 파일에서 함수 바로 위 주석 한 줄 → 빈 설명 칸 · 코드에 없는 이름 경고)
         start <작업> · hold <작업> "사유"
         block <작업> "유저에게 필요한 것" · done <작업> · verify-add <대상> "확인할 것" [--section N]
         section-set <노드> <N|->(화면 섹션 바꾸기 · «-» 면 Main 만)
         fill <틀 노드> --title … [--summary …] [--text …] [--doc 경로#앵커] [--func "파일 | 함수 | 설명 | ⭐"]…(작업)
           [--script 경로](검증) · [--option "라벨|풀이|장점;…|단점;…"]… [--recommend N] [--why …] [--detail …](설문 · 제목 = 질문)
         survey-add <대상|-> "질문" --option "라벨|풀이|장점;…|단점;…" … [--recommend N] [--why "추천 이유"] [--detail "배경"] [--graph task|hand_off] [--section N]
         survey-ack <설문> ["무엇을 했나"] · import-analysis <폴더>(reqs.json · facts.json → Task 노드)
         file-add <파일|폴더>…(지급 파일 노드 · 폴더면 안의 파일 전부 · 다시 해도 있는 경로는 그대로)
  2ND  : answer-start <질문> · answer <질문> --short "결론(60자)" "본문"
  INSP : verify-start <검증> · verify-hold <검증> "사유" · run <검증> pass|fail "근거(시험 경로 · 명령)"
  공통 : inbox(내 역할이 할 일 + 대상 맥락) · show <id>(노드 + 연결 노드) · check(형식 · 연결 · 앵커 점검) · frames [섹션](빈 틀 노드 id)
  유저(화면 · 시험용 --role user): vote <설문> [--pick N|--clear] [--memo …] [--hold|--unhold] · edit <노드> [--title …] [--summary …] [--text …]
         funcs <작업> [--row f1] [--file …] [--name …] [--desc …] [--core|--no-core] [--del] · check-add <대상> "확인할 것"
  한 번만: migrate(옛 형식 answers · verified · 유저 questions → 질문 · 검증 노드)
출력은 짧게 — 성공 한 줄 · 실패는 «실패: 원인» 한 줄(표준 오류) + 종료코드 1
쓰기는 flowtree_store 하나로만(잠금 → 다시 읽기 → 고침 → 교체) · 역할이 다른 칸은 거부
파이썬 3.10 이상 · 표준 라이브러리만
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from pathlib import Path

# 이 파일이 있는 폴더 — flowtree_store · tree_check import
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import flowtree_store as store  # noqa: E402
import tree_check  # noqa: E402

# 점검 출력 최대 줄 수(넘으면 개수만)
CHECK_LINES = 20


# 시각 글자 줄이기(«2026-11-01 21:30:05» → «11-01 21:30»)
# at: 시각 글자
def short_at(at):
    return str(at or "")[5:16]


# 노드 한 줄 — «id [상태] 제목»(일 노드) · «id 종류 제목»(그 밖)
# n: 노드 / nodes: id → 노드 / now: 지금 초
def node_line(n, nodes, now):
    if n.get("kind") in store.WORK_KINDS:
        # 상태
        st = store.status(n, nodes, now)
        # 상태 글자(착수면 지난 분)
        lab = st["label"] + (f" {int((now - st['since']) // 60)}분" if st["status"] in ("doing", "late") and st["since"] else "")
        if st["stale"]:
            lab += " · 대상 다시 완료"
        if n.get("closed"):
            lab += " · 닫힘"
        if n.get("kind") == "survey" and n.get("acks") and not store.survey_pending(n) and st["status"] != "todo":
            lab += " · 반영됨"
        return f"{n['id']} [{lab}] {store.eff(n, 'title')}"
    return f"{n.get('id')} {tree_check.NODE_KINDS.get(n.get('kind'), n.get('kind'))} {store.eff(n, 'title')}"


# 연결 문서 글자(«경로#앵커»)
# n: 노드
def doc_text(n):
    # 경로 · 앵커
    ref = tree_check.doc_ref(n)
    if not ref:
        return ""
    return ref[0] + (f"#{ref[1]}" if ref[1] else "")


# 대상 맥락 한 줄 — «→ id 제목 — 요약 · 문서»
# nid: 대상 id / nodes: id → 노드 / now: 지금 초
def ctx_line(nid, nodes, now):
    # 대상 노드
    n = nodes.get(nid)
    if not n:
        return f"  → {nid}" + ("" if nid.startswith(store.SCREEN_PREFIX) else " (없는 노드)")
    # 덧붙일 조각
    parts = [p for p in (store.eff(n, "summary"), doc_text(n)) if p]
    return f"  → {node_line(n, nodes, now)}" + (f" — {' · '.join(parts)}" if parts else "")


# 질문의 대상 id 목록(질문 선)
# tree: 그래프 / qid: 질문 id
def ask_targets(tree, qid):
    return [e.get("target") for e in tree.get("edges", []) if e.get("kind") == "asks" and e.get("source") == qid]


# 설문 답 글자 — «선택: 라벨 · 메모: …» · «보류 · 메모: …»
# n: 설문 노드
def vote_text(n):
    # 지금 답 · 선택지
    v = store.survey_vote(n)
    opts = n.get("options") or []
    # 조각
    parts = ["보류"] if v["hold"] else []
    if v["pick"] == store.PICK_OTHER:
        parts.append("기타")
    elif v["pick"] is not None and v["pick"] < len(opts):
        parts.append(f"선택: {v['pick'] + 1}. {opts[v['pick']].get('label', '')}")
    if v["memo"]:
        parts.append(f"메모: {v['memo']}")
    return " · ".join(parts) or "미응답"


# 할 일 목록 줄 — 역할별
# tree: 그래프 / role: 역할 / now: 지금 초
def inbox_lines(tree, role, now):
    # id → 노드
    nodes = store.node_map(tree)
    # 출력 줄
    out = []
    for n in nodes.values():
        # 종류
        kind = n.get("kind")
        # 빈 틀 노드는 할 일이 아님
        if kind not in store.WORK_KINDS or n.get("frame"):
            continue
        # 상태
        st = store.status(n, nodes, now)
        # 함수 표(지우지 않은 행)
        rows = [r for r in store.func_rows(n) if not r.get("del")] if kind == "task" else []
        if role == "main" and kind == "task":
            # 이름 바뀜(완료된 작업도) — 유저가 고친 이름을 코드에 반영할 일
            out.extend(f"{n['id']} [이름 바뀜] {store.eff(n, 'title')} — {store.func_change(r)} (코드 · 시험 · 문서도 새 이름으로 → funcs-ack {n['id']})"
                       for r in store.funcs_pending(n))
        if role == "main":
            if kind == "task" and st["status"] != "done":
                out.append(node_line(n, nodes, now) + (f" — {st['last'].get('note')}" if st["last"] and st["last"].get("note") else "")
                           + (f" · 함수 {len(rows)}" if rows else ""))
            elif kind == "survey" and store.survey_pending(n):
                out.append(f"{n['id']} [설문 {'보류' if store.survey_vote(n)['hold'] else '결정됨'}] {store.eff(n, 'title')} — {vote_text(n)}")
            elif kind == "verify" and st["status"] == "fail":
                out.append(node_line(n, nodes, now) + f" — {st['last'].get('note', '')}")
                out.append(ctx_line(n.get("parent"), nodes, now))
        elif role == "2nd":
            if kind == "question" and not n.get("closed") and st["status"] in ("todo", "answering"):
                out.append(node_line(n, nodes, now))
                # 대상 id 목록
                targets = ask_targets(tree, n["id"])
                out.extend(ctx_line(t, nodes, now) for t in targets)
                if not targets:
                    out.append("  (섬 질문 — 대상 없음)")
        elif role == "insp":
            if kind == "verify" and st["status"] in ("todo", "checking"):
                out.append(node_line(n, nodes, now) + (f" — 지난 결과 {st['last'].get('result')}" if st["stale"] else ""))
                out.append(ctx_line(n.get("parent"), nodes, now))
        elif role == "user":
            if (kind == "task" and st["status"] == "block") or (kind == "question" and st["status"] == "answered" and not n.get("closed")) \
                    or (kind == "survey" and st["status"] == "todo"):
                out.append(node_line(n, nodes, now))
    return out or ["할 일 없음"]


# 노드 보기 줄 — 노드 전체 + 연결 노드 한 줄씩
# tree: 그래프 / nid: 노드 id / now: 지금 초
def show_lines(tree, nid, now):
    # id → 노드
    nodes = store.node_map(tree)
    # 노드
    n = nodes.get(nid)
    if n is None:
        raise store.StoreError(f"없는 id «{nid}»")
    # 출력 줄
    out = [node_line(n, nodes, now)]
    out.append(f"그래프: {store.graph_of(nodes, n)}")
    if "screen" in n:
        out.append(f"섹션: {n['screen']}")
    if n.get("frame"):
        out.append("빈 틀 노드")
    if store.eff(n, "script"):
        out.append(f"스크립트: {store.eff(n, 'script')}")
    for key, name in (("summary", "요약"), ("text", "설명")):
        if store.eff(n, key):
            out.append(f"{name}: {store.eff(n, key)}" + (f"  (유저 고침 — 원래: {n.get(key) or '없음'})" if (n.get("edit") or {}).get(key) else ""))
    if (n.get("edit") or {}).get("title"):
        out.append(f"제목 유저 고침 — 원래: {n.get('title', '')}")
    out.extend(func_lines(n))
    if n.get("rename_of"):
        out.append(f"이름 바꾸기 대상: {n['rename_of']}")
    if n.get("kind") == "survey":
        # 추천 번호
        rec = n.get("recommend")
        for i, o in enumerate(n.get("options") or []):
            out.append(f"선택지 {i + 1}{' ★추천' if rec == i else ''}: {o.get('label', '')}" + (f" — {o['text']}" if o.get("text") else ""))
            out.extend(f"    + {x}" for x in o.get("pros") or [])
            out.extend(f"    − {x}" for x in o.get("cons") or [])
        if n.get("why"):
            out.append(f"추천 이유: {n['why']}")
        if n.get("detail"):
            out.append(f"배경: {n['detail']}")
        out.append(f"유저 답: {vote_text(n)}" + (" · 반영 필요(survey-ack)" if store.survey_pending(n) else ""))
        for a in n.get("acks") or []:
            out.append(f"반영 {short_at(a.get('at'))} {a.get('by')}" + (f" — {a['note']}" if a.get("note") else ""))
    for e in n.get("edits") or []:
        out.append(f"고침 {short_at(e.get('at'))} {e.get('by')} {e.get('field')}: {e.get('old')} → {e.get('new')}")
    if doc_text(n):
        out.append(f"문서: {doc_text(n)}")
    if n.get("parent"):
        out.append(("대상" if n.get("kind") == "verify" else "부모") + ":")
        out.append(ctx_line(n["parent"], nodes, now))
    for e in n.get("events") or []:
        out.append(f"사건 {short_at(e.get('at'))} {e.get('by')} {e.get('t')}" + (f" — {e['note']}" if e.get("note") else ""))
    for r in n.get("runs") or []:
        out.append(f"결과 {short_at(r.get('at'))} {r.get('by')} {r.get('result')} — {r.get('note', '')}")
    for a in n.get("answers") or []:
        out.append(f"답 {short_at(a.get('at'))} {a.get('by')}: {a.get('short', '')}")
        if a.get("text"):
            out.append("  " + a["text"].replace("\n", "\n  "))
    if n.get("kind") == "question":
        # 대상 id 목록
        targets = ask_targets(tree, nid)
        out.append("대상:" if targets else "대상: 없음(섬)")
        out.extend(ctx_line(t, nodes, now) for t in targets)
    # 아래 노드
    kids = [c for c in nodes.values() if c.get("parent") == nid]
    if kids:
        out.append("아래:")
        out.extend(f"  {node_line(c, nodes, now)}" for c in kids)
    # 이 노드를 묻는 질문 · 이어진 선
    for e in tree.get("edges", []):
        if e.get("kind") == "asks" and e.get("target") == nid and e.get("source") in nodes:
            out.append(f"질문: {node_line(nodes[e['source']], nodes, now)}")
        elif e.get("kind") != "asks" and nid in (e.get("source"), e.get("target")):
            # 상대 id
            other = e["target"] if e.get("source") == nid else e.get("source")
            out.append(f"선 {e.get('kind')} {'→' if e.get('source') == nid else '←'} {other} {nodes.get(other, {}).get('title', '')}")
    return out


# 함수 표 줄 — 행마다 «id 파일 | 함수 | 설명 | ⭐» + 유저 고친 칸 · 이름 바뀜 · 지움 / 맨 끝 반영 기록
# n: 노드
def func_lines(n):
    if n.get("kind") != "task":
        return []
    # 행 목록
    rows = store.func_rows(n)
    if not rows:
        return []
    out = ["함수 표(파일 | 함수 | 설명 | ⭐ — 이 이름으로 만든다 · 유저 칸은 MAIN 이 못 덮음):"]
    for r in rows:
        # 유저가 고친 칸
        mine = "모든 칸(유저 행)" if r.get("by") == "user" else " · ".join(sorted(r.get("user") or {}))
        out.append(f"  {r.get('id')} {store.func_val(r, 'file')} | {store.func_val(r, 'name')} | {store.func_val(r, 'desc')} | {'⭐' if store.func_val(r, 'core') else ''}"
                   + (" (유저가 지움)" if r.get("del") else "")
                   + (f" (유저 고침: {mine})" if mine and not r.get("del") else "")
                   + (f" · 이름 바뀜: {store.func_change(r)} — 코드 · 시험 · 문서도 새 이름으로 → funcs-ack" if store.func_pending(r) else ""))
    for k in n.get("func_acks") or []:
        out.append(f"이름 반영 {short_at(k.get('at'))} {k.get('by')}: {' · '.join(k.get('changes') or [])}" + (f" — {k['note']}" if k.get("note") else ""))
    return out


# funcs-scan — 노드 함수 표의 파이썬 파일에서 함수(· 메서드 · 클래스) 정의를 찾아 바로 위 주석 한 줄
#   반환 {«파일::함수»: 설명(없으면 "")} — 코드에 없는 이름은 열쇠 없음 · .py 아닌 파일 · 없는 파일도 없음으로
# tree: 그래프 / nid: 작업 id / root: 프로젝트 루트
def scan_funcs(tree, nid, root):
    import scan_code
    # 노드
    n = store.node_map(tree).get(nid)
    if n is None or n.get("kind") != "task":
        raise store.StoreError(f"없는 작업 «{nid}»")
    # 결과 · 파일별 정의 캐시
    found, cache = {}, {}
    for r in store.func_rows(n):
        # 파일 · 함수
        f, nm = store.func_val(r, "file"), store.func_val(r, "name")
        if r.get("del") or not nm or not f.endswith(".py"):
            continue
        if f not in cache:
            # 파일 경로 — 루트 기준 · 없으면 루트 아래에서 이름으로
            path = Path(root) / f
            if not path.is_file():
                path = next((x for x in Path(root).rglob(Path(f).name) if not set(x.parts) & scan_code.SKIP_DIRS), None)
            cache[f] = {}
            if path and path.is_file():
                # 소스 · 줄
                src = path.read_text(encoding="utf-8")
                lines = src.splitlines()
                for node in ast.walk(ast.parse(src)):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        cache[f].setdefault(node.name, (scan_code.comment_above(lines, node) or [""])[0])
        if nm in cache[f]:
            found[f"{f}::{nm}"] = cache[f][nm]
    return found


# 파일 · 폴더 → 프로젝트 루트 기준 파일 경로(폴더는 안의 파일 전부 · 점 이름 · 원본 지문 목록 제외)
# paths: 받은 경로 / root: 프로젝트 루트
def file_paths(paths, root):
    # 루트 · 결과
    root = Path(root).resolve()
    out = []
    for raw in paths:
        p = (root / raw).resolve()
        if not p.exists():
            raise store.StoreError(f"없는 경로: {raw}")
        if root not in p.parents:
            raise store.StoreError(f"프로젝트 밖 경로: {raw}")
        found = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file() and x.name != "_origin_md5.txt"
                                               and not any(s.startswith(".") for s in x.relative_to(p).parts))
        out += [x.relative_to(root).as_posix() for x in found]
    return out


# 점검 줄 — 오류 · 경고만(많으면 개수만)
# tree_path: tree.json 경로 / root: 프로젝트 루트 → (줄 목록, 오류 수)
def check_lines(tree_path, root):
    # 점검 결과
    probs = tree_check.check(store.read_json(tree_path, {}) or {}, store.read_json(tree_path.with_name("tree.auto.json")),
                             store.read_json(tree_path.with_name("tree.user.json")), root=root)
    # 오류 · 경고
    bad = [p for p in probs if p["level"] in ("error", "warn")]
    # 오류 수
    errs = sum(1 for p in bad if p["level"] == "error")
    # 출력 줄 — 오류 먼저
    out = [f"{'오류' if p['level'] == 'error' else '경고'} {p['code']} {p['target'] or ''} — {p['msg']}"
           for p in sorted(bad, key=lambda p: p["level"] != "error")[:CHECK_LINES]]
    if len(bad) > CHECK_LINES:
        out.append(f"… 외 {len(bad) - CHECK_LINES}")
    out.append(f"점검: 오류 {errs} · 경고 {len(bad) - errs}" if bad else "점검 정상")
    return out, errs


# 명령줄 해석기 만들기
def build_parser():
    # 공통 옵션(명령 앞 · 뒤 어디에 써도 됨)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--role", default=argparse.SUPPRESS, help="역할 main · 2nd · insp")
    common.add_argument("--tree", default=argparse.SUPPRESS, help="tree.json 경로(기본 docs/flowtree/tree.json)")
    common.add_argument("--root", default=argparse.SUPPRESS, help="프로젝트 루트 — check 의 문서 경로 기준(기본 현재 폴더)")
    # 해석기
    ap = argparse.ArgumentParser(prog="flowtree.py", description="flowtree 그래프 명령", parents=[common])
    # 명령 묶음
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="명령")
    # 명령 하나 추가
    # name: 명령 / args: [(이름, 설명, 추가 옵션)]
    def cmd(name, *args):
        # 명령 해석기
        p = sub.add_parser(name, parents=[common])
        for a in args:
            p.add_argument(a[0], help=a[1], **(a[2] if len(a) > 2 else {}))
        return p
    p = cmd("add", ("parent", "부모 id(맨 위면 -)"), ("title", "제목"))
    p.add_argument("--summary", default="", help="요약(60자 이내)")
    p.add_argument("--text", default="", help="설명")
    p.add_argument("--doc", default=None, help="연결 문서 «경로#앵커»")
    p.add_argument("--graph", default=None, choices=(*store.GRAPHS, *store.OLD_GRAPHS), help="그래프 task · hand_off(옛 이름 adr 도 받음 · 없으면 부모 그래프 · 맨 위면 hand_off)")
    p.add_argument("--names", default=None, help="옛 이름 칸 «파일.py · 함수_이름 …» — 함수 표 행으로 올림")
    p.add_argument("--func", action="append", default=[], help="함수 표 행 «파일 | 함수 | 설명 | ⭐»(여러 번)")
    p.add_argument("--section", default=None, help="화면 섹션 번호(없으면 칸 없음)")
    p = cmd("funcs-set", ("id", "작업 id"))
    p.add_argument("--row", action="append", default=[], help="행 «파일 | 함수 | 설명 | ⭐»(여러 번 · ⭐ = 핵심)")
    p.add_argument("--json", default=None, help="행 목록 JSON(«@경로» 면 파일)")
    cmd("funcs-ack", ("id", "작업 id"), ("note", "무엇을 했나", {"nargs": "?", "default": ""}))
    cmd("funcs-scan", ("id", "작업 id"))
    cmd("start", ("id", "작업 id"))
    cmd("hold", ("id", "작업 id"), ("note", "사유"))
    cmd("block", ("id", "작업 id"), ("note", "유저에게 필요한 것"))
    cmd("done", ("id", "작업 id"))
    p = cmd("verify-add", ("id", "대상 id"), ("note", "확인할 것"))
    p.add_argument("--section", default=None, help="화면 섹션 번호(없으면 대상을 따름)")
    cmd("section-set", ("id", "노드 id"), ("section", "섹션 번호(칸을 지우려면 -)"))
    p = cmd("fill", ("id", "틀 노드 id"))
    for k, h in (("--title", "제목(설문은 질문)"), ("--summary", "요약(60자)"), ("--text", "설명"), ("--doc", "연결 문서 «경로#앵커»"),
                 ("--script", "검증 스크립트 경로"), ("--why", "추천 이유"), ("--detail", "배경")):
        p.add_argument(k, default=None, help=h)
    p.add_argument("--func", action="append", default=[], help="함수 표 행 «파일 | 함수 | 설명 | ⭐»(여러 번)")
    p.add_argument("--option", action="append", default=[], help="선택지 «라벨|풀이|장점;…|단점;…»(여러 번)")
    p.add_argument("--recommend", type=int, default=None, help="추천 선택지 번호(1부터)")
    cmd("frames", ("section", "섹션 번호(없으면 전부)", {"nargs": "?", "default": None}))
    cmd("answer-start", ("id", "질문 id"))
    p = cmd("answer", ("id", "질문 id"), ("note", "본문", {"nargs": "?", "default": ""}))
    p.add_argument("--short", required=True, help="결론 한 줄(60자 이내)")
    cmd("verify-start", ("id", "검증 id"))
    cmd("verify-hold", ("id", "검증 id"), ("note", "사유"))
    cmd("run", ("id", "검증 id"), ("result", "pass · fail"), ("note", "근거(시험 경로 · 명령)"))
    p = cmd("survey-add", ("id", "대상 id(맨 위면 -)"), ("note", "질문"))
    p.add_argument("--option", action="append", default=[], help="선택지 «라벨|풀이|장점;…|단점;…»(여러 번)")
    p.add_argument("--recommend", type=int, default=None, help="추천 선택지 번호(1부터)")
    p.add_argument("--why", default="", help="추천 이유")
    p.add_argument("--detail", default="", help="배경 · 메커니즘(긴 글 — 확대 · 세부 보기에)")
    p.add_argument("--graph", default=None, choices=(*store.GRAPHS, *store.OLD_GRAPHS), help="그래프 task · hand_off(옛 이름 adr 도 받음 · 없으면 대상 그래프 · 맨 위면 task)")
    p.add_argument("--section", default=None, help="화면 섹션 번호(없으면 대상을 따름)")
    cmd("survey-ack", ("id", "설문 id"), ("note", "무엇을 했나", {"nargs": "?", "default": ""}))
    cmd("import-analysis", ("folder", "분석 결과 폴더(reqs.json · facts.json)"))
    cmd("file-add", ("paths", "파일 · 폴더(폴더면 안의 파일 전부)", {"nargs": "+"}))
    p = cmd("vote", ("id", "설문 id"))
    p.add_argument("--pick", type=int, default=None, help="선택 번호(1부터)")
    p.add_argument("--clear", action="store_true", help="선택 해제")
    p.add_argument("--memo", default=None, help="메모")
    p.add_argument("--hold", action="store_true", help="보류")
    p.add_argument("--unhold", action="store_true", help="보류 풀기")
    p = cmd("edit", ("id", "노드 id"))
    for k, h in (("--title", "제목"), ("--summary", "요약(60자)"), ("--text", "설명"), ("--script", "검증 스크립트 경로")):
        p.add_argument(k, default=None, help=h)
    p = cmd("funcs", ("id", "작업 id"))
    p.add_argument("--row", default="", help="행 id(없으면 새 행)")
    for k, h in (("--file", "파일"), ("--name", "함수"), ("--desc", "설명")):
        p.add_argument(k, default=None, help=h)
    p.add_argument("--core", action="store_true", help="핵심 ⭐")
    p.add_argument("--no-core", action="store_true", help="핵심 풀기")
    p.add_argument("--del", dest="delete", action="store_true", help="행 지우기")
    cmd("check-add", ("id", "대상 id"), ("note", "확인할 것"))
    cmd("inbox")
    cmd("show", ("id", "노드 id"))
    cmd("check")
    cmd("migrate")
    return ap


# 해석 결과 → 쓰기 명령 인자
# a: 해석 결과
def op_args(a):
    if a.cmd == "add":
        return {"parent": a.parent, "title": a.title, "summary": a.summary, "text": a.text, "doc": a.doc, "graph": a.graph,
                "names": a.names, "funcs": a.func, "section": a.section}
    if a.cmd in ("start", "done"):
        return {"task": a.id}
    if a.cmd in ("hold", "block"):
        return {"task": a.id, "note": a.note}
    if a.cmd == "verify-add":
        return {"target": a.id, "what": a.note, "section": a.section}
    if a.cmd == "section-set":
        return {"node": a.id, "section": a.section}
    if a.cmd == "fill":
        return {"node": a.id, "title": a.title, "summary": a.summary, "text": a.text, "doc": a.doc, "funcs": a.func, "script": a.script,
                "options": a.option, "recommend": a.recommend - 1 if a.recommend else None, "why": a.why, "detail": a.detail}
    if a.cmd == "answer-start":
        return {"question": a.id}
    if a.cmd == "answer":
        return {"question": a.id, "short": a.short, "text": a.note}
    if a.cmd == "verify-start":
        return {"verify": a.id}
    if a.cmd == "verify-hold":
        return {"verify": a.id, "note": a.note}
    if a.cmd == "run":
        return {"verify": a.id, "result": a.result, "note": a.note}
    if a.cmd == "survey-add":
        return {"target": a.id, "question": a.note, "options": a.option, "why": a.why, "detail": a.detail, "graph": a.graph,
                "section": a.section, "recommend": a.recommend - 1 if a.recommend else None}
    if a.cmd == "survey-ack":
        return {"survey": a.id, "note": a.note}
    if a.cmd == "import-analysis":
        # 분석 결과 폴더
        folder = Path(a.folder)
        if not folder.is_dir():
            raise store.StoreError(f"폴더 없음: {folder}")
        return {"reqs": store.read_json(folder / "reqs.json"), "facts": store.read_json(folder / "facts.json")}
    if a.cmd == "file-add":
        return {"files": file_paths(a.paths, Path(getattr(a, "root", None) or Path.cwd()))}
    if a.cmd == "vote":
        # 인자 — 준 칸만
        kw = {"survey": a.id}
        if a.clear:
            kw["pick"] = None
        elif a.pick is not None:
            kw["pick"] = a.pick - 1
        if a.memo is not None:
            kw["memo"] = a.memo
        if a.hold or a.unhold:
            kw["hold"] = bool(a.hold)
        return kw
    if a.cmd == "edit":
        return {"node": a.id, **{k: getattr(a, k) for k in ("title", "summary", "text", "script") if getattr(a, k) is not None}}
    if a.cmd == "funcs-set":
        # 행 목록 — --row + --json
        rows = list(a.row)
        if a.json:
            # JSON 글자(«@경로» 면 파일)
            raw = Path(a.json[1:]).read_text(encoding="utf-8") if a.json.startswith("@") else a.json
            data = json.loads(raw)
            rows += data.get("rows", []) if isinstance(data, dict) else data
        return {"task": a.id, "rows": rows}
    if a.cmd == "funcs-ack":
        return {"task": a.id, "note": a.note}
    if a.cmd == "funcs":
        # 고칠 칸 — 준 것만
        cells = {k: getattr(a, k) for k in ("file", "name", "desc") if getattr(a, k) is not None}
        if a.core or a.no_core:
            cells["core"] = bool(a.core)
        return {"task": a.id, "row": a.row, "cells": cells, "delete": a.delete}
    if a.cmd == "check-add":
        return {"target": a.id, "what": a.note}
    return {}


# --short(와 그 값)를 맨 뒤로 — 파이썬 3.12 이하 argparse 는 «answer q1 --short 결론 본문» 처럼 옵션 뒤에 온
# 위치 인자(본문)를 못 받는다(«unrecognized arguments» · 3.13 부터 됨 · 대회 기계 3.11 · 2026-11-02 WSL 3.12 실측)
# argv: 명령줄 인자
def short_last(argv):
    # 앞에 둘 것 · 뒤로 보낼 것 · 위치
    out, tail, i = [], [], 0
    while i < len(argv):
        if argv[i] == "--short" and i + 1 < len(argv):
            tail += argv[i:i + 2]
            i += 2
            continue
        (tail if argv[i].startswith("--short=") else out).append(argv[i])
        i += 1
    return out + tail


# 명령 실행 — 반환 (출력 줄 목록, 종료코드)
# argv: 명령줄 인자
def run(argv):
    # 해석 결과
    a = build_parser().parse_args(short_last(list(argv)))
    # 그래프 경로 · 프로젝트 루트 · 역할
    tree_path = Path(getattr(a, "tree", None) or Path.cwd() / "docs" / "flowtree" / "tree.json")
    root = Path(getattr(a, "root", None) or Path.cwd())
    role = getattr(a, "role", None)
    # 지금 초
    now = time.time()
    if a.cmd in store.OP_ROLES:
        if not role:
            raise store.StoreError("--role 없음 — main · 2nd · insp")
        # 명령 인자(funcs-scan 은 표의 파일을 읽은 결과)
        args = {"task": a.id, "found": scan_funcs(store.read_json(tree_path, {}) or {}, a.id, root)} if a.cmd == "funcs-scan" else op_args(a)
        return [store.apply(tree_path, role, a.cmd, **args)["msg"]], 0
    if a.cmd == "check":
        return check_lines(tree_path, root)
    if a.cmd == "migrate":
        # 바꾼 개수
        counts = {}
        # 옛 유저 칸
        user_path = tree_path.with_name("tree.user.json")
        user = store.read_json(user_path, {}) or {}

        # 잠금 안에서 옮기기
        # tree: 그래프 / rev: 판 번호
        def fn(tree, rev):
            # 옮긴 결과
            new_tree, new_user, c = store.migrate(tree, user)
            tree.clear()
            tree.update(new_tree)
            counts.update(c)
            store.write_json(user_path, new_user)
        store.mutate(tree_path, fn)
        return [f"옮김: 질문 {counts['questions']} · 답 {counts['answers']} · 검증 {counts['verifies']}"], 0
    # frames — 그래프가 아직 없으면 여기서 틀까지 깖(첫 쓰기와 같음)
    if a.cmd == "frames" and not tree_path.exists():
        store.mutate(tree_path, lambda t, rev: None)
    if not tree_path.exists():
        raise store.StoreError(f"그래프 파일 없음: {tree_path}")
    # 그래프
    tree = store.read_json(tree_path, {}) or {}
    if a.cmd == "frames":
        # 빈 틀 노드 id — 섹션 고르기
        ids = [n["id"] for n in tree.get("nodes", []) if n.get("frame") and a.section in (None, str(n.get("screen")))]
        return [" ".join(ids) or "빈 틀 없음"], 0
    if a.cmd == "inbox":
        if role not in store.ROLES:
            raise store.StoreError("--role 없음 — main · 2nd · insp")
        return inbox_lines(tree, role, now), 0
    return show_lines(tree, a.id, now), 0


# 명령줄 진입점
# argv: 명령줄 인자(없으면 sys.argv)
def main(argv=None):
    # 출력 인코딩 고정(파이프 · cp949 환경에서도 한글) — 바꿔 끼운 출력(StringIO)은 그대로
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        # 출력 줄 · 종료코드
        lines, code = run(sys.argv[1:] if argv is None else argv)
    # 거부 · 형식 오류
    except (store.StoreError, ValueError, OSError) as err:
        print(f"실패: {err}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
