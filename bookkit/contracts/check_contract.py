# -*- coding: utf-8 -*-
r"""분석 결과 계약(json) 검사기 — 분석(A1 · A2 · A3)이 끝났다는 신호. 집필은 이 검사를 통과한 계약만 읽는다

    python3 bookkit/contracts/check_contract.py bookkit/books/<이름>/contracts                      폴더 안 facts · reqs · steps 전부
    python3 bookkit/contracts/check_contract.py bookkit/books/<이름>/contracts/facts.json           파일 하나(분석 카드가 자기 것만)
    python3 bookkit/contracts/check_contract.py <폴더> --task <과제 폴더>                            원본 줄 대조 — 계약의 «잘못된 예 · 정상 예» 가 원본 파일에 글자 그대로 있나
    python3 bookkit/contracts/check_contract.py <폴더> --render                                      그림 · 재생기를 실제로 그려 본다(양식 figs · kit)
    python3 bookkit/contracts/check_contract.py <폴더> --add-ids                                     항목 id 가 없는 곳에 접두 + 번호를 채워 쓰고 검사(있는 id 는 그대로)

- 결과: 파일마다 «PASS 이름 (개수 …)» 또는 «FAIL 이름» + 문제 목록(경로 · 무엇). 하나라도 FAIL 이면 종료 코드 1
- 경고(개수가 권장 범위 밖 · 숫자 이름 겹침 등)는 PASS 를 막지 않는다
- 항목 id: 목록 항목마다 «접두 + 번호»(ID_PREFIX 표) — 빠짐 · 겹침 · 접두 틀림은 FAIL. 책의 번호(질문 3 · 숨은 요구 12)와 블록 ID(s3-Q3) ·
  flowtree import-analysis 의 출처 열쇠가 이 id 를 쓴다 — 판이 바뀌어도 같은 항목은 같은 번호 · 같은 자리
- 형식: bookkit/contracts/README.md · 표준 라이브러리만 쓴다(--render 만 양식 · 엔진을 불러온다)
"""
import argparse
import json
import re
import sys
from pathlib import Path

# bookkit 폴더
KIT = Path(__file__).resolve().parent.parent
# 분류 다섯
CATS = ("화면", "시스템", "알고리즘", "파이프라인", "문서")
# 원본 조각 색
TONES = (None, "", "bad", "good")
# 과제 유형(steps.json «type»)
TYPES = ("route", "dispatch", "schedule", "other")
# 항목 id 접두 — (계약, 목록 칸) → 접두. 질문은 main = true 면 Q(3장) · false 면 B(부록 B)
ID_PREFIX = {("facts", "traps"): "T", ("facts", "defects"): "D", ("facts", "facts"): "F", ("facts", "report"): "P",
             ("reqs", "readme"): "R", ("reqs", "hidden"): "H", ("reqs", "silent"): "S", ("reqs", "questions"): "Q",
             ("steps", "conditions"): "C"}
# 부록 B 질문(main = false) 접두
ID_PREFIX_B = "B"


def prefix_of(kind, key, item):
    """항목 하나의 id 접두"""
    if (kind, key) == ("reqs", "questions") and isinstance(item, dict) and not item.get("main"):
        return ID_PREFIX_B
    return ID_PREFIX[(kind, key)]


def check_ids(d, kind, R):
    """목록 항목 id — 빠짐 · 접두 + 번호 형식 · 겹침(계약 하나 안)"""
    seen = {}
    for (k, key), _ in ID_PREFIX.items():
        if k != kind:
            continue
        for i, x in enumerate(d.get(key) or []):
            if not isinstance(x, dict):
                continue
            pre = prefix_of(kind, key, x)
            v = x.get("id")
            where = f"{key}[{i}].id"
            if not v:
                R.e(where, f"항목 id 가 없다 — «{pre}» + 번호(--add-ids 로 채울 수 있다)")
            elif not re.fullmatch(rf"{pre}\d+", str(v)):
                R.e(where, f"«{v}» — «{pre}» + 번호여야 한다")
            elif v in seen:
                R.e(where, f"«{v}» 가 {seen[v]} 와 겹친다")
            else:
                seen[v] = where
    R.counts["id"] = len(seen)


def add_ids(d, kind):
    """id 없는 항목에 접두 + 번호(같은 접두에서 쓰지 않은 가장 작은 번호부터) → 채운 수"""
    n = 0
    for (k, key), _ in ID_PREFIX.items():
        if k != kind:
            continue
        items = [x for x in (d.get(key) or []) if isinstance(x, dict)]
        used = {str(x.get("id")) for x in items if x.get("id")}
        for x in items:
            if x.get("id"):
                continue
            pre, j = prefix_of(kind, key, x), 1
            while f"{pre}{j}" in used:
                j += 1
            x_id = f"{pre}{j}"
            used.add(x_id)
            new = {"id": x_id, **x}
            x.clear()
            x.update(new)
            n += 1
    return n


# 글 안 숫자 자리 — {F['이름']} · {F["이름"]}
PH = re.compile(r"""\{F\[['"]([^'"]+)['"]\]""")


