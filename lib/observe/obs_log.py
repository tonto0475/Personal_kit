# 고정 형식 로그 — logs/app.log(항상 · 정보 이상) + logs/debug.log(켰을 때만 · 디버그 전부) · CODE_RULE 7절 칸
#   역할: 칸을 «날짜 | 시간 | 기록 종류 | 중요도 | 관련 로직 | 메시지» 로 고정 · 에러는 종류 칸(errors.py kind)으로 나눔 · 비밀값 가림
#   어디에: 앱 시작 때 setup_logging 한 번 · 이후 log_event(정상 동작) · log_error(AppError) 로 남김
#   실패하면: logs/ 폴더를 못 만들면 OSError 로 시작이 멈춤(조용히 로그 없이 돌지 않음)
import logging
import re
import sys
from pathlib import Path

# 칸 형식 — 날짜 | 시간 | 기록 종류 | 중요도 | 관련 로직 | 메시지
FORMAT = "%(asctime)s | %(kind)s | %(levelname)s | %(area)s | %(message)s"
# 날짜 · 시간 칸
DATEFMT = "%Y-%m-%d | %H:%M:%S"
# 관련 로직 칸 값들
AREAS = ("처리", "통신", "화면", "저장")
# 비밀값 무늬 — Bearer 토큰 · key=값 · token=값 · password=값
SECRET_RE = re.compile(r"(Bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,&\"']+", re.IGNORECASE)


# 비밀값 가리기
# text: 로그 문구
def mask_secret(text):
    return SECRET_RE.sub(r"\1***", str(text))


# 칸 채우기 필터 — extra 로 안 준 칸은 기본값 · 메시지의 비밀값 가림
class _FieldFilter(logging.Filter):
    # record: 로그 한 줄
    def filter(self, record):
        if not hasattr(record, "kind"):
            record.kind = "-"
        if not hasattr(record, "area"):
            record.area = "처리"
        record.msg = mask_secret(record.getMessage())
        record.args = ()
        return True


# 로그 준비 — 이 함수를 두 번 불러도 핸들러가 두 벌 생기지 않음
# log_dir: 로그 폴더 / debug: True 면 debug.log 도 / name: 로거 이름("" = 루트)
def setup_logging(log_dir="logs", debug=False, name=""):
    # 로그 폴더
    folder = Path(log_dir)
    folder.mkdir(parents=True, exist_ok=True)
    # 대상 로거
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    # 기존 핸들러 — 다시 부를 때 정리
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    # 칸 형식기
    fmt = logging.Formatter(FORMAT, DATEFMT)
    # 파일 · 수준 쌍
    targets = [(folder / "app.log", logging.INFO)]
    if debug:
        targets.append((folder / "debug.log", logging.DEBUG))
    # 파일 경로 · 수준
    for path, level in targets:
        # 파일 핸들러 — utf-8 명시
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(fmt)
        handler.addFilter(_FieldFilter())
        logger.addHandler(handler)
    # 콘솔 — 경고 이상만(콘솔 인코딩이 C 로캘이어도 깨지지 않게 utf-8)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    # 콘솔 핸들러
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    console.addFilter(_FieldFilter())
    logger.addHandler(console)
    return logger


# 정상 동작 · 처리 결과 한 줄 — 예: log_event(log, "통신", "주문 조회 120건")
# logger: 로거 / area: 관련 로직 / message: 문구 / level: 중요도
def log_event(logger, area, message, level=logging.INFO):
    logger.log(level, message, extra={"area": area, "kind": "-"})


# 에러 한 줄 — 종류 칸은 err.kind(errors.py) 그대로
# logger: 로거 / area: 관련 로직 / err: AppError
def log_error(logger, area, err):
    logger.error(str(err), extra={"area": area, "kind": getattr(err, "kind", "내부 오류")})
