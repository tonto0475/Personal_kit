# 저장(src/db/store.py) 시험 — UNIQUE 제약 · 다시 넣으면 바꿔치기(행 수 1)
import sqlite3

import pytest

from src.db.store import connect, create_table, upsert


# 시험마다 새 DB(임시 폴더)
@pytest.fixture
def conn(tmp_path):
    # 연결
    c = connect(tmp_path / "t.db")
    create_table(c)
    yield c
    c.close()


# 같은 key 두 번 → 1행 · 값은 나중 것
def test_upsert_replaces(conn):
    upsert(conn, "W43-A", "1.0")
    upsert(conn, "W43-A", "2.5")
    # 저장된 행들
    rows = conn.execute("SELECT key, value FROM records").fetchall()
    assert [tuple(r) for r in rows] == [("W43-A", "2.5")]


# 다른 key 는 따로 쌓임
def test_upsert_other_keys(conn):
    upsert(conn, "W43-A", "1")
    upsert(conn, "W44-A", "2")
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 2


# UNIQUE 제약이 key 열에 실제로 걸려 있음 — 일반 INSERT 두 번은 막힘
def test_unique_enforced(conn):
    conn.execute("INSERT INTO records (key, value) VALUES ('k', 'a')")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        conn.execute("INSERT INTO records (key, value) VALUES ('k', 'b')")


# 외래키가 켜져 있음
def test_foreign_keys_on(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