class Report:
    """한 파일의 문제 · 경고 모음"""

    def __init__(self, name):
        self.name, self.err, self.warn, self.counts = name, [], [], {}

    def e(self, where, what):
        self.err.append(f"{where}: {what}")

    def w(self, where, what):
        self.warn.append(f"{where}: {what}")


def need(R, obj, keys, where, kinds=None):
    """obj 가 dict 이고 keys 가 다 있나(값 종류도 — kinds = {열쇠: 종류})"""
    if not isinstance(obj, dict):
        R.e(where, f"dict 여야 한다(지금 {type(obj).__name__})")
        return False
    ok = True
    for k in keys:
        if k not in obj:
            R.e(where, f"«{k}» 가 없다")
            ok = False
        elif kinds and k in kinds and not isinstance(obj[k], kinds[k]):
            R.e(f"{where}.{k}", f"{kinds[k].__name__ if isinstance(kinds[k], type) else '/'.join(t.__name__ for t in kinds[k])} 여야 한다")
            ok = False
    return ok


def cat_ok(R, v, where):
    """분류 하나(또는 목록)가 다섯 중 하나인가"""
    for c in (v if isinstance(v, list) else [v]):
        if c not in CATS:
            R.e(where, f"분류 «{c}» 는 없다 — {' · '.join(CATS)}")


def raw_ok(R, pairs, where):
    """원본 줄 조각 [[글, 색 | null], …] 모양"""
    if not isinstance(pairs, list) or not pairs:
        R.e(where, "[[글, 색], …] 목록이어야 한다 — 색 null = 설명 글 · \"\" · \"bad\" · \"good\" = 원본 조각")
        return
    for i, p in enumerate(pairs):
        if not (isinstance(p, list) and len(p) == 2 and isinstance(p[0], str) and p[1] in TONES):
            R.e(f"{where}[{i}]", f"[글, 색] 짝이어야 한다 — 색은 null · \"\" · \"bad\" · \"good\" (지금 {str(p)[:60]})")


# ════════════════════════════════════════════════════════════
# v3 서식 — 칸 글자 수(경고). 한도 = v3 정본 계약(books/_selftest_v3/contracts)의 같은 칸 최대 + 약간
# 넘으면 책 모양이 v3 와 갈린다: 표 칸이 한 글자씩 줄바꿈 · ◎ 제목이 두 줄 · ◎ 카드가 쪽 반을 넘는다(RULES.md 6절 칸 길이표)
# ════════════════════════════════════════════════════════════
# (계약, 목록 칸) → {칸: 최대 글자 수}
FMT_MAX = {("reqs", "hidden"): {"text": 28, "where": 55, "make": 36}, ("reqs", "readme"): {"text": 40, "make": 28},
           ("reqs", "silent"): {"title": 24, "why": 150, "default": 60}, ("reqs", "questions"): {"q": 75, "why": 140, "opp": 125},
           ("facts", "traps"): {"what": 48, "naive": 150, "fix": 100}, ("facts", "defects"): {"what": 55, "fix": 115},
           ("facts", "facts"): {"title": 32, "effect": 120, "do": 75}}
# (계약, 목록 칸) → {칸: 최소 글자 수} — v3 는 이유 · 반대면을 실측 숫자를 넣은 1~2문장으로 썼다(31자 이상)
FMT_MIN = {("reqs", "questions"): {"why": 25, "opp": 20}, ("reqs", "silent"): {"why": 35}}
# 무엇을 줄이면 되는지(경고 끝에 붙는 말)
FMT_HINT = {"hidden": "1장 표 — «숨은 요구» 는 굵은 짧은 구(v3 10~23자), 길면 «만들 것» 칸이 한 글자씩 줄바꿈된다",
            "readme": "1장 표 — README 원문 요지(v3 10~33자)", "silent": "1장 ◎ — 제목은 한 줄(v3 11~19자)",
            "questions": "3장 · 부록 B ◎", "traps": "2장 ◎ 카드 — 칸 하나 2~3문장 · 카드 300자 안팎",
            "defects": "부록 A 결함 표", "facts": "부록 A 사실 ◎"}
# ◎ 카드 하나(함정 · 사실) 글 전체 한도 — v3 최대 324
FMT_CARD = 360


def flen(v):
    """칸 글자 수 — 꾸밈(**· !! · ++)은 빼고 {F['이름']} 은 숫자 네 자리로 센다 · [[글, 색]] 목록은 글만"""
    if isinstance(v, list):
        return sum(flen(p[0]) for p in v if isinstance(p, list) and p and isinstance(p[0], str))
    s = re.sub(r"\{[^{}]*\}", "0000", str(v or ""))
    return len(re.sub(r"\*\*|!!|\+\+", "", s))


