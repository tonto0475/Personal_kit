# -*- coding: utf-8 -*-
r"""task10 개편판(v3) 책의 공통 자료 — 빌드 때 과제 폴더 CSV 7개를 직접 열어 계산한 값(F)과, 오래 걸리는 풀이의 저장 결과(C · C3).

- F = 이 파일이 빌드 때마다 CSV 에서 다시 계산(정리 · 센 값 · 방안 A 의 결과). 손으로 적은 숫자 없음
- C = work\task10_cache.json (v1 의 저장 결과 — 솔버 · 필요 대수 · 완전탐색). 책 안에서 «저장 결과» 라고 밝힌다
- C3 = work\task10v3_cache.json (work\v3_cache.py — 하루 트립을 시작 · 끝 거점까지 남긴 것. 이어 붙이기 단계 재생기용)
- 개편판에서 더한 계산(빌드 때 실행): 실제 원본 줄 예시 · 거점 3곳 순서 세기 · 우회 배율 · 한 곳씩 고치기(국소 탐색) · 트립 차례대로 붙이기 · 화면 예시
- work\ 의 모듈(common · wave …)은 불러오지 않는다 — 엔진의 common 과 이름이 겹친다. 필요한 계산만 여기 다시 적었다
"""
import itertools
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]  # bookblind10o
UP = ROOT / "task" / "uploads"
CACHE = ROOT / "work" / "task10_cache.json"
CACHE3 = ROOT / "work" / "task10v3_cache.json"
SPEED = 40.0  # km/h (README)
LEAD, TAIL, CAP = 20, 10, 45  # README: 도착 20분 전 · 퇴근 10분 뒤 · 정원 45
SHIFT_MAP = {"D": "D", "S": "S", "N": "N", "G": "G", "OFF": "OFF", "d": "D", "s": "S", "n": "N", "g": "G",
             "일근": "G", "오후": "S", "주간": "D", "야간": "N"}
START = {"D": 360, "G": 510, "S": 840, "N": 1320}  # 분
END = {"D": 840, "G": 1050, "S": 1320, "N": 360}  # N 은 다음 날 06:00
WAVES = [("D", "출근", 5 * 60 + 40, 0), ("N", "퇴근", 6 * 60 + 10, -1), ("G", "출근", 8 * 60 + 10, 0), ("S", "출근", 13 * 60 + 40, 0),
         ("D", "퇴근", 14 * 60 + 10, 0), ("G", "퇴근", 17 * 60 + 40, 0), ("N", "출근", 21 * 60 + 40, 0), ("S", "퇴근", 22 * 60 + 10, 0)]
HUB_SHORT = {"강남역": "강남", "사당역": "사당", "잠실역": "잠실", "서현역": "서현", "수원역": "수원", "기흥역": "기흥", "경기광주역": "광주",
             "이천터미널": "이천", "여주역": "여주", "이천기숙사": "기숙사", "청주터미널": "청주", "오창터미널": "오창", "오송역": "오송",
             "세종터미널": "세종", "유성온천역": "유성", "청주기숙사": "청주기숙사"}


