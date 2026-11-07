# 저장 — SQLite 연결 · UNIQUE 표 · 다시 넣으면 바꿔치기(upsert)
#   표 · 열 이름은 과제에 맞게 바꿈. 큰 판(트랜잭션 도우미 · 상태머신 작업 표 · 감사 기록)은 부품 창고 lib/db
import sqlite3

# 표 만들기 SQL — key UNIQUE 로 같은 키는 한 행만
SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


# 연결 — 외래키 켜기 · 행을 이름으로 읽기(row["value"])
# path: DB 파일 경로 / timeout_sec: 잠김 대기 초
def connect(path, timeout_sec=10):
    # 연결
    conn = sqlite3.connect(str(path), timeout=timeout_sec)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# UNIQUE 표 만들기 — 이미 있으면 그대로
# conn: 연결
def create_table(conn):
    conn.execute(SCHEMA)
    conn.commit()


# 다시 넣으면 바꿔치기 — 같은 key 가 있으면 value · 시각만 새로(«있나 확인 → 넣기» 두 단계가 아니라 한 문장이라 사이에 끼어들 틈 없음)
# conn: 연결 / key: 고유 키 / value: 값
def upsert(conn, key, value):
    # with conn — 끝나면 커밋 · 예외면 취소
    with conn:
        conn.execute(
            "INSERT INTO records (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
            (key, value))
