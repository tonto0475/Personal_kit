#!/usr/bin/env python3
"""동시 요청 테스트 틀 — 같은 요청 2번에 결과가 1행만 쌓이는지 확인. 표준 라이브러리만(Python 3.8+).

과제마다 바꿔 끼우는 것은 두 함수뿐:
    send_once(key)   같은 요청을 1번 보냄(API 호출 · DB 쓰기 함수 그대로). key = 요청을 구별하는 값
    count_rows(key)  그 key 로 쌓인 결과 행 수를 셈

check_race 가 하는 일:
    1) 동시 2번 — 스레드 두 개를 Barrier 로 같은 순간에 출발시켜 send_once 를 부름
    2) 간격 2번 — 0.1초 간격으로 send_once 를 두 번 부름
    두 경우에 서로 다른 key 를 써서 앞 경우의 행이 뒤 경우에 섞이지 않음. 각각 «행 수 1» 인지 돌려줌

sqlite 는 파일 전체를 잠가 진짜 동시 쓰기가 잘 안 일어남 → 버그가 있어도 우연히 통과할 수 있음.
그래서 sqlite_unique_on 으로 «중복 금지 설정(UNIQUE 인덱스 · 제약)이 그 열에 실제로 걸렸나» 를 같이 확인.

pytest 예시 (tests/test_orders_race.py):
    import sqlite3, sys
    sys.path.insert(0, "scripts/race")              # 이 파일이 있는 폴더(작업 폴더 = 키트 기준)
    from race_check import check_race, describe, sqlite_unique_on
    from src.db.orders import save_order             # 과제의 쓰기 함수

    def test_same_order_twice(tmp_path):
        db = tmp_path / "t.db"
        ...표 만들기...
        def send_once(key):  save_order(db, order_id=key)
        def count_rows(key):
            with sqlite3.connect(db) as c:
                return c.execute("SELECT COUNT(*) FROM orders WHERE order_id=?", (key,)).fetchone()[0]
        result = check_race(send_once, count_rows)
        assert result["ok"], describe(result)
        assert sqlite_unique_on(db, "orders", ["order_id"]), "order_id 에 UNIQUE 없음"

다른 DB(PostgreSQL 등): count_rows 만 그 연결로 바꾸면 됨(예: psycopg 로 SELECT COUNT(*)).
    PostgreSQL 은 행 잠금이라 동시 2번이 실제로 겹침. 설정 확인은 sqlite 전용 — PostgreSQL 은 pg_indexes 를 조회.
    (이 부분은 설치 · 시험 안 함)
"""
import sqlite3
import threading
import time
from contextlib import closing


# 동시 2번 — Barrier 로 두 스레드를 같은 순간에 출발시켜 send_once 호출
# send_once: 요청 1번 보내는 함수 / key: 요청 구별 값 / join_sec: 스레드 하나를 기다리는 최대 초(멈춘 호출 대비)
def _send_together(send_once, key, join_sec):
    # 출발선 — 두 스레드가 모두 도착해야 함께 출발
    barrier = threading.Barrier(2)
    # 스레드 안에서 난 에러 문구 목록
    errors = []

    # 스레드 하나가 하는 일 — 출발선 대기 후 요청 1번
    def worker():
        try:
            barrier.wait()
            send_once(key)
        # 요청 중 난 모든 에러 — 결과에 남김(테스트 판정은 행 수로)
        except Exception as err:
            errors.append("{}: {}".format(type(err).__name__, err))

    # 스레드 두 개
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
    # 스레드 하나
    for t in threads:
        t.start()
    for t in threads:
        t.join(join_sec)
        if t.is_alive():
            errors.append("응답 없음 ({}초)".format(join_sec))
    return errors


# 간격 2번 — gap_sec 초 간격으로 send_once 를 두 번 호출
# send_once: 요청 1번 보내는 함수 / key: 요청 구별 값 / gap_sec: 두 요청 사이 간격 초
def _send_with_gap(send_once, key, gap_sec):
    # 요청 중 난 에러 문구 목록
    errors = []
    # 몇 번째 요청인지 — 0 · 1
    for i in range(2):
        if i:
            time.sleep(gap_sec)
        try:
            send_once(key)
        # 요청 중 난 모든 에러 — 결과에 남김
        except Exception as err:
            errors.append("{}: {}".format(type(err).__name__, err))
    return errors


