# How to run — 설비 점검 기록 앱 (예시)

> 🔴 **유저가 직접 쓴다 · 에이전트는 쓰지 않는다.** 이 파일은 유저가 참고하는 **모양 견본**(docs/examples/DEPLOY_PLAN_example.md 와 같은 가상 과제).
> 명령 · 버튼 이름 · 주소는 실제 앱 그대로 쓴다(채점 · 검토자가 그대로 따라 친다).

## 1. 실행
- 로컬 한 줄(저장소 루트에서): `bash kit/run.sh`
- 컨테이너 두 줄(저장소 루트에서):
	- `docker build -t app .`
	- `docker run --rm -p 3000:3000 -v app-data:/app/data app`
- 접속: http://localhost:3000 (서버는 0.0.0.0:3000 에 뜬다 · 포트를 바꾸려면 `PORT=8080 bash kit/run.sh` · 컨테이너는 `-e PORT=8080 -p 8080:8080`)

## 2. 시험 계정
- inspector / inspect123 — 켜질 때 없으면 자동으로 만든다(비밀번호는 환경변수 `TEST_PASSWORD` 로 바꿈)

## 3. 데이터 넣는 법
- 켜질 때 기본 데이터(설비 3대 · 점검 20건 · 고정 시드)가 자동으로 들어간다 — 따로 할 일 없음
- 추가: 화면 «점검 추가» 버튼 · CSV 는 «CSV 올리기» 버튼(양식 `data/sample_inspections.csv`) · API 는 아래 4번

## 4. 따라 하기
1. http://localhost:3000 접속 → «로그인» 에 시험 계정 입력
2. 왼쪽 «설비» 에서 «프레스-01» 선택
3. «점검 추가» → 결과 «불량» · 메모 입력 → «저장»
4. «점검 목록» 맨 위에 방금 줄이 보인다(21건)
5. «요약» 탭에서 불량 수가 1 늘었는지 확인
6. 같은 설비에 «불량» 을 3번 연속 저장하면 상단에 «연속 불량 알람» 띠가 뜬다

## 5. 설정

| 이름 | 기본값 | 뜻 | 바꾸는 곳 |
|---|---|---|---|
| PORT | 3000 | 서버 포트 | 로컬: 명령 앞 · 컨테이너: -e 와 -p |
| DB_PATH | data/app.db(컨테이너 /app/data/app.db) | SQLite 파일 | 같음 |
| DEFECT_LIMIT | 3 | 연속 불량 알람 기준 | 같음 |
| TEST_PASSWORD | inspect123 | 시험 계정 비밀번호 | 같음 |

## 6. 시험
- 로컬: `python3 -m pytest -q tests` (kit 폴더에서)
- 컨테이너 안: `docker run --rm app python -m pytest -q tests`

## 7. API 예시
- `curl -s http://localhost:3000/health`
- `curl -s http://localhost:3000/api/summary`
- `curl -s -X POST http://localhost:3000/api/inspections -H "Content-Type: application/json" -d '{"machine": "프레스-01", "result": "불량"}'`

## 8. Notes
- 이 제출 환경(대회 샌드박스)에는 docker 가 없어 컨테이너 빌드 · 실행을 직접 확인하지 못했다. Dockerfile 은 로컬과 같은 시작 명령(run.sh) · 같은 포트(3000)로 뜨게 썼고, 로컬 `bash kit/run.sh` 로 /health 200 · 시험 31 passed 를 확인했다
- 설계 · 결정 기록 · 섹션 작업 순서(인수인계): docs/hand_off.md «작업 개요» · 작업 흐름: docs/WORKLOG.md
