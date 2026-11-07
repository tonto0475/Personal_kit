# -*- coding: utf-8 -*-
"""분석 결과 읽기 — 책의 숫자 · 원본 줄 · 그림 데이터는 contracts/ 의 계약 json 세 개에서만 온다(빌드는 계산을 다시 돌리지 않는다)

계약(형식: bookkit/contracts/README.md · 검사: bookkit/contracts/check_contract.py)
  contracts/facts.json  A1 자료 함정 — numbers(글에 쓰는 실측 값) · files · traps(2장) · defects(부록 A 표) · facts(부록 A 사실) · figures(자료 띠 · 적용 실험)
  contracts/reqs.json   A2 README   — readme(1장 원문 요구) · hidden(숨은 요구) · silent(말하지 않은 곳) · questions(3장 · 부록 B)
  contracts/steps.json  A3 알고리즘  — numbers · players(재생기 셋) · figures(큰 흐름 · 순서 지도 · 화면 …) · tables(순서 · 전부 세기 · 조건별)

- 장 content 파일의 fill() 은 F = D.facts() 로 숫자를 꺼내 f"… {F['이름']} …" 로 쓴다(손으로 적은 숫자 금지)
- 목록 칸(숨은 요구 · 함정 · 질문 …)은 아래 도우미가 계약을 칸 모양으로 바꿔 준다 — 집필은 글 칸에 집중한다
- 계약이 아직 없으면 빈 값을 돌려준다(빈 칸으로 보이고 빌드는 된다)

과제 유형별 대응(분석 틀 bookkit/analysis/ 가 steps.json 을 낸다)
  | 유형               | 재생기 채우기          | 재생기 고치기          | 재생기 이어 붙이기      | 더 쓸 수 있는 그림            |
  | 경로 · 묶기        | 곳을 차에 담기(지도)   | 한 곳씩 바꾸기(지도)   | 경로를 차에 잇기        | 순서 지도                      |
  | 배차 · 사건 시뮬   | 일을 차에 맡기기(평면) | 배차 규칙 바꾸기       | 일을 시각순으로 차에    | 상태 전이 · 시각별 막대 + 임계 |
  | 일정 · 배정        | 일을 자원에 담기(평면) | 맞바꾸기 · 옮기기      | 일정을 자원 줄에        | 시각별 막대 + 임계 · 두 줄 비교 |
  | 배치 · 덮기        | 한 대씩 놓기(평면)     | 한 대씩 바꾸기         | 목표까지 더 놓아 보기   | 대수별 막대 + 허용선           |
  | 측정 · 관리도      | 성분 빼기(화살표 지도) | 고차까지 빼기(잔차)    | 관리도(시간순 · 이탈)   | 줄별 이탈 막대 + 기준선        |
  평면 좌표면 지도 칸 "geo": False · 점 = (y, x) · 공동 목적지가 없으면 "target": None · 바탕 선 "edges"
"""
import math
from pathlib import Path

from .. import contract as K

# 과제 폴더 — README.md 와 uploads/ 가 있는 곳. new_book.py --task 가 넣는다(분석 스크립트 · 계약 검사가 원본 줄을 대조할 때 쓴다)
TASK_DIR = None
# 계약 폴더 — 책 폴더/contracts
CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
# 읽은 계약(한 번 빌드에 한 번만 읽는다)
_C = {}


def contract(name):
    """contracts/<name>.json → dict(없으면 빈 dict)"""
    if name not in _C:
        _C[name] = K.read(CONTRACTS, name)
    return _C[name]


# 숫자 모음(한 번만 만든다)
_F = None


class _Later:
    """1차판(빌드 --stage 1)에서 아직 없는 숫자 — 글에는 회색 «2차판» 으로 보이고, 셈을 해도 그대로 남는다"""

    def __format__(self, spec):
        return "⟪2차판⟫"

    def __str__(self):
        return "⟪2차판⟫"

    __repr__ = __str__

    def _same(self, *a):
        return self

    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __rtruediv__ = _same
    __floordiv__ = __rfloordiv__ = __mod__ = __neg__ = __abs__ = __round__ = __getitem__ = _same


class _Numbers(dict):
    """숫자 모음 — 1차판에서는 없는 이름이 오류 대신 _Later(회색 «2차판»)"""

    def __missing__(self, key):
        from book import engine as E
        if E.STAGE == 1:
            return _Later()
        raise KeyError(key)


def facts():
    """글에 쓰는 실측 값 — facts.json «numbers» + steps.json «numbers»(같은 이름이면 계약 검사가 알린다)
    1차판(--stage 1)은 아직 없는 이름을 회색 «2차판» 으로 채운다(빌드가 멈추지 않게)"""
    global _F
    if _F is None:
        _F = _Numbers()
        _F.update(K.revive(contract("facts").get("numbers", {})))
        _F.update(K.revive(contract("steps").get("numbers", {})))
    return _F


def reqs():
    """reqs.json 그대로"""
    return contract("reqs")


def player(name):
    """재생기 칸 — steps.json «players»[name](채우기 · 고치기 · 이어붙이기) · 없으면 빈 dict"""
    return K.revive(contract("steps").get("players", {}).get(name, {}))


def figure(name):
    """그림 칸 — steps.json · facts.json 의 «figures»[name] · 없으면 빈 dict"""
    for c in ("steps", "facts"):
        f = contract(c).get("figures", {})
        if name in f:
            return K.revive(f[name])
    return {}


def table(name):
    """표 칸 — steps.json «tables»[name] · 없으면 빈 dict"""
    return K.revive(contract("steps").get("tables", {}).get(name, {}))


def hidden_rows():
    """1장 «숨은_요구»"""
    return K.hidden_rows(reqs())


def readme_groups():
    """1장 «README_요구»"""
    return K.readme_groups(reqs())


def silent_rows():
    """1장 «말하지_않은_곳»"""
    return K.silent_rows(reqs())


def question_rows(main=True):
    """3장 «질문들»(main=True) · 부록 B «나머지_질문»(main=False)"""
    return K.question_rows(reqs(), main)


def trap_cards():
    """2장 «함정» — facts.json traps 가운데 big"""
    from ..kit import raw
    return K.trap_cards(contract("facts"), raw)


def defect_groups():
    """부록 A «결함_파일별»"""
    from ..kit import mono, raw
    return K.defect_groups(contract("facts"), mono, raw=raw)


def fact_cards():
    """부록 A «사실»"""
    from ..kit import raw
    return K.fact_cards(contract("facts"), raw)


def report_table():
    """부록 C «C_리포트_표» — facts.json report"""
    from ..kit import mono
    return K.report_table(contract("facts"), mono)


def hm(m):
    """분 → «07:30»"""
    return K.hm(m)


def env():
    """글 안 {식} 의 실행 환경 — 이름은 «각주 없이 처음 나온 코드 이름» 경고에서도 빠진다"""
    return {"F": facts(), "hm": hm, "math": math}