# 같은 요청 2번(동시 · 간격) 후 각각 행 수 1 인지 확인
# send_once: 요청 1번 보내는 함수(key 하나를 받음) / count_rows: key 의 결과 행 수를 세는 함수
# gap_sec: 간격 경우의 간격 초 / key_prefix: 이번 시험의 key 앞머리 / join_sec: 동시 경우 스레드 대기 최대 초
# 돌려주는 값: {"together": {"key", "rows", "ok", "errors"}, "gap": {...}, "gap_sec": 간격 초, "ok": 둘 다 1행인가}
def check_race(send_once, count_rows, gap_sec=0.1, key_prefix="race", join_sec=30):
    # 결과 사전
    result = {"gap_sec": gap_sec}
    # 경우 이름 · 보내는 함수
    for name, send in (("together", lambda k: _send_together(send_once, k, join_sec)),
                       ("gap", lambda k: _send_with_gap(send_once, k, gap_sec))):
        # 이 경우의 key — 경우마다 달라 서로 섞이지 않음
        key = "{}-{}".format(key_prefix, name)
        # 요청 중 난 에러 목록
        errors = send(key)
        # 쌓인 행 수
        rows = count_rows(key)
        result[name] = {"key": key, "rows": rows, "ok": rows == 1, "errors": errors}
    result["ok"] = result["together"]["ok"] and result["gap"]["ok"]
    return result


# 결과 한 줄 요약 — assert 메시지용. 예: «동시 2번: 2행(✗) · 0.1초 간격 2번: 1행(✓)»
# result: check_race 가 돌려준 사전
def describe(result):
    # 경우별 문구 목록
    parts = []
    # 경우 이름 · 표시 이름
    for name, label in (("together", "동시 2번"), ("gap", "{}초 간격 2번".format(result["gap_sec"]))):
        # 경우 하나의 결과
        r = result[name]
        # 에러 문구 — 있을 때만
        err = " 에러 {}".format(r["errors"]) if r["errors"] else ""
        parts.append("{}: {}행({}){}".format(label, r["rows"], "✓" if r["ok"] else "✗", err))
    return " · ".join(parts)


# sqlite 중복 금지 설정 확인 — columns 와 열 구성이 정확히 같은 UNIQUE 인덱스 · 제약 · PRIMARY KEY 이름, 없으면 None
#   부분 인덱스(WHERE 가 붙은 UNIQUE)는 일부 행만 막아서 제외
# db_path: sqlite 파일 경로 / table: 표 이름 / columns: 열 이름 목록(문자열 하나도 가능)
def sqlite_unique_on(db_path, table, columns):
    # 찾는 열 묶음
    want = {columns} if isinstance(columns, str) else set(columns)
    # sqlite 연결 — with 를 벗어나면 닫힘
    with closing(sqlite3.connect(str(db_path), timeout=10)) as conn:
        # PRIMARY KEY 열 — table_info 의 6번째 칸(pk 순번)이 0 보다 큰 열
        pk = {row[1] for row in conn.execute("PRAGMA table_info({})".format(_quote(table))) if row[5] > 0}
        if pk and pk == want:
            return "PRIMARY KEY"
        # 인덱스 목록 한 줄 — (순번, 이름, unique, 출처, partial)
        for row in conn.execute("PRAGMA index_list({})".format(_quote(table))):
            if not row[2] or (len(row) > 4 and row[4]):
                continue
            # 이 인덱스의 열 묶음
            cols = {r[2] for r in conn.execute("PRAGMA index_info({})".format(_quote(row[1])))}
            if cols == want:
                return row[1]
    return None


# sqlite 이름 따옴표 처리 — PRAGMA 인자에 표 · 인덱스 이름을 안전하게 넣음
# name: 표 또는 인덱스 이름
def _quote(name):
    return '"' + name.replace('"', '""') + '"'
