# 에러 4종(src/core/errors.py) 시험 — 종류 값 · 화면 문구 · 부모로 잡히는지
import sys
from pathlib import Path

import pytest

# 저장소 루트 — 어느 폴더에서 pytest 를 돌려도 src 를 찾게 sys.path 앞에 추가
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.errors import (  # noqa: E402
    KINDS, AppError, ExternalError, ExternalTimeout, InputError, InternalError)


# 종류 값이 CODE_RULE 7절 글자 그대로인지
def test_kind_names():
    assert KINDS == ("입력 오류", "외부 실패", "timeout", "내부 오류")
    assert InputError("x").kind == "입력 오류"
    assert ExternalError("x").kind == "외부 실패"
    assert ExternalTimeout("x").kind == "timeout"
    assert InternalError("x").kind == "내부 오류"


# 화면 문구 = «[종류] 메시지» · str 은 메시지 그대로(로그 메시지 칸)
def test_screen_text():
    # 시험용 timeout 에러
    err = ExternalTimeout("API 연결 실패 (timeout 10초)")
    assert str(err) == "API 연결 실패 (timeout 10초)"
    assert err.screen_text() == "[timeout] API 연결 실패 (timeout 10초)"


# 네 종류 모두 공통 부모로 잡히고, 잡은 뒤 종류 값으로 구별됨
@pytest.mark.parametrize("cls, kind", [
    (InputError, "입력 오류"), (ExternalError, "외부 실패"),
    (ExternalTimeout, "timeout"), (InternalError, "내부 오류")])
def test_caught_by_parent(cls, kind):
    with pytest.raises(AppError, match=r"^주문 조회 실패 \(행 3\)$") as info:
        raise cls("주문 조회 실패 (행 3)")
    assert info.value.kind == kind


# timeout 은 외부 실패와 형제 — except ExternalError 에 잡히지 않음
def test_timeout_not_external():
    with pytest.raises(ExternalTimeout, match="timeout 10초"):
        try:
            raise ExternalTimeout("API 연결 실패 (timeout 10초)")
        except ExternalError:
            pytest.fail("timeout 이 외부 실패로 잡힘")