def check_format(d, kind, R):
    """칸 글자 수 · 묶음 크기가 v3 서식 범위 안인가(경고)"""
    if kind == "reqs":
        groups = []
        for x in d.get("readme", []):
            if isinstance(x, dict):
                if not groups or groups[-1][0] != x.get("group"):
                    groups.append([x.get("group"), 0])
                groups[-1][1] += 1
        small = [f"{g}({n})" for g, n in groups if n < 3]
        if len(groups) > 5 or small:
            R.w("readme.group", f"묶음 {len(groups)}개" + (f" · 3행 안 되는 묶음 {', '.join(small)}" if small else "")
                + " — v3 는 4묶음 · 묶음마다 5~8행(작은 표가 여럿이면 쪽이 들쭉날쭉하다 — 비슷한 묶음을 합친다)")
    for (k, lst), lim in FMT_MAX.items():
        if k != kind:
            continue
        mins = FMT_MIN.get((k, lst), {})
        for i, x in enumerate(d.get(lst, [])):
            if not isinstance(x, dict):
                continue
            where = f"{lst}[{i}]" + (f"({x['id']})" if x.get("id") else "")
            for f, mx in lim.items():
                n = flen(x.get(f, ""))
                if n > mx:
                    R.w(where, f"«{f}» {n}자 — v3 한도 {mx}자({FMT_HINT[lst]})")
            for f, mn in mins.items():
                n = flen(x.get(f, ""))
                if f in x and n < mn:
                    R.w(where, f"«{f}» {n}자 — 너무 짧다(v3 는 실측 숫자를 넣은 1~2문장 · {mn}자 이상)")
            if lst in ("traps", "facts"):
                card = sum(flen(x.get(f, "")) for f in ("what", "title", "raw", "naive", "fix", "effect", "do"))
                if card > FMT_CARD and (lst != "traps" or x.get("big")):
                    R.w(where, f"◎ 카드 전체 {card}자 — v3 한도 {FMT_CARD}자(칸마다 2~3문장 · 원본 조각은 두세 개)")


def expr_in_raw(R, pairs, where):
    """원본 조각(색 "" · bad · good)에 {식} — 원본은 글자 그대로라 계산되지 않는다(FAIL)"""
    for i, p in enumerate(pairs if isinstance(pairs, list) else []):
        if isinstance(p, list) and len(p) == 2 and p[1] is not None and isinstance(p[0], str) and re.search(r"\{\s*[A-Za-z_]", p[0]):
            R.e(f"{where}[{i}]", f"원본 조각 «{p[0][:40]}» 에 {{식}} — 원본 조각은 글자 그대로라 계산되지 않는다. 숫자는 설명 글(색 null)로 옮긴다")


def cell_ok(R, v, where, T=None, file=None, tone="bad"):
    """결함 «bad» · «good» 칸 — 글자(« · » 로 나눈 조각마다 원본 칩) 또는 [[글, 색]] 목록(색 null = 칩 없는 설명 글)"""
    if isinstance(v, list):
        raw_ok(R, v, where)
        expr_in_raw(R, v, where)
        return
    if not isinstance(v, str):
        R.e(where, "글자 또는 [[글, 색], …] 이어야 한다")
        return
    if re.search(r"\{\s*[A-Za-z_]", v):
        R.e(where, f"«{v[:40]}» 에 {{식}} — 원본 칩은 글자 그대로라 계산되지 않는다")
    if T:
        for part in v.split(" · "):
            if part and not T.has(part, file):
                R.w(where, f"«{part[:50]}» 이 {file} 에 글자 그대로 없다 — "
                           + ("정리한 값을 넣었나?" if tone == "bad" else f"설명 글이면 [[\"{part[:20]}\", null]] 로 쓴다(v3: 칩 없이 글 · 초록 칩은 원본에 있는 값만)"))


def count(R, name, n, lo, hi, where):
    """권장 개수 범위 — 밖이면 경고"""
    R.counts[name] = n
    if not lo <= n <= hi:
        R.w(where, f"{n}개 — 권장 {lo}~{hi}개(RULES.md 5절)")


def strings(v):
    """값 안의 글자 전부"""
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


# ════════════════════════════════════════════════════════════
# 원본 대조(--task)
# ════════════════════════════════════════════════════════════
class Task:
    """과제 폴더의 원본 파일(uploads/ 아래) — 이름 → 줄 목록"""

    def __init__(self, folder):
        self.dir = Path(folder)
        self.files = {}
        up = self.dir / "uploads"
        for p in sorted(up.rglob("*")) if up.is_dir() else []:
            if p.is_file() and p.suffix.lower() in (".csv", ".txt", ".json", ".tsv", ".log", ".md", ".yaml", ".yml"):
                try:
                    self.files[p.name] = p.read_text(encoding="utf-8-sig").splitlines()
                except UnicodeDecodeError:
                    self.files[p.name] = p.read_text(encoding="cp949", errors="replace").splitlines()
        rd = self.dir / "README.md"
        if rd.is_file():
            self.files["README.md"] = rd.read_text(encoding="utf-8-sig").splitlines()

    def names(self, field):
        """«a.csv · b.csv» → 있는 파일 이름 목록(없으면 전체)"""
        want = [x.strip() for x in re.split(r"[·,]", field or "") if x.strip()]
        got = [n for n in want if n in self.files]
        return got or list(self.files)

    def has(self, text, field):
        """원본 조각이 그 파일(들)의 한 줄 안에 글자 그대로 있나"""
        if not text.strip():
            return True
        return any(text in ln for n in self.names(field) for ln in self.files[n])


def check_raw_in_task(R, T, pairs, field, where):
    for i, p in enumerate(pairs if isinstance(pairs, list) else []):
        if isinstance(p, list) and len(p) == 2 and p[1] in ("", "bad", "good") and isinstance(p[0], str):
            if not T.has(p[0], field):
                R.w(f"{where}[{i}]", f"원본 조각 «{p[0][:50]}» 이 {field or '과제 파일'} 에 글자 그대로 없다(손으로 베꼈거나 정리한 값?)")


