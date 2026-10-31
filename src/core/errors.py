# 에러 4종 — 로그의 종류 칸과 화면 메시지가 같은 «종류» 값을 읽는 예외 클래스
#   종류 이름은 docs/CODE_RULE.md 7절과 글자까지 같게: 입력 오류 · 외부 실패 · timeout · 내부 오류
#   사용 예:
#       raise ExternalTimeout("API 연결 실패 (timeout 10초)")
#       except AppError as err:  logger.error("%s | %s", err.kind, err)  /  화면에 err.screen_text()
#   timeout 은 외부 실패의 하위가 아닌 형제 — 7절이 네 종류를 나란히 두고, 5절이 재시도를 넘긴 호출을 따로 timeout 종류로 기록하라고 함


# 앱 에러 공통 부모 — 종류 값은 하위 클래스가 한 곳(kind)에서 정함
class AppError(Exception):
    # 종류 — 로그 종류 칸 · 화면 메시지 앞머리에 같이 쓰이는 값
    kind = "내부 오류"

    # 화면 표시 문구 — «[종류] 메시지»
    def screen_text(self):
        return "[{}] {}".format(self.kind, self)


# 입력 오류 — 사용자 입력 · 입력 파일 형식이 틀림
class InputError(AppError):
    # 종류
    kind = "입력 오류"


# 외부 실패 — API · DB 가 오류 응답 · 연결 실패
class ExternalError(AppError):
    # 종류
    kind = "외부 실패"


# timeout — 외부 호출이 제한 시간 안에 응답하지 않음(재시도까지 넘김). 내장 TimeoutError 와 이름이 겹치지 않게 ExternalTimeout
class ExternalTimeout(AppError):
    # 종류
    kind = "timeout"


# 내부 오류 — 코드 자체의 잘못(일어나면 안 되는 상태)
class InternalError(AppError):
    # 종류
    kind = "내부 오류"


# 종류 이름 전체 — 로그 종류 칸에 들어갈 수 있는 값(7절 순서)
KINDS = (InputError.kind, ExternalError.kind, ExternalTimeout.kind, InternalError.kind)
