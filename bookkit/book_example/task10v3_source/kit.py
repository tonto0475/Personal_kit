# -*- coding: utf-8 -*-
"""개편판 공용 조각 — 분류 색 표시 · ◎ 항목 · 단계 재생기 셋(방안 A 채우기 · 한 곳씩 고치기 · 트립 이어 붙이기)
장 파일(pv · s1 …)끼리는 서로 부르지 않는다. 같은 블록을 «한눈에» 와 본문에 함께 넣으려고 여기에 둔다(블록 id 만 다르게)"""
from book.engine import esc

from . import data as D
from . import figs

# ── 분류 — 화면 · 시스템 · 알고리즘 · 파이프라인 · 문서 ─────────────────
CATS = {"화면": "ui", "시스템": "sys", "알고리즘": "alg", "파이프라인": "pipe", "문서": "doc"}
CAT_DESC = {"화면": "운영자 · 사원이 보고 누르는 것",
            "시스템": "저장 · 계산 작업 · 한 번에 적용 · 컨테이너 · 테스트",
            "알고리즘": "노선 · 버스 배정 · 필요 대수를 정하는 핵심 계산",
            "파이프라인": "CSV 를 읽어 검사하고 정리 · 예외 처리하는 일(핵심 계산의 앞 단계)",
            "문서": "HOW_TO_RUN · AI_COLLABORATION 등 제출 글"}

STYLE = """<style>
.cat{display:inline-block;font-size:.74em;font-weight:700;padding:0 .42em;border-radius:4px;border:1px solid;white-space:nowrap;line-height:1.55;vertical-align:.06em;margin-left:.25em}
.cat-ui{color:#15803d;background:#e9f7ee;border-color:#9ad4ae}
.cat-sys{color:#6d28d9;background:#f5f0ff;border-color:#c9b5f5}
.cat-alg{color:#1d4ed8;background:#eaf1ff;border-color:#a9c1f5}
.cat-pipe{color:#b45309;background:#fff7e6;border-color:#f0c98a}
.cat-doc{color:#0f766e;background:#eaf7f4;border-color:#9fd6cb}
td .cat{margin-left:0}
.qi{margin:.5em 0 .65em;padding:.45em .85em .55em;border:1px solid #d6dbe3;border-left:4px solid #94a3b8;border-radius:6px;background:#fff}
.qi.alg{border-left-color:#2563eb}.qi.ui{border-left-color:#16a34a}.qi.sys{border-left-color:#7c3aed}.qi.pipe{border-left-color:#b45309}.qi.doc{border-left-color:#0f766e}
.qi .qh{margin:0 0 .2em;font-weight:700;line-height:1.5}
.qi .qm{color:#2563eb;margin-right:.3em}
.qi dl{margin:0;display:grid;grid-template-columns:max-content 1fr;column-gap:.7em;row-gap:.12em;font-size:.92em;line-height:1.58}
.qi dt{font-weight:700;color:#4b5563;white-space:nowrap}
.qi dd{margin:0}
.mono{font-family:Consolas,"D2Coding","Noto Sans Mono",monospace;font-size:.88em;background:#f4f6f9;border:1px solid #e3e6eb;border-radius:4px;padding:0 .3em;white-space:pre-wrap;overflow-wrap:anywhere}
.mono.bad{background:#fdecec;border-color:#f5b5b5;color:#991b1b}
.mono.good{background:#e9f7ee;border-color:#a7dcb8;color:#15803d}
table.apxdef{table-layout:fixed;width:100%}
table.apxdef th:nth-child(1){width:30px}
table.apxdef th:nth-child(2){width:49%}
table.apxdef th:nth-child(3){width:29%}
.legend{font-size:.9em;line-height:1.7;margin:.3em 0 .6em}
.legend .cat{margin:0 .3em 0 0}
.legend span.ld{color:#4b5563;margin-right:.9em}
</style>"""


def chip(cat):
    return f'<span class="cat cat-{CATS[cat]}">{esc(cat)}</span>'


def mono(text, tone=""):
    """원본 데이터 조각 — 글자 그대로(빈 칸 · 공백이 보이게)"""
    return f'<span class="mono{(" " + tone) if tone else ""}">{esc(text)}</span>'


def legend_html():
    return '<p class="legend">' + "".join(f'{chip(c)}<span class="ld">{esc(d)}</span>' for c, d in CAT_DESC.items()) + "</p>"