# ════════════════════════════════════════════════════════════
# facts.json — A1 자료 함정
# ════════════════════════════════════════════════════════════
def check_facts(d, R, T=None):
    need(R, d, ["contract", "version", "numbers", "traps"], "facts.json")
    if d.get("contract") != "facts":
        R.e("facts.json.contract", "\"facts\" 여야 한다")
    if not isinstance(d.get("numbers", {}), dict):
        R.e("facts.json.numbers", "dict 여야 한다 — {이름: 실측 값}")
    for i, f in enumerate(d.get("files", [])):
        need(R, f, ["name"], f"files[{i}]")
        if T and isinstance(f, dict) and f.get("name") and f["name"] not in T.files:
            R.w(f"files[{i}]", f"«{f['name']}» 가 과제 uploads/ 에 없다")
    traps = d.get("traps", [])
    for i, t in enumerate(traps):
        w = f"traps[{i}]"
        if need(R, t, ["id", "file", "what", "cat", "raw", "naive", "fix"], w):
            cat_ok(R, t["cat"], f"{w}.cat")
            raw_ok(R, t["raw"], f"{w}.raw")
            expr_in_raw(R, t["raw"], f"{w}.raw")
            if "lines" in t and not (isinstance(t["lines"], list) and all(isinstance(x, int) for x in t["lines"])):
                R.e(f"{w}.lines", "[첫 줄, 끝 줄] 정수 목록이어야 한다")
            if "measured" in t and not isinstance(t["measured"], dict):
                R.e(f"{w}.measured", "dict 여야 한다 — {\"정리한 값\": 208, \"그냥 읽은 값\": 24}")
            if T:
                check_raw_in_task(R, T, t["raw"], t["file"], f"{w}.raw")
                if isinstance(t.get("lines"), list) and t["lines"]:
                    n = max((len(T.files[x]) for x in T.names(t["file"])), default=0)
                    if max(t["lines"]) > n:
                        R.e(f"{w}.lines", f"줄 {max(t['lines'])} 이 파일 줄 수 {n} 보다 크다")
    ids = [t.get("id") for t in traps if isinstance(t, dict)]
    if len(ids) != len(set(ids)):
        R.e("traps", "id 가 겹친다")
    count(R, "함정(2장 · big)", sum(1 for t in traps if isinstance(t, dict) and t.get("big")), 5, 8, "traps(big = true)")
    for i, x in enumerate(d.get("defects", [])):
        w = f"defects[{i}]"
        if need(R, x, ["file", "what", "bad", "good", "fix"], w):
            cell_ok(R, x["bad"], f"{w}.bad", T, x["file"], "bad")
            cell_ok(R, x["good"], f"{w}.good", T, x["file"], "good")
    R.counts["결함(부록 A)"] = len(d.get("defects", []))
    for i, x in enumerate(d.get("facts", [])):
        w = f"facts[{i}]"
        if need(R, x, ["title", "cat", "raw", "effect", "do"], w):
            cat_ok(R, x["cat"], f"{w}.cat")
            raw_ok(R, x["raw"], f"{w}.raw")
            expr_in_raw(R, x["raw"], f"{w}.raw")
            if T:
                check_raw_in_task(R, T, x["raw"], "", f"{w}.raw")
    count(R, "사실(부록 A)", len(d.get("facts", [])), 8, 12, "facts")
    for i, x in enumerate(d.get("report", [])):
        w = f"report[{i}]"
        if need(R, x, ["file", "line", "kind", "raw", "action"], w) and T and x["file"] in T.files:
            lines = T.files[x["file"]]
            if isinstance(x["line"], int) and 1 <= x["line"] <= len(lines) and x["raw"] not in lines[x["line"] - 1]:
                R.w(f"{w}", f"{x['file']} {x['line']}번째 줄에 «{x['raw'][:40]}» 이 없다")
    R.counts["숫자"] = len(d.get("numbers", {}))
    check_figures(d.get("figures", {}), R, "facts.json.figures")
    check_format(d, "facts", R)


# ════════════════════════════════════════════════════════════
# reqs.json — A2 README 요구 · 질문
# ════════════════════════════════════════════════════════════
def check_reqs(d, R, T=None):
    need(R, d, ["contract", "version", "readme", "hidden", "silent", "questions"], "reqs.json")
    if d.get("contract") != "reqs":
        R.e("reqs.json.contract", "\"reqs\" 여야 한다")
    for key, fields in (("readme", ["group", "text", "cat", "make"]), ("hidden", ["text", "where", "cat", "make"]),
                        ("silent", ["title", "cat", "why", "default"]), ("questions", ["q", "cat", "why", "rec", "opp", "main"])):
        for i, x in enumerate(d.get(key, [])):
            if need(R, x, fields, f"{key}[{i}]"):
                cat_ok(R, x["cat"], f"{key}[{i}].cat")
    if not isinstance(d.get("readme_fn", {}), dict):
        R.e("readme_fn", "{묶음 이름: {용어: 설명}} 이어야 한다")
    groups = []
    for x in d.get("readme", []):
        if isinstance(x, dict) and (not groups or groups[-1] != x.get("group")):
            groups.append(x.get("group"))
    if len(groups) != len(set(groups)):
        R.w("readme", f"같은 group 이 떨어져 두 번 나온다({groups}) — 묶음이 둘로 갈라진다. 같은 group 끼리 붙여 쓴다")
    R.counts["README 요구"] = len(d.get("readme", []))
    count(R, "숨은 요구", len(d.get("hidden", [])), 8, 12, "hidden")
    count(R, "말하지 않은 곳", len(d.get("silent", [])), 7, 10, "silent")
    qs = [q for q in d.get("questions", []) if isinstance(q, dict)]
    count(R, "질문(3장)", sum(1 for q in qs if q.get("main")), 5, 8, "questions(main = true)")
    count(R, "질문(부록 B)", sum(1 for q in qs if not q.get("main")), 6, 10, "questions(main = false)")
    check_format(d, "reqs", R)


