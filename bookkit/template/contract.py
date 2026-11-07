# -*- coding: utf-8 -*-
"""분석 결과 계약(json) → 양식 칸 값 — 계약 파일 읽기 · json 이 못 담는 모양(짝 · 함수) 되살리기 · 계약 → 칸 모양 바꾸기

- 계약 = 책 폴더 contracts/ 의 facts.json(A1 자료 함정) · reqs.json(A2 README 요구 · 질문) · steps.json(A3 알고리즘 그림 · 재생기)
- 형식 문서는 bookkit/contracts/README.md · 검사는 bookkit/contracts/check_contract.py
- 과제와 무관하다. 이 파일은 고치지 않는다(빌드가 양식과 다르면 «구조 바뀜» 으로 알린다)
"""
import json
from pathlib import Path

# 계약 파일 이름 — 분석 카드 A1 · A2 · A3 이 하나씩 쓴다
NAMES = ("facts", "reqs", "steps")
# 분류 다섯 — 화면 · 시스템 · 알고리즘 · 파이프라인 · 문서(kit.CATS 와 같은 순서)
CATS = ("화면", "시스템", "알고리즘", "파이프라인", "문서")
# 짝으로 되살리는 목록의 최대 길이 — 이보다 짧고 글자 · 숫자만 든 목록은 (a, b …) 짝으로 바꾼다(좌표 · 범례 · 표 칸 위치)
PAIR_MAX = 4


def hm(m):
    """분 → «07:30»(24시 넘으면 다음 날 시각) — 시간표 칸에 «hm» 이 없을 때 쓴다"""
    return f"{int(m) // 60 % 24:02d}:{int(m) % 60:02d}"


def read(folder, name):
    """contracts/<name>.json → dict. 파일이 없으면 빈 dict(빈 양식도 빌드되게 — 칸은 빈 칸으로 보인다)"""
    p = Path(folder) / f"{name}.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _scalar(v):
    """글자 · 숫자 · 참거짓 · 없음"""
    return v is None or isinstance(v, (str, int, float, bool))


def revive(v, key=None):
    """json 값 → 양식 칸 값. json 은 짝(tuple)과 함수를 못 담는다 — 아래 규칙으로 되살린다
    - 글자 · 숫자만 든 4개 이하 목록 → 짝(tuple): 좌표 (위도, 경도) · 범례 (이름, 색) · 표 칸 위치 (행, 열) · 원본 줄 조각 (글, 색)
    - "notes" 의 열쇠 "0" · "3" → 정수 0 · 3(표 행 번호)
    - 시간표 "deadhead": {곳 a: {곳 b: 분}} → 함수(a, b) · "place": {곳: 이름} → 함수(곳) · 경로 "measure": {"a→b→c": 길이} → 함수(경로)"""
    if isinstance(v, list):
        out = [revive(x) for x in v]
        if 0 < len(out) <= PAIR_MAX and all(_scalar(x) for x in out):
            return tuple(out)
        return out
    if isinstance(v, dict):
        if key == "deadhead":
            table = v
            return lambda a, b: table[a][b]
        if key == "place":
            names = v
            return lambda n: names.get(n, n)
        if key == "measure":
            lens = v
            return lambda stops: lens["→".join(str(n) for n, _ in stops)]
        if key == "notes":
            return {int(k): revive(x) for k, x in v.items()}
        out = {k: revive(x, k) for k, x in v.items()}
        if "trips" in out and "steps" in out and "hm" not in out:  # 시간표 칸 — 시각 글 함수
            out["hm"] = hm
        return out
    return v


def route_key(names):
    """경로 길이 표(measure)의 열쇠 — 들르는 곳 이름을 «→» 로 잇는다(분석 쪽이 같은 함수로 만든다)"""
    return "→".join(str(n) for n in names)


# ════════════════════════════════════════════════════════════
# 계약 → 칸 모양(장 content 파일이 부른다)
# ════════════════════════════════════════════════════════════
class Row(tuple):
    """칸 한 행(짝) + 계약 항목 id(.id — Q1 · H3 …). 짝처럼 풀어 쓰고(a, b = row), 책의 번호 · 블록 ID 는 id 를 쓴다"""

    def __new__(cls, items, id=None):
        r = super().__new__(cls, items)
        r.id = id
        return r


def hidden_rows(R):
    """reqs.json «hidden» → 1장 «숨은_요구» [(요구, 어디서 드러나나, 분류, 만들 것)]"""
    return [Row((h["text"], h["where"], h["cat"], h["make"]), h.get("id")) for h in R.get("hidden", [])]


