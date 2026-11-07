# SQLite 기본 — 연결 · 트랜잭션 도우미 · UNIQUE upsert
#   역할: 외래키 켠 연결 · «한 묶음 전부 반영 또는 전부 취소» with 블록 · 같은 키를 다시 넣으면 바꿔치기
#   어디에: src/db/ 의 저장 함수. 중복 방지는 UNIQUE 제약 + upsert 로(«있나 확인 → 넣기» 두 단계로 쓰지 않음 — 그 사이에 끼어듦)
#   실패하면: 제약 위반 · 잠김은 sqlite3 예외 그대로 올라오고 with 블록 안 변경은 전부 취소됨 · 이름이 식별자가 아니면 InternalError
import sqlite3
from contextlib import contextmanager

from src.core.errors import InternalError


# 연결 — 외래키 켜기 · 행을 dict 처럼(row["열"]) · 자동 커밋 모드(트랜잭션은 transaction() 으로 명시)
# path: DB 파일 경로(":memory:" 가능) / timeout_sec: 다른 연결이 잠갔을 때 기다리는 초
def connect(path, timeout_sec=10):
    # 연결 — isolation_level=None 이면 파이썬이 몰래 BEGIN 을 끼우지 않음
    conn = sqlite3.connect(str(path), timeout=timeout_sec, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# 트랜잭션 도우미 — with 블록이 정상으로 끝나면 COMMIT, 예외가 나면 ROLLBACK 후 다시 올림
# conn: connect() 연결 / immediate: True 면 시작부터 쓰기 잠금(읽고 → 쓰는 사이 다른 쓰기가 끼지 못함)
@contextmanager
def transaction(conn, immediate=True):
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
    # 블록 안 모든 예외 — 취소 후 그대로 올림
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# 이름 검사 — 표 · 열 이름은 ? 자리에 넣을 수 없어 문자열로 끼우므로 식별자만 허용(SQL 주입 방지)
# names: 이름들
def _check_names(*names):
    # 이름 하나
    for name in names:
        if not str(name).isidentifier():
            raise InternalError("표 · 열 이름이 식별자가 아님: {!r}".format(name))


# UNIQUE upsert — 키가 없으면 넣고 있으면 나머지 열을 새 값으로 바꿈. 표에 key_cols UNIQUE 제약이 있어야 함
# conn: 연결 / table: 표 이름 / row: {열: 값} / key_cols: 고유 키 열들 / update_cols: 바꿀 열(None 이면 키 밖 전부)
def upsert(conn, table, row, key_cols, update_cols=None):
    # 열 목록
    cols = list(row)
    # 바꿀 열
    updates = list(update_cols) if update_cols is not None else [c for c in cols if c not in key_cols]
    _check_names(table, *cols, *key_cols, *updates)
    # 바꿀 열이 없으면 아무것도 안 함(이미 있으면 그대로)
    action = "DO UPDATE SET " + ", ".join("{0}=excluded.{0}".format(c) for c in updates) if updates else "DO NOTHING"
    # SQL 문
    sql = "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) {}".format(
        table, ", ".join(cols), ", ".join("?" * len(cols)), ", ".join(key_cols), action)
    conn.execute(sql, [row[c] for c in cols])
