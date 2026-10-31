# 진행률 바(비동기 작업 중) · 위험 동작 확인 대화상자 화면 조각
#   역할: 오래 걸리는 작업을 항목 단위로 돌리며 «처리 i / n» 바를 갱신하고, 삭제 · 덮어쓰기 같은 되돌릴 수 없는 동작 앞에서 확인을 받음
#   어디에: 일괄 처리 · 외부 호출 반복 · 파일 생성 화면(진행률) / 삭제 · 초기화 · 전송 단추(확인)
#   실패하면: 작업 함수가 AppError 를 내면 그 자리에서 멈추고 바 아래에 «[종류] 메시지» + 처리 건수를 남김(입력 수 ≠ 처리 수가 화면에 보임)
from nicegui import run, ui

from src.core.errors import AppError


# 진행률 바 — 바 + 상태 한 줄. 반환: (바, 글자)
def progress_bar():
    with ui.column().classes("w-full gap-1"):
        # 바 — 0 ~ 1
        bar = ui.linear_progress(value=0, show_value=False).props("rounded size=10px")
        # 상태 한 줄 — 길이를 모르는 글이라 줄바꿈
        text = ui.label("대기").classes("text-sm whitespace-normal")
    return bar, text


# 항목마다 work(항목)을 스레드에서 실행하며 바 갱신. 반환: 처리 결과 목록(멈췄으면 거기까지)
#   work 가 블로킹(파일 · HTTP)이어도 화면이 멈추지 않게 run.io_bound
# items: 처리할 항목 목록 / work: 항목 하나 처리 함수 / bar · text: progress_bar 반환값
async def run_with_progress(items, work, bar, text):
    # 전체 수 · 결과
    total = len(items)
    results = []
    bar.set_value(0)
    # 항목 번호 · 항목
    for i, item in enumerate(items, start=1):
        try:
            results.append(await run.io_bound(work, item))
        # 앱 에러 — 멈추고 종류 · 처리 건수 표시
        except AppError as err:
            text.set_text("{} · 처리 {} / {}".format(err.screen_text(), i - 1, total))
            return results
        bar.set_value(i / total if total else 1)
        text.set_text("처리 {} / {}".format(i, total))
    if total == 0:
        bar.set_value(1)
        text.set_text("처리 0 / 0")
    return results


# 위험 동작 확인 — 확인이면 True · 취소 · 바깥 클릭 · Esc 면 False
# title: 제목(동작 이름) / message: 대상 · 결과(«LOT-1001 외 3건 삭제») / ok_label: 확인 단추 글자
async def confirm(title, message, ok_label="실행"):
    # 대화상자
    with ui.dialog() as dialog, ui.card().classes("min-w-[320px]"):
        ui.label(title).classes("text-lg font-semibold")
        ui.label(message).classes("whitespace-normal")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("취소", on_click=lambda: dialog.submit(False)).props("flat no-caps")
            ui.button(ok_label, on_click=lambda: dialog.submit(True)).props("color=negative no-caps")
    # 누른 결과 — 닫히면 None
    result = await dialog
    dialog.delete()
    return result is True
