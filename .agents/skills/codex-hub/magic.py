#!/usr/bin/env python3
# 허브 마법봉 요청 처리 — main-magic · 2nd-magic 공용 · 표준 라이브러리만
"""
요청 = devview 가 마법봉을 누른 순간 쓴 <작업 폴더>/.codex-hub/requests/<요청id>.json(보기 · 고른 노드 · 파일 · 줄 · 글자 · 질문)
  python3 ~/.codex/skills/codex-hub/magic.py show 요청id                고른 대상 · 할 일 · 답 자리(상태 줄은 여기서 바꿈 · 2ND 질문 노드는 답변 준비 중으로)
  python3 ~/.codex/skills/codex-hub/magic.py answer-node 요청id --short '결론(60자)' '본문'
    답 자리 node = 새 질문 노드 · 고른 질문 노드 · 고른 설문 노드(«질문 · 답» 칸 answers[] — 물은 글 q 도 같이)
  python3 ~/.codex/skills/codex-hub/magic.py answer-md 요청id '답'     md · txt — 고른 것 없음 = 맨 위 «🤖 질문 · 답변» 절 · 고른 글자 = 그 문단 아래 · 표 = 고른 행 아래 새 행
  python3 ~/.codex/skills/codex-hub/magic.py answer-code 요청id '답'   코드 — 고른 줄 아래 주석 · 고른 줄 없음 = 파일 맨 위(실행 · 인코딩 줄 아래)
  python3 ~/.codex/skills/codex-hub/magic.py answer-form 요청id '답'   CSV · PDF · 그 밖 · 설문 질문 문항 — 설명 폼(저장소 밖 /tmp/sv · devview 설문 탭)
  설문 제출 요청(답 자리 survey) — show 가 MAIN 에는 확정 문항 · 할 일, 2ND 에는 질문 문항 · answer-form 명령을 보여 줌
  python3 ~/.codex/skills/codex-hub/magic.py answer-note 요청id '답' --title '짧은 제목'   책 스티커 — 그 스티커 answer 칸 · 꼬리 질문 요청이면 그 꼬리 답(bookkit/notes.py answer)
출력: 성공 한 줄(show 는 몇 줄) · 실패 «실패: 원인» + 종료코드 1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# 이 파일 폴더 — hub.py(작업 폴더 찾기 · 상태 줄) 와 같은 곳
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hub  # noqa: E402

# 요청 id 모양
RID_RE = re.compile(r"^m[0-9]{4}-[0-9]{6}-[0-9a-f]{4}$")
# 맨 위 질문 · 답변 절 제목
TOP_HEAD = "## 🤖 질문 · 답변"
# 확장자 → 주석 기호(한 줄 앞 기호 · 또는 (여는, 닫는) 짝)
COMMENT = {}
for _e in ("py", "pyi", "sh", "bash", "zsh", "rb", "pl", "r", "yaml", "yml", "toml", "ini", "cfg", "conf", "dockerfile",
           "makefile", "ps1"):
    COMMENT[_e] = "#"
for _e in ("js", "mjs", "cjs", "jsx", "ts", "tsx", "java", "kt", "kts", "c", "h", "cpp", "hpp", "cc", "cs", "go", "rs",
           "swift", "scala", "dart", "php", "scss", "less"):
    COMMENT[_e] = "//"
for _e in ("sql", "lua", "hs"):
    COMMENT[_e] = "--"
for _e in ("html", "htm", "xml", "vue", "svelte"):
    COMMENT[_e] = ("<!--", "-->")
COMMENT["css"] = ("/*", "*/")
COMMENT["bat"] = COMMENT["cmd"] = "REM"
# 설명 폼 저장 폴더 기본값(2ND 는 저장소에 설문을 남기지 않음 — 2nd 스킬 규칙) · 시험은 MAGIC_SURVEY_DIR
FORM_DIR = "/tmp/sv"
# 보여 줄 고른 글자 최대 길이
SHOW_TEXT = 600


# 거부 · 실패 — 원인 한 줄
class MagicError(Exception):
    pass


# 요청 읽기 — 반환 (요청 사전, 요청 파일 경로)
# rid: 요청 id
def load_request(rid):
    if not RID_RE.match(rid or ""):
        raise MagicError(f"요청 id 형식 오류 «{rid}» — m월일-시분초-4자리")
    # 요청 파일
    p = hub.hub_dir() / "requests" / f"{rid}.json"
    req = hub.read_json(p)
    if not isinstance(req, dict):
        raise MagicError(f"요청 파일 없음: {p}")
    return req, p


# flowtree 불러오기 — 요청의 flowtree 폴더 → 작업 폴더/devview/flowtree · 반환 (flowtree_store, flowtree 명령 모듈, tree.json 경로)
# req: 요청
def flowtree(req):
    # 후보 폴더
    cands = [Path(req["flowtree"])] if req.get("flowtree") else []
    cands.append(Path(req.get("root") or os.getcwd()) / "devview" / "flowtree")
    for d in cands:
        if (d / "flowtree_store.py").is_file():
            sys.path.insert(0, str(d))
            import flowtree as ftcli  # noqa: E402
            import flowtree_store as store  # noqa: E402
            # 그래프 파일
            tp = Path(req.get("tree") or Path(req.get("root") or os.getcwd()) / "docs" / "flowtree" / "tree.json")
            if not tp.is_file():
                raise MagicError(f"그래프 파일 없음: {tp}")
            return store, ftcli, tp
    raise MagicError("flowtree 없음(devview/flowtree)")


# 상태 줄 바꾸기 — 등록이 없으면 조용히 넘어감(답 일은 계속)
# text: 상태 줄
def set_status(text):
    try:
        # 허브 폴더 · 자기 등록
        h = hub.hub_dir()
        nick, data = hub.find_me(h)
        data["status"] = hub.one_line(text[:120], "상태 줄")
        data["status_at"] = hub.now_text()
        hub.write_json(hub.session_path(h, nick), data)
    except (hub.HubError, OSError):
        pass


# 한 줄로 줄이기
# s: 글 / n: 최대 글자
def short(s, n=60):
    # 한 줄 글
    t = " ".join(str(s or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


# 대상 파일 실제 경로 — 요청의 abs(덧붙인 폴더 포함) → 작업 폴더 기준
# req: 요청
def target_path(req):
    # 답 자리
    t = req.get("target") or {}
    if t.get("abs") and Path(t["abs"]).is_file():
        return Path(t["abs"])
    # 작업 폴더 기준 경로
    p = Path(req.get("root") or os.getcwd()) / str(t.get("file") or "")
    if not p.is_file():
        raise MagicError(f"파일 없음: {t.get('file')}")
    return p


# ======= show =======
# 지시 붙은 마법봉(Alt+E · Alt+R)의 대상 · 지시 줄 — 대상 = 보기의 선택(코드 줄 · 글자 · 표 칸 · Git · 책 스티커)
# req: 요청 / out: 출력 줄 목록
def instruction_lines(req, out):
    r = (req.get("target") or {}).get("ref") or {}
    if r.get("kind") == "code":
        g = r.get("range") or {}
        out.append(f"대상 파일: {r.get('file')}" + (f" · 줄 {g.get('start_line')}–{g.get('end_line')}" if g.get("start_line") else "")
                   + (f" · 실제 경로 {r['abs']}" if r.get("abs") else ""))
        if r.get("table"):
            out.append(f"  표 행 {r['table'].get('line')} 열 {r['table'].get('col')}")
        if str(r.get("text") or "").strip():
            out.append("고른 글자:\n" + (r["text"] if len(r["text"]) <= SHOW_TEXT else r["text"][:SHOW_TEXT] + " …(줄임)"))
    elif r.get("kind") == "git":
        out.append(f"대상 Git: 커밋 {r.get('commit') or '-'} «{short(r.get('subject'), 50)}» · 파일 {r.get('git_file') or '-'}"
                   f" — git show {r.get('commit') or 'HEAD'}{' -- ' + r['git_file'] if r.get('git_file') else ''}")
    elif r.get("kind") == "note":
        out.append(f"대상 책 스티커: 책 {r.get('book')} · 스티커 {r.get('note')} «{r.get('text')}» · 블록 {r.get('block') or '-'}"
                   f" · notes {r.get('notes_file')}")
    elif not req.get("nodes"):
        out.append(f"대상 없음(보기 {req.get('view') or '-'})")
    out.append(f"지시: {req.get('instruction')}")


# 설문 노드가 «결정 · 반영 전» 인가 — 선택 또는 메모가 있고 · 보류 아님 · 마지막 답이 반영 기록보다 새것(허브 survey_state 의 ok)
# store: flowtree_store / nd: 설문 노드
def survey_ok(store, nd):
    v = store.survey_vote(nd)
    if v["hold"] or (v["pick"] is None and not v["memo"]):
        return False
    return v["seq"] > max((int(a.get("seq") or 0) for a in nd.get("acks") or []), default=0)


# main — 고른 노드 중 hand_off 작업 · 검증 · 질문 노드를 종류별 할 일로 · 나머지는 맥락
# req: 요청 / out: 출력 줄 목록
def show_main(req, out):
    if req.get("instruction") and not req.get("nodes"):
        # 노드 없는 지시 — 대상 + 지시대로(그래프 안 읽음)
        instruction_lines(req, out)
        out.append("할 일: 대상 + 지시대로 — 내가 코드를 쓰지 않고 서브에게(구현 → 구현 서브 · 조사 · 질문 → 놀고 있는 서브) · 대상 파일 · 줄 · 지시를 지시문에 그대로")
        set_status(f"작업 : 지시 {short(req.get('instruction'), 40)}")
        return
    store, ftcli, tp = flowtree(req)
    # 그래프 · id → 노드 · 옮긴 원본(옛 promote 기록 — 명령이 빠진 판이면 빈 사전) · 지금 초
    tree = store.read_json(tp, {}) or {}
    nodes = store.node_map(tree)
    moved = getattr(store, "promoted_map", lambda t: {})(tree)
    now = time.time()
    # 고른 id 목록
    ids = [x["id"] for x in req.get("nodes") or []]
    # hand_off 작업 노드(옛 이름 adr 도 받음)
    work = [i for i in ids if i in nodes and nodes[i].get("kind") == "task" and store.graph_of(nodes, nodes[i]) in ("adr", "hand_off")
            and i not in moved]
    # 검증 · 질문 노드(종류는 트리 기준 — 화면이 보낸 종류만 믿지 않음)
    ver = [i for i in ids if nodes.get(i, {}).get("kind") == "verify"]
    ask = [i for i in ids if nodes.get(i, {}).get("kind") == "question"]
    # 설문 노드 — 유저 답(선택 · 메모)이 있는 것 = 결정으로 받음(답 없는 설문은 허브가 미리 뺌)
    sv = [i for i in ids if nodes.get(i, {}).get("kind") == "survey" and survey_ok(store, nodes[i])]
    for i in ids:
        if i in work or i in ver or i in ask or i in sv:
            out.extend(ftcli.show_lines(tree, i, now))
        elif i in nodes:
            out.append("맥락: " + ftcli.node_line(nodes[i], nodes, now) + (f" — {nodes[i]['summary']}" if nodes[i].get("summary") else ""))
        else:
            out.append(f"맥락: {i}")
    if req.get("instruction"):
        instruction_lines(req, out)
        out.append("지시를 따른다 — 위 노드 · 대상에 지시대로(서브에게)")
    if not work and not ver and not ask and not sv and req.get("instruction"):
        set_status(f"작업 : 지시 {short(req.get('instruction'), 40)}")
        return
    if not work and not ver and not ask and not sv:
        out.append("멈춤: 고른 노드에 작업 · 검증 · 질문 노드 없음(답한 설문 노드도 없음) — 노드를 만들지 말고 유저에게 무엇을 할지 묻고 턴을 끝낸다")
        set_status("확인 : 마법봉 — 작업 · 검증 · 질문 노드 없음 · 유저 확인 대기")
        return
    if work:
        out.append(f"할 일: {' · '.join(work)} — 하나씩 python3 devview/flowtree/flowtree.py --role main start <id> → 구현 서브에게 시킨다"
                   " → 서브 커밋을 확인하고 done <id>")
    if ver:
        out.append(f"검증 할 일: {' · '.join(ver)} — 검증관에게 고정 양식(섹션 번호 · 성공 기준 · 커밋 해시 · 볼 파일 · 축)으로 준다"
                   " · 검증관이 flowtree.py --role insp verify-start · run 을 직접 남긴다")
    if ask:
        out.append(f"질문 할 일: {' · '.join(ask)} — 놀고 있는 서브에게 답을 시킨다"
                   "(flowtree.py --role 2nd answer-start <id> → answer <id> --short '결론(60자)' '본문')")
    for i in sv:
        par = nodes[i].get("parent")
        out.append(f"설문 할 일: {i} — 유저가 답한 설문(결정) · hand_off 에 반영 → python3 devview/flowtree/flowtree.py --role main survey-ack {i} '무엇을 했나'"
                   + (f" → 그 설문이 붙은 작업 {par} 시작(위 «할 일» 과 같이 start → 구현 서브)" if par else " → 이어진 작업 시작")
                   + " · 맨 앞 설문(«이 범위로 시작» 등)은 카드 P(bookkit/cards/P.md 지휘) 대로 범위 승인")
    if not work and sv:
        set_status(f"작업 : 설문 {' · '.join(sv)[:40]} 결정 반영")
        return
    if not work:
        set_status(f"확인 : 마법봉 {' · '.join(ver + ask)[:60]}")
        return
    # 첫 작업 노드 · 그 hand_off 절 번호(연결 문서 앵커)
    n = nodes[work[0]]
    anchor = str((n.get("doc") or {}).get("anchor") or "") if isinstance(n.get("doc"), dict) else ""
    set_status(f"❇️_{anchor} : 작업. {short(n.get('title'), 40)}" if re.match(r"^\d+(-\d+)*$", anchor) else f"작업 : {short(n.get('title'), 40)}")


# 2nd — 질문 · 대상 · 답 자리
# req: 요청 / out: 출력 줄 목록 / rid: 요청 id
def show_2nd(req, out, rid):
    # 답 자리
    t = req.get("target") or {}
    kind = t.get("kind")
    out.append(f"질문: {req.get('question')}")
    if req.get("instruction") and req.get("instruction") != req.get("question"):
        out.append(f"지시: {req['instruction']} — 이 지시대로 답한다(답 자리는 아래 그대로)")
    cmd = f"python3 ~/.codex/skills/codex-hub/magic.py"
    if kind == "node":
        store, ftcli, tp = flowtree(req)
        # 질문 id · 그래프 · id → 노드 · 지금 초
        q = t.get("question")
        tree = store.read_json(tp, {}) or {}
        nodes = store.node_map(tree)
        now = time.time()
        if q not in nodes:
            raise MagicError(f"질문 노드 없음: {q}")
        if nodes[q].get("kind") == "survey":
            # 설문 노드 — 질문 = 메모(또는 입력창 글) · 답은 그 설문 노드 «질문 · 답» 칸(유저 답 votes 는 그대로)
            out.append(f"설문 노드 {q} ‹{short(store.eff(nodes[q], 'title'), 60)}› — 이 설문에 대한 질문(답 = 설문 노드 안 «질문 · 답»)")
            out.extend(ftcli.show_lines(tree, q, now))
        elif store.status(nodes[q], nodes, now)["status"] == "todo":
            store.apply(tp, "2nd", "answer-start", question=q)
            out.append(f"{q} 답변 준비 중")
        # 앞 답(이미 답이 달린 노드에 다시 물음) — 이어서 답하도록
        for i, a in enumerate(nodes[q].get("answers") or [], 1):
            out.append(f"앞 답 {i} ({a.get('at', '')[5:16]}): {a.get('short', '')}" + (f" — {short(a.get('text'), 300)}" if a.get("text") else "")
                       + (f"  (물은 글: {short(a.get('q'), 120)})" if a.get("q") else ""))
        for x in t.get("targets") or []:
            out.append(ftcli.ctx_line(x, nodes, now))
        if not t.get("targets"):
            out.append("  (섬 질문 — 대상 노드 없음)")
        if t.get("commit") or t.get("git_file"):
            out.append(f"Git: 커밋 {t.get('commit') or '-'} «{short(t.get('subject'), 50)}» · 파일 {t.get('git_file') or '-'}"
                       f" — git show {t.get('commit') or 'HEAD'}{' -- ' + t['git_file'] if t.get('git_file') else ''}")
        out.append(f"답 자리: node {q} → {cmd} answer-node {rid} --short '결론(60자)' '본문(근거 파일 · 줄)'")
    elif kind in ("md", "code", "form"):
        # 고른 범위 · 글자
        r = t.get("range") or {}
        text = str(t.get("text") or "")
        where = f"줄 {r.get('start_line')}–{r.get('end_line')}" if r.get("start_line") else "고른 것 없음(파일 전체)"
        out.append(f"파일: {t.get('file')} · {where}" + (f" · 표 행 {t['table'].get('line')} 열 {t['table'].get('col')}"
                                                          if t.get("table") else ""))
        if text.strip():
            out.append("고른 글자:\n" + (text if len(text) <= SHOW_TEXT else text[:SHOW_TEXT] + " …(줄임)"))
        out.append(f"답 자리: {kind} → {cmd} answer-{kind} {rid} '답(근거 파일 · 줄)'")
    elif kind == "note":
        # 책 스티커 — 자리(쪽 · 장 · 절 · 글) · 블록 ID(= 장-칸 이름 · 장-항목 id → content 칸 · contracts 의 같은 id)
        out.append(f"책: {t.get('book')} · 문서 {t.get('doc') or '-'} · 스티커 {t.get('note')} · notes {t.get('notes_file')}")
        out.append(f"자리: {t.get('ctx') or '-'}")
        if t.get("block"):
            out.append(f"블록 {t['block']} — 책 폴더 content/ 의 그 칸 · contracts/*.json 의 같은 id 를 읽는다(bookkit/README «판 · 블록 ID»)")
        if t.get("thread"):
            # 꼬리 질문 — 맥락(원 질문 · 원 답 · 앞 꼬리) 뒤 답 자리 = 그 꼬리
            out.append(f"원 질문: {t.get('orig_q') or '-'}")
            out.append(f"원 답: {short(t.get('orig_a'), SHOW_TEXT)}")
            for x in t.get("prev") or []:
                out.append(f"꼬리 {x.get('id')}: {x.get('q')}\n  답: {short(x.get('a'), 300) or '(답 없음)'}")
            out.append(f"꼬리 질문 {t['thread']}: {req.get('question')}")
            out.append(f"답 자리: note 꼬리 {t['thread']} → {cmd} answer-note {rid} '답(근거 칸 · 계약 id)'")
        else:
            out.append(f"답 자리: note → {cmd} answer-note {rid} '답(근거 칸 · 계약 id)' --title '짧은 제목(20자 안팎 · 책 아래 질문 줄 행 이름)'")
    elif kind == "chat":
        # 지시 붙은 2ND · 그래프 밖 · 대상 없음 — 노드 · 파일에 쓰지 않음
        out.append(f"대상 없음(보기 {req.get('view') or '-'})")
        out.append("답 자리 없음 — 대화로 답(노드 · 파일에 쓰지 않는다 · answer-* 명령 없음)")
    else:
        raise MagicError(f"답 자리 모름: {kind}")
    set_status(f"답변 : {short(req.get('question'), 50)}")


# 설문 제출 — MAIN = 확정 문항(결정 문서 반영 · 커밋 → 작업) · 2ND = 질문 문항(설명 폼으로 답 → MAIN 에 알림)
# req: 요청 / out: 출력 줄 목록 / rid: 요청 id
def show_survey(req, out, rid):
    # 대상 · 문항 · 결과 전체 명령
    t = req.get("target") or {}
    items = t.get("items") or []
    sid = t.get("survey")
    res = f"python3 ~/.codex/skills/survey/survey.py{' --dir ' + t['dir'] if t.get('dir') else ''} result {sid}"
    out.append(f"설문: ‹{t.get('title')}› {sid} · 프로젝트 {t.get('project') or '-'} · 결과 전체 = {res}")
    for it in items:
        out.append(f"  [{it.get('id') or '-'}] {it.get('question')} → {it.get('text') or '-'}")
    if t.get("extra"):
        out.append(f"추가 지시: {t['extra']}")
    if req.get("role") == "main":
        out.append("할 일: 확정 문항을 결정 문서에 반영(survey 스킬 4절 — 질문 아래 «> > 🚹 답» · «🟢 결정») → 설문 · 결과 파일과 같이 커밋"
                   " → 반영한 결정대로 작업 시작(작업 → 구현 서브 · 검증 → 검증관 · main 1-7) · 추가 지시가 있으면 따른다")
        set_status(f"작업 : 설문 {sid} 확정 {len(items)}개 반영")
        return
    cmd = "python3 ~/.codex/skills/codex-hub/magic.py"
    out.append(f"답 자리: form → {cmd} answer-form {rid} '답(문항 id 별 · 근거 파일 · 줄)'")
    out.append(f"답을 넣은 뒤: python3 ~/.codex/skills/codex-hub/hub.py send --to main '설문 {sid} 질문 답 · 설명 폼 <폼 id>"
               " — 답을 배경에 넣어 다시 묻는 설문을 만들어 줘'")
    set_status(f"답변 : 설문 {sid} 질문 {len(items)}개")


# show — 요청 내용 · 할 일
# rid: 요청 id
def cmd_show(rid):
    req, _ = load_request(rid)
    # 출력 줄
    out = [f"요청 {rid} · {req.get('skill')} · 보기 {req.get('view') or '-'} · {req.get('at')}"]
    role = req.get("role")
    if (req.get("target") or {}).get("kind") == "survey" and role in ("main", "2nd"):
        show_survey(req, out, rid)
    elif role == "main":
        show_main(req, out)
    elif role == "2nd":
        show_2nd(req, out, rid)
    else:
        raise MagicError(f"역할 모름: {role}")
    return "\n".join(out)


# ======= 파일 읽기 · 쓰기(인코딩 · 줄바꿈 유지) =======
# 파일 → (줄 목록, 인코딩, 줄바꿈, 끝 줄바꿈 여부)
# path: 파일
def read_lines(path):
    # 원본 바이트
    raw = path.read_bytes()
    enc = "utf-8"
    if raw.startswith(b"\xef\xbb\xbf"):
        enc, raw = "utf-8-sig", raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        enc, text = "cp949", raw.decode("cp949")
    eol = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n")
    end_nl = text.endswith("\n")
    if end_nl:
        text = text[:-1]
    return (text.split("\n") if text else []), enc, eol, end_nl


# 줄 목록 → 파일(같은 인코딩 · 줄바꿈 · 임시 파일 교체)
# path: 파일 / lines: 줄 목록 / enc: 인코딩 / eol: 줄바꿈 / end_nl: 끝 줄바꿈
def write_lines(path, lines, enc, eol, end_nl):
    # 쓸 글
    text = eol.join(lines) + (eol if end_nl or not lines else "")
    data = (b"\xef\xbb\xbf" if enc == "utf-8-sig" else b"") + text.encode("utf-8" if enc == "utf-8-sig" else enc)
    # 임시 파일
    tmp = path.with_name(f".{path.name}.{os.getpid()}.magic")
    tmp.write_bytes(data)
    try:
        os.chmod(tmp, path.stat().st_mode & 0o7777)
    except OSError:
        pass
    os.replace(tmp, path)


# 고른 글자의 지금 위치 — 기록한 줄에 그 글자가 그대로면 그 줄 · 아니면 문서에서 찾은 첫 자리 · 못 찾으면 기록한 줄(범위 안으로)
# lines: 줄 목록 / r: 기록 범위 / text: 고른 글자 → (시작 번호, 끝 번호) 0부터
def locate(lines, r, text):
    # 기록한 시작 · 끝(0부터)
    s = max(0, int(r.get("start_line") or 1) - 1)
    e = max(s, int(r.get("end_line") or (s + 1)) - 1)
    # 고른 글자의 첫 줄 · 줄 수
    first = (text or "").strip("\n").split("\n")[0].strip()
    span = max(0, (text or "").strip("\n").count("\n"))
    if first:
        if s < len(lines) and first in lines[s]:
            return s, min(len(lines) - 1, s + span) if lines else 0
        for i, ln in enumerate(lines):
            if first in ln:
                return i, min(len(lines) - 1, i + span)
    if not lines:
        return 0, -1
    s = min(s, len(lines) - 1)
    return s, min(max(s, e), len(lines) - 1)


# ======= answer-md =======
# 표 행 칸 나누기(앞뒤 | · \| 는 글자)
# row: 표 행 글
def split_row(row):
    # 앞뒤 공백 · 바깥 | 뺀 글
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


# 표 행인가(구분 줄 제외)
# line: 줄
def is_table_row(line):
    # 앞뒤 공백 뺀 줄
    s = line.strip()
    return s.startswith("|") and not re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", s)


# 콜아웃 줄 — «> [!answer] 🤖 2ND · 질문» + 답 줄
# q: 질문 / a: 답
def callout(q, a):
    return [f"> [!answer] 🤖 2ND · {short(q, 200)}"] + [f"> {x}" if x.strip() else ">" for x in a.strip("\n").split("\n")]


# md · txt 에 답 넣기 — 반환 (경로, 넣은 줄 번호 1부터)
# req: 요청 / ans: 답
def answer_md(req, ans):
    # 대상 · 경로 · 질문
    t = req.get("target") or {}
    path = target_path(req)
    q = req.get("question") or ""
    lines, enc, eol, end_nl = read_lines(path)
    r = t.get("range") or {}
    text = str(t.get("text") or "")
    tb = t.get("table") if isinstance(t.get("table"), dict) else None
    at = None
    if tb and lines:
        # 표 행 — 기록한 줄 · 고른 글자로 다시 찾기
        s, _ = locate(lines, {"start_line": tb.get("line"), "end_line": tb.get("line")}, text)
        if not is_table_row(lines[s]):
            # 기록한 줄 근처의 표 행
            near = [i for i in range(max(0, s - 3), min(len(lines), s + 4)) if is_table_row(lines[i])]
            s = near[0] if near else None
        if s is not None:
            # 칸 수 · 답 칸 · 새 행
            cells = split_row(lines[s])
            col = min(max(0, int(tb.get("col") or 0)), len(cells) - 1)
            cell = " ".join(ans.split("\n")).replace("|", "\\|").strip()
            new = ["🤖"] + [""] * (len(cells) - 1)
            new[col] = f"🤖 {cell}" if col == 0 else cell
            # 머리줄을 골랐으면 구분 줄(|---|) 아래로 — 머리줄과 구분 줄 사이에 넣으면 표가 깨짐
            if s + 1 < len(lines) and lines[s + 1].strip().startswith("|") and not is_table_row(lines[s + 1]):
                s += 1
            lines.insert(s + 1, "| " + " | ".join(new) + " |")
            at = s + 2
    if at is None and r.get("start_line") and text.strip() and lines:
        # 고른 글자 — 그 글자가 든 문단(코드 울타리 안이면 울타리 끝) 아래
        _, e = locate(lines, r, text)
        # 코드 울타리 안인가(앞의 ``` 수가 홀수)
        fences = sum(1 for x in lines[:e + 1] if x.lstrip().startswith("```"))
        if fences % 2 == 1:
            while e + 1 < len(lines) and not lines[e + 1].lstrip().startswith("```"):
                e += 1
            e = min(e + 1, len(lines) - 1)
        else:
            while e + 1 < len(lines) and lines[e + 1].strip() and not lines[e + 1].lstrip().startswith(("#", "```")):
                e += 1
        block = [""] + callout(q, ans) + ([""] if e + 1 < len(lines) and lines[e + 1].strip() else [])
        lines[e + 1:e + 1] = block
        at = e + 3
    if at is None:
        # 고른 것 없음 — 맨 위 «🤖 질문 · 답변» 절(있으면 그 절 끝에 덧붙임)
        head = next((i for i, x in enumerate(lines) if x.strip() == TOP_HEAD), None)
        if head is not None:
            # 절 끝 — 제목 뒤로 이어진 콜아웃(> 줄 · 사이 빈 줄)의 마지막 줄 다음(그 뒤 문서 본문은 이 절이 아님)
            last = head
            for k in range(head + 1, len(lines)):
                if lines[k].lstrip().startswith(">"):
                    last = k
                elif lines[k].strip():
                    break
            end = last + 1
            lines[end:end] = [""] + callout(q, ans)
            at = end + 2
        else:
            # 넣을 자리 — 머리말(--- … ---) 뒤 · 첫 줄이 # 제목이면 그 아래
            i = 0
            if lines and lines[0].strip() == "---":
                close = next((k for k in range(1, len(lines)) if lines[k].strip() == "---"), None)
                i = close + 1 if close is not None else 0
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and re.match(r"^#\s", lines[i]):
                i += 1
            # 콜아웃 앞 줄 수(빈 줄 · 제목 · 빈 줄)
            pre = (1 if i > 0 else 0) + 2
            lines[i:i] = ([""] if i > 0 else []) + [TOP_HEAD, ""] + callout(q, ans) + [""]
            at = i + pre + 1
    write_lines(path, lines, enc, eol, end_nl)
    return path, at


# ======= answer-code =======
# 코드 파일에 주석으로 답 넣기 — 반환 (경로, 넣은 줄 번호 1부터)
# req: 요청 / ans: 답
def answer_code(req, ans):
    # 대상 · 경로 · 질문 · 확장자 · 주석 기호
    t = req.get("target") or {}
    path = target_path(req)
    q = req.get("question") or ""
    name = path.name.lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else name
    mark = COMMENT.get(ext)
    if mark is None:
        raise MagicError(f"주석 기호 모름(.{ext}) — answer-form 으로")
    lines, enc, eol, end_nl = read_lines(path)
    r = t.get("range") or {}
    text = str(t.get("text") or "")
    # 답 줄 — 머리 한 줄 + 답
    body = [f"🤖 2ND · 질문: {short(q, 200)}"] + [x for x in ans.strip("\n").split("\n")]

    # 주석 한 줄
    # x: 글 / ind: 들여쓰기
    def com(x, ind):
        if isinstance(mark, tuple):
            return f"{ind}{mark[0]} {x} {mark[1]}"
        return f"{ind}{mark} {x}".rstrip() if x.strip() else f"{ind}{mark}"
    if r.get("start_line") and lines:
        # 고른 줄 아래 — 끝 줄의 들여쓰기에 맞춤
        _, e = locate(lines, r, text)
        ind = re.match(r"^\s*", lines[e]).group(0)
        lines[e + 1:e + 1] = [com(x, ind) for x in body]
        at = e + 2
    else:
        # 맨 위 — 실행 줄(#!) · 인코딩 줄(coding: · PEP 263 은 둘째 줄까지) · <?xml · <!DOCTYPE · <?php 아래
        i = 0
        if i < len(lines) and lines[i].startswith("#!"):
            i += 1
        while i < min(2, len(lines)) and re.match(r"^[ \t\f]*#.*?coding[:=]", lines[i]):
            i += 1
        while i < len(lines) and re.match(r"^\s*(<\?xml|<!DOCTYPE|<\?php)", lines[i], re.I):
            i += 1
        lines[i:i] = [com(x, "") for x in body]
        at = i + 1
    write_lines(path, lines, enc, eol, end_nl)
    return path, at


# ======= answer-form =======
# 설명 폼 등록 — survey.py(같은 스킬 폴더의 형제 survey) new · 반환 설문 id
# req: 요청 / ans: 답 / rid: 요청 id
def answer_form(req, ans, rid):
    # 설문 도구
    sv = HERE.parent / "survey" / "survey.py"
    if not sv.is_file():
        raise MagicError(f"설문 도구 없음: {sv}")
    # 대상
    t = req.get("target") or {}
    src = " · ".join(x for x in (str(t.get("file") or ""), short(t.get("text"), 80) if str(t.get("text") or "").strip() else "") if x)
    if t.get("kind") == "survey":
        # 설문 질문 문항 — 대상 = 설문 · 문항 id
        src = f"설문 {t.get('survey')} · 문항 " + " · ".join(str(x.get("id") or "-") for x in t.get("items") or [])
    spec = {"title": f"🤖 2ND 답 — {short(req.get('question'), 40)}", "intro": f"대상: {src or '-'} · 요청 {rid}",
            "items": [{"id": "1", "title": short(req.get("question"), 200), "body": ans, "source": src}]}
    # 질문 파일(임시)
    fd, tmp = tempfile.mkstemp(prefix=f"magic_{rid}_", suffix=".json")
    os.close(fd)
    try:
        Path(tmp).write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(sv), "--dir", os.environ.get("MAGIC_SURVEY_DIR") or FORM_DIR, "new", tmp, "--project", "2nd"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if r.returncode != 0:
        raise MagicError(f"설명 폼 실패 — {(r.stderr or r.stdout).strip()[-200:]}")
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])["id"]
    except (ValueError, KeyError, IndexError):
        raise MagicError(f"설명 폼 출력 해석 실패 — {r.stdout.strip()[-200:]}") from None


# ======= answer-note =======
# 책 스티커 answer 칸 — bookkit/notes.py answer 재사용(답이 달리면 책 아래 질문 줄 행) · 꼬리 질문이면 그 꼬리의 답 · 반환 notes.py 출력 한 줄
# req: 요청 / ans: 답 / title: 짧은 제목(질문 줄 행 이름 · 없으면 안 바꿈)
def answer_note(req, ans, title=None):
    # 대상 · 키트 · notes.json 폴더
    t = req.get("target") or {}
    root = Path(req.get("root") or os.getcwd())
    tool = root / "bookkit" / "notes.py"
    if not tool.is_file():
        raise MagicError(f"notes.py 없음: {tool}")
    book = (root / str(t.get("notes_file") or "")).parent
    if not (book / "notes.json").is_file():
        raise MagicError(f"notes.json 없음: {book}")
    # 답 파일(임시 — 줄 바꿈 · 기호 그대로)
    fd, tmp = tempfile.mkstemp(prefix=f"note_{t.get('note')}_", suffix=".md")
    os.close(fd)
    try:
        Path(tmp).write_text(ans, encoding="utf-8")
        extra = (["--thread", str(t["thread"])] if t.get("thread") else []) + (["--title", title] if title and title.strip() else [])
        r = subprocess.run([sys.executable, str(tool), "answer", str(t.get("note")), "--file", tmp, "--book", str(book)] + extra,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if r.returncode != 0:
        raise MagicError(f"스티커 답 실패 — {(r.stdout + r.stderr).strip()[-200:]}")
    return r.stdout.strip().splitlines()[-1]


# ======= 명령줄 =======
def build_parser():
    # 해석기
    ap = argparse.ArgumentParser(prog="magic.py", description="허브 마법봉 요청 — show · answer-node · answer-md · answer-code · answer-form · answer-note")
    # 명령 묶음
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="명령")
    p = sub.add_parser("show")
    p.add_argument("rid")
    p = sub.add_parser("answer-node")
    p.add_argument("rid")
    p.add_argument("body", nargs="?", default="")
    p.add_argument("--short", required=True, help="결론 한 줄(60자)")
    for name in ("answer-md", "answer-code", "answer-form", "answer-note"):
        p = sub.add_parser(name)
        p.add_argument("rid")
        p.add_argument("answer")
        if name == "answer-note":
            p.add_argument("--title", help="짧은 제목(책 아래 질문 줄 행 이름 · 원 질문 답에)")
    return ap


# 명령 실행 — 출력 글
# a: 해석 결과
def run(a):
    if a.cmd == "show":
        return cmd_show(a.rid)
    req, _ = load_request(a.rid)
    if req.get("role") != "2nd":
        raise MagicError(f"{a.cmd} 는 2nd-magic 요청에만(이 요청 {req.get('role')})")
    # 답 자리 종류
    kind = (req.get("target") or {}).get("kind")
    want = a.cmd.split("-", 1)[1]
    # 설문 질문 문항의 답 자리 = 설명 폼(answer-form)
    if kind == "survey":
        kind = "form"
    if kind != want:
        raise MagicError(f"이 요청의 답 자리는 {kind} — answer-{kind} 로")
    if a.cmd == "answer-node":
        store, _, tp = flowtree(req)
        t = req["target"]
        # 설문 노드 답 자리 — 물은 글(메모 · 입력창 글)도 같이 남김
        extra = {"ask": t.get("ask") or req.get("question") or ""} if t.get("own") == "survey" else {}
        return store.apply(tp, "2nd", "answer", question=t["question"], short=a.short, text=a.body, **extra)["msg"]
    if not a.answer.strip():
        raise MagicError("답 없음")
    if a.cmd == "answer-md":
        p, line = answer_md(req, a.answer)
        return f"답 넣음: {req['target'].get('file') or p}:{line}"
    if a.cmd == "answer-code":
        p, line = answer_code(req, a.answer)
        return f"답 넣음: {req['target'].get('file') or p}:{line}"
    if a.cmd == "answer-note":
        return answer_note(req, a.answer, a.title)
    sid = answer_form(req, a.answer, a.rid)
    return f"설명 폼 등록: {sid} — devview 설문 탭(Alt+S)"


# 명령줄 진입점 — 종료코드
# argv: 인자(없으면 sys.argv)
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    # 인자 — --short(와 값)를 맨 뒤로: 파이썬 3.12 이하 argparse 는 «answer-node 요청id --short 결론 본문» 의 본문을 못 받음(3.13 부터 됨)
    args = list(sys.argv[1:] if argv is None else argv)
    if "--short" in args and args.index("--short") + 1 < len(args):
        k = args.index("--short")
        args = args[:k] + args[k + 2:] + args[k:k + 2]
    try:
        print(run(build_parser().parse_args(args)))
    except (MagicError, hub.HubError, OSError, ValueError) as err:
        print(f"실패: {err}", file=sys.stderr)
        return 1
    except Exception as err:  # noqa: BLE001 — flowtree_store.StoreError 등(모듈을 늦게 불러서 이름으로 못 잡음)
        if type(err).__name__ == "StoreError":
            print(f"실패: {err}", file=sys.stderr)
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