def qitem(w, title, cat, fields, fn=None, id=None, raw=()):
    """◎ 항목 — title · cat(분류 하나 또는 목록) · fields = [(이름, 꾸밈 글)]. raw = 꾸밈 글 대신 HTML 을 그대로 넣을 이름들"""
    cats = cat if isinstance(cat, (list, tuple)) else [cat]
    head = f'<p class="qh"><span class="qm">◎</span>{w.t(title)}{"".join(chip(c) for c in cats)}</p>'
    dl = "".join(f"<dt>{esc(k)}</dt><dd>{v if k in raw else w.t(v)}</dd>" for k, v in fields)
    h = f'<div class="qi {CATS[cats[0]]}">{head}<dl>{dl}</dl></div>'
    return w.html(h, fn=fn, id=id)


# ════════════════════════════════════════════════════════════
# 단계 재생기 1 — 방안 A(거리순)가 사람을 버스에 채우는 과정
# ════════════════════════════════════════════════════════════
def _stops_txt(stops):
    return "→".join(f"{D.short(n)}{c}" for n, c in stops)


def stepper_A(w, id, task, title=None, note=True):
    F = D.facts()
    steps = F["A1_steps"]
    nb = len(F["A1_buses"])
    det = [D.detour(b) for b in F["A1_bus_stops"]]
    last_of_bus = {}
    for i, st in enumerate(steps):
        last_of_bus[st["bus"]] = i
    out = []
    for i, st in enumerate(steps):
        state = [[] for _ in range(nb)]
        for s2 in steps[:i + 1]:
            state[s2["bus"]].append((s2["hub"], s2["n"]))
        lines = []
        for b in range(nb):
            if state[b]:
                fill = sum(c for _, c in state[b])
                lines.append((f"{'▶ ' if b == st['bus'] else ''}버스 {b + 1}  {fill}/{D.CAP}\n{_stops_txt(state[b])}", figs.BUS_COLORS[b]))
            else:
                lines.append((f"버스 {b + 1}  —\n", "#9aa3ad"))
        svg = figs.map_svg(F, state, "거리순으로 채우는 중 — 사업장에서 먼 거점부터", "버스별 채움", lines, cur=st["bus"])
        txt = f"**{D.short(st['hub'])}** {st['n']}명을 버스 {st['bus'] + 1} 에 담는다 — 이 버스 {st['cum']}/{D.CAP}명."
        b = st["bus"]
        if last_of_bus[b] == i:
            txt += f" 완성 — {F['A1_bus_km'][b]}km · {F['A1_bus_min'][b]}분."
            worst = max(det[b], key=lambda x: x[4])
            if worst[4] > 1.5:
                names = [n for n, _ in F["A1_bus_stops"][b]]
                txt += (f" {D.short(worst[0])} 사원은 직통이면 {worst[3]:.0f}km 인데 이 버스로 {worst[2]:.0f}km — !!직통의 {worst[4]:.1f}배!!.")
                if len(names) >= 3:
                    ll = D.hub_ll()
                    dirs = " → ".join([D.short(names[0])] + [f"{D.short(names[i])}({D.direction(ll[names[i]], ll[names[i - 1]])}으로)"
                                                             for i in range(1, len(names))])
                    txt += f" {dirs} 꺾이는 **지그재그**다."
        out.append({"svg": svg, "text": txt, "row": b})
    rows, bad = [], []
    for b in range(nb):
        r = max(x[4] for x in det[b])
        rows.append([f"버스 {b + 1}", _stops_txt(F["A1_bus_stops"][b]), f"{F['A1_bus_km'][b]}", f"{F['A1_bus_min'][b]}", f"{r:.2f}배"])
        if r > 1.5:
            bad.append((b, "우회 배율"))
    return w.stepper(out, title=title or f"거리순이 {F['wave_n']}명을 버스에 채우는 과정",
                     table={"header": ["버스", "담는 거점(인원)", "경로 km", "최장 승차(분)", "우회 배율"], "rows": rows, "small": True,
                            "bad_cells": bad},
                     task=task, auto_ms=1100, id=id,
                     caption="우회 배율 = 그 버스에서 가장 많이 돌아가는 사원의 «탄 거리 ÷ 그 거점에서 사업장까지 직통 거리». 1.5배를 넘는 칸은 빨강",
                     fn={"우회 배율": "(detour ratio) 버스가 여러 거점을 들르느라 직통보다 얼마나 더 달리는지. 2.0배면 직통의 두 배 거리를 탄다"} if note else None)


