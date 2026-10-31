# 견본 앱 ② 현황판 + 대화창 — dashboard.py 틀 그대로 + 오른쪽 «말풍선 대화창» 패널(O6)
#   대화창: 말풍선 · 스트리밍(조각이 이어 붙음) · 자동 스크롤 · 응답 중 입력 막기 · 빈 상태 · 실패는 본문 오류 띠
#   LLM: 환경변수 LLM_BASE_URL · LLM_API_KEY · LLM_MODEL 이 다 있으면 OpenAILLM, 없으면 FakeLLM
#   실행: python3 -m ref.sample_apps.dashboard_chat → http://<주소>:<PORT 또는 3000>/
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# 저장소 루트 — 파일을 직접 실행해도 src · ref · lib 를 찾게 sys.path 앞에 추가
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nicegui import run, ui  # noqa: E402

from lib.llm.llm_client import FakeLLM, OpenAILLM  # noqa: E402
from ref.sample_apps.dashboard import DEFAULT_PORT, HOST, build, empty_state  # noqa: E402
from src.core.errors import AppError, InternalError  # noqa: E402
from src.ui.app import lamp  # noqa: E402
from src.ui.theme import ACCENT, BG_WINDOW, BORDER, NEUTRAL, ON_ACCENT, TEXT, TEXT_DIM  # noqa: E402

# ⭐ 바꿀 곳 — 앱 제목
APP_TITLE = "생산 현황 · AI 질의"
# 대화창 폭(px)
CHAT_WIDTH_PX = 400
# FakeLLM 조각 사이 지연 초 — 글자가 이어 붙는 모습이 보이게(실제 LLM 은 지연 없음)
FAKE_PIECE_DELAY_SEC = 0.04
# ⭐ 바꿀 곳 — 가짜 응답(차례로 · 다 쓰면 마지막 반복)
FAKE_REPLIES = [
    "목표 불량률 2.0 % 초과 라인: L3 (2.6 %) · L5 (2.3 %).\n나머지 4개 라인은 목표 이내.",
    "최근 14일 생산량 평균 1,017 개 · 계획 1,000 개 대비 +1.7 %.",
]
# ⭐ 바꿀 곳 — 시스템 지시(현황 숫자를 문맥으로 붙임)
SYSTEM_PROMPT = "생산 현황 질의 응답. 아래 현황 데이터만 근거로 짧게 답할 것.\n현황: {context}"


# 대화창 CSS — 말풍선 색(보낸 쪽 강조 · 받은 쪽 중립) · 패널 테두리(색은 theme 토큰)
def _chat_css():
    return """
.chat-drawer {{ background: {win}; border-left: 1px solid {border}; }}
.chat-head {{ border-bottom: 1px solid {border}; }}
.chat-foot {{ border-top: 1px solid {border}; }}
.q-message-text--sent {{ color: {accent}; }}
.q-message-text--sent .q-message-text-content {{ color: {on_accent}; }}
.q-message-text--received {{ color: {neutral}; }}
.q-message-text--received .q-message-text-content {{ color: {text}; }}
.q-message-name, .q-message-stamp {{ color: {dim}; }}
.q-message-text--sent .q-message-stamp {{ color: {on_accent}; opacity: .7; }}
.q-message-text-content .chat-text {{ white-space: pre-wrap; word-break: break-word; }}
""".format(win=BG_WINDOW, border=BORDER, accent=ACCENT, on_accent=ON_ACCENT, neutral=NEUTRAL, text=TEXT,
           dim=TEXT_DIM)


