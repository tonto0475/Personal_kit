# 동시 요청 테스트 틀(race_check.py) 자기 시험 — 임시 sqlite 파일에 실제로 써서 행 수로 판정
#   python3 -m pytest -q scripts/race
import shutil
import sqlite3
import sys
import tempfile
import time
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

# 이 폴더 — race_check 를 import 하려고 sys.path 앞에 추가
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from race_check import check_race, describe, sqlite_unique_on  # noqa: E402

# 버그판의 «확인 → 쓰기» 사이 틈 초 — 두 스레드가 둘 다 «없음» 을 보게 함
GAP_IN_BUG_SEC = 0.2


# 임시 폴더 — with 를 벗어나면 정확히 이 폴더만 지움
@contextmanager
def temp_dir():
    # 임시 폴더 경로
    d = Path(tempfile.mkdtemp(prefix="race_check_"))
    try:
        yield d
    finally:
        shutil.rmtree(str(d))


# 시험마다 새 임시 폴더
@pytest.fixture
def tmp_dir():
    # 임시 폴더 경로
    with temp_dir() as d:
        yield d


# 주문 표 만들기
# db: sqlite 파일 경로 / unique: order_id 에 UNIQUE 를 걸지
def make_table(db, unique):
    # sqlite 연결
    with closing(sqlite3.connect(str(db))) as conn:
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, order_id TEXT {})".format(
            "UNIQUE" if unique else ""))
        conn.commit()


# key 로 쌓인 행 수
# db: sqlite 파일 경로 / key: 주문 번호
def count_rows(db, key):
    # sqlite 연결
    with closing(sqlite3.connect(str(db))) as conn:
        return conn.execute("SELECT COUNT(*) FROM orders WHERE order_id=?", (key,)).fetchone()[0]


# 정상판 쓰기 — UNIQUE 에 기대어 중복이면 무시
# db: sqlite 파일 경로 / key: 주문 번호
def save_ok(db, key):
    # sqlite 연결 — 요청마다 새로 엶(실제 서버의 요청 하나와 같게)
    with closing(sqlite3.connect(str(db), timeout=10)) as conn:
        conn.execute("INSERT OR IGNORE INTO orders (order_id) VALUES (?)", (key,))
        conn.commit()


# 버그판 쓰기 — UNIQUE 없이 «있나 확인 → 없으면 쓰기», 사이에 틈
# db: sqlite 파일 경로 / key: 주문 번호
def save_bug(db, key):
    # sqlite 연결
    with closing(sqlite3.connect(str(db), timeout=10)) as conn:
        # 이미 있는 행 수
        found = conn.execute("SELECT COUNT(*) FROM orders WHERE order_id=?", (key,)).fetchone()[0]
        time.sleep(GAP_IN_BUG_SEC)
        if not found:
            conn.execute("INSERT INTO orders (order_id) VALUES (?)", (key,))
            conn.commit()


# (a) UNIQUE + 중복 무시 → 동시 · 간격 둘 다 1행, 설정 확인 참
def test_ok_version(tmp_dir):
    # 시험 DB 파일
    db = tmp_dir / "ok.db"
    make_table(db, unique=True)
    # 시험 결과
    result = check_race(lambda k: save_ok(db, k), lambda k: count_rows(db, k))
    assert result["together"]["rows"] == 1, describe(result)
    assert result["gap"]["rows"] == 1, describe(result)
    assert result["ok"] is True
    assert sqlite_unique_on(db, "orders", ["order_id"]) is not None
    assert sqlite_unique_on(db, "orders", "order_id") is not None


# (b) 버그판 → 동시 2번에서 2행을 잡아냄(간격 2번은 1행으로 통과 — 동시 경우가 필요한 이유), 설정 확인 거짓
def test_bug_version(tmp_dir):
    # 시험 DB 파일
    db = tmp_dir / "bug.db"
    make_table(db, unique=False)
    # 시험 결과
    result = check_race(lambda k: save_bug(db, k), lambda k: count_rows(db, k))
    assert result["together"]["rows"] == 2, describe(result)
    assert result["gap"]["rows"] == 1, describe(result)
    assert result["ok"] is False
    assert describe(result) == "동시 2번: 2행(✗) · 0.1초 간격 2번: 1행(✓)"
    assert sqlite_unique_on(db, "orders", ["order_id"]) is None


# 설정 확인 — UNIQUE 인덱스(CREATE UNIQUE INDEX) · 다른 열 · 부분 인덱스 · 복합 열 구별
def test_unique_kinds(tmp_dir):
    # 시험 DB 파일
    db = tmp_dir / "idx.db"
    # sqlite 연결
    with closing(sqlite3.connect(str(db))) as conn:
        conn.executescript(
            "CREATE TABLE a (x TEXT, y TEXT, z TEXT);"
            "CREATE UNIQUE INDEX ux_a_x ON a (x);"
            "CREATE UNIQUE INDEX ux_a_yz ON a (y, z) WHERE y IS NOT NULL;"
            "CREATE TABLE b (x TEXT, y TEXT, UNIQUE (x, y));")
    assert sqlite_unique_on(db, "a", ["x"]) == "ux_a_x"
    assert sqlite_unique_on(db, "a", ["y", "z"]) is None
    assert sqlite_unique_on(db, "b", ["x", "y"]) is not None
    assert sqlite_unique_on(db, "b", ["x"]) is None


# 요청 중 에러는 결과에 남음 — UNIQUE 위반을 그대로 던지는 쓰기도 1행이면 통과, 에러 문구는 보임
def test_errors_recorded(tmp_dir):
    # 시험 DB 파일
    db = tmp_dir / "raise.db"
    make_table(db, unique=True)

    # 중복이면 IntegrityError 를 던지는 쓰기
    # key: 주문 번호
    def save_raise(key):
        # sqlite 연결
        with closing(sqlite3.connect(str(db), timeout=10)) as conn:
            conn.execute("INSERT INTO orders (order_id) VALUES (?)", (key,))
            conn.commit()

    # 시험 결과
    result = check_race(save_raise, lambda k: count_rows(db, k))
    assert result["ok"] is True
    assert len(result["together"]["errors"]) == 1
    assert "IntegrityError" in result["together"]["errors"][0]


# (c) 뒷정리 — with 를 벗어나면 DB 파일이 든 임시 폴더가 사라짐
def test_cleanup():
    with temp_dir() as d:
        make_table(d / "c.db", unique=True)
        save_ok(d / "c.db", "k")
        assert count_rows(d / "c.db", "k") == 1
    assert not d.exists()
