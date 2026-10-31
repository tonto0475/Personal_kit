# lib/db 시험 — 외래키 · 트랜잭션 취소 · upsert · 상태머신 전이 · 동시 집기 · 감사 기록
import sys
import threading
from pathlib import Path

import pytest

# 이 폴더 · 저장소 루트 — import 경로에 추가
HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1]):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from db_jobs import DONE, FAILED, PENDING, RUNNING, add_job, claim_next, count_by_status, create_tables, transition  # noqa: E402
from db_sqlite import connect, transaction, upsert  # noqa: E402
from src.core.errors import InternalError  # noqa: E402


# 시험마다 새 DB 파일
@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "t.db"


# 외래키가 켜져 있고 행을 이름으로 읽음
def test_connect(db_path):
    # 연결
    conn = connect(db_path)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.execute("CREATE TABLE p (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE c (id INTEGER PRIMARY KEY, p_id INTEGER REFERENCES p(id))")
    with pytest.raises(Exception, match="FOREIGN KEY"):
        conn.execute("INSERT INTO c (p_id) VALUES (99)")
    assert conn.execute("SELECT 1 AS one").fetchone()["one"] == 1


# 블록 안 예외 → 전부 취소 · 정상 → 반영
def test_transaction(db_path):
    # 연결
    conn = connect(db_path)
    conn.execute("CREATE TABLE t (k TEXT UNIQUE, v INTEGER)")
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES ('a', 1)")
            raise RuntimeError("중간 실패")
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    with transaction(conn):
        conn.execute("INSERT INTO t VALUES ('a', 1)")
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1


# 같은 키 두 번 → 1행 · 값은 나중 것 · 이름 주입 거부
def test_upsert(db_path):
    # 연결
    conn = connect(db_path)
    conn.execute("CREATE TABLE w (week TEXT, tool TEXT, rate REAL, UNIQUE (week, tool))")
    upsert(conn, "w", {"week": "W43", "tool": "A", "rate": 1.0}, ["week", "tool"])
    upsert(conn, "w", {"week": "W43", "tool": "A", "rate": 2.5}, ["week", "tool"])
    assert [tuple(r) for r in conn.execute("SELECT * FROM w")] == [("W43", "A", 2.5)]
    with pytest.raises(InternalError):
        upsert(conn, "w; DROP TABLE w", {"week": "x"}, ["week"])


# 대기 → 진행 → 완료 · 허용 안 된 전이 거부 · 같은 키 등록 1번 · 감사 기록
def test_state_machine(db_path):
    # 연결
    conn = connect(db_path)
    create_tables(conn)
    # 작업 id · 새로 만들었나
    job_id, created = add_job(conn, "order-1", {"n": 1})
    assert created and add_job(conn, "order-1") == (job_id, False)
    with pytest.raises(InternalError, match="허용 안 된 전이"):
        transition(conn, job_id, PENDING, DONE)
    assert claim_next(conn, "w1")["status"] == RUNNING
    assert transition(conn, job_id, RUNNING, FAILED, actor="w1", error="외부 timeout")
    assert not transition(conn, job_id, RUNNING, DONE)
    assert count_by_status(conn) == {FAILED: 1}
    # 감사 기록 동작들
    actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    assert actions == ["등록", "pending→running", "running→failed"]


# 두 일꾼이 동시에 집어도 한 작업은 한 번만 집힘
def test_claim_race(db_path):
    create_tables(connect(db_path))
    add_job(connect(db_path), "only-one")
    # 집은 결과들
    got = []
    # 출발선
    barrier = threading.Barrier(2)

    # 일꾼 하나 — 각자 연결
    def worker(name):
        # 일꾼 연결
        conn = connect(db_path)
        barrier.wait()
        got.append(claim_next(conn, name))

    # 스레드 두 개
    threads = [threading.Thread(target=worker, args=("w{}".format(i),)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sum(1 for g in got if g is not None) == 1
