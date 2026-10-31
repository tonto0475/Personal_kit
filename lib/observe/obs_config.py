# 설정 로더 — config.yaml + 환경변수 덮어쓰기 + 필수값 검사
#   역할: 주소 · 포트 · timeout · 임계값을 파일 한 곳에서 읽고, 환경변수(APP_API__TIMEOUT_SEC 처럼 «__» = 한 단계 아래)로 덮어씀
#   어디에: 앱 시작 직후 한 번(app.py · 스크립트 맨 위) — 결과 dict 를 각 모듈에 넘김
#   실패하면: 파일 없음 · YAML 형식 오류 · 필수값 빠짐 → InputError(어느 키인지 문구에) · 시작을 멈춤
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.core.errors import InputError


# 문자열 → 기존 값과 같은 형(정수 · 실수 · 참거짓). 기존 값이 없으면 문자열 그대로
# text: 환경변수 값 / old: 파일에 있던 값
def _cast(text, old):
    if isinstance(old, bool):
        return text.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(old, int):
        return int(text)
    if isinstance(old, float):
        return float(text)
    return text


# 점 경로로 값 꺼내기 — "api.base_url" → cfg["api"]["base_url"] (없으면 None)
# cfg: 설정 dict / dotted: 점으로 이은 키
def get_path(cfg, dotted):
    # 지금 위치 값
    node = cfg
    # 키 한 단계
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


# 설정 읽기
# path: config.yaml 경로 / required: 필수 키(점 경로) 목록 / env_prefix: 덮어쓸 환경변수 앞머리 / dotenv_path: .env 경로(없으면 건너뜀)
def load_config(path="config/config.yaml", required=(), env_prefix="APP_", dotenv_path=".env"):
    # 파일 경로
    file = Path(path)
    if not file.exists():
        raise InputError("설정 파일 없음: {}".format(file))
    try:
        # 파일 내용 — 빈 파일이면 빈 dict
        cfg = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    # YAML 문법 오류
    except yaml.YAMLError as err:
        raise InputError("설정 파일 형식 오류: {} ({})".format(file, err))
    if Path(dotenv_path).exists():
        # .env 값은 이미 있는 환경변수를 덮지 않음
        load_dotenv(dotenv_path, override=False)
    # 환경변수 이름 · 값
    for name, text in os.environ.items():
        if not name.startswith(env_prefix):
            continue
        # 키 단계들 — APP_API__TIMEOUT_SEC → ["api", "timeout_sec"]
        keys = name[len(env_prefix):].lower().split("__")
        # 넣을 자리의 부모 dict
        node = cfg
        # 중간 키
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        try:
            node[keys[-1]] = _cast(text, node.get(keys[-1]))
        # 숫자 자리에 숫자가 아닌 값
        except ValueError:
            raise InputError("환경변수 {} 형식 오류: {!r}".format(name, text))
    # 빠진 필수 키
    missing = [k for k in required if get_path(cfg, k) in (None, "")]
    if missing:
        raise InputError("필수 설정 빠짐: {}".format(", ".join(missing)))
    return cfg