def readme_groups(R):
    """reqs.json «readme» → 1장 «README_요구» [{"name", "rows": [(원문 요지, 분류, 만들 것)], "fn"}] — 같은 group 이 이어지는 줄을 한 묶음으로"""
    out = []
    fns = R.get("readme_fn", {})
    for r in R.get("readme", []):
        if not out or out[-1]["name"] != r["group"]:
            out.append({"name": r["group"], "rows": [], "fn": fns.get(r["group"]) or None})
        out[-1]["rows"].append(Row((r["text"], r["cat"], r["make"]), r.get("id")))
    return out


def silent_rows(R):
    """reqs.json «silent» → 1장 «말하지_않은_곳» [(제목, 분류, 왜 문제인가, 기본 가정)]"""
    return [Row((s["title"], s["cat"], s["why"], s["default"]), s.get("id")) for s in R.get("silent", [])]


def question_rows(R, main=True):
    """reqs.json «questions» → 3장 «질문들»(main=True) · 부록 B «나머지_질문»(main=False) [(질문, 분류, 이유, 추천, 반대면)]"""
    return [Row((q["q"], q["cat"], q["why"], q["rec"], q["opp"]), q.get("id")) for q in R.get("questions", []) if bool(q.get("main")) == main]


def trap_cards(F, raw):
    """facts.json «traps»(big = true) → 2장 «함정» [{"title", "cat", "data", "naive", "do", "fn"}] — raw = kit.raw"""
    return [{"id": t.get("id"), "title": t["what"], "cat": t["cat"], "data": raw(*[tuple(p) for p in t["raw"]]), "naive": t["naive"], "do": t["fix"],
             "fn": t.get("fn") or None} for t in F.get("traps", []) if t.get("big")]


def cell(v, tone, mono, raw=None):
    """결함 표 «잘못된 예 · 정상 예» 칸 → HTML (v3 결함 표와 같은 모양)
    - 글자: « · » 로 나눈 조각마다 원본 조각 하나(mono) — «일근 · g» → 칩 둘
    - [[글, 색], …]: 원본 줄 조각 — 색 null = 그냥 글(«명단에 있는 키» 같은 설명 · v3 는 칩 없이 글) · "" · "bad" · "good" = 원본 조각"""
    if isinstance(v, (list, tuple)):
        pairs = [tuple(p) for p in v]
        if raw:
            return raw(*pairs)
        return " ".join(mono(t, c) for t, c in pairs if c is not None)
    s = str(v)
    return " · ".join(mono(p, tone) for p in s.split(" · ")) if " · " in s else mono(s, tone)


def defect_groups(F, mono, per_table=6, raw=None):
    """facts.json «defects» → 부록 A «결함_파일별» — 파일 순서대로 묶고 표 하나에 per_table 행까지(넘으면 표를 나눈다)
    bad · good 칸 모양은 cell() — raw = kit.raw(설명 글이 섞인 [[글, 색]] 칸에 쓴다)"""
    desc = {f["name"]: f.get("desc", "") for f in F.get("files", [])}
    groups = []
    for d in F.get("defects", []):
        if not groups or groups[-1]["file"] != d["file"]:
            groups.append({"file": d["file"], "rows": [], "fns": {}})
        groups[-1]["rows"].append(Row((d["what"], cell(d["bad"], "bad", mono, raw), cell(d["good"], "good", mono, raw), d["fix"]), d.get("id")))
        groups[-1]["fns"].update(d.get("fn") or {})
    out = []
    for g in groups:
        chunks = [g["rows"][i:i + per_table] for i in range(0, len(g["rows"]), per_table)]
        tables = [{"caption": f"{g['file']} 의 결함" + (f" ({k + 1}/{len(chunks)})" if len(chunks) > 1 else ""), "rows": c,
                   "fn": (g["fns"] or None) if k == len(chunks) - 1 else None} for k, c in enumerate(chunks)]
        out.append({"sub": f"{g['file']} — {desc[g['file']]}" if desc.get(g["file"]) else g["file"], "tables": tables})
    return out


def fact_cards(F, raw):
    """facts.json «facts» → 부록 A «사실» [(제목, 분류, 실제 데이터 HTML, 계획에 주는 영향, 이렇게)]"""
    return [Row((x["title"], x["cat"], raw(*[tuple(p) for p in x["raw"]]), x["effect"], x["do"]), x.get("id")) for x in F.get("facts", [])]


def report_table(F, mono):
    """facts.json «report» → 부록 C «C_리포트_표» {"rows": [[파일, 줄, 종류, 원본 값 HTML, 처리]], "caption"} · 없으면 빈 dict"""
    rows = [[r["file"], str(r["line"]), r["kind"], mono(r["raw"]), r["action"]] for r in F.get("report", [])]
    return {"rows": rows, "caption": "검증 리포트 예 — 이 자료의 실제 줄"} if rows else {}
