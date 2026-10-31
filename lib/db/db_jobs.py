# 상태머신 작업 표 + 감사 기록 표
#   역할: 작업을 대기 → 진행 → 완료 · 실패 로만 옮기고(허용 전이만), 조건부 UPDATE 로 두 일꾼이 같은 작업을 집지 못하게 함 · 바뀔 때마다 감사 기록
#   어디에: 맡긴 일을 나중에 처리하는 큐(외부 작업 요청 · 사람 검토 큐 · 재처리) · «누가 언제 무엇을 바꿨나» 를 보여 줘야 할 때
#   실패하면: 허용 안 된 전이 → InternalError · 이미 다른 쪽이 옮긴 작업 → False(예외 아님 — 정상 경쟁 결과)
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from src.core.errors import InternalError

# 상태 값 — 대기 · 진행 · 완료 · 실패
PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
# 허용 전이 표 — 지금 상태 → 옮겨 갈 수 있는 상태들
ALLOWED = {PENDING: (RUNNING,), RUNNING: (DONE, FAILED)}

# 표 만들기 SQL — job_key UNIQUE 로 같은 일 두 번 등록 방지
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    job_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    payload TEXT,
    worker TEXT,
    error TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    detail TEXT
);
"""


# 지금 시각 — UTC ISO 문자열(시간대 섞임 방지)
def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# 짧은 트랜잭션 — 자동 커밋 연결(isolation_level=None)에서 BEGIN IMMEDIATE ~ COMMIT
# conn: 연결
@contextmanager
def _tx(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    # 블록 안 예외 — 취소 후 올림
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# 표 두 개 만들기
# conn: sqlite3 연결(isolation_level=None 권장 — db_sqlite.connect)
def create_tables(conn):
    conn.executescript(SCHEMA)


# 감사 기록 한 줄 — 호출한 쪽 트랜잭션 안에서 같이 반영됨
# conn: 연결 / actor: 누가 / action: 무엇을 / target: 대상 / detail: 덧붙일 내용(dict 면 JSON)
def write_audit(conn, actor, action, target, detail=None):
    # 저장할 내용 문자열
    text = json.dumps(detail, ensure_ascii=False) if isinstance(detail, dict) else detail
    conn.execute("INSERT INTO audit_log (at, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
                 (_now(), actor, action, str(target), text))


# 작업 등록 — 같은 job_key 가 이미 있으면 새로 만들지 않고 기존 id. (id, 새로 만들었나) 를 돌려줌
# conn: 연결 / job_key: 일 구별 키 / payload: 작업 내용 dict / actor: 등록한 쪽
def add_job(conn, job_key, payload=None, actor="system"):
    with _tx(conn):
        # 넣기 결과 — 이미 있으면 0 행
        cur = conn.execute("INSERT OR IGNORE INTO jobs (job_key, payload, updated_at) VALUES (?, ?, ?)",
                           (job_key, json.dumps(payload, ensure_ascii=False), _now()))
        # 새로 만들었나
        created = cur.rowcount == 1
        # 작업 id
        job_id = conn.execute("SELECT id FROM jobs WHERE job_key = ?", (job_key,)).fetchone()[0]
        if created:
            write_audit(conn, actor, "등록", job_id, {"job_key": job_key})
    return job_id, created


# 상태 옮기기 — 허용 전이만 · «지금 상태가 from_status 일 때만» UPDATE(조건부) → 성공하면 True, 이미 바뀌었으면 False
# conn: 연결 / job_id: 작업 id / from_status · to_status: 전 · 후 상태 / actor: 옮긴 쪽 / error: 실패 사유(실패로 옮길 때)
def transition(conn, job_id, from_status, to_status, actor="system", error=None):
    if to_status not in ALLOWED.get(from_status, ()):
        raise InternalError("허용 안 된 전이: {} → {}".format(from_status, to_status))
    with _tx(conn):
        # 바뀐 행 수 — 0 이면 다른 쪽이 먼저 옮김
        cur = conn.execute(
            "UPDATE jobs SET status = ?, worker = ?, error = ?, updated_at = ? WHERE id = ? AND status = ?",
            (to_status, actor, error, _now(), job_id, from_status))
        if cur.rowcount != 1:
            return False
        write_audit(conn, actor, "{}→{}".format(from_status, to_status), job_id, error)
    return True


# 대기 작업 하나 집기 — 가장 오래된 대기 작업을 진행으로 옮김. 집은 작업 행(sqlite3.Row) 또는 None
# conn: 연결 / worker: 일꾼 이름
def claim_next(conn, worker):
    # 후보 몇 개 — 앞 후보를 남이 먼저 집으면 다음으로
    for row in conn.execute("SELECT id FROM jobs WHERE status = ? ORDER BY id LIMIT 5", (PENDING,)).fetchall():
        if transition(conn, row[0], PENDING, RUNNING, actor=worker):
            return conn.execute("SELECT * FROM jobs WHERE id = ?", (row[0],)).fetchone()
    return None


# 상태별 개수 — 화면 · 로그용 {상태: 개수}
# conn: 연결
def count_by_status(conn):
    return {s: n for s, n in conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")}

