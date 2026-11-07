# -*- coding: utf-8 -*-
"""분석 틀 공용 — 과제 폴더 찾기 · 거리 · 재생기 칸 만들기(채우기 · 고치기 · 이어 붙이기) · 전부 세기 실측 · 그림 칸 · steps.json 쓰기

- 과제와 무관하다. 유형별 틀(route_bundle · dispatch_sim · schedule_assign · coverage_place · stat_model)이 불러 쓴다
- 표준 라이브러리만 쓴다(대회 리눅스에서 바로 돈다). 계산이 무거우면 이 틀을 복사한 그 책의 work/ 에서 pandas 등을 더 쓴다
- 만든 칸 모양은 양식 kit.stepper_* · figs.* 의 칸과 같다(json 으로 — 짝 = 목록 · 함수 = 표). 형식: bookkit/contracts/README.md
"""
import itertools
import json
import math
import os
import re
import time
from pathlib import Path

# bookkit 폴더
KIT = Path(__file__).resolve().parent.parent
# 차 색 — 양식 figs.COLORS 와 같다(차 하나 = 색 하나)
COLORS = ["#2563eb", "#dc2626", "#16a34a", "#7c3aed", "#b45309", "#0f766e", "#db2777", "#4b5563", "#0891b2", "#65a30d", "#ea580c"]


# ════════════════════════════════════════════════════════════
# 과제 폴더 · 쓰기
# ════════════════════════════════════════════════════════════
def task_dir(book=None, given=None):
    """과제 폴더 — given → 책 content/data.py 의 TASK_DIR → 환경변수 BOOK_TASK_DIR → 책 폴더에서 위로 README.md + uploads/ 가 함께 있는 곳"""
    if given:
        return Path(given)
    if book:
        m = re.search(r"^TASK_DIR = (.+)$", (Path(book) / "content" / "data.py").read_text(encoding="utf-8"), re.M)
        if m and m.group(1).strip() != "None":
            return Path(eval(m.group(1)))  # noqa: S307 — new_book.py 가 repr 로 쓴 경로 글자
    if os.environ.get("BOOK_TASK_DIR"):
        return Path(os.environ["BOOK_TASK_DIR"])
    for p in Path(book or ".").resolve().parents:
        if (p / "README.md").is_file() and (p / "uploads").is_dir():
            return p
    raise FileNotFoundError("과제 폴더를 못 찾았다 — --task <폴더> 로 준다")


def plain(v):
    """json 으로 쓸 값 — 짝 → 목록 · 모음 → 정렬 목록"""
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted(plain(x) for x in v)
    return v


