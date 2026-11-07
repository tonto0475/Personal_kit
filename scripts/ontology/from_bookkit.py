#!/usr/bin/env python3
"""bookkit 분석 결과 → 데이터 지도 초안 — docs/ONTOLOGY.md 칸 모양 그대로 새 파일에 쓴다. 표준 라이브러리만(Python 3.8+).

    python3 scripts/ontology/from_bookkit.py bookkit/books/<책>/contracts [--task <과제 폴더>] [--out docs/ONTOLOGY_draft.md] [--force]

- 읽는 것: 계약 facts.json · reqs.json · steps.json(있는 것만) · --task 를 주면 자료 파일의 머리 줄(열 이름)
- 쓰는 것: 초안 파일 하나(기본 docs/ONTOLOGY_draft.md) — docs/ONTOLOGY.md 는 절대 덮지 않는다 · 초안이 이미 있으면 --force 없이는 멈춤
- 항목 번호: 계약 항목의 id(R1 · H1 · Q1 · T1 · F1 …)를 그대로 쓴다. id 가 없으면 접두 + 순번으로 채우고 «순번 대체» 로 알린다
"""
import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 출력 인코딩 — 환경변수에 기대지 않는다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 키트 루트(이 파일 = <키트>/scripts/ontology/from_bookkit.py)
KIT = Path(__file__).resolve().parents[2]
# 기본 출력 파일
DEFAULT_OUT = KIT / "docs" / "ONTOLOGY_draft.md"
# 덮으면 안 되는 정본 이름
CANON_NAME = "ONTOLOGY.md"
# 자료 파일 읽기 인코딩 후보(앞부터)
ENCODINGS = ("utf-8-sig", "utf-8", "cp949")
# 목록 칸 → id 접두
PREFIX = {"readme": "R", "hidden": "H", "silent": "S", "questions": "Q", "traps": "T", "facts": "F", "defects": "D"}
# 분류 → README 풀이 «어디로» 추정(초안 — 서브가 고친다)
WHERE_BY_CAT = {"화면": "지도 밖(결과물)", "시스템": "지도 밖(결과물)", "문서": "지도 밖(결과물)",
                "알고리즘": "계산 / 규칙", "파이프라인": "규칙 / 출처"}
# «같은 대상이 두 줄» 류 함정을 3번 구별 기준으로도 보내는 낱말
DUP_WORDS = ("두 줄", "중복", "겹", "같은 주문", "같은 대상")
# 꾸밈 글 표시(**굵게** · !!빨강!! · ++초록++)
MARK_RE = re.compile(r"\*\*|!!|\+\+")
# 숫자 자리 {F['이름']}
NUM_RE = re.compile(r"\{F\[['\"]([^'\"]+)['\"]\]\}")


# 계약 json 하나 읽기 — 없으면 빈 사전
# folder: 계약 폴더 / name: facts · reqs · steps
def load_contract(folder: Path, name: str) -> dict:
    p = folder / f"{name}.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# 글 칸 정리 — 숫자 자리를 실측 값으로 · 꾸밈 표시 · 표를 깨는 | · 줄바꿈 제거
# text: 계약 글 / numbers: 이름 → 값
def clean(text, numbers: dict) -> str:
    if text is None:
        return ""
    s = NUM_RE.sub(lambda m: str(numbers.get(m.group(1), "{" + m.group(1) + "?}")), str(text))
    s = MARK_RE.sub("", s)
    return s.replace("|", "/").replace("\n", " ").strip()


# 목록 칸에 id 붙이기 — 있으면 그대로, 없으면 접두 + 순번(대체 개수를 센다)
# items: 계약 목록 / key: 칸 이름 / fallback: 칸 이름 → 순번 대체 개수
def with_ids(items: list, key: str, fallback: dict) -> list:
    out = []
    for i, it in enumerate(items or [], 1):
        iid = it.get("id") if isinstance(it, dict) else None
        if not iid:
            iid = f"{PREFIX[key]}{i}"
            fallback[key] = fallback.get(key, 0) + 1
        out.append((str(iid), it))
    return out


# 자료 파일의 머리 줄(열 이름) 읽기 — 못 읽으면 None
# path: 자료 파일
def read_header(path: Path):
    raw = path.read_bytes()[:65536]
    for enc in ENCODINGS:
        try:
            first = raw.decode(enc).splitlines()[0]
        except (UnicodeDecodeError, IndexError):
            continue
        return [c.strip() for c in next(csv.reader(io.StringIO(first)))]
    return None


