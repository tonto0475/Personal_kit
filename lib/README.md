# lib — 부품 창고

> 대회 때 필요하면 꺼내 쓰는 부품. **제출물에 통째로 넣지 않는다** — 필요한 함수만 src/ 로(testing 부품은 tests/ 로) 복사하고 from lib. import 를 복사한 자리로 바꾸며(lib 는 커밋되지 않는다), 가져온 것과 이유를 WORKLOG 에 한 줄 남긴다.
> 이 폴더는 .gitignore «*» 라 과제 저장소에 커밋되지 않는다. 시험: 저장소 루트에서 `python3 -m pytest lib/<분야> -q`
> 부품마다 파일 머리에 «세 줄 설명»(역할 · 어디에 쓰나 · 실패하면). 꺼내 쓴 부품은 서술형 설명 대상이다.

| 분야 | 파일 | 함수 | 한 줄 |
|---|---|---|---|
| api | api_client.py | ApiClient · AsyncApiClient(request · get_json · post_json) · classify · should_retry · iter_pages · iter_cursor | 기본 주소 · timeout · 토큰(환경변수) · 요청 로그 · for 문 재시도(429 · 502 · 503 · 504 · timeout · 연결 실패 · 점점 늘리는 간격 · Retry-After · POST 는 Idempotency-Key 있을 때만) · 성공 · 실패 · 모름 → errors.py · page · cursor 페이지 넘김 |
| api | api_webhook.py | sign · verify_signature | HMAC-SHA256 «시각.본문» 서명 · 허용 범위 300초 · 상수시간 비교 → InputError |
| api | api_poll.py | poll_job · apoll_job | 비동기 작업 상태 폴링: 완료 → 응답 · 실패 → ExternalError · 시간 초과 → ExternalTimeout |
| db | db_sqlite.py | connect · transaction · upsert | 외래키 켜기 · row_factory · with 트랜잭션(예외면 취소) · UNIQUE ON CONFLICT DO UPDATE |
| db | db_jobs.py | create_tables · add_job · transition · claim_next · write_audit · count_by_status | 대기 → 진행 → 완료 · 실패 허용 전이만 · 조건부 UPDATE 로 동시 집기 방지 · 전이마다 감사 기록 |
| data | csv_load.py | read_csv_auto · clean_columns · split_unit | CSV 인코딩 판별(utf-8-sig → utf-8 → cp949) · 열 이름 공백 제거 · 단위 괄호 분리 |
| data | quality.py | quality_report · report_markdown · group_defect_rate | 행 수 · 결측률 · 중복 · 범위 밖 리포트(dict · 마크다운) · 그룹별 불량률(미측정 분모 인자 필수 · 분모 0 이면 NaN) |
| data | spc.py | individuals_limits · xbar_limits · nelson_rules · cpk | I · X-bar 관리 한계(MR̄/1.128 · R̄/d2) · Nelson 1 ~ 3 · Cpk(한쪽 규격 처리) |
| judge | judge.py | check_threshold · ConsecutiveAlarm · consecutive_alarm_points | 기준값 판정(op = 이상 · 초과 · 이하 · 미만 필수 · 차이값 같이) · 연속 N회 알람 |
| judge | tz_kst.py | now_utc · to_utc · to_kst · parse_to_utc · kst_day_range_utc | KST ↔ UTC · 저장은 UTC · 시간대 없는 시각은 assume 필수 |
| llm | llm_client.py | OpenAILLM.chat · stream · FakeLLM | OpenAI 호환 httpx 어댑터(LLM_BASE_URL · LLM_API_KEY · LLM_MODEL · usage · 소요 시간 로그) · 같은 모양 가짜 |
| llm | json_out.py | strip_code_fence · parse_and_check · ask_json · format_error | JSON 출력 검증(코드 블록 벗기기 → 파싱 → if 검사 → 오류 붙여 1회 재요청 → 화면 문구) |
| observe | obs_config.py | load_config · get_path | config.yaml + .env + 환경변수 APP_A__B 덮어쓰기 · 필수값 검사 → InputError |
| observe | obs_log.py | setup_logging · log_event · log_error · mask_secret | app.log · debug.log · CODE_RULE 7절 칸 · 비밀값 가림 |
| observe | obs_health.py | add_health | NiceGUI · FastAPI 에 GET /health · 항목별 검사 · 하나라도 실패면 503 |
| observe | obs_periodic.py | PeriodicTask(start · stop) | N초마다 동기 · 비동기 함수 실행 · 회차 예외에도 계속 · stop 으로 정상 종료 |
| testing | fake_api.py | FakeApi(add · fail_next · timeout_next · delay_next · repeat_last · transport) · body_json | MockTransport 가짜 서버 + 장애 주입(5xx · timeout · 지연 · 같은 응답 두 번) · 받은 요청 기록 |
| testing | boundary.py | cases · check · range_table | 경계값 표 → pytest parametrize · 범위 경계 네 점 자동 생성 |
| ui | upload_check.py | read_upload · preview_rows · validate_rows · to_csv_bytes · UploadCheckPanel | 업로드 → 미리보기 20행 → 검증 결과(행 · 열 · 사유) → CSV 내려받기(utf-8-sig) |
| ui | progress_confirm.py | progress_bar · run_with_progress · confirm | 비동기 진행률 바(처리 i / n · 에러 나면 멈춤) · 위험 동작 확인 대화상자 |
| output | report_out.py | setup_korean_font · save_png · md_table · write_report · save_csv | Pretendard 등록 PNG(out/) · 마크다운 보고서 · CSV utf-8-sig |
