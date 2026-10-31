# LLM 어댑터 — OpenAI 호환 /chat/completions 를 httpx 로 직접 호출 + 같은 모양의 가짜 어댑터
#   역할: chat(한 번에 받기) · stream(조각씩 받기) 두 함수로 LLM 호출 · 토큰 수(usage) · 소요 시간 기록 · 실패를 errors.py 에러로 바꿈
#   어디에: 요약 · 분류 · 보고서 문구 생성 기능. 개발 · 시험은 FakeLLM, 대회장에서 OpenAILLM 으로 바꿔 끼움(함수 모양이 같음)
#   실패하면: 설정 없음 → InputError · 제한 시간 넘김 → ExternalTimeout · HTTP 오류 · 연결 실패 → ExternalError(키 값은 문구 · 로그에 안 넣음)
#   설정: 환경변수 LLM_BASE_URL(예: https://api.openai.com/v1) · LLM_API_KEY · LLM_MODEL — 키는 코드 · config 에 쓰지 않음
import json
import logging
import os
import time

import httpx

from src.core.errors import ExternalError, ExternalTimeout, InputError

# 로그 기록기 — 관련 로직 «통신»
logger = logging.getLogger("llm")


# 응답 usage 칸 → 입력 · 출력 · 합계 토큰 dict(칸이 없으면 None — 0 으로 지어내지 않음)
# usage: 응답의 usage dict 또는 None
def _usage(usage):
    usage = usage or {}
    return {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens")}


# 호출 결과 한 줄 로그 — 모델 · 토큰 · 소요 시간
# model: 모델 이름 / result: {text, usage, elapsed_sec}
def _log_call(model, result):
    # 토큰 수
    u = result["usage"]
    logger.info("LLM 호출 완료 | model=%s | tokens in=%s out=%s total=%s | %.2f초",
                model, u["prompt_tokens"], u["completion_tokens"], u["total_tokens"], result["elapsed_sec"])


# 실제 어댑터 — OpenAI 호환 서버(OpenAI · vLLM · Ollama 의 /v1 등)
class OpenAILLM:
    # base_url: API 주소(없으면 LLM_BASE_URL) / model: 모델 이름(없으면 LLM_MODEL)
    # timeout_sec: 제한 시간 초(LLM 은 오래 걸리는 호출 → 30) / transport: 시험용 httpx 전송층(MockTransport)
    def __init__(self, base_url=None, model=None, timeout_sec=30, transport=None):
        # API 주소 — 끝 «/» 제거
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        # 모델 이름
        self.model = model or os.environ.get("LLM_MODEL", "")
        # 제한 시간 초
        self.timeout_sec = timeout_sec
        # API 키 — 환경변수에서만
        api_key = os.environ.get("LLM_API_KEY", "")
        # 빠진 설정 이름 목록
        missing = [name for name, val in (("LLM_BASE_URL", self.base_url), ("LLM_MODEL", self.model),
                                          ("LLM_API_KEY", api_key)) if not val]
        if missing:
            raise InputError("LLM 설정 없음: {}".format(", ".join(missing)))
        # HTTP 클라이언트 — 연결 재사용
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout_sec, transport=transport,
                                   headers={"Authorization": "Bearer " + api_key})
        # 마지막 stream 호출 결과 — {text, usage, elapsed_sec}
        self.last = None

    # 요청 본문
    # messages: [{"role": ..., "content": ...}] / stream: 조각 받기 여부 / params: temperature 등 추가 인자
    def _body(self, messages, stream, params):
        # 요청 본문 dict
        body = {"model": self.model, "messages": messages, "stream": stream}
        if stream:
            # 마지막 조각에 usage 를 달라는 옵션(OpenAI 규격 · 지원 안 하는 서버는 무시)
            body["stream_options"] = {"include_usage": True}
        body.update(params)
        return body

    # HTTP 상태 확인 — 400 이상이면 외부 실패
    # resp: 응답
    def _check_status(self, resp):
        if resp.status_code >= 400:
            raise ExternalError("LLM 호출 실패 (HTTP {})".format(resp.status_code))

    # 한 번에 받기 — 돌려줌: {text: 응답 글, usage: 토큰 dict, elapsed_sec: 소요 초}
    # messages: 대화 목록 / params: 추가 인자
    def chat(self, messages, **params):
        # 시작 시각
        t0 = time.perf_counter()
        try:
            # 응답
            resp = self.client.post("/chat/completions", json=self._body(messages, False, params))
        # 제한 시간 넘김
        except httpx.TimeoutException:
            raise ExternalTimeout("LLM 응답 없음 (timeout {}초)".format(self.timeout_sec))
        # 연결 실패 등
        except httpx.RequestError as err:
            raise ExternalError("LLM 연결 실패 ({})".format(type(err).__name__))
        self._check_status(resp)
        try:
            # 응답 JSON
            data = resp.json()
            # 응답 글
            text = data["choices"][0]["message"]["content"] or ""
        # 응답 모양이 규격과 다름
        except (ValueError, KeyError, IndexError, TypeError):
            raise ExternalError("LLM 응답 형식 오류 (choices[0].message.content 없음)")
        # 결과
        result = {"text": text, "usage": _usage(data.get("usage")), "elapsed_sec": time.perf_counter() - t0}
        _log_call(self.model, result)
        return result

    # 조각씩 받기 — 글 조각을 하나씩 내줌. 끝나면 self.last 에 {text, usage, elapsed_sec}
    # messages: 대화 목록 / params: 추가 인자
    def stream(self, messages, **params):
        # 시작 시각
        t0 = time.perf_counter()
        # 받은 조각 목록 · 마지막 usage
        parts, usage = [], None
        try:
            # 응답 스트림
            with self.client.stream("POST", "/chat/completions", json=self._body(messages, True, params)) as resp:
                if resp.status_code >= 400:
                    resp.read()
                self._check_status(resp)
                # SSE 한 줄 — «data: {...}» · «data: [DONE]»
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    # 줄의 JSON 부분
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        # 조각 JSON
                        chunk = json.loads(payload)
                    # 깨진 줄
                    except ValueError:
                        raise ExternalError("LLM 스트림 형식 오류 (JSON 아님)")
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    # 이 조각의 선택지 목록(usage 만 든 마지막 조각은 빈 목록)
                    choices = chunk.get("choices") or []
                    # 이 조각의 글
                    piece = (choices[0].get("delta") or {}).get("content") if choices else None
                    if piece:
                        parts.append(piece)
                        yield piece
        # 제한 시간 넘김
        except httpx.TimeoutException:
            raise ExternalTimeout("LLM 응답 없음 (timeout {}초)".format(self.timeout_sec))
        # 연결 실패 등
        except httpx.RequestError as err:
            raise ExternalError("LLM 연결 실패 ({})".format(type(err).__name__))
        self.last = {"text": "".join(parts), "usage": _usage(usage), "elapsed_sec": time.perf_counter() - t0}
        _log_call(self.model, self.last)