# ════════════════════════════════════════════════════════════
# steps.json — A3 알고리즘 그림 · 재생기
# ════════════════════════════════════════════════════════════
# 그림 이름 → 꼭 있어야 하는 열쇠(figs 함수 설명과 같다)
FIG_KEYS = {"그림_큰흐름": ["flow", "bars"], "그림_자료띠": ["title", "total", "segments"], "순서_지도": ["points", "short", "target", "target_label", "best", "worst"],
            "C_적용_그림": ["names", "fail", "rows", "labels"], "C_화면_그림": ["left", "right"],
            "상태전이": ["states"], "시각막대": ["bars"], "두줄비교": ["rows"]}


def check_figures(figs, R, where):
    if not isinstance(figs, dict):
        R.e(where, "dict 여야 한다 — {그림 이름: 칸}")
        return
    for name, P in figs.items():
        if name == "순서_지도" and isinstance(P, dict) and P.get("kind") == "arrows":  # 측정 화살표 두 판(분석 틀 stat_model)
            need(R, P, ["x", "y", "scale", "good", "bad"], f"{where}.{name}")
        elif name in FIG_KEYS:
            need(R, P, FIG_KEYS[name], f"{where}.{name}")
    R.counts["그림"] = R.counts.get("그림", 0) + len(figs)


def check_map(R, M, where):
    if need(R, M, ["points", "weights", "short"], where):
        for n in M["weights"]:
            if n not in M["points"]:
                R.e(f"{where}.weights", f"«{n}» 의 좌표가 points 에 없다")
        long_ = [f"{n}→{s}" for n, s in M["short"].items() if n in M["weights"] and len(str(s)) > 5]
        if long_:
            R.w(f"{where}.short", f"짧은 이름이 5자를 넘는다 {long_[:4]} — 지도 이름표가 겹친다(2~3자)")
        # 그리는 점(weights)이 지도 범위(bounds · fit_points)의 일부에만 몰렸나 — 다른 사업장 점까지 범위에 넣으면 지도 한쪽에 뭉친다
        drawn = [M["points"][n] for n in M["weights"] if n in M["points"]]
        box = M.get("bounds")
        if not box and M.get("fit_points"):
            fp = M["fit_points"]
            box = (min(p[0] for p in fp), max(p[0] for p in fp), min(p[1] for p in fp), max(p[1] for p in fp))
        if drawn and box and len(box) == 4 and box[1] > box[0] and box[3] > box[2]:
            ry = (max(p[0] for p in drawn) - min(p[0] for p in drawn)) / (box[1] - box[0])
            rx = (max(p[1] for p in drawn) - min(p[1] for p in drawn)) / (box[3] - box[2])
            if min(rx, ry) < 0.5:
                R.w(f"{where}", f"그리는 점이 지도 범위의 한 방향 {min(rx, ry):.0%} 에만 몰렸다 — 이름표가 겹친다. bounds · fit_points 를 그리는 점(weights) + 목적지로(analysis/_common.map_spec)")


def check_state(R, state, M, where):
    if not isinstance(state, list):
        R.e(where, "차마다 [[곳, 수], …] 목록이어야 한다")
        return
    for b, stops in enumerate(state):
        for s_ in stops:
            if not (isinstance(s_, list) and len(s_) == 2):
                R.e(f"{where}[{b}]", f"[곳, 수] 짝이어야 한다(지금 {str(s_)[:40]})")
            elif isinstance(M, dict) and s_[0] not in M.get("points", {}):
                R.e(f"{where}[{b}]", f"곳 «{s_[0]}» 이 지도 points 에 없다")