# 과제 폴더에서 이름이 같은 파일 찾기(처음 하나)
# task: 과제 폴더 / name: 파일 이름
def find_file(task: Path, name: str):
    hits = sorted(p for p in task.rglob(name) if p.is_file())
    return hits[0] if hits else None


# 초안 글 만들기 → (글, 순번 대체 사전, 열 이름 사전)
# folder: 계약 폴더 / task: 과제 폴더(없으면 None)
def build(folder: Path, task) -> tuple:
    facts, reqs, steps = (load_contract(folder, n) for n in ("facts", "reqs", "steps"))
    if not (facts or reqs or steps):
        raise SystemExit(f"실패: 계약 json 이 없음 — {folder}")
    # 숫자 이름 → 값(이름이 겹치면 steps 가 이긴다 — 계약 README 규칙)
    numbers = {**facts.get("numbers", {}), **steps.get("numbers", {})}
    # 순번 대체 개수
    fallback = {}
    readme = with_ids(reqs.get("readme"), "readme", fallback)
    hidden = with_ids(reqs.get("hidden"), "hidden", fallback)
    silent = with_ids(reqs.get("silent"), "silent", fallback)
    questions = with_ids(reqs.get("questions"), "questions", fallback)
    traps = with_ids(facts.get("traps"), "traps", fallback)
    fact_rows = with_ids(facts.get("facts"), "facts", fallback)
    defects = with_ids(facts.get("defects"), "defects", fallback)
    files = facts.get("files", [])
    # 파일 이름 → 열 이름 목록(--task 가 있고 읽힌 것만)
    headers = {}
    if task is not None:
        for f in files:
            p = find_file(task, f.get("name", ""))
            h = read_header(p) if p else None
            if h:
                headers[f["name"]] = h
    c = lambda t: clean(t, numbers)
    task_name = reqs.get("task") or facts.get("task") or steps.get("task") or "(과제 이름)"
    big = [t for _, t in traps if t.get("big")]
    L = []
    w = L.append
    w(f"# ONTOLOGY 초안 — {task_name}")
    w("")
    w("> [!abstract] 초안 — from_bookkit.py 가 bookkit 분석 결과로 만든 칸(docs/ONTOLOGY.md 와 같은 모양)")
    w(f"> - 출처: {folder.as_posix()} · 만든 시각 {datetime.now():%Y-%m-%d %H:%M}")
    w("> - 서브가 할 일: 열 정의 · 구별 기준 · 연결 · 규칙 번호를 보태고, 질문 문장을 «확인할 것» 항목으로 줄여 docs/ONTOLOGY.md 로 옮긴다($ontology 1-0)")
    w("> - 번호 = 계약 항목 id(R 요구 · H 숨은 요구 · S 말하지 않은 곳 · Q 질문 · T 함정 · F 사실 · D 결함) — 옮길 때 근거 칸에 남긴다")
    w("> - «(초안)» 표시 칸은 추정이다 · README 문장은 bookkit 요지라 원문으로 바꿔 옮긴다")
    w("")
    w("> [!danger] 확인할 것 — 질문은 유저가 직접 · 위에서부터")
    w("> | 번호 | 단계 | 확인할 것 | 답에 따라 바뀌는 것 | 상태 | 받은 답(요지) |")
    w("> |---|---|---|---|---|---|")
    for iid, q in questions:
        stage = "?(본문 질문)" if q.get("main") else "?(부록 질문)"
        rec = f" · 기본 가정: {c(q.get('rec'))}" if q.get("rec") else ""
        w(f"> | {iid} | {stage} | {c(q.get('q'))}{rec} | {c(q.get('opp'))} | ⬜ | |")
    for iid, s in silent:
        w(f"> | {iid} | ? | {c(s.get('title'))} — {c(s.get('why'))} · 기본 가정: {c(s.get('default'))} | (초안) | ⬜ | |")
    w(">")
    w("> - 단계(1 쉬움 · 2 깊음)는 서브가 정한다 · 질문 문장은 항목으로 줄인다($ontology 1-7)")
    w("")
    w("> [!summary] 0. 한눈에 보기")
    w("> | 항목 | 내용 |")
    w("> |---|---|")
    w("> | 누가 쓰나 | |")
    w(f"> | 무엇을 하나 | {c(task_name)} |")
    w("> | 최종 결과 | |")
    w("> | 누구와 맞추나 | 담당자 |")
    w(f"> | 아직 모르는 핵심 | {' · '.join(i for i, _ in questions) or '—'} |")
    w(f"> | 가장 큰 함정 | {c(big[0].get('what')) if big else ''} |")
    w(f"> | 지금 상태 | 확인할 것 {len(questions) + len(silent)}개 중 답 받음 0개 · 만들 것 판정 {len(readme) + len(hidden)}개(초안) |")
    w("")
    w("> [!tip] 만들 것 판정 — 답을 받을 때마다 고친다")
    w("> | 항목 | 판정 | 이유(쉬운 말) | 근거 |")
    w("> |---|---|---|---|")
    for iid, r in readme:
        w(f"> | {c(r.get('make') or r.get('text'))} | ⭐ 필수 | README 요구 — {c(r.get('text'))} | README {iid} |")
    for iid, h in hidden:
        w(f"> | {c(h.get('make') or h.get('text'))} | 🟢 권장(초안) | {c(h.get('text'))} — {c(h.get('where'))} | 숨은 요구 {iid} |")
    w("")
    w("> [!quote] 1. README 문장 풀이 — 과제 글을 한 문장씩 어디에 적었나(전 문장) · R = 과제 요구 · r = 과제 외 요구")
    w("> **R — 과제 요구**(README · 요청 문서 등 과제가 시키는 것)")
    w(">")
    w("> | 번호 | 문장(원문 그대로) | 어디로 | 지도에 적은 곳 |")
    w("> |---|---|---|---|")
    for iid, r in readme:
        where = WHERE_BY_CAT.get(r.get("cat", ""), "?")
        w(f"> | {iid} | {c(r.get('text'))} (요지 · {c(r.get('group'))}) | {where}(초안) | 만들 것 판정 «{c(r.get('make'))}» |")
    w(">")
    w("> **r — 과제 외 요구**(대회 운영 안내 — 시험 시간 · 써야 할 프로그램 · 제출 방법 · 금지 도구 · 환경 주의사항 · 2 ~ 9번에 안 적는다)")
    w(">")
    w("> | 번호 | 문장(원문 그대로) | 종류 | 언제 지키나 |")
    w("> |---|---|---|---|")
    w("> | r1 | (서브가 README 에서 옮긴다 — bookkit 은 과제 외 안내를 따로 나누지 않는다) | | |")
    w("")
    w("---")
    w("")
    w("> [!example] 2. 대상 — 따로 이름이 붙어 하나씩 셀 수 있는 것")
    w("> | 대상 | 뜻 | 다르게 부르는 말 | 데이터에서는 | 근거 |")
    w("> |---|---|---|---|---|")
    for f in files:
        w(f"> | (초안) {c(f.get('desc'))} | | | {c(f.get('name'))} | 데이터 |")
    w(">")
    w("> - 🔢 " + (" · ".join(f"{f.get('name')} {f.get('rows')}행" for f in files) or "아직 안 셈"))
    w("")
    w("> [!note] 3. 구별 기준 — 무엇이 같으면 같은 것인가")
    dups = [(i, t) for i, t in traps if any(k in str(t.get("what", "")) for k in DUP_WORDS)]
    for iid, t in dups:
        w(f"> - (초안) {c(t.get('file'))} — {c(t.get('what'))} · {c(t.get('fix'))} [데이터 · {iid}]")
    if not dups:
        w("> - (서브가 채움 — profile.py 의 구별 기준 후보로)")
    w("")
    w("> [!info] 4. 정보 — 대상 하나를 설명하는 값")
    w("> | 대상 | 정보 | 데이터 열 | 모양 · 범위(말로 — 단위 먼저 · 시간대 표시 여부) | 근거 |")
    w("> |---|---|---|---|---|")
    for name, cols in headers.items():
        for col in cols:
            w(f"> | {name} | ? | {col} | 아직 안 셈(profile.py) | 데이터 |")
    if not headers:
        w("> | | | | (--task 를 주면 자료 파일 열 이름이 여기에) | |")
    w("")
    w("> [!tip] 5. 연결 — 대상끼리 어떻게 이어지나")
    w("> | 시작 | 연결 | 끝 | 하나에 몇 개 | 무엇으로 잇나 | 시점 | 근거 |")
    w("> |---|---|---|---|---|---|---|")
    names = list(headers)
    links = 0
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            for col in [x for x in headers[names[a]] if x in headers[names[b]]]:
                w(f"> | {names[a]} | ? | {names[b]} | 모름 | {col}(두 파일에 같은 이름 열 · 초안) | ? | 데이터 |")
                links += 1
    if not links:
        w("> | | | | | (서브가 채움) | | |")
    w("")
    w("> [!warning] 6. 경우 — 값이 될 수 있는 것")
    w("> | 대상 · 정보 | 경우 | 데이터에서 알아보는 법 | 나중에 바뀌나 · 무엇이 바꾸나 | 근거 |")
    w("> |---|---|---|---|---|")
    for iid, t in traps:
        lines = t.get("lines") or []
        at = "" if not lines else (f"{lines[0]}줄" if lines[0] == lines[-1] else f"{lines[0]}~{lines[-1]}줄")
        w(f"> | {c(t.get('file'))} | {c(t.get('what'))} | {at} · {c(t.get('fix'))} | ? | 데이터 · {iid} |")
    for iid, d in defects:
        w(f"> | {c(d.get('file'))} | {c(d.get('what'))} | 잘못된 예 «{c(d.get('bad'))}» · 정상 «{c(d.get('good'))}» | ? | 데이터 · {iid} |")
    if not (traps or defects):
        w("> | | | | | |")
    w("")
    w("> [!abstract] 7. 규칙 — 데이터에 대해 늘 지켜야 하는 것")
    n = 0
    for iid, t in traps:
        n += 1
        w(f"> - **{n}.** (초안) {c(t.get('fix'))} [데이터 · {iid}] — 확인: test_rule{n}_(이름은 서브가)")
    for iid, f in fact_rows:
        n += 1
        w(f"> - **{n}.** (초안) {c(f.get('title'))} — {c(f.get('do'))} [데이터 · {iid}] — 확인: 담당자 답 뒤")
    if not n:
        w("> - (서브가 채움)")
    w("")
    w("> [!success] 8. 계산 — 결과 숫자를 만드는 식")
    w("> - (서브가 채움 — bookkit 4장 · steps.json 의 방안과 맞춘다)")
    w("> - 🔢 " + (" · ".join(f"{k} = {v}" for k, v in numbers.items()) or "아직 안 셈"))
    w("")
    w("> [!quote] 9. 출처 — 값이 어디서 오나")
    w("> | 값 | 어디서 | 받는 법 | 주의 |")
    w("> |---|---|---|---|")
    for f in files:
        note = " · ".join(i for i, t in traps if t.get("file") == f.get("name"))
        w(f"> | {c(f.get('desc'))} | {c(f.get('name'))} | 파일 읽기 | {('함정 ' + note) if note else ''} |")
    w("")
    w("> [!example]- 10. 바뀐 기록")
    w("> | 시각 | 무엇이 바뀌었나 | 계기 |")
    w("> |---|---|---|")
    w(f"> | {datetime.now():%Y-%m-%d %H:%M} | 초안(from_bookkit) | bookkit 분석 결과 |")
    w("")
    return "\n".join(L), fallback, headers


