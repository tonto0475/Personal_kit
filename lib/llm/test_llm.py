# lib/llm 시험 — 네트워크 없이(httpx.MockTransport 가짜 서버 · FakeLLM)
import json

import httpx
import pytest

from lib.llm.json_out import ask_json, format_error, parse_and_check, strip_code_fence
from lib.llm.llm_client import FakeLLM, OpenAILLM
from src.core.errors import ExternalError, ExternalTimeout, InputError

# 가짜 서버 응답에 쓸 usage
USAGE = {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}


# 시험마다 LLM 환경변수 채움(실제 키 아님)
@pytest.fixture(autouse=True)
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://fake-llm/v1")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")


# 가짜 서버로 붙은 실제 어댑터
# handler: 요청 → 응답 함수
def make_llm(handler):
    return OpenAILLM(transport=httpx.MockTransport(handler))


# 한 번에 받기 — 주소 · 키 헤더 · 본문 · usage · 소요 시간
def test_chat_ok():
    # 받은 요청 기록
    seen = {}

    # 가짜 서버 — 요청을 기록하고 정상 응답
    # request: 들어온 요청
    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "안녕"}}], "usage": USAGE})

    # 결과
    res = make_llm(handler).chat([{"role": "user", "content": "hi"}], temperature=0)
    assert seen["url"] == "http://fake-llm/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "fake-model" and seen["body"]["temperature"] == 0
    assert res["text"] == "안녕" and res["usage"] == USAGE and res["elapsed_sec"] >= 0


# 설정 없음 · HTTP 오류 · timeout · 연결 실패 · 응답 모양 오류 → 에러 종류, 키는 문구에 없음
def test_chat_errors(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY")
    with pytest.raises(InputError, match="LLM_API_KEY"):
        OpenAILLM()
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    # 대화
    msgs = [{"role": "user", "content": "hi"}]
    with pytest.raises(ExternalError, match="HTTP 401") as info:
        make_llm(lambda r: httpx.Response(401, json={"error": "bad key test-key"})).chat(msgs)
    assert "test-key" not in str(info.value)

    # timeout 내는 가짜 서버
    # request: 들어온 요청
    def slow(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(ExternalTimeout, match="timeout 30초"):
        make_llm(slow).chat(msgs)

    # 연결 실패 가짜 서버
    # request: 들어온 요청
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ExternalError, match="연결 실패"):
        make_llm(down).chat(msgs)
    with pytest.raises(ExternalError, match="응답 형식"):
        make_llm(lambda r: httpx.Response(200, json={"choices": []})).chat(msgs)


# 조각씩 받기 — SSE 줄을 이어 붙이고 마지막 usage 를 기록
def test_stream_ok():
    # SSE 본문 — 조각 2개 + usage 조각 + 끝 표시
    sse = "".join("data: {}\n\n".format(json.dumps(c)) for c in [
        {"choices": [{"delta": {"role": "assistant"}}]},
        {"choices": [{"delta": {"content": "불량률 "}}]},
        {"choices": [{"delta": {"content": "5%"}}]},
        {"choices": [], "usage": USAGE},
    ]) + "data: [DONE]\n\n"
    # 어댑터
    llm = make_llm(lambda r: httpx.Response(200, content=sse.encode("utf-8"),
                                            headers={"content-type": "text/event-stream"}))
    assert list(llm.stream([{"role": "user", "content": "hi"}])) == ["불량률 ", "5%"]
    assert llm.last["text"] == "불량률 5%" and llm.last["usage"] == USAGE


# 스트림 HTTP 오류
def test_stream_http_error():
    # 어댑터
    llm = make_llm(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(ExternalError, match="HTTP 500"):
        list(llm.stream([{"role": "user", "content": "hi"}]))


# 가짜 어댑터도 같은 모양 — chat 결과 칸 · stream 조각
def test_fake_llm_same_shape():
    # 가짜 어댑터
    fake = FakeLLM(["가나다라마바"])
    assert set(fake.chat([{"role": "user", "content": "x"}])) == {"text", "usage", "elapsed_sec"}
    assert list(fake.stream([{"role": "user", "content": "x"}])) == ["가나다라", "마바"]
    assert fake.last["text"] == "가나다라마바"


# 코드 블록 벗기기 · 필수 키 · 형식 검사
def test_parse_and_check():
    assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fence(' {"a": 1} ') == '{"a": 1}'
    # 필수 키 형식
    req = {"summary": "str", "score": "int"}
    assert parse_and_check('```json\n{"summary": "s", "score": 3}\n```', req) == ({"summary": "s", "score": 3}, [])
    assert parse_and_check('{"score": 3}', req)[1] == ["필수 키 없음: summary"]
    assert parse_and_check('{"summary": "s", "score": true}', req)[1] == ["형식 다름: score (int 필요)"]
    assert parse_and_check("요약입니다", req)[1] == ["JSON 아님"]
    assert parse_and_check("[1]", req)[1] == ["최상위가 객체 아님"]
    assert format_error(["필수 키 없음: summary"]) == "LLM 응답 형식 오류 (필수 키 없음: summary)"


# 첫 응답이 틀리면 오류를 붙여 1회 재요청 → 통과
def test_ask_json_retry_once():
    # 첫 답은 키 빠짐 · 둘째 답은 정상
    fake = FakeLLM(['{"score": 1}', '```json\n{"summary": "ok", "score": 1}\n```'])
    # 결과 / 기록
    obj, meta = ask_json(fake, [{"role": "user", "content": "요약해"}], {"summary": "str", "score": "int"})
    assert obj == {"summary": "ok", "score": 1}
    assert meta["attempts"] == 2 and meta["usage"]["total_tokens"] > 0
    # 재요청 대화의 마지막 말 — 틀린 점이 들어 있어야 함
    retry_msg = fake.calls[1][-1]["content"]
    assert "필수 키 없음: summary" in retry_msg
    assert len(fake.calls[0]) == 1


# 재요청도 틀리면 화면 문구가 든 ExternalError · 두 번만 부름
def test_ask_json_fail_message():
    # 계속 틀린 답
    fake = FakeLLM(['{"score": 1}'])
    with pytest.raises(ExternalError) as info:
        ask_json(fake, [{"role": "user", "content": "요약해"}], {"summary": "str"})
    assert str(info.value) == "LLM 응답 형식 오류 (필수 키 없음: summary)"
    assert info.value.screen_text() == "[외부 실패] LLM 응답 형식 오류 (필수 키 없음: summary)"
    assert len(fake.calls) == 2