def check_players(P, R):
    if not isinstance(P, dict):
        R.e("players", "dict 여야 한다")
        return
    for name in P:
        if name not in ("채우기", "고치기", "이어붙이기"):
            R.e(f"players.{name}", "이름은 채우기 · 고치기 · 이어붙이기 중 하나")
    # 측정 화살표(kind quiver) · 관리도(kind chart) — 분석 틀 stat_model · 지도 · 시간표 칸 대신(본 것은 사본에서 빼 아래 지도 · 시간표 검사를 건너뛴다)
    P = dict(P)
    for name in ("채우기", "고치기"):
        if isinstance(P.get(name), dict) and P[name].get("kind") == "quiver":
            check_quiver(R, P.pop(name), f"players.{name}", name)
    if isinstance(P.get("이어붙이기"), dict) and P["이어붙이기"].get("kind") == "chart":
        check_chart(R, P.pop("이어붙이기"))
    f = P.get("채우기")
    if f is not None and need(R, f, ["title", "task", "map", "frame_title", "right_title", "words", "steps"], "players.채우기"):
        check_map(R, f["map"], "players.채우기.map")
        for i, st in enumerate(f["steps"]):
            if need(R, st, ["state", "cur", "text"], f"players.채우기.steps[{i}]"):
                check_state(R, st["state"], f["map"], f"players.채우기.steps[{i}].state")
        check_table(R, f.get("table"), "players.채우기.table", 8, steps=f["steps"])
        R.counts["채우기 단계"] = len(f["steps"])
    x = P.get("고치기")
    if x is not None and need(R, x, ["title", "task", "map", "right_title", "words", "steps"], "players.고치기"):
        check_map(R, x["map"], "players.고치기.map")
        lens = x.get("measure")
        uses_km = "{km" in x["words"].get("line", "")
        if uses_km and not isinstance(lens, dict):
            R.e("players.고치기.measure", "줄 글에 {km} 가 있으면 measure = {\"곳a→곳b→…\": 길이} 표가 있어야 한다")
        for i, st in enumerate(x["steps"]):
            w = f"players.고치기.steps[{i}]"
            if need(R, st, ["state", "head", "text"], w):
                check_state(R, st["state"], x["map"], f"{w}.state")
                for g in st.get("gone", []):
                    if not (isinstance(g, list) and len(g) == 2):
                        R.e(f"{w}.gone", "[차 번호, 곳] 짝이어야 한다")
                if uses_km and isinstance(lens, dict):
                    for stops in st["state"]:
                        k = "→".join(str(n) for n, _ in stops)
                        if stops and k not in lens:
                            R.e(f"{w}.state", f"경로 «{k}» 의 길이가 measure 표에 없다")
        check_table(R, x.get("table"), "players.고치기.table", 8, steps=x["steps"])
        R.counts["고치기 단계"] = len(x["steps"])
    c = P.get("이어붙이기")
    if c is not None and need(R, c, ["title", "task", "timetable", "heads", "texts"], "players.이어붙이기"):
        T = c["timetable"]
        if need(R, T, ["trips", "steps", "have", "axis", "ticks", "legend", "deadhead", "place", "words"], "players.이어붙이기.timetable"):
            n = len(T["steps"])
            if len(c["heads"]) != n + 1 or len(c["texts"]) != n + 1:
                R.e("players.이어붙이기", f"heads · texts 는 단계 수 + 1 = {n + 1}개(지금 {len(c['heads'])} · {len(c['texts'])})")
            places = {t.get("frm") for t in T["trips"]} | {t.get("to") for t in T["trips"]}
            dh = T["deadhead"]
            if isinstance(dh, dict):
                miss = [f"{a}→{b}" for a in places for b in places if not (isinstance(dh.get(a), dict) and b in dh[a])]
                if miss:
                    R.e("players.이어붙이기.timetable.deadhead", f"빈 차 이동 시간 표에 없는 짝 {len(miss)}개(예: {miss[:3]}) — 일에 나오는 곳 전부 × 전부")
            else:
                R.e("players.이어붙이기.timetable.deadhead", "{곳 a: {곳 b: 분}} 표여야 한다")
            if not isinstance(T["place"], dict):
                R.e("players.이어붙이기.timetable.place", "{곳: 보일 이름} 표여야 한다")
            for i, s_ in enumerate(T["steps"]):
                if not (isinstance(s_, dict) and isinstance(s_.get("trip"), int) and 0 <= s_["trip"] < len(T["trips"]) and isinstance(s_.get("bus"), int)):
                    R.e(f"players.이어붙이기.timetable.steps[{i}]", "{\"trip\": 일 번호, \"bus\": 차 번호} 이어야 한다(일 번호는 trips 범위 안)")
            used = 1 + max((s_.get("bus", 0) for s_ in T["steps"] if isinstance(s_, dict)), default=0)
            if used > T.get("rows", 10):
                R.w("players.이어붙이기.timetable.rows", f"쓴 차 {used}대가 줄 수 {T.get('rows', 10)} 보다 많다 — 넘는 차는 안 보인다(rows 를 늘린다 · 16 까지 권장)")
        R.counts["이어 붙이기 단계"] = len(c.get("heads", [])) - 1


def check_quiver(R, q, where, name):
    """측정 화살표 재생기(kind quiver) — 판 칸 · 단계마다 칸 수만큼 dx · dy"""
    if need(R, q, ["title", "task", "plate", "right_title", "steps"], where) and need(R, q["plate"], ["x", "y", "scale"], f"{where}.plate"):
        n = len(q["plate"]["x"])
        if len(q["plate"]["y"]) != n:
            R.e(f"{where}.plate", f"x {n}개 · y {len(q['plate']['y'])}개 — 칸 수가 같아야 한다")
        for i, st in enumerate(q["steps"]):
            w = f"{where}.steps[{i}]"
            if need(R, st, ["dx", "dy", "text"], w) and (len(st["dx"]) != n or len(st["dy"]) != n):
                R.e(w, f"dx {len(st['dx'])} · dy {len(st['dy'])} — 판 칸 수 {n} 와 같아야 한다")
        check_table(R, q.get("table"), f"{where}.table", 8, steps=q["steps"])
        R.counts[f"{name} 단계"] = len(q["steps"])