# LLM 고르기 — 환경변수 3개가 다 있으면 실제, 아니면 가짜. 반환: (어댑터, 가짜 여부)
def make_llm():
    if all(os.environ.get(k) for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")):
        return OpenAILLM(), False
    return FakeLLM(FAKE_REPLIES), True


# 현황 문맥 글 — 숫자 카드 · 라인별 불량률만 JSON 한 줄로(토큰 절약)
# data: load_data 모양 dict
def context_text(data):
    return json.dumps({"kpis": data["kpis"], "lines": dict(zip(data["lines"], data["defect"])),
                       "defect_target": data["defect_target"]}, ensure_ascii=False)


# 대화창 패널 — 오른쪽 drawer. 반환: 보내기 함수 send(글)(시험 · 다른 단추에서 부름)
# parts: dashboard.build 반환 dict
def chat_panel(parts):
    ui.add_css(_chat_css())
    # LLM 어댑터 · 가짜 여부
    llm, is_fake = make_llm()
    with parts["lamps"]:
        # LLM 램프 함수
        set_llm = lamp("LLM")
    if is_fake:
        set_llm("none", "FakeLLM")
    # 대화 기록 — [{"role", "content"}] (시스템 지시 제외)
    history = []
    # 응답 중 여부 — 목록 한 칸
    busy = [False]

    with ui.right_drawer(value=True, fixed=True).props("width={} :breakpoint=0".format(CHAT_WIDTH_PX)) \
            .classes("chat-drawer p-0") as drawer:
        with ui.column().classes("w-full h-full no-wrap gap-0"):
            with ui.row().classes("chat-head w-full items-center no-wrap px-4 py-2"):
                ui.label("AI 질의").classes("font-semibold whitespace-nowrap")
                ui.space()
                ui.button(icon="delete_sweep", on_click=lambda: clear()).props("flat dense round") \
                    .tooltip("대화 지우기")
            # 말풍선 스크롤 영역
            scroll = ui.scroll_area().classes("grow w-full")
            with scroll:
                # 말풍선 목록
                box = ui.column().classes("w-full gap-1 px-3 py-2")
                with box:
                    # 빈 상태 요소 — clear 에서 새로 만들어 바꿔 끼움(목록 한 칸)
                    empty_ref = [empty_state("대화 없음")]
            with ui.row().classes("chat-foot w-full items-center no-wrap gap-2 px-3 py-3"):
                # 입력 칸
                inp = ui.input(placeholder="질문 입력").props("dense outlined").classes("grow") \
                    .mark("chat-input").on("keydown.enter", lambda: send(inp.value))
                # 보내기 단추
                btn = ui.button(icon="send", on_click=lambda: send(inp.value)).props("unelevated dense") \
                    .classes("px-3").mark("chat-send")

    with parts["header_right"]:
        ui.button(icon="forum", on_click=drawer.toggle).props("flat dense round").tooltip("대화창 열기 · 닫기")

    # 맨 아래로 스크롤 — 말풍선이 그려진 뒤에 움직이게 짧게 미룸
    def to_bottom():
        ui.timer(0.05, lambda: scroll.scroll_to(percent=1.0), once=True)

    # 입력 막기 · 풀기
    # on: True 면 막음
    def lock(on):
        busy[0] = on
        if on:
            inp.disable()
            btn.disable()
        else:
            inp.enable()
            btn.enable()

    # 대화 지우기 — 응답 중이면 무시
    def clear():
        if busy[0]:
            return
        history.clear()
        box.clear()
        with box:
            empty_ref[0] = empty_state("대화 없음")

    # 보내기 — 사용자 말풍선 → 빈 AI 말풍선 → 조각마다 이어 붙이기 → 입력 풀기
    # text: 질문 글
    async def send(text):
        # 질문 — 앞뒤 공백 제거
        question = (text or "").strip()
        if not question or busy[0]:
            return
        lock(True)
        inp.value = ""
        empty_ref[0].set_visibility(False)
        # 보낸 시각
        stamp = time.strftime("%H:%M:%S")
        with box:
            with ui.chat_message(name="사용자", stamp=stamp, sent=True).classes("chat-user"):
                ui.label(question).classes("chat-text")
            # 말풍선 안 자식이 여럿이면 말풍선도 여럿 → 한 column 으로 묶음
            with ui.chat_message(name="AI", stamp=stamp, sent=False).classes("chat-ai"), ui.column().classes("gap-0"):
                # 응답 글
                answer = ui.label("").classes("chat-text")
                # 첫 조각 전 대기 표시
                spinner = ui.spinner("dots", size="md")
        to_bottom()
        history.append({"role": "user", "content": question})
        # 보낼 대화 — 시스템 지시(현황 문맥) + 기록
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context=context_text(parts["data"][0]))}] \
            + history
        # 조각 생성기
        gen = llm.stream(messages)
        try:
            while True:
                # 다음 조각 — 실제 LLM 은 네트워크를 기다리므로 스레드에서(화면 멈춤 방지)
                piece = await run.io_bound(next, gen, None)
                if piece is None:
                    break
                spinner.set_visibility(False)
                answer.set_text(answer.text + piece)
                to_bottom()
                if is_fake:
                    await asyncio.sleep(FAKE_PIECE_DELAY_SEC)
            history.append({"role": "assistant", "content": answer.text})
            if not is_fake:
                set_llm("ok", llm.model)
        # 외부 실패 · timeout · 그 밖의 예외
        except Exception as err:
            if not isinstance(err, AppError):
                err = InternalError("{}: {}".format(type(err).__name__, err))
            answer.set_text("응답 실패")
            parts["show_error"](err)
            set_llm("ng", err.kind)
            # 실패한 질문은 기록에서 뺌(다음 질문 문맥이 꼬이지 않게)
            history.pop()
        finally:
            spinner.set_visibility(False)
            lock(False)
            inp.run_method("focus")

    return send


# 페이지 — 현황판 틀 + 대화창. 쿼리 ?demo=empty · ?demo=fail 은 dashboard 와 같음
# demo: 흉내 값
def index(demo: str = ""):
    # 틀 부품
    parts = build(demo, title=APP_TITLE)
    chat_panel(parts)


# 서버 실행 — reload 끔 · 브라우저 자동 열기 끔
def main():
    ui.page("/")(index)
    ui.run(host=HOST, port=int(os.environ.get("PORT", DEFAULT_PORT)), title=APP_TITLE,
           reload=False, show=False, dark=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