# 가짜 어댑터 — 네트워크 없이 정해 둔 답을 차례로 돌려줌. 함수 모양은 OpenAILLM 과 같음
class FakeLLM:
    # replies: 돌려줄 응답 글 목록(부를 때마다 하나씩 · 다 쓰면 마지막 것 반복) / delay_sec: 흉내 낼 지연 초
    def __init__(self, replies, delay_sec=0.0):
        # 응답 글 목록
        self.replies = list(replies)
        # 흉내 지연 초
        self.delay_sec = delay_sec
        # 받은 요청 기록 — 시험에서 재요청 내용을 확인
        self.calls = []
        # 마지막 stream 결과
        self.last = None

    # 다음 응답 글
    # messages: 대화 목록
    def _next(self, messages):
        self.calls.append(messages)
        if self.delay_sec:
            time.sleep(self.delay_sec)
        return self.replies[min(len(self.calls), len(self.replies)) - 1]

    # 한 번에 받기 — 토큰 수는 글자 수로 흉내
    # messages: 대화 목록 / params: 무시
    def chat(self, messages, **params):
        # 응답 글
        text = self._next(messages)
        # 입력 글자 수
        n_in = sum(len(m.get("content", "")) for m in messages)
        return {"text": text, "usage": {"prompt_tokens": n_in, "completion_tokens": len(text),
                                        "total_tokens": n_in + len(text)}, "elapsed_sec": self.delay_sec}

    # 조각씩 받기 — 응답 글을 4글자씩 내줌
    # messages: 대화 목록 / params: 무시
    def stream(self, messages, **params):
        # 한 번에 받은 결과
        result = self.chat(messages)
        # 조각 시작 위치
        for i in range(0, len(result["text"]), 4):
            yield result["text"][i:i + 4]
        self.last = result
