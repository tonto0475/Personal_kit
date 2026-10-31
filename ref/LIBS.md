# LIBS — 라이브러리 세 줄 설명

> 서술형 · 면접에서 «이건 왜 썼나» 에 답하는 한 장. 줄마다 **역할 · 어디에 · 실패하면**.
> 판 고정은 requirements.txt · 부품 창고 lib/ 의 어느 파일이 쓰는지는 괄호.

## nicegui (3.18.0)
- 역할: 파이썬만으로 웹 화면(버튼 · 표 ui.aggrid · 그래프 ui.echart). 안쪽은 FastAPI 서버 + Vue/Quasar 화면
- 어디에: src/ui/app.py · 0.0.0.0 바인딩 · 오래 걸리는 호출은 async 함수 + await(화면 멈춤 방지)
- 실패하면: 포트가 이미 쓰이면 시작 실패 · 동기 블로킹 호출(time.sleep · 동기 httpx)이 화면 전체를 멈춤 · 브라우저 콘솔과 서버 로그를 같이 봄

## pandas
- 역할: 표 데이터 — CSV · 엑셀 읽기, 거르기 · 묶기(groupby) · 합치기(merge)
- 어디에: data/ 입력 정리 · 집계 · 화면 표에 넘길 행 만들기 · CSV 내보내기는 encoding="utf-8-sig"(엑셀 한글)
- 실패하면: 인코딩 틀리면 UnicodeDecodeError · 열 이름 틀리면 KeyError · 숫자 열에 글자가 섞이면 형이 object 로 바뀌어 계산이 조용히 틀림 → 읽은 직후 dtypes · 결측 개수 확인

## numpy
- 역할: 숫자 배열 계산(평균 · 표준편차 · 벡터 연산) — pandas 의 바닥
- 어디에: 통계 · 관리 한계선 · 판정 수치 계산(core/)
- 실패하면: 모양(shape)이 안 맞으면 ValueError · 빈 배열 평균은 경고 + nan → 판정 전에 개수 확인

## httpx
- 역할: HTTP 호출 — 동기(Client) · 비동기(AsyncClient) 같은 모양 · timeout 기본 지원
- 어디에: src/api/client.py 한 곳(외부 호출 격리) · 시험은 MockTransport 로 네트워크 없이(tests/conftest.py · lib/testing/fake_api.py)
- 실패하면: 제한 시간 넘김 → TimeoutException(→ ExternalTimeout) · 연결 실패 → ConnectError(→ ExternalError) · 4xx · 5xx 는 예외가 아니라 status_code 로 옴 → 직접 확인

## openpyxl (3.1.5)
- 역할: 엑셀(.xlsx) 읽기 · 쓰기 엔진 — pandas read_excel · to_excel 가 안에서 부름
- 어디에: 엑셀 입력 · 엑셀 결과물(out/)
- 실패하면: 없으면 pandas 가 «Missing optional dependency 'openpyxl'» · .xls(옛 형식)는 못 읽음

## matplotlib
- 역할: 그림 파일(PNG) 그래프 — 화면 그래프는 ECharts(ui.echart), 이건 차선책
- 어디에: 보고서용 PNG 를 out/ 에 저장(savefig) · 서버에선 Agg 백엔드(창 없이)
- 실패하면: 한글 글꼴을 안 정하면 글자가 네모(□) → assets/fonts 글꼴 지정 · 창 띄우는 백엔드면 서버에서 멈춤

## PyYAML
- 역할: config/config.yaml 읽기(yaml.safe_load)
- 어디에: 설정 로더(lib/observe/obs_config.py) — 주소 · 포트 · timeout · 임계값
- 실패하면: 들여쓰기 · 콜론 틀리면 YAMLError(→ InputError 로 시작 멈춤) · 빈 파일은 None → 빈 dict 로 받음 · yaml.load(안전하지 않음) 쓰지 않음

## python-dotenv
- 역할: .env 파일의 KEY=값 을 환경변수로 올림(load_dotenv)
- 어디에: 앱 시작 때 한 번 · 코드는 os.environ 으로만 읽음(비밀값을 코드 · 설정에 안 씀)
- 실패하면: .env 가 없어도 조용히 넘어감 → 필수 키는 따로 검사 · 기본은 이미 있는 환경변수를 덮지 않음(override=False)

## pytest (9.2.0) · pytest-asyncio
- 역할: 시험 실행 — test_*.py 의 test_ 함수를 모아 돌림 · 픽스처(conftest.py) · parametrize(경계값 표)
- 어디에: tests/ · 커밋 관문 python3 -m pytest -q 종료코드 0 · 버그 재현은 xfail(strict)
- 실패하면: 실패 줄과 기대 · 실제 값을 보여 줌 · import 오류는 수집 단계에서 전체 실패 · 저장소 루트에서 돌리면 부품 창고까지 수집될 수 있어 폴더를 지정

## sqlite3 (표준 라이브러리)
- 역할: 파일 하나짜리 DB — 설치 없음 · SQL · UNIQUE · 트랜잭션
- 어디에: src/db/store.py · 중복 방지는 UNIQUE + ON CONFLICT DO UPDATE(upsert) · 외래키는 연결마다 PRAGMA foreign_keys = ON
- 실패하면: 다른 연결이 쓰는 중이면 «database is locked»(timeout 초만큼 기다린 뒤) · 제약 위반은 IntegrityError · 커밋을 안 하면 변경이 사라짐(with conn 으로)
