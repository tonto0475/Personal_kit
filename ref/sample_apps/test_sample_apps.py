# 견본 앱 시험 — NiceGUI 사용자 흉내(user_simulation · 서버 · 브라우저 없이): 현황판 첫 화면 · 빈 상태 · 오류 띠 · 대화 응답 말풍선 · 응답 중 입력 막힘
#   실행: python3 -m pytest ref/sample_apps -q
import asyncio
import sys
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

# 저장소 루트 — ref · src · lib import 용
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ref.sample_apps.dashboard import judge_kpi  # noqa: E402
from ref.sample_apps.dashboard_chat import FAKE_REPLIES  # noqa: E402

# 이 폴더
HERE = Path(__file__).resolve().parent
# 견본 앱 파일
DASHBOARD = HERE / "dashboard.py"
DASHBOARD_CHAT = HERE / "dashboard_chat.py"


# 환경변수 LLM_* 제거 — 시험이 실제 LLM 으로 가지 않게
@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    # 환경변수 이름
    for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)


# 숫자 카드 판정 — 클수록 좋음 · 작을수록 좋음 · 차이 수치
def test_judge_kpi():
    assert judge_kpi(98.4, 98.0, True)["state"] == "ok"
    assert judge_kpi(2.3, 2.0, False) == {"state": "ng", "word": "미달", "diff": pytest.approx(0.3)}
    assert judge_kpi(3, 5, False)["word"] == "달성"


# 현황판 첫 화면 — 숫자 카드 · 구역 제목 · 램프 «API 연결»
@pytest.mark.asyncio
async def test_dashboard_open():
    async with user_simulation(main_file=DASHBOARD) as user:
        await user.open("/")
        # 화면에 있어야 할 글자
        for text in ("생산량", "수율", "불량률", "대기 로트", "추이", "로트", "API 연결 (18건)", "미달"):
            await user.should_see(text)
        await user.should_not_see("[외부 실패]")


# 빈 상태 · 오류 띠 — ?demo=empty → «데이터 없음» / ?demo=fail → «[외부 실패] ...» 띠 + 램프 끊김
@pytest.mark.asyncio
async def test_dashboard_empty_and_fail():
    async with user_simulation(main_file=DASHBOARD) as user:
        await user.open("/?demo=empty")
        await user.should_see("데이터 없음")
        await user.should_not_see("생산량")
        await user.open("/?demo=fail")
        await user.should_see("[외부 실패] 현황 API 연결 실패")
        await user.should_see("API 끊김")


# 대화 — 보내면 사용자 말풍선 + AI 응답 말풍선 · 응답 중 입력 막힘 · 끝나면 풀림 · 램프 FakeLLM
@pytest.mark.asyncio
async def test_chat_reply_and_lock():
    async with user_simulation(main_file=DASHBOARD_CHAT) as user:
        await user.open("/")
        await user.should_see("대화 없음")
        await user.should_see("LLM 미설정 (FakeLLM)")
        # 입력 칸
        inp = user.find(marker="chat-input").elements.pop()
        user.find(marker="chat-input").type("목표 초과 라인").trigger("keydown.enter")
        # 첫 조각이 붙기 시작할 만큼만 기다림(응답 전체는 약 1초)
        await asyncio.sleep(0.2)
        assert inp.enabled is False
        # 보내기 단추 — 같이 막힘
        send_btn = user.find(marker="chat-send").elements.pop()
        assert send_btn.enabled is False
        await user.should_see("목표 초과 라인", retries=20)
        # 응답 전체 — 가짜 첫 응답 마지막 줄
        await user.should_see(FAKE_REPLIES[0].splitlines()[-1], retries=40)
        # 마지막 조각 뒤 스트림 종료 확인까지 — 최대 2초 대기(0.05초 간격)
        for _ in range(40):
            if inp.enabled:
                break
            await asyncio.sleep(0.05)
        assert inp.enabled is True and send_btn.enabled is True
        assert inp.value == ""
        # 말풍선 — 사용자 · AI 두 개
        assert len(user.find(ui.chat_message).elements) == 2
        await user.should_not_see("대화 없음")
