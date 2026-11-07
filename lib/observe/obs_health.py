# 헬스 체크 경로 — NiceGUI · FastAPI app 에 GET /health 붙이기
#   역할: 앱이 살아 있는지 · 의존 대상(API · DB)이 닿는지를 한 번에 JSON 으로 · 하나라도 실패면 503
#   어디에: app.py 에서 add_health(app, {"db": db_ok, "api": api_ok}) — nicegui 의 app 도 FastAPI 라 그대로 붙음 · 채점 · 상태바 램프가 읽음
#   실패하면: 검사 함수가 False · 예외 → 그 항목 ok=False + 사유 · 전체 status «fail» · HTTP 503(검사 하나가 경로 전체를 죽이지 않음)
import inspect
import time

from fastapi.responses import JSONResponse


# 검사 하나 실행 — (통과?, 사유 · 걸린 ms)
# check: 인자 없는 함수(동기 · 비동기) — True/None 이면 통과
async def _run(check):
    # 시작 시각
    started = time.monotonic()
    try:
        # 검사 결과
        result = check()
        if inspect.isawaitable(result):
            result = await result
        # 통과 여부
        ok = result is None or bool(result)
        # 사유
        detail = "" if ok else "검사 결과 False"
    # 검사 안의 모든 예외 — 그 항목만 실패
    except Exception as err:
        ok, detail = False, "{}: {}".format(type(err).__name__, err)
    return ok, detail, round((time.monotonic() - started) * 1000, 1)


# /health 붙이기
# app: FastAPI 또는 nicegui.app / checks: {이름: 검사 함수} / path: 경로
def add_health(app, checks=None, path="/health"):
    # 경로 처리 함수
    async def health():
        # 항목별 결과
        items = {}
        # 이름 · 검사 함수
        for name, check in (checks or {}).items():
            # 결과 셋
            ok, detail, took_ms = await _run(check)
            items[name] = {"ok": ok, "detail": detail, "ms": took_ms}
        # 전체 통과
        all_ok = all(v["ok"] for v in items.values())
        return JSONResponse({"status": "ok" if all_ok else "fail", "checks": items},
                            status_code=200 if all_ok else 503)

    app.get(path)(health)
    return health