def check_chart(R, c):
    """관리도 재생기(kind chart) — 점 · 단계 · 한계 · heads/texts 개수"""
    w = "players.이어붙이기"
    if need(R, c, ["title", "task", "chart", "heads", "texts"], w) and need(R, c["chart"], ["points", "series", "steps", "center", "ucl", "lcl", "axis"], f"{w}.chart"):
        Ch = c["chart"]
        n = len(Ch["steps"])
        if len(c["heads"]) != n + 1 or len(c["texts"]) != n + 1:
            R.e(w, f"heads · texts 는 단계 수 + 1 = {n + 1}개(지금 {len(c['heads'])} · {len(c['texts'])})")
        for i, p in enumerate(Ch["points"]):
            if not (isinstance(p, list) and len(p) == 4 and isinstance(p[2], int) and 0 <= p[2] < len(Ch["series"])):
                R.e(f"{w}.chart.points[{i}]", "[x 위치, 값, 줄 번호(series 범위 안), 한계 밖?] 이어야 한다")
                break
        for i, st in enumerate(Ch["steps"]):
            if not all(isinstance(j, int) and 0 <= j < len(Ch["points"]) for j in st):
                R.e(f"{w}.chart.steps[{i}]", "점 번호(points 범위 안) 목록이어야 한다")
        if not Ch["lcl"] <= Ch["center"] <= Ch["ucl"]:
            R.e(f"{w}.chart", "아래 한계 ≤ 가운데 ≤ 위 한계 여야 한다")
        if len(Ch["series"]) > 8:
            R.w(f"{w}.chart.series", f"줄 {len(Ch['series'])}개 — 8개 넘으면 색 · 오른쪽 목록이 넘친다")
        R.counts["관리도 단계"] = n


def check_table(R, t, where, max_rows, steps=None):
    if t is None:
        return
    if need(R, t, ["header", "rows"], where):
        if len(t["rows"]) > max_rows:
            R.w(where, f"{len(t['rows'])}행 — {max_rows}행 이하 권장(쪽 높이 · RULES.md 6절)")
        hdr = [str(h) for h in t["header"]]
        for key in ("bad_cells", "good_cells", "hl_cells"):
            for rc in t.get(key, []):
                if not (isinstance(rc, list) and len(rc) == 2):
                    R.e(f"{where}.{key}", "[행, 열 이름] 짝이어야 한다")
                    continue
                r, col = rc
                if isinstance(col, str) and col not in hdr:
                    R.e(f"{where}.{key}", f"열 «{col}» 이 header 에 없다({hdr})")
                if not (isinstance(r, int) and 0 <= r < len(t["rows"])):
                    R.e(f"{where}.{key}", f"행 {r} 이 표({len(t['rows'])}행) 밖")
        for k in (t.get("notes") or {}):
            if not (str(k).isdigit() and int(k) < len(t["rows"])):
                R.e(f"{where}.notes", f"행 {k} 이 표 밖")
        if steps is not None:
            for i, st in enumerate(steps):
                r = st.get("row") if isinstance(st, dict) else None
                if r is not None and not (isinstance(r, int) and 0 <= r < len(t["rows"])):
                    R.e(f"{where}", f"단계 {i} 의 row={r} 가 표 밖")


def check_steps(d, R, T=None):
    need(R, d, ["contract", "version", "type"], "steps.json")
    if d.get("contract") != "steps":
        R.e("steps.json.contract", "\"steps\" 여야 한다")
    if d.get("type") not in TYPES:
        R.e("steps.json.type", f"{' · '.join(TYPES)} 중 하나")
    check_players(d.get("players", {}), R)
    check_figures(d.get("figures", {}), R, "steps.json.figures")
    for name, t in (d.get("tables") or {}).items():
        check_table(R, t, f"tables.{name}", 20)
    for i, c in enumerate(d.get("conditions", [])):
        need(R, c, ["name", "value", "result"], f"conditions[{i}]")
    R.counts["숫자"] = len(d.get("numbers", {}))
    R.counts["조건"] = len(d.get("conditions", []))