# ════════════════════════════════════════════════════════════
# 단계 재생기 2 — 한 곳씩 고치기(국소 탐색): 방안 A 계획을 출발점으로
# ════════════════════════════════════════════════════════════
def _ls_lines(state, hl):
    out = []
    for b, stops in enumerate(state):
        if not stops:
            out.append((f"버스 {b + 1}  —\n", "#9aa3ad"))
            continue
        n = sum(c for _, c in stops)
        km = D.route_km([h for h, _ in stops])
        out.append((f"{'▶ ' if b in hl else ''}버스 {b + 1}  {n}명 · {km:.0f}km\n{_stops_txt(stops)}", figs.BUS_COLORS[b]))
    return out


def ls_text(s, prev_km, no):
    """고치기 한 단계의 설명(꾸밈 글)과 표 한 줄"""
    info, k = s["info"], s["km"]
    d = f"총 **{prev_km:.0f} → {k:.0f}km** (−{round(prev_km) - round(k)})"
    if s["kind"] == "reorder":
        b = info["bus"] + 1
        txt = (f"**고치기 {no} — 순서 바꾸기.** 버스 {b} 의 들르는 순서를 {'→'.join(D.short(h) for h in info['old'])} 에서 "
               f"{'→'.join(D.short(h) for h in info['new'])} 순서로 바꾼다(사람은 그대로). {d}.")
        row = f"순서 바꾸기 · 버스{b}"
    else:
        i, j = info["i"] + 1, info["j"] + 1
        if s["kind"] == "move":
            act = f"버스 {i} 의 {D.short(info['h'])} {info['k']}명을 버스 {j} 로 옮긴다"
            row = f"옮기기 · 버스{i} {D.short(info['h'])}{info['k']} → 버스{j}"
        else:
            act = f"버스 {i} 의 {D.short(info['h'])} {info['k']}명과 버스 {j} 의 {D.short(info['h2'])} {info['k2']}명을 맞바꾼다"
            row = f"맞바꾸기 · 버스{i} {D.short(info['h'])}{info['k']} ↔ 버스{j} {D.short(info['h2'])}{info['k2']}"
        gone = "".join(f" 버스 {b + 1} 의 경로에서 {D.short(h)}({dr}) 정류가 빠진다." for b, h, dr in info["gone"])
        txt = f"**고치기 {no} — {'옮기기' if s['kind'] == 'move' else '맞바꾸기'}.** {act}.{gone} {d}."
    return txt, row


def stepper_LS(w, id, task, title=None):
    F = D.facts()
    steps = D.local_search()
    out, rows = [], []
    prev = None
    for no, s in enumerate(steps):
        hl = set(s["changed"])
        gone = [(b, h) for b, h, _ in s["info"].get("gone", [])]
        if s["kind"] == "start":
            txt = (f"**출발점 — 방안 A 거리순 계획.** 총 **{s['km']:.0f}km**. 지금부터 한 번에 한 곳만 바꿔 보고, "
                   "총 km 가 줄면 받아들인다.")
            row = ["출발", "방안 A 거리순 그대로", f"{s['km']:.0f}"]
            head = f"출발점 — 총 {s['km']:.0f}km"
        else:
            txt, r = ls_text(s, prev, no)
            if no == len(steps) - 1:
                txt += " 더 바꿔 봐도 줄지 않아 **여기서 멈춘다.**"
            row = [str(no), r, f"{s['km']:.0f}"]
            head = f"고치기 {no} — 총 {prev:.0f} → {s['km']:.0f}km"
        svg = figs.map_svg2(F, s["state"], head, "버스별 경로", _ls_lines(s["state"], hl), hl=hl, gone=gone)
        out.append({"svg": svg, "text": txt, "row": no})
        rows.append(row)
        prev = s["km"]
    return w.stepper(out, title=title or "한 곳씩 고치기 — 방안 A 계획에서 출발",
                     table={"header": ["#", "고친 것", "총 km"], "rows": rows, "small": True},
                     task=task, auto_ms=1300, id=id,
                     caption="빨간 × = 이번 고치기로 그 버스가 더는 들르지 않는 거점. 굵은 선 = 이번에 바뀐 버스")


# ════════════════════════════════════════════════════════════
# 단계 재생기 3 — 트립을 시각 순서로 버스에 이어 붙이기(이천 · 탑승률 100% · 아침)
# ════════════════════════════════════════════════════════════
SHIFT_DIR = {"출근": "출근", "퇴근": "퇴근"}