def write_steps(path, doc):
    """steps.json 쓰기(utf-8 · 들여쓰기 1) → 경로"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # 조건 항목 id(C1 · C2 …) — 계약 검사가 빠짐을 FAIL 로 본다(있는 id 는 그대로)
    doc = dict(doc, conditions=[c if c.get("id") else {"id": f"C{i + 1}", **c} for i, c in enumerate(doc.get("conditions") or [])])
    p.write_text(json.dumps(plain(doc), ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def hm(m):
    """분 → «07:30»"""
    return f"{int(m) // 60 % 24:02d}:{int(m) % 60:02d}"


# ════════════════════════════════════════════════════════════
# 거리
# ════════════════════════════════════════════════════════════
def dist(a, b, geo):
    """두 점 사이 거리 — geo=True 면 (위도, 경도) km, 아니면 (y, x) 평면 거리"""
    if not geo:
        return math.hypot(a[0] - b[0], a[1] - b[1])
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def route_len(names, pts, end, geo):
    """들르는 순서대로 돌고 end(공동 목적지 · 없으면 None)까지 간 길이"""
    seq = [pts[n] for n in names] + ([end] if end is not None else [])
    return sum(dist(seq[i], seq[i + 1], geo) for i in range(len(seq) - 1))


def route_key(names):
    """경로 길이 표의 열쇠 — 양식 contract.route_key 와 같다"""
    return "→".join(str(n) for n in names)


# ════════════════════════════════════════════════════════════
# 지도 칸
# ════════════════════════════════════════════════════════════
def map_spec(pts, weights, short, end, end_label, geo, below=()):
    """figs.route_map 의 지도 칸 — 그리는 점(weights 에 든 곳)과 목적지로 범위를 정한다
    점 전체로 정하면 다른 사업장 · 쓰지 않는 곳까지 들어가 그리는 점이 지도 한쪽에 몰린다(이름표가 겹친다)"""
    used = [pts[n] for n in weights if n in pts] or list(pts.values())
    fit = used + ([end] if end is not None else [])
    pad = (0.012, 0.012, 0.025, 0.03) if geo else _pad(fit)
    return {"points": pts, "weights": weights, "short": short, "below": list(below), "target": end, "target_label": end_label,
            "geo": geo, "fit_points": fit, "pad": pad}


def _pad(fit):
    """평면 좌표 여백 — 범위의 8%"""
    ys, xs = [p[0] for p in fit], [p[1] for p in fit]
    dy, dx = (max(ys) - min(ys)) or 1, (max(xs) - min(xs)) or 1
    return (dy * 0.08, dy * 0.08, dx * 0.08, dx * 0.12)


def steps_count(state):
    """state 안의 [곳, 수] 전부"""
    return [x for r in state for x in r]


def _stop_word(state, words):
    """수가 전부 1 이면(일 한 건 = 한 곳) 오른쪽 목록에 수를 붙이지 않는다 — «S1» (아니면 «S12» 처럼 이름 + 수)"""
    if steps_count(state) and all(c == 1 for _, c in steps_count(state)):
        words = dict(words, stop="{short}")
    return words


# ════════════════════════════════════════════════════════════
# 재생기 1 — 채우기
# ════════════════════════════════════════════════════════════
def fill_player(steps, n_veh, M, cap, unit, veh, measure, title, task, frame_title):
    """steps = [(차 번호, 곳, 수)] 담는 순서 → kit.stepper_fill 칸
    단계 글 = 동작 + 결과 숫자 · 차가 다 차면 «완성 — 길이» · 표 = 차마다 한 줄(담은 곳 · 길이)"""
    state = [[] for _ in range(n_veh)]
    last = {b: i for i, (b, _, _) in enumerate(steps)}
    out = []
    for i, (b, place, n) in enumerate(steps):
        state[b].append([place, n])
        load = sum(c for _, c in state[b])
        txt = (f"**{M['short'].get(place, place)}** {n}{unit}을 {veh} {b + 1} 에 담는다 — 이 {veh} "
               + (f"{load}/{cap}{unit}." if cap else f"{load}{unit}."))
        if last[b] == i:
            txt += f" 완성 — 길이 {measure([p for p, _ in state[b]]):.1f}."
        out.append({"state": [list(map(list, s)) for s in state], "cur": b, "text": txt, "row": b})
    rows = []
    for b in range(n_veh):
        names = [p for p, _ in state[b]]
        ones = all(c == 1 for _, c in steps_count(state))
        rows.append([f"{veh} {b + 1}", "→".join(M["short"].get(p, p) + ("" if ones else str(c)) for p, c in state[b]) or "—",
                     f"{sum(c for _, c in state[b])}", f"{measure(names):.1f}" if names else "0"])
    return {"title": title, "task": task, "caption": f"한 단계 = 한 곳을 {veh} 하나에 담기. 표는 {veh}마다 담은 곳과 길이", "auto_ms": 1100,
            "map": M, "frame_title": frame_title, "right_title": f"{veh}별 채움",
            "words": _stop_word(state, {"line": "{mark}" + veh + (" {k}  {fill}/{cap}\n{stops}" if cap else " {k}  {fill}" + unit + "\n{stops}"), "empty": veh + " {k}  —\n"}),
            "cap": cap or "", "steps": out,
            "table": {"header": [veh, "담는 곳(수)", f"합계({unit})", "길이"], "rows": rows[:8], "small": True}}, state


# ════════════════════════════════════════════════════════════
# 재생기 2 — 한 곳씩 고치기(국소 탐색)
# ════════════════════════════════════════════════════════════
def local_search(state, cost, cap, max_steps=7, min_gain=1e-6):
    """state = [[[곳, 수] …] 차마다] 에서 한 번에 하나씩 바꿔 총비용이 가장 많이 주는 것을 받아들인다(줄지 않으면 멈춘다)
    바꾸기 = 순서 바꾸기(차 안 두 곳 맞바꾸기) · 옮기기(곳 하나를 다른 차 끝으로 · 정원 안) · 맞바꾸기(두 차의 곳 하나씩)
    cost(곳 이름 목록) → 한 차의 비용 → [(종류, 설명 dict, 새 state, 총비용, 바뀐 차 목록, 빠진 [(차, 곳)])] (첫 줄 = 출발점)"""
    def total(st):
        return sum(cost([p for p, _ in r]) for r in st if r)

    cur = [list(map(list, r)) for r in state]
    rec = [("start", {}, [list(map(list, r)) for r in cur], total(cur), [], [])]
    for _ in range(max_steps):
        base = total(cur)
        best = None
        for b, r in enumerate(cur):
            for i, j in itertools.combinations(range(len(r)), 2):
                nr = list(r)
                nr[i], nr[j] = nr[j], nr[i]
                g = base - (total(cur) - cost([p for p, _ in r]) + cost([p for p, _ in nr]))
                if g > min_gain and (best is None or g > best[0]):
                    best = (g, "reorder", {"bus": b, "old": [p for p, _ in r], "new": [p for p, _ in nr]}, {b: nr}, [])
        for a, b in itertools.permutations(range(len(cur)), 2):
            for i, item in enumerate(cur[a]):
                if sum(c for _, c in cur[b]) + item[1] <= cap:
                    na, nb = cur[a][:i] + cur[a][i + 1:], cur[b] + [item]
                    g = base - (total(cur) - cost([p for p, _ in cur[a]]) - cost([p for p, _ in cur[b]]) + cost([p for p, _ in na]) + cost([p for p, _ in nb]))
                    if g > min_gain and (best is None or g > best[0]):
                        best = (g, "move", {"i": a, "j": b, "h": item[0], "k": item[1]}, {a: na, b: nb}, [(a, item[0])])
        for a, b in itertools.combinations(range(len(cur)), 2):
            for i, x in enumerate(cur[a]):
                for j, y in enumerate(cur[b]):
                    la = sum(c for _, c in cur[a]) - x[1] + y[1]
                    lb = sum(c for _, c in cur[b]) - y[1] + x[1]
                    if la <= cap and lb <= cap:
                        na, nb = list(cur[a]), list(cur[b])
                        na[i], nb[j] = y, x
                        g = base - (total(cur) - cost([p for p, _ in cur[a]]) - cost([p for p, _ in cur[b]]) + cost([p for p, _ in na]) + cost([p for p, _ in nb]))
                        if g > min_gain and (best is None or g > best[0]):
                            best = (g, "swap", {"i": a, "j": b, "h": x[0], "k": x[1], "h2": y[0], "k2": y[1]}, {a: na, b: nb}, [(a, x[0]), (b, y[0])])
        if best is None:
            break
        _, kind, info, change, gone = best
        for b, r in change.items():
            cur[b] = r
        gone = [(b, p) for b, p in gone if p not in [q for q, _ in cur[b]]]
        rec.append((kind, info, [list(map(list, r)) for r in cur], total(cur), sorted(change), gone))
    return rec


def fix_player(rec, M, cost, veh, unit, title, task):
    """local_search 기록 → kit.stepper_fix 칸(경로 길이 표 measure 포함)"""
    sh = M["short"]
    steps, rows, lens = [], [], {}
    prev = None
    for no, (kind, info, st, tot, changed, gone) in enumerate(rec):
        for r in st:
            if r:
                lens[route_key(p for p, _ in r)] = cost([p for p, _ in r])
        if kind == "start":
            txt = f"**출발점 — 채우기 결과.** 총 **{tot:.1f}**. 한 번에 하나만 바꿔 보고 총합이 줄면 받아들인다."
            row, head = ["출발", "채우기 결과 그대로", f"{tot:.1f}"], f"출발점 — 총 {tot:.1f}"
        else:
            d = f"총 **{prev:.1f} → {tot:.1f}**"
            if kind == "reorder":
                act = f"{veh} {info['bus'] + 1} 의 순서를 {'→'.join(sh.get(h, h) for h in info['old'])} 에서 {'→'.join(sh.get(h, h) for h in info['new'])} 로 바꾼다"
                row = [str(no), f"순서 바꾸기 · {veh}{info['bus'] + 1}", f"{tot:.1f}"]
            elif kind == "move":
                act = f"{veh} {info['i'] + 1} 의 {sh.get(info['h'], info['h'])} {info['k']}{unit}을 {veh} {info['j'] + 1} 로 옮긴다"
                row = [str(no), f"옮기기 · {veh}{info['i'] + 1} {sh.get(info['h'], info['h'])} → {veh}{info['j'] + 1}", f"{tot:.1f}"]
            else:
                act = (f"{veh} {info['i'] + 1} 의 {sh.get(info['h'], info['h'])} 와 {veh} {info['j'] + 1} 의 {sh.get(info['h2'], info['h2'])} 를 맞바꾼다")
                row = [str(no), f"맞바꾸기 · {sh.get(info['h'], info['h'])} ↔ {sh.get(info['h2'], info['h2'])}", f"{tot:.1f}"]
            name = {"reorder": "순서 바꾸기", "move": "옮기기", "swap": "맞바꾸기"}[kind]
            txt = f"**고치기 {no} — {name}.** {act}. {d}."
            if no == len(rec) - 1:
                txt += " 더 바꿔 봐도 줄지 않아 **여기서 멈춘다.**" if len(rec) < 8 else " (단계 수 상한에서 멈춘다)"
            head = f"고치기 {no} — 총 {prev:.1f} → {tot:.1f}"
        steps.append({"state": st, "hl": list(changed), "gone": [list(g) for g in gone], "head": head, "text": txt, "row": no})
        rows.append(row)
        prev = tot
    return {"title": title, "task": task, "caption": f"빨간 × = 이번 고치기로 그 {veh}가 더는 들르지 않는 곳. 굵은 선 = 이번에 바뀐 {veh}", "auto_ms": 1300,
            "map": M, "right_title": f"{veh}별 경로", "words": _stop_word(rec[0][2], {"line": "{mark}" + veh + " {k}  {fill}" + unit + " · {km:.1f}\n{stops}", "empty": veh + " {k}  —\n"}),
            "measure": lens, "steps": steps, "table": {"header": ["#", "고친 것", "총합"], "rows": rows, "small": True}}


# ════════════════════════════════════════════════════════════
# 재생기 3 — 이어 붙이기(일을 시작 시각 순서로 차에)
# ════════════════════════════════════════════════════════════
def chain(trips, deadhead):
    """trips = [{"start", "end", "frm", "to"}] → 시작 시각 순서로 차에 붙인다
    규칙: 앞 일을 끝낸 곳에서 이번 일 출발지까지 시간 안에 닿는 차 가운데 가장 일찍 닿는 차 · 없으면 새 차
    → [{"trip", "bus", "new", "cands": [{"bus", "at", "free", "dh", "arr", "ok"}]}]"""
    order = sorted(range(len(trips)), key=lambda i: (trips[i]["start"], i))
    buses = []  # 차마다 (비는 시각, 있는 곳)
    out = []
    for i in order:
        t = trips[i]
        cands = []
        for b, (free, at) in enumerate(buses):
            dh = deadhead[at][t["frm"]]
            cands.append({"bus": b, "at": at, "free": free, "dh": dh, "arr": free + dh, "ok": free + dh <= t["start"] + 1e-9})
        ok = [c for c in cands if c["ok"]]
        if ok:
            b = min(ok, key=lambda c: (c["arr"], c["bus"]))["bus"]
            new = False
        else:
            b, new = len(buses), True
            buses.append(None)
        buses[b] = (t["end"], t["to"])
        out.append({"trip": i, "bus": b, "new": new, "cands": cands})
    return out


def chain_player(trips, deadhead, names, have, veh, job, title, task, rows=None):
    """trips(+ "color") · deadhead {a: {b: 분}} · names {곳: 보일 이름} → kit.stepper_chain 칸. have = 보유 대수"""
    rec = chain(trips, deadhead)
    nm = lambda p: names.get(p, p)  # noqa: E731
    texts, heads = [], []
    for k, st in enumerate(rec):
        t = trips[st["trip"]]
        head = f"**{hm(t['start'])} {nm(t['frm'])} 출발** {job}"
        if st["new"]:
            if st["cands"]:
                best = min(st["cands"], key=lambda c: c["arr"])
                why = f"가장 빨리 닿는 {veh} {best['bus'] + 1} 도 **{hm(best['arr'])}** 에야 닿는다"
            else:
                why = f"아직 쓴 {veh}가 없다"
            txt = f"{head} — {why}. → **{veh} {st['bus'] + 1}** 새로 투입."
            if st["bus"] >= have:
                txt += f" !!보유 {have}대를 넘는다.!!"
        else:
            c = next(x for x in st["cands"] if x["bus"] == st["bus"])
            n_ok = sum(1 for x in st["cands"] if x["ok"])
            txt = (f"{head}. {veh} {st['bus'] + 1} — {hm(c['free'])} 부터 {nm(c['at'])}에 있고 {c['dh']:.0f}분이면 닿는다"
                   + (f"(닿는 {veh} {n_ok}대 중 가장 이르다)" if n_ok > 1 else "") + f". → **{veh} {st['bus'] + 1}** 에 이어 붙인다.")
        texts.append(txt)
        heads.append(f"일 {k + 1} / {len(rec)} — 시작 시각 순서")
    nb = 1 + max(s["bus"] for s in rec)
    texts.append(f"**{veh} {nb}대.** 일 {len(rec)}개를 시작 시각 순서로 붙인 결과다(보유 {have}대).")
    heads.append(f"다 붙인 결과 — {veh} {nb}대(보유 {have}대)")
    steps = [{"trip": s["trip"], "bus": s["bus"]} for s in rec]
    return timetable_player(trips, steps, heads, texts, deadhead, names, have, veh, job, title, task, rows), nb


def timetable_player(trips, steps, heads, texts, deadhead, names, have, veh, job, title, task, rows=None):
    """일 · 배정 단계 · 단계 글을 이미 만든 경우(배차 시뮬레이션 등) → kit.stepper_chain 칸
    steps = [{"trip", "bus"}] 붙인 순서 · heads · texts = 단계 수 + 1(마지막 = 정리)"""
    nm = lambda p: names.get(p, p)  # noqa: E731
    nb = 1 + max(s["bus"] for s in steps)
    t0 = min(t["start"] for t in trips)
    t1 = max(t["end"] for t in trips)
    span = t1 - t0
    step = 10 if span <= 90 else 30 if span <= 240 else 60 if span <= 480 else 120
    a0, a1 = int(t0 // step) * step, int(-(-t1 // step)) * step
    places = sorted({t["frm"] for t in trips} | {t["to"] for t in trips})
    T = {"trips": [{k: t[k] for k in ("start", "end", "frm", "to")} | {"color": t.get("color", "#2563eb")} for t in trips],
         "steps": steps, "have": have, "axis": [a0, a1],
         "ticks": list(range(a0 + step, a1, step)) or [a0], "rows": rows or max(10, min(16, nb)),
         "legend": [[job, "#2563eb", False], ["빈 차 이동", "#9aa3ad", True]],
         "deadhead": {a: {b: deadhead[a][b] for b in places} for a in places}, "place": {p: nm(p) for p in places},
         "words": {"unit": veh + " {k}", "have": "▲ 보유 {n}대", "where": "{t} 에 " + veh + "가 있는 곳", "end": "다 붙였을 때",
                   "done": "{place} {t} 도착 · 일 {n}개", "take": "▶ {place} {t} 출발을 맡음", "run": "달리는 중 → {t} {place}",
                   "idle": "{place} 에 있음({t}~)"}}
    return {"title": title, "task": task, "caption": f"막대 한 줄 = {veh} 한 대, 막대 하나 = {job} 하나 · 점선 = 빈 차 이동", "auto_ms": 1300,
            "timetable": T, "heads": heads, "texts": texts}


# ════════════════════════════════════════════════════════════
# 전부 세기 실측 · 순서 표 · 그림 칸
# ════════════════════════════════════════════════════════════
def sec_text(x):
    """초 → 시간 글(양식 kit.sec_text 와 같다)"""
    if x < 1:
        return f"{x:.2f}초"
    if x < 90:
        return f"{x:.1f}초" if x < 10 else f"{x:.0f}초"
    if x < 7200:
        return f"약 {x / 60:.0f}분"
    if x < 172800:
        return f"약 {x / 3600:.0f}시간"
    return f"약 {x / 86400:.0f}일"


def brute_table(names, measure, sizes=(5, 6, 7, 8), est=(10, 12, 15), unit="곳"):
    """곳 n 개의 순서를 전부 세어 가장 짧은 것을 찾는 시간 — 작은 크기는 실제로 재고(time.perf_counter), 큰 크기는 가짓수 비율로 추정
    → (표 칸, 실측 {n: 초})"""
    sec = {}
    for n in sizes:
        if n > len(names):
            break
        sub = names[:n]
        t = time.perf_counter()
        min(itertools.permutations(sub), key=lambda o: measure(list(o)))
        sec[n] = time.perf_counter() - t
    nmax = max(sec)
    rows = [[f"{n}{unit}", f"{math.factorial(n):,}", sec_text(s), "실측"] for n, s in sec.items()]
    rows += [[f"{n}{unit}", f"{math.factorial(n):,}", sec_text(sec[nmax] * math.factorial(n) / math.factorial(nmax)), f"추정({nmax}{unit}의 시간 × 가짓수 비율)"]
             for n in est if n > nmax]
    bad = [[i, "전부 세는 데 걸린 시간"] for i, r in enumerate(rows) if r[3] != "실측"]
    return ({"header": [f"{unit} 수", "도는 순서 가짓수", "전부 세는 데 걸린 시간", "구분"], "rows": rows, "small": True, "bad_cells": bad,
             "caption": f"{unit} 수에 따라 «전부 세기» 가 걸리는 시간"}, sec)


def orders_example(three, pts, end, end_label, short, geo):
    """곳 셋을 도는 순서 6가지 → (순서 표 칸, 순서 지도 칸, 행 [(순서, 길이)])"""
    rows = [(list(o), route_len(list(o), pts, end, geo)) for o in itertools.permutations(three)]
    best = min(rows, key=lambda r: r[1])
    worst = max(rows, key=lambda r: r[1])
    trs = [["→".join(short.get(h, h) for h in o) + (f" → {end_label}" if end is not None else ""), f"{km:.1f}"] for o, km in rows]
    gi, bi = rows.index(best), rows.index(worst)
    table = {"header": ["도는 순서", "길이"], "rows": trs, "good_rows": [gi], "bad_rows": [bi],
             "notes": {gi: ["← 가장 짧다", "good"], bi: ["← 가장 길다", "bad"]}, "small": True}
    fig = {"points": {n: pts[n] for n in three}, "short": short, "target": end if end is not None else pts[three[-1]], "target_label": end_label,
           "best": [best[0], f"가장 짧다 {best[1]:.1f}"], "worst": [worst[0], f"가장 길다 {worst[1]:.1f}"], "geo": geo, "label": "곳 세 곳의 순서"}
    return table, fig, rows


def busy_bars(intervals, t0, t1, step, limit, limit_label, title, unit=""):
    """구간 [(시작, 끝)] → 시각마다 동시에 진행 중인 수 막대 + 한도선(figs.time_bars 칸)"""
    bars = []
    for m in range(int(t0), int(t1), int(step)):
        bars.append({"label": hm(m), "value": sum(1 for a, b in intervals if a <= m < b)})
    return {"title": title, "bars": bars, "limit": limit, "limit_label": limit_label, "unit": unit, "label": title}


def conditions_table(conds, header, cols, limit_col=None, limit=None, caption=""):
    """조건별 결과 [{"name", "value", "result": {열: 값}}] → 조건별 표 칸(한도를 넘는 칸 빨강)"""
    rows = [[c["value"]] + [c["result"][k] for k in cols] for c in conds]
    bad = [[i, limit_col] for i, c in enumerate(conds) if limit_col and limit is not None and c["result"][cols[header.index(limit_col) - 1]] > limit]
    return {"header": header, "rows": rows, "bad_cells": bad, "small": True, "caption": caption}


# ════════════════════════════════════════════════════════════
# 그림 칸 — 큰 흐름(A3) · 전부 아니면 전무 실험(A1)
# ════════════════════════════════════════════════════════════
# 큰 흐름 위 상자 글 기본값 — 과제 글로 바꾼다(줄바꿈 \n · 상자마다 3줄 · 줄마다 12자 안팎)
FLOW = {"input": "입력 파일\n(과제 uploads)", "check": "검증 · 적용\n전부 아니면 전무", "plan": "계획 계산", "out1": "운영자 화면", "out2": "개인 화면"}


def overview_fig(columns, title, legend, flow=None, note="", label="하루의 묶음"):
    """figs.overview 칸 — columns = [{"label": 시각 글, "sub": 아래 글(5자 안팎), "values": [수 …]}] (4~12개) · legend = [[이름, 색]]"""
    cols = [{"label": c["label"], "sub": c.get("sub", ""), "sub_tone": c.get("sub_tone", "#2563eb"), "note": c.get("note", ""), "values": c["values"]}
            for c in columns]
    vmax = max((v for c in cols for v in c["values"]), default=1) or 1
    return {"flow": dict(FLOW, **(flow or {})), "bars": {"title": title, "legend": legend, "columns": cols, "k": 150 / vmax,
                                                          "colors": [x[1] for x in legend] or ["#2563eb"]}, "note": note, "label": label}


def txn_fig(tables, fail):
    """전부 아니면 전무 실험(figs.txn 칸) — 메모리 DB(sqlite3)에 표를 차례로 넣다 fail 번째(0부터)에서 실패시킨다
    tables = {파일 이름: 행 수} (넣는 순서) → 트랜잭션 없이 / 있게 두 번 실제로 넣어 남은 행 수를 센다"""
    import sqlite3
    names = list(tables)
    rows = {}
    for mode in ("none", "txn"):
        db = sqlite3.connect(":memory:", isolation_level=None)
        for n in names:
            db.execute(f'CREATE TABLE "{n}" (v INTEGER)')
        if mode == "txn":
            db.execute("BEGIN")
        try:
            for i, n in enumerate(names):
                if i == fail:
                    raise ValueError("검증 실패")
                db.executemany(f'INSERT INTO "{n}" VALUES (?)', ((k,) for k in range(tables[n])))
            if mode == "txn":
                db.execute("COMMIT")
        except ValueError:
            if mode == "txn":
                db.execute("ROLLBACK")
        rows[mode] = {n: db.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
        db.close()
    return {"names": names, "fail": fail, "rows": rows,
            "labels": {"none": ["트랜잭션 없음", f"앞 {fail}개만 들어간 채 멈춘다 — 반쯤 적용"], "txn": ["트랜잭션 있음", "실패하면 전부 취소 — 적용 전 상태 그대로"]},
            "order": "넣는 순서 →", "fail_text": "✗ 검증 실패", "unit": "행", "label": "트랜잭션 실험"}
