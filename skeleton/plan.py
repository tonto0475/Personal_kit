#!/usr/bin/env python3
# 뼈대 계획표 초안 — 과제 폴더(README · 자료 파일) + bookkit 분석 결과(있으면) → skeleton/out/plan.json · plan.md
"""
사용: python3 skeleton/plan.py --task <과제 폴더> [--book bookkit/books/<이름>] [--out skeleton/out]
- 규칙 기반 초안: 자료 파일 · 열 이름 → K1 읽기 함수 / README 의 화면 · 역할 · 저장 · 배포 문장 → K0 · K2 · K3
- 이름이 기계적으로 정해진 칸은 «다듬을 칸» 표시 — 서브가 다듬고, 유저가 hand_off 의 파일 · 함수 표에서 정한다
- 표준 라이브러리만 · 파이썬 3.10 이상 · 과제 폴더는 읽기만
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 이 파일이 있는 폴더(skeleton)
HERE = Path(__file__).resolve().parent
# 자료 파일로 보는 확장자
DATA_EXT = (".csv", ".tsv", ".xlsx", ".json")
# 자료 파일 찾을 때 건너뛸 폴더 이름
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "kit", ".codex", ".codex-hub"}
# 자주 나오는 영어 낱말 → 한글(자료 이름 다듬기 초안 · 없으면 영어 그대로 두고 «다듬을 칸»)
WORDS = {
    "order": "주문", "orders": "주문", "station": "작업장", "stations": "작업장", "stop": "정류장", "stops": "정류장",
    "vehicle": "차량", "vehicles": "차량", "bus": "버스", "buses": "버스", "truck": "트럭", "trucks": "트럭",
    "driver": "기사", "drivers": "기사", "employee": "직원", "employees": "직원", "worker": "작업자", "workers": "작업자",
    "shift": "근무", "shifts": "근무", "schedule": "일정", "schedules": "일정", "route": "노선", "routes": "노선",
    "customer": "고객", "customers": "고객", "product": "제품", "products": "제품", "item": "품목", "items": "품목",
    "location": "위치", "locations": "위치", "site": "현장", "sites": "현장", "warehouse": "창고", "depot": "차고",
    "demand": "수요", "request": "요청", "requests": "요청", "task": "작업", "tasks": "작업", "job": "작업", "jobs": "작업",
    "user": "사용자", "users": "사용자", "log": "기록", "logs": "기록", "event": "사건", "events": "사건",
    "time": "시각", "times": "시각", "distance": "거리", "distances": "거리", "matrix": "표", "price": "가격", "prices": "가격",
    "inventory": "재고", "stock": "재고", "machine": "설비", "machines": "설비", "line": "라인", "lines": "라인",
    "sensor": "센서", "sensors": "센서", "lot": "로트", "lots": "로트", "defect": "불량", "defects": "불량",
    "equipment": "장비", "equipments": "장비", "tool": "공구", "tools": "공구", "asset": "자산", "assets": "자산",
    "booking": "예약", "bookings": "예약", "reservation": "예약", "reservations": "예약", "rental": "대여", "rentals": "대여",
    "room": "방", "rooms": "방", "seat": "좌석", "seats": "좌석", "member": "회원", "members": "회원",
}
# README 문장 분류 규칙 — (묶음, 정규식)
SENTENCE_RULES = {
    "K0": r"docker|도커|컨테이너|compose|배포|실행 방법|HOW_TO_RUN|포트|port|/health|헬스",
    "K2": r"저장|DB|데이터베이스|sqlite|이력|판 번호|버전|되돌|적용|반영|중복|두 번|업로드",
    "K3": r"화면|페이지|대시보드|보기|조회|지도|시간표|일정표|표로|목록|업로드|로그인|권한|역할|운영자|관리자|사원|직원|기사|작업자",
    "K4": r"계획|계산|배차|배정|경로|노선|최적|최소|최대|규칙|순서|묶",
}
# 역할로 보는 낱말
ROLE_WORDS = ("운영자", "관리자", "사원", "직원", "기사", "작업자", "고객", "점장", "감독자", "담당자")
# 화면 자리 규칙 — (낱말 정규식, 경로, 함수 이름, 설명)
PAGE_RULES = [
    (r".", "/", "첫_화면", "앱 껍데기 · 메뉴 · 램프"),
    (r"업로드|올리|파일 선택", "/upload", "업로드_화면", "업로드 → 미리보기 → 검사 결과 → 적용"),
    (r"결과|계획|조회|목록|표", "/result", "결과_화면", "결과 표"),
    (r"지도|위치|경로|노선", "/map", "지도_화면", "지도 자리"),
    (r"시간표|일정|배차표|근무표|타임라인", "/timetable", "시간표_화면", "시간표 자리"),
]
# A3 분석 type → 계산 함수 이름
CALC_NAMES = {"route": "경로_계산", "dispatch": "배차_계산", "schedule": "배정_계산"}


# 파일 글자 읽기 — utf-8-sig → utf-8 → cp949 순
# path: 파일 경로
def 글자_읽기(path):
    # 시도할 인코딩
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return path.read_text(encoding=enc)
        # 이 인코딩이 아님
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


# 과제 폴더의 자료 파일 목록 — README · 키트 폴더 제외 · 상대 경로 순
# task: 과제 폴더
def 자료_파일_찾기(task):
    # 찾은 파일
    found = []
    # 후보 경로
    for p in sorted(task.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in DATA_EXT:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(task).parts[:-1]):
            continue
        found.append(p)
    return found


# CSV 머리줄 · 행 수 — (열 이름 목록, 행 수)
# path: CSV 경로
def 열_이름_읽기(path):
    if path.suffix.lower() not in (".csv", ".tsv"):
        return [], None
    # 파일 글자
    text = 글자_읽기(path)
    # 줄 목록 — 빈 줄 제외
    rows = list(csv.reader(text.splitlines(), delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return [], 0
    return [c.strip() for c in rows[0]], len(rows) - 1


# 파일 이름 → 한글 자료 이름(초안) — (이름, 다듬어야 하나)
# stem: 확장자 뺀 파일 이름 / desc: bookkit facts 의 설명(있으면)
def 자료_이름_짓기(stem, desc=None):
    if desc:
        # 설명의 첫 낱말 — 공백 · 괄호 앞까지
        word = re.split(r"[\s(·,/]", desc.strip())[0]
        if word:
            return 이름_다듬기(word), False
    # 낱말 조각들
    parts = [w for w in re.split(r"[_\-\s.]+", stem.lower()) if w]
    # 한글로 바꾼 조각
    korean = [WORDS.get(w, w) for w in parts]
    return 이름_다듬기("_".join(korean) or stem), any(w not in WORDS for w in parts)


# 파이썬 이름으로 쓸 수 있게 — 글자 · 숫자 · 밑줄만 · 숫자로 시작하면 앞에 «자료_»
# name: 원래 이름
def 이름_다듬기(name):
    # 바꾼 이름
    out = re.sub(r"\W+", "_", name).strip("_")
    if not out or out[0].isdigit():
        out = "자료_" + out
    return out


# README 문장 나누기 — 줄 · 마침표 기준 · 머리 기호 제거
# text: README 글자
def 문장_나누기(text):
    # 문장 목록
    out = []
    # 줄
    for line in text.splitlines():
        # 앞 기호 뺀 줄
        line = re.sub(r"^[\s#>*\-+|0-9.)]+", "", line).strip()
        if not line:
            continue
        # 조각
        for piece in re.split(r"(?<=[.!?。])\s+", line):
            if piece.strip():
                out.append(piece.strip())
    return out


# bookkit 계약 폴더 찾기 — 책 폴더(contracts/ 밑) 또는 계약 폴더 그대로
# book: --book 값
def 계약_읽기(book):
    if not book:
        return {}
    # 계약 폴더
    folder = book / "contracts" if (book / "contracts").is_dir() else book
    # 계약 이름 → 내용
    out = {}
    # 계약 이름
    for name in ("facts", "reqs", "steps"):
        # 계약 파일
        p = folder / f"{name}.json"
        if p.is_file():
            try:
                out[name] = json.loads(p.read_text(encoding="utf-8"))
            # 형식 오류 — 그 계약만 건너뜀
            except json.JSONDecodeError as err:
                print(f"경고: {p} 형식 오류 — {err}", file=sys.stderr)
    return out


# 계획표 만들기
# task: 과제 폴더 / contracts: bookkit 계약 dict
def 계획_만들기(task, contracts):
    # README 경로 · 글자
    readme = task / "README.md"
    text = 글자_읽기(readme) if readme.is_file() else ""
    # 문장
    sentences = 문장_나누기(text)
    # bookkit reqs 의 «만들 것» 요지도 문장에 보탬
    for r in (contracts.get("reqs", {}).get("readme") or []):
        if r.get("make", "만들 것") == "만들 것" and r.get("text"):
            sentences.append(f"[bookkit {r.get('id', '')}] {r['text']}")
    # 묶음 → 근거 문장
    hits = {k: [s for s in sentences if re.search(rx, s, re.I)] for k, rx in SENTENCE_RULES.items()}
    # bookkit facts 파일 설명
    descs = {f.get("name"): f.get("desc") for f in (contracts.get("facts", {}).get("files") or []) if f.get("name")}

    # ── K1 입력 ──
    # K1 항목 · 쓰인 이름
    k1_items, used = [], set()
    # 자료 파일
    for p in 자료_파일_찾기(task):
        # 열 이름 · 행 수
        cols, nrows = 열_이름_읽기(p)
        # 자료 이름 · 다듬을지
        name, rough = 자료_이름_짓기(p.stem, descs.get(p.name))
        while name in used:
            name += "_2"
        used.add(name)
        # 상대 경로
        rel = p.relative_to(task).as_posix()
        k1_items.append({
            "file": "src/core/입력.py", "func": f"{name}_읽기", "source": rel, "columns": cols, "rows": nrows,
            "why": f"{rel} — 열 {len(cols)}개({', '.join(cols[:8])}{' …' if len(cols) > 8 else ''}) · {nrows if nrows is not None else '?'}행",
            "todo": "다듬을 칸: 자료 이름(영어 그대로)" if rough else ""})
    k1_items += [
        {"file": "src/core/입력.py", "func": "검사_리포트", "why": "결측 · 중복 키 · 형식 오류 · 범위 밖 → 리포트 줄(보고만)", "todo": ""},
        {"file": "src/core/입력.py", "func": "전부_읽기", "why": "진입점 — 과제 폴더 → tables · report", "todo": ""}]
    # K1 설정 칸 — 파일마다 필수 열 · 고유 키
    k1_settings = [f"input.{i['func'][:-3]}.required = {i['columns']}" for i in k1_items if i.get("columns")]
    k1_settings += [f"input.{i['func'][:-3]}.key = ?" for i in k1_items if i.get("columns")] + ["input.ranges = ?(최소 · 최대)"]
    # bookkit 함정 — 처리 결정 칸(비움)
    for t in (contracts.get("facts", {}).get("traps") or []):
        k1_settings.append(f"함정 {t.get('id', '?')} 처리 = ?({t.get('file', '')} · {t.get('what', '')})")

    # ── K2 저장 ──
    # 표 이름(자료 이름)
    tables = [i["func"][:-3] for i in k1_items if i.get("columns") is not None and i.get("source")]
    k2_items = [
        {"file": "src/db/저장.py", "func": "표_만들기", "why": f"표 {len(tables)}개({', '.join(tables[:6])}) + versions(판 번호)", "todo": "다듬을 칸: 표 · 열 이름(영어)"},
        {"file": "src/db/저장.py", "func": "적용", "why": "진입점 — 검사 통과 자료를 한 트랜잭션으로 · 같은 자료 두 번 → 판 하나", "todo": ""},
        {"file": "src/db/저장.py", "func": "판_목록", "why": "판 번호 · 시각 · 행 수", "todo": ""}]
    k2_settings = [f"표 {t} 고유 키 = ?" for t in tables] + ["판 보관 개수 = ?", "되돌리기 = ?"]

    # ── K3 화면 ──
    # 화면 근거 글자 전체
    screen_text = " ".join(hits["K3"]) or text
    # 페이지 목록
    pages = []
    # 규칙
    for rx, path, func, what in PAGE_RULES:
        # 그 규칙에 걸린 문장
        why = next((s for s in hits["K3"] if re.search(rx, s)), "") if path != "/" else "기본"
        if path == "/" or why:
            pages.append({"file": "src/ui/화면.py", "func": func, "path": path, "why": f"{what} — {why[:60]}" if why != "기본" else what, "todo": ""})
    # 역할
    roles = [w for w in ROLE_WORDS if w in screen_text]
    if re.search(r"로그인|권한|역할", screen_text) or len(roles) >= 2:
        pages.append({"file": "src/ui/화면.py", "func": "로그인_화면", "path": "/login", "why": f"역할 {', '.join(roles) or '?'} — lib/auth", "todo": ""})
    k3_settings = ["화면 문구 · 메뉴 이름 = ?", f"역할 = {roles or '?'}", "표 열 순서 = ?"]

    # ── K4 계산 ──
    # A3 분석
    steps = contracts.get("steps", {})
    # 분석 type
    kind = steps.get("type")
    # 계산 함수 이름
    calc = CALC_NAMES.get(kind, "계획_계산")
    k4_items = [
        {"file": "src/core/계산.py", "func": calc, "why": "진입점 — 정리된 표 → 결과" + (f" · bookkit A3 type={kind}" if kind else " · A3 없음(근거 문장으로 초안)"), "todo": "" if kind else "다듬을 칸: 계산 이름"},
        {"file": "src/core/계산.py", "func": "기본_규칙", "why": "A3 방안 A 를 옮김(bookkit/books/<이름>/work/a3.py)" if kind else "가장 단순한 규칙 하나(담당자 답 전)", "todo": ""}]
    k4_settings = [f"{c.get('name')} = ?" for c in (steps.get("conditions") or []) if c.get("name")] + ["최적화 목표 = ?", "동률 처리 = ?"]

    # ── K0 · K5 ──
    # 컨테이너 요구
    docker = any(re.search(r"docker|도커|컨테이너", s, re.I) for s in hits["K0"])
    # 실행 문서 양식
    how_to = [p.name for p in task.glob("*.md") if p.name.upper().startswith(("HOW_TO", "AI_COLLAB"))]
    k0_items = [{"file": "src/ui/app.py", "func": "설정_읽기", "why": "config.yaml + 환경변수", "todo": ""},
                {"file": "src/ui/app.py", "func": "상태_검사_붙이기", "why": "/health — DB 열기", "todo": ""},
                {"file": "Dockerfile · .dockerignore" + (" · compose.yaml" if re.search(r"compose", text, re.I) else ""),
                 "func": "-", "why": "컨테이너 요구 있음" if docker else "README 에 컨테이너 말 없음 — 그래도 양식만", "todo": ""}]
    k0_items += [{"file": n, "func": "-", "why": "과제 제출 양식 — 칸만 채움", "todo": ""} for n in how_to]
    k5_items = [{"file": "tests/test_냉시동.py", "func": "test_냉시동", "why": "새 DB → K1 → K2 → K4", "todo": ""},
                {"file": "tests/test_같은_요청_두번.py", "func": "test_같은_요청_두번", "why": "scripts/race 틀", "todo": ""},
                {"file": "tests/test_경계값.py", "func": "test_경계값", "why": "lib/testing/boundary", "todo": ""}]

    # 묶음 목록
    bundles = [
        {"id": "K0", "name": "실행 · 배포", "confirm": False, "items": k0_items, "settings": ["log.debug = false", "업무 기준값 이름만(값 ?)"], "evidence": hits["K0"][:6]},
        {"id": "K1", "name": "입력 파이프라인", "confirm": True, "items": k1_items, "settings": k1_settings, "evidence": [], "entry": "src.core.입력:전부_읽기"},
        {"id": "K2", "name": "저장 · 적용", "confirm": True, "items": k2_items, "settings": k2_settings, "evidence": hits["K2"][:6], "entry": "src.db.저장:적용"},
        {"id": "K3", "name": "화면 틀", "confirm": False, "items": pages, "settings": k3_settings, "evidence": hits["K3"][:6]},
        {"id": "K4", "name": "계산 자리", "confirm": True, "items": k4_items, "settings": k4_settings, "evidence": hits["K4"][:6], "entry": f"src.core.계산:{calc}"},
        {"id": "K5", "name": "시험 틀", "confirm": False, "items": k5_items, "settings": ["경계값 범위 = ?"], "evidence": []},
    ]
    # 과제 이름 — README 첫 제목 · 없으면 폴더 이름
    title = next((ln.lstrip("#").strip() for ln in text.splitlines() if ln.startswith("# ")), "") or task.name
    return {"task": title, "task_dir": str(task), "made_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "book": bool(contracts), "app_module": "src.ui.app", "pages": [p["path"] for p in pages if p["path"] != "/login"] + ["/health"],
            "bundles": bundles}


# 계획표 → 마크다운
# plan: 계획표 dict
def 마크다운_만들기(plan):
    # 줄 목록
    out = [f"# 뼈대 계획표 — {plan['task']}", "",
           f"> {plan['made_at']} · plan.py 초안 · bookkit {'있음' if plan['book'] else '없음'} · «다듬을 칸» 은 서브가 다듬고 유저가 hand_off 의 파일 · 함수 표에서 정한다", ""]
    # 묶음
    for b in plan["bundles"]:
        out.append(f"## {b['id']} {b['name']} — {'유저 확인 뒤' if b['confirm'] else '바로 시작'}" + (f" · 진입점 `{b['entry']}`" if b.get("entry") else ""))
        out += ["", "| 파일 | 함수 | 근거 | 다듬을 칸 |", "|---|---|---|---|"]
        # 항목
        for i in b["items"]:
            # 함수 칸
            fn = i["func"] + (f" `{i['path']}`" if i.get("path") else "")
            out.append(f"| {i['file']} | {fn} | {i['why'].replace('|', '/')} | {i.get('todo', '')} |")
        out += ["", "비워 둘 설정 칸: " + " · ".join(str(s) for s in b["settings"])]
        if b.get("evidence"):
            out += ["", "README 근거:"] + [f"- {s[:120]}" for s in b["evidence"]]
        out.append("")
    return "\n".join(out)


# 실행
# argv: 인자(없으면 sys.argv)
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    # 해석기
    ap = argparse.ArgumentParser(description="뼈대 계획표 초안")
    ap.add_argument("--task", required=True, help="과제 폴더(README.md · 자료 파일)")
    ap.add_argument("--book", default=None, help="bookkit 책 폴더 또는 계약 폴더(있으면)")
    ap.add_argument("--out", default=str(HERE / "out"), help="출력 폴더(기본 skeleton/out)")
    # 해석 결과
    a = ap.parse_args(argv)
    # 과제 폴더
    task = Path(a.task).resolve()
    if not task.is_dir():
        print(f"실패: 과제 폴더 없음 — {task}", file=sys.stderr)
        return 1
    # 계획표
    plan = 계획_만들기(task, 계약_읽기(Path(a.book).resolve() if a.book else None))
    # 출력 폴더
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "plan.md").write_text(마크다운_만들기(plan), encoding="utf-8")
    # 묶음별 항목 수
    counts = " · ".join(f"{b['id']} {len(b['items'])}" for b in plan["bundles"])
    print(f"계획표: {out / 'plan.json'} · {out / 'plan.md'} ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