def hm(m):
    return f"{int(m) // 60 % 24:02d}:{int(m) % 60:02d}"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin((np.radians(lon2) - np.radians(lon1)) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def norm_id(x):
    x = x.strip()
    return x.zfill(6) if x.isdigit() else x


def _rd(name):
    return pd.read_csv(UP / f"{name}.csv", dtype=str, keep_default_na=False, encoding="utf-8")


_F = None
_C = None


def cache():
    global _C
    if _C is None:
        if not CACHE.exists():
            raise FileNotFoundError(f"저장 결과가 없다 — work 폴더에서 py -3 task10_cache.py 를 먼저 돌린다: {CACHE}")
        _C = json.loads(CACHE.read_text(encoding="utf-8"))
    return _C


# ════════════════════════════════════════════════════════════
# 방안 A (그리디) — 풀이기를 쓰지 않는 계획. work\c1_methods.py 와 같은 규칙
# ════════════════════════════════════════════════════════════
def path_len_km(pts):
    return float(sum(haversine_km(*pts[k], *pts[k + 1]) for k in range(len(pts) - 1)))


def plan_metrics(buses, campus_ll):
    tot, rides, n = 0.0, [], 0
    for b in buses:
        seq = list(b) + [campus_ll]
        tot += path_len_km(seq)
        rem = [path_len_km(seq[k:]) for k in range(len(seq) - 1)]
        rides += [r / SPEED * 60 for r in rem]
        n += len(b)
    rides = np.array(rides)
    return dict(buses=len(buses), km=round(tot), max_min=round(rides.max()), mean_min=round(rides.mean()),
                over90=int((rides > 90).sum()), n=n)


def plan_A_dist(pts, campus_ll, cap=CAP):
    order = sorted(pts, key=lambda p: -haversine_km(*p, *campus_ll))
    return [order[i:i + cap] for i in range(0, len(order), cap)]


def plan_A_sweep(pts, campus_ll, cap=CAP):
    ang = lambda p: math.atan2(p[0] - campus_ll[0], (p[1] - campus_ll[1]) * math.cos(math.radians(campus_ll[0])))  # noqa: E731
    a = sorted(pts, key=ang)
    angs = [ang(p) for p in a]
    gaps = [(angs[(i + 1) % len(a)] - angs[i]) % (2 * math.pi) for i in range(len(a))]
    s = (int(np.argmax(gaps)) + 1) % len(a)
    a = a[s:] + a[:s]
    chunks = [a[i:i + cap] for i in range(0, len(a), cap)]
    return [sorted(c, key=lambda p: -haversine_km(*p, *campus_ll)) for c in chunks]


# ════════════════════════════════════════════════════════════
# 사실 계산
# ════════════════════════════════════════════════════════════
def facts():
    global _F
    if _F is not None:
        return _F
    emp, sch, shf, sit, hub, veh, rl = [_rd(n) for n in ["employees", "schedule", "shifts", "sites", "hubs", "vehicles", "ride_log"]]
    F = {}
    sizes = {n: (UP / f"{n}.csv").stat().st_size for n in ["employees", "schedule", "shifts", "sites", "hubs", "vehicles", "ride_log"]}
    F.update(n_emp=len(emp), n_sch=len(sch), n_rl=len(rl), n_veh=len(veh), n_hub=len(hub), n_site=len(sit), mb=sum(sizes.values()) / 1e6,
             icn_buses=int((veh.depot_site == "ICN").sum()), cju_buses=int((veh.depot_site == "CJU").sum()))
    # ── 정리
    emp["line"] = emp.index + 2
    sch["line"] = sch.index + 2
    emp["eid"] = emp.emp_id.map(norm_id)
    sch["eid"] = sch.emp_id.map(norm_id)
    sch["d"] = sch.work_date.str.replace("/", "-")
    sch["sc"] = sch.shift_code.map(SHIFT_MAP)
    emp["lat"] = pd.to_numeric(emp.home_lat, errors="coerce")
    emp["lon"] = pd.to_numeric(emp.home_lon, errors="coerce")
    emp["coord_ok"] = emp.lat.between(33, 39) & emp.lon.between(124, 132)
    for c in ("lat", "lon"):
        hub[c] = pd.to_numeric(hub[c], errors="coerce")
        sit[c] = pd.to_numeric(sit[c])
    site = {r.site_id: (r.lat, r.lon) for r in sit.itertuples()}
    emp["site_n"] = emp.site_id.str.upper().replace({"이천캠퍼스": "ICN"})
    # ── 일정 파일의 이어 붙인 구조
    sl = sch.work_date.str.contains("/")
    dup_first = sch.duplicated(["eid", "d"], keep="first")
    ids = set(emp.emp_id)
    unreg = sorted(set(sch.eid) - set(emp.eid))
    unreg_rows = sch[sch.eid.isin(unreg)]
    F.update(slash_rows=int(sl.sum()), slash_emps=int(sch[sl].eid.nunique()), slash_first=int(sch[sl].line.min()), slash_last=int(sch[sl].line.max()),
             zero_rows=int((sch.emp_id.str.len() < 6).sum()),
             unreg_ids=unreg, n_unreg=len(unreg), unreg_rows=len(unreg_rows), unreg_first=int(unreg_rows.line.min()), unreg_last=int(unreg_rows.line.max()),
             dup_first=int(sch[dup_first].line.min()), dup_last=int(sch[dup_first].line.max()), dup_rows=int(dup_first.sum()),
             no_sched=sorted(set(emp.eid) - set(sch.eid)))
    lost = sch[~sch.emp_id.isin(ids)]
    F["naive_lost"] = len(lost)
    F["naive_lost_pct"] = 100 * len(lost) / len(sch)
    F["lost_union"] = int((~(~sl & sch.emp_id.isin(ids))).sum())
    F["lost_union_pct"] = 100 * F["lost_union"] / len(sch)
    F["lost_space"] = int((lost.eid.isin(emp.eid) & (lost.emp_id.str.len() == 6)).sum())
    F["space_ids"] = int((emp.emp_id != emp.emp_id.str.strip()).sum())
    # 근무 코드
    F["code_variants"] = int(sch.shift_code.isin(["d", "s", "n", "g", "일근", "오후", "주간", "야간"]).sum())
    F["code_E"] = int((sch.shift_code == "E").sum())
    F["code_blank"] = int((sch.shift_code == "").sum())
    # 중복 (사번, 날짜)
    g = sch.groupby(["eid", "d"]).sc.agg(lambda s: tuple(s.fillna("?")))
    gd = g[g.map(len) > 1]
    F["sch_dup_pairs"] = len(gd)
    F["sch_dup_conflict"] = int(gd.map(lambda t: len(set(t)) > 1).sum())
    # 명단 중복
    d = emp[emp.emp_id.map(norm_id).duplicated(keep=False)]
    pairs, same, later_old = 0, 0, 0
    for _, x in d.groupby("eid"):
        pairs += 1
        if x[["home_lat", "home_lon", "updated_at"]].drop_duplicates().shape[0] == 1:
            same += 1
        else:
            later_old += int(x.sort_values("line").iloc[-1].updated_at < x.sort_values("line").iloc[0].updated_at)
    F.update(emp_dup_pairs=pairs, emp_dup_same=same, emp_dup_diff=pairs - same, emp_dup_later_old=later_old)
    # 좌표
    bad = emp[~emp.coord_ok]
    blank = bad.lat.isna()
    zero = (bad.lat == 0) & (bad.lon == 0)
    swap = (bad.lat > 100) & bad.lon.between(30, 45)
    F.update(coord_bad=len(bad), coord_blank=int(blank.sum()), coord_zero=int(zero.sum()), coord_swap=int(swap.sum()),
             coord_slip=int((~blank & ~zero & ~swap).sum()))
    F["coord_fix"] = F["coord_swap"] + F["coord_slip"]
    F["coord_lost"] = F["coord_blank"] + F["coord_zero"]
    # 사업장 열
    F["site_variants"] = int((~emp.site_id.isin(["ICN", "CJU", "PGY"])).sum())
    F["n_pgy"] = int((emp.site_id == "PGY").sum())
    F["dest_blank"] = int((emp.dest_site == "").sum())
    e1 = emp.sort_values(["eid", "updated_at"]).drop_duplicates("eid", keep="last").copy()
    e1["dest_n"] = e1.dest_site.where(e1.dest_site != "", e1.site_n)
    e1["d_icn"] = haversine_km(e1.lat, e1.lon, *site["ICN"])
    e1["d_cju"] = haversine_km(e1.lat, e1.lon, *site["CJU"])
    e1["near_campus"] = np.where(e1.d_icn < e1.d_cju, "ICN", "CJU")
    mis = e1[(e1.dest_site != "") & e1.site_n.isin(["ICN", "CJU"]) & (e1.site_n != e1.dest_site)]
    mis_ok = mis[mis.coord_ok]
    F.update(site_mismatch=len(mis), site_mismatch_agree=int((mis_ok.near_campus == mis_ok.dest_n).sum()), site_mismatch_ok=len(mis_ok))
    # ── 정리한 근무 (사번 6자리 · 날짜 통일 · 코드 통일 · 중복은 첫 행)
    s1 = sch[~dup_first]
    m = s1.merge(e1[["eid", "site_n", "dest_n", "lat", "lon", "coord_ok"]], on="eid", how="inner")
    F["n_clean_rows"] = len(m)
    dates = sorted(m.d.unique())
    F["dates"] = dates
    F["n_days"] = len(dates)
    dow = {d: pd.Timestamp(d).dayofweek for d in dates}
    F["dow"] = dow
    wk = [d for d in dates if dow[d] < 5]
    cnt = m[m.sc.isin(list("DSNG"))].groupby(["d", "dest_n", "sc"]).size()

    def n(d, c, s):
        return int(cnt.get((d, c, s), 0))

    F["cnt"] = {(d, c, s): n(d, c, s) for d in dates for c in ("ICN", "CJU") for s in "DSNG"}
    mean_wk = lambda c, s: sum(n(d, c, s) for d in wk) / len(wk)  # noqa: E731
    F["wk_mean"] = {(c, s): mean_wk(c, s) for c in ("ICN", "CJU") for s in "DSNG"}
    F["icn_g"] = round(F["wk_mean"][("ICN", "G")])
    F["cju_g"] = round(F["wk_mean"][("CJU", "G")])
    F["g_total_max"] = int(m[(m.sc == "G")].groupby("d").size().max())
    F["g_div"] = F["g_total_max"] / CAP
    F["g_ceil"] = math.ceil(F["g_div"])
    F["icn_g_ceil"] = math.ceil(F["icn_g"] / CAP)
    F["cju_g_ceil"] = math.ceil(F["cju_g"] / CAP)
    F["day_riders"] = {d: int(m[(m.d == d) & m.sc.isin(list("DSNG"))].shape[0]) for d in dates}
    F["wk_riders"] = round(sum(F["day_riders"][d] for d in wk) / len(wk))
    we = [d for d in dates if dow[d] >= 5]
    F["we_riders"] = round(sum(F["day_riders"][d] for d in we) / len(we))
    # 06:10 파동(전날 N 퇴근)
    def n_prev(d):
        pd_ = (pd.Timestamp(d) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        return {c: n(pd_, c, "N") for c in ("ICN", "CJU")}

    F["wave0610"] = {d: n_prev(d) for d in dates}
    F["w0610_first"] = sum(F["wave0610"][dates[0]].values())
    F["w0610_second"] = sum(F["wave0610"][dates[1]].values())
    F["sat_0610"] = F["wave0610"]["2026-11-14"]
    # 11/17 청주 일근 — 정리 후 vs 그냥
    d17 = "2026-11-17"
    F["cju_g_1117"] = n(d17, "CJU", "G")
    naive = sch[(sch.work_date == d17) & (sch.shift_code == "G")].merge(emp[["emp_id", "site_id"]].drop_duplicates("emp_id"), on="emp_id")
    F["cju_g_1117_naive"] = int((naive.site_id == "CJU").sum())
    d10 = "2026-11-10"
    F["icn_g_1110_dest"] = n(d10, "ICN", "G")
    F["icn_g_1110_site"] = int(m[(m.d == d10) & (m.sc == "G") & (m.site_n == "ICN")].shape[0])
    F["cju_g_1110"] = n(d10, "CJU", "G")
    # ── 거점
    hh = hub[(hub.in_use == "Y") & hub.lat.notna() & (hub.hub_id != "H17")].copy()
    ec = e1[e1.coord_ok].copy()
    Dm = np.stack([haversine_km(ec.lat.values, ec.lon.values, h.lat, h.lon) for h in hh.itertuples()], axis=1)
    ec["near"] = hh.hub_id.values[Dm.argmin(1)]
    ec["near_km"] = Dm.min(1)
    F["walk_median"] = float(ec.near_km.median())
    F["walk_mean"] = float(ec.near_km.mean())
    F["walk_p90"] = float(ec.near_km.quantile(0.9))
    F["far10"] = int((ec.near_km > 10).sum())
    hh2 = hub[hub.lat.notna() & (hub.hub_id != "H17")]
    D2 = np.stack([haversine_km(ec.lat.values, ec.lon.values, h.lat, h.lon) for h in hh2.itertuples()], axis=1)
    ec["near2"] = hh2.hub_id.values[D2.argmin(1)]
    ec["near2_km"] = D2.min(1)
    o12 = ec[ec.near2 == "H12"]
    F.update(osong_n=len(o12), osong_open=float(o12.near2_km.mean()), osong_closed=float(o12.near_km.mean()))
    F["hubs_in_use_N"] = hub[hub.in_use == "N"].hub_name.tolist()
    F["hub_nocoord"] = hub[hub.lat.isna()].hub_name.tolist()
    F["hub_dup"] = int(hub.dropna(subset=["lat"]).duplicated(["lat", "lon"], keep=False).sum())
    F["dorm_icn"] = int(((emp.home_lat == "37.256") & (emp.home_lon == "127.468")).sum())
    F["dorm_cju"] = int(((emp.home_lat == "36.642") & (emp.home_lon == "127.43")).sum())
    F["v09_seats_blank"] = bool((veh[veh.vehicle_id == "V09"].seats == "").all())
    F["hubs"] = {r.hub_id: dict(name=r.hub_name, short=HUB_SHORT.get(r.hub_name, r.hub_name), lat=float(r.lat) if pd.notna(r.lat) else None,
                                lon=float(r.lon) if pd.notna(r.lon) else None) for r in hub.itertuples()}
    F["site"] = site
    F["hub_km"] = {r.hub_name: {c: float(haversine_km(r.lat, r.lon, *site[c])) for c in site} for r in hub.itertuples() if pd.notna(r.lat)}
    # ── 지난달 탑승 기록
    rl["b"] = pd.to_numeric(rl.boarded, errors="coerce")
    rl["dow"] = pd.to_datetime(rl.run_date).dt.dayofweek
    F["rl_blank"] = int(rl.b.isna().sum())
    F["rl_over"] = int((rl.b > 45).sum())
    F["rl_over_min"] = int(rl[rl.b > 45].b.min())
    F["rl_over_max"] = int(rl[rl.b > 45].b.max())
    F["rl_days"] = rl.run_date.nunique()
    F["rl_routes"] = rl.route_name.nunique()
    F["rl_routes_icn"] = rl[rl.route_name.str.startswith("ICN")].route_name.nunique()
    F["rl_routes_cju"] = rl[rl.route_name.str.startswith("CJU")].route_name.nunique()
    rd_ = rl[(rl.direction == "출근") & (rl.dow < 5)].groupby(["shift_code", "run_date"]).b.sum().groupby(level=0).mean()
    ratios = {s: float(rd_[s] / (F["wk_mean"][("ICN", s)] + F["wk_mean"][("CJU", s)])) for s in "DSNG"}
    F["ride_ratio"] = ratios
    F["ride_lo"] = min(ratios.values())
    F["ride_hi"] = max(ratios.values())
    F["ride_avg"] = float(rd_.sum() / sum(F["wk_mean"][(c, s)] for c in ("ICN", "CJU") for s in "DSNG"))
    # ── 방안 A: 11/10 평일 ICN 일근 출근 — 좌표 정상 · 가장 가까운 거점 위치
    ec2 = ec.set_index("eid")
    w = m[(m.d == d10) & (m.sc == "G") & (m.dest_n == "ICN") & m.coord_ok].copy()
    w["near"] = w.eid.map(ec2.near)
    hl = hub.set_index("hub_id")
    w["hlat"] = w.near.map(hl.lat)
    w["hlon"] = w.near.map(hl.lon)
    w["hname"] = w.near.map(hl.hub_name)
    pts = list(zip(w.hlat, w.hlon))
    cl = site["ICN"]
    F["wave_n"] = len(w)
    F["wave_bad_coord"] = F["icn_g_1110_dest"] - len(w)
    F["wave_hub_counts"] = w.groupby("hname").size().sort_values(ascending=False).to_dict()
    F["_wave_people"] = sorted(zip(w.eid, w.hname))  # (사번, 거점) — 화면 예시용
    nm = {(r.hlat, r.hlon): r.hname for r in w.itertuples()}
    F["_pts"] = pts
    F["_nm"] = nm
    A1 = plan_A_dist(pts, cl)
    A2 = plan_A_sweep(pts, cl)
    F["A1"] = plan_metrics(A1, cl)
    F["A2"] = plan_metrics(A2, cl)
    F["A1_buses"] = A1
    F["A2_buses"] = A2
    # A1 채우기 단계: (거점, 버스 번호, 담은 수, 그 버스 누적, 그 버스 누적 km)
    steps = []
    for bi, b in enumerate(A1):
        run = 0
        for (hn, c) in _runs(b, nm):
            run += c
            steps.append(dict(hub=hn, bus=bi, n=c, cum=run))
    F["A1_steps"] = steps
    F["A1_bus_stops"] = [[(hn, c) for hn, c in _runs(b, nm)] for b in A1]
    F["A1_bus_km"] = [round(path_len_km(list(b) + [cl]), 1) for b in A1]
    F["A1_bus_min"] = [round(path_len_km(list(b) + [cl]) / SPEED * 60) for b in A1]
    # ── 줄 번호 근거(부록 B)
    ln = lambda idx: [int(i) + 2 for i in idx]  # noqa: E731
    F["lines"] = dict(
        space_ids=emp[emp.emp_id != emp.emp_id.str.strip()].line.tolist(),
        coord_blank=bad[blank].line.tolist(), coord_zero=bad[zero].line.tolist(), coord_swap=bad[swap].line.tolist(),
        coord_slip=bad[~blank & ~zero & ~swap].line.tolist(),
        pgy=emp[emp.site_id == "PGY"].line.tolist(),
        site_variants=emp[~emp.site_id.isin(["ICN", "CJU", "PGY"])].line.tolist(),
        dest_blank=emp[emp.dest_site == ""].line.tolist(),
        code_E=sch[sch.shift_code == "E"].line.tolist(), code_blank=sch[sch.shift_code == ""].line.tolist(),
        code_variants=sch[sch.shift_code.isin(["d", "s", "n", "g", "일근", "오후", "주간", "야간"])].line.tolist(),
        rl_blank=ln(rl.index[rl.b.isna()]), rl_over=ln(rl.index[rl.b > 45]),
        hub_H12=int(hub[hub.hub_id == "H12"].index[0]) + 2, hub_H17=int(hub[hub.hub_id == "H17"].index[0]) + 2,
        hub_H18=int(hub[hub.hub_id == "H18"].index[0]) + 2, veh_V09=int(veh[veh.vehicle_id == "V09"].index[0]) + 2)
    F["emp_bom"] = (UP / "employees.csv").read_bytes()[:3] == b"\xef\xbb\xbf"
    F["osong_rl"] = float(rl[(rl.route_name == "CJU-오송") & (rl.direction == "출근") & (rl.dow < 5)].groupby("run_date").b.sum().mean())
    F["addr_blank"] = int((emp.home_area.str.strip() == "").sum())
    # 노선별 탑승 ÷ 예정(일근 · 평일) — 청주터미널(청주1+청주2) · 청주기숙사
    mm = m[m.coord_ok].merge(ec[["eid", "near2"]], on="eid")
    gwk = mm[(mm.sc == "G") & mm.d.isin(wk)]
    rr = {}
    for nm_, hid, routes in (("청주터미널", "H10", ["CJU-청주1", "CJU-청주2"]), ("청주기숙사", "H16", ["CJU-청주기숙사"])):
        sched = gwk[gwk.near2 == hid].groupby("d").size().mean()
        board = rl[(rl.direction == "출근") & (rl.shift_code == "G") & (rl.dow < 5) & rl.route_name.isin(routes)].groupby("run_date").b.sum().mean()
        rr[nm_] = float(board / sched)
    F["route_ratio"] = rr
    _F = F
    return F


def _runs(b, nm):
    seq = []
    for p in b:
        if seq and seq[-1][0] == nm[p]:
            seq[-1][1] += 1
        else:
            seq.append([nm[p], 1])
    return seq


# ════════════════════════════════════════════════════════════
# 트랜잭션 실험 — 파일 7개를 차례로 넣다 5번째에서 실패 (sqlite 로 실제 실행)
# ════════════════════════════════════════════════════════════
def txn_demo():
    names = ["employees", "schedule", "shifts", "sites", "hubs", "vehicles", "ride_log"]
    rows = {n: len(_rd(n)) for n in names}
    out = {}
    for mode in ("none", "txn"):
        con = sqlite3.connect(":memory:", isolation_level=None)
        for n in names:
            con.execute(f"create table {n}(x)")
        before = {n: 0 for n in names}
        try:
            if mode == "txn":
                con.execute("begin")
            for i, n in enumerate(names):
                if i == 4:
                    raise ValueError("hubs.csv 5번째 파일 검증 실패")
                con.executemany(f"insert into {n} values (?)", [(k,) for k in range(rows[n])])
            if mode == "txn":
                con.execute("commit")
        except ValueError:
            if mode == "txn":
                con.execute("rollback")
        out[mode] = {n: con.execute(f"select count(*) from {n}").fetchone()[0] for n in names}
        con.close()
    return out, rows


def fleet_frame(campus, rate, limit):
    """저장 결과의 하루 이어 쓰기 프레임(trips · chains · fleet). 해 없음이면 None"""
    return cache()["fleet_frames"].get(f"{campus}|{rate}|{limit}")


def peak_concurrent(frame):
    """같은 시각에 동시에 달리는 트립 수의 최댓값(5분 간격으로 훑는다)"""
    trips = frame["trips"]
    return max(sum(1 for x in trips if x[1] <= t < x[2]) for t in range(0, 1440, 5))


def longest_ride_min(frame):
    return max(x[4] for x in frame["trips"]) / SPEED * 60


def lst(lines, k=8):
    """줄 번호 목록 → 글자(길면 앞 k개 + «… 총 N»)"""
    s = " · ".join(f"{x:,}" for x in lines[:k])
    return s + (f" … 총 {len(lines)}" if len(lines) > k else "")


# ════════════════════════════════════════════════════════════
# 개편판(v3)에서 더한 계산
# ════════════════════════════════════════════════════════════
_C3 = None


def cache3():
    """work\\task10v3_cache.json — 하루 트립(시작 · 끝 거점 포함)과 이분 매칭으로 이은 필요 대수"""
    global _C3
    if _C3 is None:
        if not CACHE3.exists():
            raise FileNotFoundError(f"개편판 저장 결과가 없다 — py -3 -I work\\v3_cache.py 를 먼저 돌린다: {CACHE3}")
        _C3 = json.loads(CACHE3.read_text(encoding="utf-8"))
    return _C3


def shifts():
    """shifts.csv — 근무 코드 → 이름 · 시작 · 끝(OFF 제외)"""
    s = _rd("shifts")
    return {r.shift_code: dict(name=r.shift_name, start=r.start_time, end=r.end_time) for r in s.itertuples() if r.shift_code != "OFF"}


def short(name):
    return HUB_SHORT.get(name, name)


def hub_ll():
    """거점 이름 → (위도, 경도) — 좌표가 있는 거점만"""
    F = facts()
    return {h["name"]: (h["lat"], h["lon"]) for h in F["hubs"].values() if h["lat"] is not None}


def direction(ll, ref):
    """ref 에서 본 ll 의 방위(8방) — «동쪽» · «북서쪽» …"""
    dy = ll[0] - ref[0]
    dx = (ll[1] - ref[1]) * math.cos(math.radians(ref[0]))
    a = math.degrees(math.atan2(dy, dx))
    names = ["동", "북동", "북", "북서", "서", "남서", "남", "남동"]
    return names[int(((a + 22.5) % 360) // 45)] + "쪽"


def route_km(names, campus="ICN"):
    """거점 이름 순서(먼 곳 → …) → 사업장까지 열린 경로 길이 km"""
    loc = hub_ll()
    return path_len_km([loc[n] for n in names] + [facts()["site"][campus]])


def orders_example(hubs=("서현역", "기흥역", "경기광주역")):
    """버스 한 대가 거점 몇 곳을 들러 이천캠퍼스로 갈 때 — 순서마다 길이(km). 전부 세는 쉬운 방법"""
    rows = [(list(p), route_km(p)) for p in itertools.permutations(hubs)]
    best = min(rows, key=lambda r: r[1])
    worst = max(rows, key=lambda r: r[1])
    return rows, best, worst


def detour(stops, campus="ICN"):
    """정류 [(거점, 인원)](먼 곳 → 사업장) → 거점마다 (이름, 인원, 탄 거리 km, 직통 km, 배율)"""
    loc = hub_ll()
    cl = facts()["site"][campus]
    pts = [loc[n] for n, _ in stops] + [cl]
    out = []
    for k, (n, c) in enumerate(stops):
        rem = path_len_km(pts[k:])
        direct = float(haversine_km(*loc[n], *cl))
        out.append((n, c, rem, direct, rem / direct if direct > 0 else 1.0))
    return out


def detour_table():
    """방안 A 거리순 · 방안 B(솔버 10초 저장 결과) — 버스마다 가장 크게 돌아가는 배율과 1.5배 넘는 버스"""
    F, C = facts(), cache()
    a = [max(x[4] for x in detour(b)) for b in F["A1_bus_stops"]]
    b10 = [max(x[4] for x in detour([(n, c) for n, c in s])) for s in C["B_time"]["10"]["stops"]]
    return dict(A=a, A_over=[i for i, r in enumerate(a) if r > 1.5], B=b10, B_over=[i for i, r in enumerate(b10) if r > 1.5])


# ── 한 곳씩 고치기(국소 탐색) — 방안 A 거리순 계획을 출발점으로 ──────────
def _best_order(hubs):
    """거점 집합 → (가장 짧은 열린 경로 km, 순서)"""
    key = tuple(sorted(hubs))
    if key not in _ORDER_CACHE:
        best = (1e18, None)
        for perm in itertools.permutations(key):
            L = route_km(perm)
            if L < best[0]:
                best = (L, list(perm))
        _ORDER_CACHE[key] = best
    return _ORDER_CACHE[key]


_ORDER_CACHE = {}
_LS = None
MIN_GAIN = 0.5  # km — 이보다 적게 줄이는 바꾸기는 받지 않는다(표에 «−0km» 처럼 보이는 단계를 만들지 않는다)


def local_search():
    """방안 A 거리순(정류 순서 그대로)에서 시작 → ① 버스마다 들르는 순서를 가장 짧게 → ② 버스 사이 옮기기 · 맞바꾸기 중
    총 km 를 가장 많이 줄이는 것 하나씩(줄지 않으면 멈춤). 단계마다 상태 · 바뀐 버스 · 설명 재료를 남긴다"""
    global _LS
    if _LS is not None:
        return _LS
    F = facts()
    cl = F["site"]["ICN"]
    loc = hub_ll()
    state = [[(h, c) for h, c in b] for b in F["A1_bus_stops"]]

    def bus_km(stops):
        return route_km([h for h, _ in stops]) if stops else 0.0

    def total(st):
        return sum(bus_km(b) for b in st)

    steps = [dict(kind="start", state=[list(b) for b in state], km=total(state), changed=[], info={})]
    # ① 순서 바꾸기
    for i, b in enumerate(state):
        L0 = bus_km(b)
        L1, order = _best_order([h for h, _ in b])
        if L1 < L0 - 0.05:
            cnt = dict(b)
            new = [(h, cnt[h]) for h in order]
            old = list(b)
            state[i] = new
            steps.append(dict(kind="reorder", state=[list(x) for x in state], km=total(state), changed=[i],
                              info=dict(bus=i, old=[h for h, _ in old], new=order, old_km=L0, new_km=L1)))
    # ② 옮기기 · 맞바꾸기 — 최선 개선 하나씩
    while True:
        cur = total(state)
        best = None
        dicts = [dict(b) for b in state]
        n = len(state)
        for i in range(n):
            for h, c in dicts[i].items():
                for j in range(n):
                    if i == j:
                        continue
                    free = CAP - sum(dicts[j].values())
                    cands = []
                    for k in sorted({c, min(c, free)}):
                        if 0 < k <= free:
                            cands.append(("move", h, k, None, 0))
                    for h2, c2 in dicts[j].items():
                        if h2 == h:
                            continue
                        k = min(c, c2)
                        cands.append(("swap", h, k, h2, k))
                        if c != c2 and sum(dicts[i].values()) - c + c2 <= CAP and sum(dicts[j].values()) - c2 + c <= CAP:
                            cands.append(("swap", h, c, h2, c2))
                    for kind, hh, k1, h2, k2 in cands:
                        di, dj = dict(dicts[i]), dict(dicts[j])
                        di[hh] -= k1
                        dj[hh] = dj.get(hh, 0) + k1
                        if h2 is not None:
                            dj[h2] -= k2
                            di[h2] = di.get(h2, 0) + k2
                        di = {a: b for a, b in di.items() if b > 0}
                        dj = {a: b for a, b in dj.items() if b > 0}
                        Li = _best_order(list(di))[0] if di else 0.0
                        Lj = _best_order(list(dj))[0] if dj else 0.0
                        v = cur - bus_km(state[i]) - bus_km(state[j]) + Li + Lj
                        if v < cur - MIN_GAIN and (best is None or v < best[0] - 1e-9):
                            best = (v, i, j, kind, hh, k1, h2, k2, di, dj)
        if best is None:
            break
        v, i, j, kind, hh, k1, h2, k2, di, dj = best
        old_i, old_j = {h for h, _ in state[i]}, {h for h, _ in state[j]}
        state[i] = [(h, di[h]) for h in _best_order(list(di))[1]] if di else []
        state[j] = [(h, dj[h]) for h in _best_order(list(dj))[1]] if dj else []
        gone = [(i, h) for h in sorted(old_i - set(di))] + [(j, h) for h in sorted(old_j - set(dj))]
        steps.append(dict(kind=kind, state=[list(x) for x in state], km=total(state), changed=[i, j],
                          info=dict(i=i, j=j, h=hh, k=k1, h2=h2, k2=k2, gone=[(b, h, direction(loc[h], cl)) for b, h in gone])))
    _LS = steps
    return steps


# ── 트립을 차례대로 버스에 붙이기 — 저장 결과(C3)의 하루 트립 ─────────────
def chain_steps(campus="ICN", rate="1.0", until=9 * 60):
    """시작 시각 순서로 트립을 하나씩 — 시간 안에 출발지에 닿는 빈 버스가 있으면 가장 가까운 버스, 없으면 새 버스.
    아침(until 전 출발) 단계 기록 + 하루 전체를 같은 규칙으로 붙인 대수 · 이분 매칭 대수"""
    C3 = cache3()
    d = C3["chain"][f"{campus}|{rate}"]
    trips = d["trips"]
    loc = {k: tuple(v) for k, v in C3["loc"].items()}

    def dh_min(a, b):
        return float(haversine_km(*loc[a], *loc[b])) / SPEED * 60

    order = sorted(range(len(trips)), key=lambda i: (trips[i][1], trips[i][0]))
    buses, steps = [], []
    for j in order:
        t = trips[j]
        info = []
        for b, ch in enumerate(buses):
            last = trips[ch[-1]]
            dm = dh_min(last[4], t[2])
            info.append(dict(bus=b, free=last[3], at=last[4], dh=dm, arr=last[3] + dm, busy=last[3] > t[1] + 1e-9))
        ok = [x for x in info if x["arr"] <= t[1] + 1e-9]
        if ok:
            pick = min(ok, key=lambda x: (x["dh"], x["bus"]))["bus"]
            buses[pick].append(j)
        else:
            buses.append([j])
            pick = len(buses) - 1
        if t[1] < until:
            steps.append(dict(trip=j, bus=pick, new=not ok, cands=info, n_ok=len(ok)))
    morning = [[j for j in ch if trips[j][1] < until] for ch in buses]
    morning = [m for m in morning if m]
    peak = max(sum(1 for t in trips if t[1] <= m < t[3]) for m in range(0, 1440))
    return dict(trips=trips, steps=steps, morning=morning, fleet_day=len(buses), fleet_match=d["fleet"], n_trips=len(trips), peak=peak)


# ── 실제 원본 줄 — 자료 함정마다 «잘못된 예 · 정상 예» ─────────────────
def raw_lines(name):
    """CSV 원본 줄(머리 포함, BOM 은 뗀다) — 줄 번호 n 은 [n - 1]"""
    return (UP / f"{name}.csv").read_text(encoding="utf-8-sig").splitlines()


def _fix_coord(v, lo, hi):
    """소수점 어긋남 — 10 을 곱하거나 나눠 범위 안에 드는 값"""
    x = float(v)
    for _ in range(4):
        if lo <= x <= hi:
            return x
        x = x / 10 if x > hi else x * 10
    return x


_EX = None


def examples():
    """자료 함정마다 실제 원본 줄(머리 = 1줄)에서 뽑은 예 — 값은 전부 CSV 에서"""
    global _EX
    if _EX is not None:
        return _EX
    F = facts()
    L = F["lines"]
    emp, sch, hub, veh, rl, shf = (raw_lines(n) for n in ("employees", "schedule", "hubs", "vehicles", "ride_log", "shifts"))
    row = lambda lines, n: lines[n - 1].split(",")  # noqa: E731
    X = {}
    # schedule — 청주 2주차 블록 · 같은 사람의 앞 절반 줄
    b = row(sch, F["slash_first"])
    X["blk_bad"] = sch[F["slash_first"] - 1]
    X["blk_good"] = next(ln for ln in sch[1:F["slash_first"] - 1] if ln.split(",")[0].lstrip("0") == b[0].lstrip("0"))
    X["blk_id_bad"], X["blk_id_good"] = b[0], X["blk_good"].split(",")[0]
    X["unreg"] = sch[F["unreg_first"] - 1]
    X["code_var"] = [row(sch, n)[2] for n in L["code_variants"][:2]]
    X["code_var_line"] = sch[L["code_variants"][0] - 1]
    X["code_E"] = sch[L["code_E"][0] - 1]
    X["code_blank"] = sch[L["code_blank"][0] - 1]
    # (사번, 날짜) 중복 — 근무가 다른 쌍
    s = _rd("schedule")
    s["eid"] = s.emp_id.map(norm_id)
    s["d"] = s.work_date.str.replace("/", "-")
    s["line"] = s.index + 2
    dd = s[s.duplicated(["eid", "d"], keep=False)].sort_values(["eid", "d", "line"])
    pair = None
    for _, g in dd.groupby(["eid", "d"]):
        if g.shift_code.map(SHIFT_MAP).nunique() > 1:
            pair = (sch[int(g.line.iloc[0]) - 1], sch[int(g.line.iloc[-1]) - 1])
            break
    X["dup_pair"] = pair
    # employees
    head = emp[0].split(",")
    col = {c: i for i, c in enumerate(head)}
    X["emp_head"] = head
    X["space"] = row(emp, L["space_ids"][0])[0]
    X["space_line"] = emp[L["space_ids"][0] - 1]
    e = _rd("employees")
    e["line"] = e.index + 2
    e["eid"] = e.emp_id.map(norm_id)
    d2 = e[e.eid.duplicated(keep=False)].sort_values(["eid", "line"])
    dup = None
    for _, g in d2.groupby("eid"):
        if g.iloc[-1].updated_at < g.iloc[0].updated_at and g[["home_lat", "home_lon"]].drop_duplicates().shape[0] > 1:
            dup = [dict(line=int(r.line), id=r.emp_id, area=r.home_area, lat=r.home_lat, lon=r.home_lon, upd=r.updated_at) for r in g.itertuples()]
            break
    X["dup_emp"] = dup
    X["site_var"] = [row(emp, n)[col["site_id"]] for n in L["site_variants"]]
    X["site_var_ex"] = sorted(set(X["site_var"]), key=X["site_var"].index)
    X["pgy"] = emp[L["pgy"][0] - 1]
    X["dest_blank"] = emp[L["dest_blank"][0] - 1]
    mm = e[(e.dest_site != "") & e.site_id.str.upper().isin(["ICN", "CJU"]) & (e.site_id.str.upper() != e.dest_site)]
    X["mismatch"] = mm.iloc[0][["emp_id", "site_id", "dest_site", "home_area"]].tolist()
    for k in ("coord_blank", "coord_zero", "coord_swap", "coord_slip"):
        r = row(emp, L[k][0])
        X[k] = (r[col["emp_id"]], r[col["home_area"]], r[col["home_lat"]], r[col["home_lon"]])
    X["slip_all"] = [(row(emp, n)[col["home_lat"]], row(emp, n)[col["home_lon"]]) for n in L["coord_slip"]]
    lat, lon = X["coord_slip"][2], X["coord_slip"][3]
    X["slip_fix"] = (_fix_coord(lat, 33, 39), _fix_coord(lon, 124, 132))
    ab = e[e.home_area.str.strip() == ""]
    X["addr_blank"] = ab.iloc[0][["emp_id", "home_area", "home_lat", "home_lon"]].tolist() if len(ab) else None
    X["normal_emp"] = emp[1]
    X["bom"] = (UP / "employees.csv").read_bytes()[:3].hex(" ").upper()
    # 사실 — 거점 · 차량 · 기록 · 시각
    X["dorm_emp"] = next(ln for ln in emp[1:] if ln.split(",")[col["home_lat"]] == "37.256" and ln.split(",")[col["home_lon"]] == "127.468")
    X["dorm_hub"] = next(ln for ln in hub if "이천기숙사" in ln)
    X["hub_H12"], X["hub_H17"], X["hub_H18"] = hub[L["hub_H12"] - 1], hub[L["hub_H17"] - 1], hub[L["hub_H18"] - 1]
    X["hub_H04"] = next(ln for ln in hub if ln.startswith("H04,"))
    X["veh_V09"] = veh[L["veh_V09"] - 1]
    X["veh_ok"] = veh[L["veh_V09"] - 2]
    X["rl_blank"] = rl[L["rl_blank"][0] - 1]
    X["rl_over"] = rl[L["rl_over"][-1] - 1]
    X["rl_head"] = rl[0]
    X["shift_N"] = next(ln for ln in shf if ln.startswith("N,"))
    r2 = _rd("ride_log")
    day = sorted(r2.run_date.unique())[1]
    g = r2[(r2.run_date == day) & (r2.direction == "출근") & (r2.shift_code == "G")]
    X["rl_day"], X["rl_day_routes"] = day, len(g)
    # 거점에서 가장 멀리 사는 사원(사용 거점 기준)
    hh = _rd("hubs")
    hh = hh[(hh.in_use == "Y") & (hh.lat != "") & (hh.hub_id != "H17")]
    ec = e.sort_values(["eid", "updated_at"]).drop_duplicates("eid", keep="last").copy()
    ec["lat"] = pd.to_numeric(ec.home_lat, errors="coerce")
    ec["lon"] = pd.to_numeric(ec.home_lon, errors="coerce")
    ec = ec[ec.lat.between(33, 39) & ec.lon.between(124, 132)]
    Dm = np.stack([haversine_km(ec.lat.values, ec.lon.values, float(h.lat), float(h.lon)) for h in hh.itertuples()], axis=1)
    k = int(Dm.min(1).argmax())
    X["far"] = (ec.iloc[k].emp_id, ec.iloc[k].home_area, float(Dm.min(1)[k]), hh.iloc[int(Dm[k].argmin())].hub_name)
    _EX = X
    return X


# ── 화면 예시 — 방안 A 거리순 계획에서 읽은 값 ─────────────────────────
def screen_example():
    """사원 화면(사번 → 내 버스) · 운영자 화면(날짜 → 버스별) 예시. 11/10 이천 일근 출근 · 방안 A 거리순"""
    F = facts()
    arrive = START["G"] - LEAD
    depart = END["G"] + TAIL
    buses = []
    for b, stops in enumerate(F["A1_bus_stops"]):
        names = [h for h, _ in stops]
        L = route_km(names)
        buses.append(dict(no=b + 1, stops=stops, km=L, start=arrive - L / SPEED * 60, n=sum(c for _, c in stops)))
    first_hub = F["A1_bus_stops"][0][0][0]
    eid = next(e for e, h in F["_wave_people"] if h == first_hub)
    stops0 = F["A1_bus_stops"][0]
    rem = route_km([h for h, _ in stops0])
    ride = rem / SPEED * 60
    return dict(buses=buses, arrive=arrive, depart=depart, emp=eid, hub=first_hub, bus=1, board=arrive - ride, ride=ride,
                home_arrive=depart + ride, n_buses=len(buses))


def env():
    return {"F": facts(), "C": cache(), "C3": cache3(), "hm": hm, "SH": shifts(), "short": short}