def _trip_txt(t, SH):
    code, kind = t[0][0], t[0][1:3]
    place = figs._place(t[2])
    return f"**{D.hm(t[1])} {place} 출발** {SH[code]['name']} {kind}({t[5]}명)"


def chain_data():
    ch = D.chain_steps("ICN", "1.0")
    trips = ch["trips"]
    mt = [j for m in ch["morning"] for j in m]
    ch["peak_morning"] = max(sum(1 for j in mt if trips[j][1] <= m < trips[j][3]) for m in range(0, 9 * 60))
    return ch


def stepper_chain(w, id, task, title=None):
    F = D.facts()
    SH = D.shifts()
    ch = chain_data()
    trips, steps = ch["trips"], ch["steps"]
    have = F["icn_buses"]
    out = []
    first_over = None
    for k, st in enumerate(steps):
        t = trips[st["trip"]]
        place = figs._place(t[2])
        b = st["bus"]
        head = _trip_txt(t, SH)
        if st["new"]:
            if not st["cands"]:
                txt = f"{head} — 아직 쓴 버스가 없다. → **버스 {b + 1}** 새로 투입."
            else:
                idle = [c for c in st["cands"] if not c["busy"]]
                busy = [c for c in st["cands"] if c["busy"]]
                best = min(st["cands"], key=lambda c: c["arr"])
                why = []
                if busy:
                    why.append("달리는 중 — " + " · ".join(f"버스 {c['bus'] + 1}" for c in busy))
                if idle:
                    why.append("쉬는 버스 — " + " · ".join(f"버스 {c['bus'] + 1}({figs._place(c['at'])}, {place}까지 {c['dh']:.0f}분)" for c in idle))
                txt = (f"{head}. {'. '.join(why)}. 가장 빨리 닿는 버스도 **{D.hm(best['arr'])}** 에야 {place}에 닿는다. "
                       f"→ **버스 {b + 1}** 새로 투입.")
            if b >= have:
                txt += f" !!보유 {have}대를 넘는다.!!"
                if first_over is None:
                    first_over = k
        else:
            c = next(x for x in st["cands"] if x["bus"] == b)
            if c["dh"] < 0.5:
                where = f"버스 {b + 1} — {D.hm(c['free'])} 부터 {place}에서 대기"
            else:
                where = f"버스 {b + 1} — {D.hm(c['free'])} 부터 {figs._place(c['at'])}에서 대기, {place}까지 {c['dh']:.0f}분({D.hm(c['arr'])} 도착)"
            more = f" 시간 안에 닿는 버스 {st['n_ok']}대 중 가장 가까운 버스다." if st["n_ok"] > 1 else ""
            txt = f"{head}. {where}.{more} → **버스 {b + 1}** 에 이어 붙인다."
        svg = figs.chain_frame(ch, k, have, f"트립 {k + 1} / {len(steps)} — 출발 시각 순서")
        out.append({"svg": svg, "text": txt, "row": None})
    nb = len(ch["morning"])
    # 마지막 — 정리 단계
    if first_over is not None:
        st = steps[first_over]
        idle = [c for c in st["cands"] if not c["busy"]]
        idle_txt = ", ".join(f"버스 {c['bus'] + 1} · {figs._place(c['at'])}" for c in idle)
        t = trips[st["trip"]]
        reason = (f"{D.hm(t[1])} {figs._place(t[2])} 출발 때 쉬고 있던 버스({idle_txt})가 너무 멀리 있어서다." if idle
                  else "그 시각에 모든 버스가 달리고 있어서다.")
    else:
        reason = ""
    summ = (f"**아침에만 {nb}대.** 같은 시각에 달리는 버스는 많아야 {ch['peak_morning']}대인데 {nb}대가 든다 — {reason} "
            f"하루 전체 트립 {ch['n_trips']}개를 같은 방식으로 붙여도 {ch['fleet_day']}대다.")
    out.append({"svg": figs.chain_frame(ch, len(steps), have, f"다 붙인 결과 — 버스 {nb}대(보유 {have}대)"), "text": summ, "row": None})
    t0610 = D.hm(D.END["N"] + D.TAIL)
    return w.stepper(out, title=title or "트립을 버스에 이어 붙이는 과정 — 11/10 이천 아침 · 탑승률 100%",
                     task=task, auto_ms=1300, id=id,
                     caption=f"막대 한 줄 = 버스 한 대, 막대 하나 = 트립 하나(방안 B 경로 · 저장 결과). {t0610} 야간 퇴근은 11/10 야간 근무자 명단으로 만든 근사")