# ════════════════════════════════════════════════════════════
# --render — 양식 그림 함수로 실제로 그려 본다
# ════════════════════════════════════════════════════════════
def render(docs, R):
    sys.path.insert(0, str(KIT / "engine"))
    from build_book import load_book
    alias, _ = load_book(KIT / "template")
    import importlib
    figs = importlib.import_module(f"{alias}.figs")
    kit = importlib.import_module(f"{alias}.kit")
    K = importlib.import_module(f"{alias}.contract")
    fn = {"그림_큰흐름": figs.overview, "그림_자료띠": figs.file_band, "순서_지도": figs.orders_map, "C_적용_그림": figs.txn, "C_화면_그림": figs.screens,
          "상태전이": figs.states, "시각막대": figs.time_bars, "두줄비교": figs.pair_rows}
    n = 0
    for name, d in docs.items():
        for fname, P in (d.get("figures") or {}).items():
            if fname in fn:
                try:
                    fn[fname](K.revive(P))
                    n += 1
                except Exception as ex:  # noqa: BLE001 — 어떤 칸이 틀렸는지 알린다
                    R[name].e(f"figures.{fname}", f"그리기 실패 — {type(ex).__name__}: {ex}")
        P = {k: K.revive(v) for k, v in (d.get("players") or {}).items()}
        for kind, p in P.items():
            try:
                if p.get("kind") == "quiver":  # 측정 화살표(분석 틀 stat_model)
                    for st in p["steps"]:
                        figs.quiver_map(p, st)
                        n += 1
                elif p.get("kind") == "chart":  # 관리도
                    for k in range(len(p["chart"]["steps"]) + 1):
                        figs.control_chart(p["chart"], k, p["heads"][k])
                        n += 1
                elif kind in ("채우기", "고치기"):
                    for st in p["steps"]:
                        hl = set(st.get("hl", ())) if kind == "고치기" else {st.get("cur")}
                        lines = kit.vehicle_lines(st["state"], hl, p)
                        figs.route_map(p["map"], st["state"], st.get("head", p.get("frame_title", "")), p["right_title"], lines,
                                       cur=st.get("cur"), hl=hl, gone=st.get("gone", ()), style="fill" if kind == "채우기" else "fix")
                        n += 1
                else:
                    T = p["timetable"]
                    for k in range(len(T["steps"]) + 1):
                        figs.timetable(T, k, p["heads"][k])
                        n += 1
            except Exception as ex:  # noqa: BLE001
                R[name].e(f"players.{kind}", f"그리기 실패 — {type(ex).__name__}: {ex}")
    return n


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="분석 결과 계약 검사")
    ap.add_argument("paths", nargs="+", help="contracts 폴더 또는 json 파일")
    ap.add_argument("--task", help="과제 폴더(README.md · uploads/) — 원본 줄 대조")
    ap.add_argument("--render", action="store_true", help="그림 · 재생기를 양식 함수로 그려 본다")
    ap.add_argument("--add-ids", action="store_true", help="항목 id 가 없는 곳에 접두 + 번호를 채워 파일에 쓴다(있는 id 는 그대로)")
    a = ap.parse_args(argv)
    files = []
    for p in map(Path, a.paths):
        files += [p / f"{n}.json" for n in ("facts", "reqs", "steps") if (p / f"{n}.json").is_file()] if p.is_dir() else [p]
    if not files:
        print("검사할 계약이 없다 — facts.json · reqs.json · steps.json")
        return 1
    T = Task(a.task) if a.task else None
    docs, reps = {}, {}
    for f in files:
        R = Report(f.name)
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as ex:
            reps[f.stem] = R
            R.e(f.name, f"json 을 읽지 못했다 — {ex}")
            continue
        # 종류 = 안의 «contract» 칸(없으면 파일 이름) — 분석 틀 시험 출력처럼 이름이 달라도 검사한다
        kind = d.get("contract") if isinstance(d, dict) and d.get("contract") in ("facts", "reqs", "steps") else f.stem
        reps[kind] = R
        docs[kind] = d
        if a.add_ids and kind in ("facts", "reqs", "steps"):
            n = add_ids(d, kind)
            if n:
                f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"id 채움 {f.name}: {n}개")
        if kind in ("facts", "reqs", "steps"):
            check_ids(d, kind, R)
        {"facts": check_facts, "reqs": check_reqs, "steps": check_steps}.get(kind, lambda *_: R.e(f.name, "«contract» 가 facts · reqs · steps 중 하나여야 한다"))(d, R, T)
    # 글 안 숫자 자리 {F['이름']} — 숫자 이름이 계약에 있나
    nums = {}
    for k in ("facts", "steps"):
        for n in (docs.get(k, {}).get("numbers") or {}):
            if n in nums:
                reps[k].w("numbers", f"«{n}» 이 facts · steps 두 곳에 있다 — steps 값이 이긴다")
            nums[n] = k
    have_both = "facts" in docs and "steps" in docs
    for k, d in docs.items():
        miss = sorted({m for s in strings(d) for m in PH.findall(s)} - set(nums))
        if miss:
            (reps[k].e if have_both else reps[k].w)(k, f"글 안 {{F['…']}} 의 숫자 이름이 numbers 에 없다: {miss[:6]}")
    if a.render and docs:
        n = render(docs, reps)
        print(f"그려 본 그림 · 단계 {n}개")
    bad = 0
    for k, R in reps.items():
        cnt = " · ".join(f"{a_} {b}" for a_, b in R.counts.items())
        if R.err:
            bad += 1
            print(f"FAIL {R.name}" + (f"  ({cnt})" if cnt else ""))
            for e in R.err[:40]:
                print(f"  문제: {e}")
            if len(R.err) > 40:
                print(f"  … 문제 {len(R.err) - 40}개 더")
        else:
            print(f"PASS {R.name}  ({cnt})")
        for w in R.warn[:40]:
            print(f"  경고: {w}")
        if len(R.warn) > 40:
            print(f"  … 경고 {len(R.warn) - 40}개 더")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