# 진입점 — 인자 확인 → 초안 쓰기 → 한 줄 보고
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="bookkit 분석 결과 → 데이터 지도 초안(새 파일)")
    ap.add_argument("contracts", help="계약 폴더(facts.json · reqs.json · steps.json)")
    ap.add_argument("--task", help="과제 폴더 — 자료 파일 열 이름을 읽는다")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="초안 파일(기본 docs/ONTOLOGY_draft.md)")
    ap.add_argument("--force", action="store_true", help="초안 파일이 이미 있어도 새로 쓴다")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.name == CANON_NAME:
        print(f"실패: {CANON_NAME} 는 덮지 않는다 — 초안은 다른 이름으로(--out)")
        return 1
    if out.exists() and not a.force:
        print(f"실패: 이미 있음 — {out} (서브가 고쳤을 수 있다 · 다시 만들려면 --force)")
        return 1
    folder = Path(a.contracts)
    task = Path(a.task) if a.task else None
    if task is not None and not task.is_dir():
        print(f"실패: 과제 폴더 없음 — {task}")
        return 1
    text, fallback, headers = build(folder, task)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"초안: {out}")
    print("열 이름 읽음: " + (" · ".join(f"{k} {len(v)}열" for k, v in headers.items()) or "없음(--task 없음 · 못 찾음)"))
    print("순번 대체: " + (" · ".join(f"{k} {v}개" for k, v in fallback.items()) or "없음(전부 계약 id)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
