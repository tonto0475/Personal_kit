# CSV 로더 — 인코딩 자동 판별 + 열 이름 정리
#   역할: utf-8-sig → utf-8 → cp949 순으로 읽어 보고 처음 성공한 인코딩으로 표를 만듦 · 열 이름 앞뒤 공백 제거 · «두께 (nm)» → 이름 «두께» + 단위 «nm» 분리
#   어디에: 과제 data/ 의 입력 CSV 를 처음 읽을 때(엑셀 저장본은 utf-8-sig, 사내 시스템 내보내기는 cp949 가 흔함)
#   실패하면: 세 인코딩 모두 실패 · 파일 없음 · 열 이름 중복이면 InputError(조용히 깨진 글자로 읽지 않음)
import re

import pandas as pd

from src.core.errors import InputError

# 시도 순서 — BOM 있는 utf-8 을 먼저(utf-8 로 읽으면 첫 열 이름에 ﻿ 가 붙음), cp949 는 마지막
#   utf-8-sig 는 BOM 없는 utf-8 도 읽음 → BOM 없는 파일도 돌려주는 인코딩 값은 utf-8-sig
#   cp949 를 앞에 두면 안 됨 — utf-8 한글이 cp949 로 «성공» 해 깨진 글자가 될 수 있음
ENCODINGS = ("utf-8-sig", "utf-8", "cp949")

# 열 이름 끝의 단위 괄호 — «두께 (nm)» · «온도[℃]» · «압력(kPa)» 모양
UNIT_PATTERN = re.compile(r"^(.*?)\s*[\(\[]\s*([^\)\]]*?)\s*[\)\]]\s*$")


# 열 이름 하나를 이름 · 단위로 분리. 괄호가 없으면 단위는 빈 문자열
# raw: 원래 열 이름
def split_unit(raw):
    # 앞뒤 공백 뺀 열 이름
    name = str(raw).strip()
    # 단위 괄호 일치 결과
    match = UNIT_PATTERN.match(name)
    if match is None or match.group(1).strip() == "":
        return name, ""
    return match.group(1).strip(), match.group(2).strip()


# 열 이름 정리 — 공백 · 단위 분리. 돌려줌: (정리된 표, {열 이름: 단위})
# df: 원본 표
def clean_columns(df):
    # 새 열 이름 목록
    names = []
    # 열 이름 → 단위
    units = {}
    # 원래 열 이름
    for raw in df.columns:
        # 정리된 이름 / 단위
        name, unit = split_unit(raw)
        names.append(name)
        units[name] = unit
    # 정리 뒤 같은 이름이 둘 이상인 열
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise InputError("열 이름 중복 (정리 후): {}".format(", ".join(dupes)))
    # 이름만 바꾼 사본 — 원본 표는 그대로
    out = df.copy()
    out.columns = names
    return out, units


# CSV 읽기 — 인코딩 판별 + 열 이름 정리. 돌려줌: (표, 쓴 인코딩, {열 이름: 단위})
# path: CSV 경로 / kwargs: pandas.read_csv 에 그대로 넘길 인자(sep 등)
def read_csv_auto(path, **kwargs):
    # 인코딩별 실패 사유 — 셋 다 실패하면 에러 문구에 씀
    errors = []
    # 시도할 인코딩
    for enc in ENCODINGS:
        try:
            # 읽은 표
            df = pd.read_csv(path, encoding=enc, **kwargs)
        # 파일 없음 — 인코딩을 바꿔도 같으므로 바로 끝냄
        except FileNotFoundError:
            raise InputError("입력 파일 없음: {}".format(path))
        # 이 인코딩으로 해석 불가
        except UnicodeDecodeError as err:
            errors.append("{}: {}".format(enc, err.reason))
            continue
        # 정리된 표 / 단위
        cleaned, units = clean_columns(df)
        return cleaned, enc, units
    raise InputError("CSV 인코딩 판별 실패 ({})".format(" / ".join(errors)))
