# LLM 구조화 출력 — 코드 블록 벗기기 → JSON 파싱 → 필수 키 · 형식 if 문 검사 → 실패하면 에러 내용을 붙여 1회 재요청
#   역할: LLM 이 돌려준 글을 dict 로 바꾸고, 필수 키와 값 형식이 맞는지 확인 · 틀리면 무엇이 틀렸는지 알려 주고 한 번 더 요청
#   어디에: 요약 · 분류 · 점수 같은 LLM 결과를 화면 · DB 에 넣기 전(형식이 틀린 값이 그대로 저장되지 않게)
#   실패하면: 재요청도 틀리면 ExternalError — 화면 문구 예 «LLM 응답 형식 오류 (필수 키 없음: summary)»
#   검증은 pydantic 없이 if 문(줄 단위 설명 가능하게)
import json
import re

from src.core.errors import ExternalError

# ``` 또는 ```json 으로 감싼 코드 블록 — 안쪽만 꺼냄
FENCE = re.compile(r"```[a-zA-Z]*\s*\n?(.*?)\n?\s*```", re.DOTALL)

# 형식 이름 → 파이썬 형식(실수 자리에는 정수도 받음)
TYPES = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict}


# 응답 글에서 코드 블록 안쪽만 꺼냄. 블록이 없으면 앞뒤 공백만 뺀 원문
# text: LLM 응답 글
def strip_code_fence(text):
    # 첫 코드 블록
    match = FENCE.search(text)
    return (match.group(1) if match else text).strip()


# 파싱 + 검사. 돌려줌: (dict 또는 None, 오류 문구 목록 — 비면 통과)
# text: LLM 응답 글 / required: {키: 형식 이름} — 형식 이름은 TYPES 의 키
def parse_and_check(text, required):
    try:
        # 파싱 결과
        obj = json.loads(strip_code_fence(text))
    # JSON 문법 오류
    except ValueError:
        return None, ["JSON 아님"]
    if not isinstance(obj, dict):
        return None, ["최상위가 객체 아님"]
    # 없는 키 목록
    missing = [k for k in required if k not in obj]
    # 오류 문구 목록
    errors = ["필수 키 없음: {}".format(", ".join(missing))] if missing else []
    # 키 / 형식 이름
    for key, type_name in required.items():
        if key in missing:
            continue
        # 실제 값
        val = obj[key]
        # bool 은 int 의 하위라 따로 막음(true 가 정수 1 로 통과하지 않게)
        if (type_name in ("int", "float") and isinstance(val, bool)) or not isinstance(val, TYPES[type_name]):
            errors.append("형식 다름: {} ({} 필요)".format(key, type_name))
    return (obj if not errors else None), errors


# 오류 목록 → 화면 문구(건조한 시스템 메시지체)
# errors: parse_and_check 의 오류 문구 목록
def format_error(errors):
    return "LLM 응답 형식 오류 ({})".format(" / ".join(errors))


# JSON 결과 받기 — 실패하면 오류를 붙여 1회 재요청. 돌려줌: (dict, {attempts, usage 합계, elapsed_sec 합계})
# llm: chat(messages) 를 가진 어댑터(OpenAILLM · FakeLLM) / messages: 대화 목록 / required: {키: 형식 이름}
def ask_json(llm, messages, required):
    # 이번 요청에 쓸 대화 — 원본 목록은 건드리지 않음
    convo = list(messages)
    # 기록 — 시도 횟수 · 토큰 합계 · 소요 시간 합계
    meta = {"attempts": 0, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "elapsed_sec": 0.0}
    # 마지막 오류 목록
    errors = []
    # 시도 번호 — 0 처음 · 1 재요청
    for attempt in range(2):
        # LLM 결과
        result = llm.chat(convo)
        meta["attempts"] = attempt + 1
        meta["elapsed_sec"] += result["elapsed_sec"]
        # 토큰 칸 이름
        for k in meta["usage"]:
            meta["usage"][k] += result["usage"].get(k) or 0
        # 검사 결과
        obj, errors = parse_and_check(result["text"], required)
        if not errors:
            return obj, meta
        # 재요청 — 직전 답과 틀린 점을 대화에 붙임
        convo = convo + [
            {"role": "assistant", "content": result["text"]},
            {"role": "user", "content": "직전 응답이 형식에 맞지 않음: {}. 필수 키 {} 를 모두 넣은 JSON 객체 하나만 다시 출력.".format(
                " / ".join(errors), ", ".join("{}({})".format(k, t) for k, t in required.items()))},
        ]
    raise ExternalError(format_error(errors))
