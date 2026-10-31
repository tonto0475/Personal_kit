# devview — 코드 · md · git 이력 보기/편집 (웹 IDE 미리보기 칸용)

대회 웹 IDE 처럼 프로그램을 설치하기 어려운 곳에서, 작업 폴더를 **PyCharm 비슷하게** 보고 고치는 도구.
파이썬 표준 라이브러리 서버 하나 + 미리 빌드한 화면 파일이라 **pip · npm 설치 없이** 돈다. IDE 의 브라우저 미리보기 칸에 포트를 넣어 연다.

## 켜기 · 끄기

- 연습 IDE(probe_ide) 터미널에서
  - bash <키트 폴더>/devview/dv        (키트(AGENTS.md · docs 가 있는 곳)를 포트 8701 로 · 키트가 /home/user/kit 이면 bash /home/user/kit/devview/dv)
  - 미리보기 칸 PORT 에 8701 → 원형 화살표
  - 끄기: bash …/dv stop · 상태: bash …/dv status · 다른 포트: bash …/dv 8702
- 대회(키트를 ~/kit 에 clone 했다면): bash ~/kit/devview/dv
- 직접: python3 devview.py <작업 폴더> [--host 0.0.0.0] [--port 8701]
  - 0.0.0.0 에 묶어야 대회 미리보기가 열린다(응시 가이드 5장)
  - 서버 기록: ~/.devview/devview.log (작업 폴더 밖 — 제출물에 안 섞임)

## 화면

- **코드 탭**: 파일 트리(git 상태 색) · 탭 · 편집기
  - 코드 → Monaco(VS Code 편집기) + **PyCharm 2025.2 «Dark» 색**(설치본의 색 구성 원본에서 뽑은 값) · PyCharm 키맵
  - md → mdview 라이브 프리뷰 편집기(옵시디언식 — 커서가 있는 줄만 원문, 나머지는 렌더)
    - 표: 칸을 누르면 표는 그린 채로 그 칸 원문만 고침 · Enter · 칸 밖 클릭 = 확정(바로 저장) · Esc = 취소 · Tab = 다음 칸 · 키보드로 들어가면 표 전체 원문
  - 보던 탭 · 열린 파일 · 보기를 서버 ~/.devview/state.json 에도 저장 — 빈 저장소로 새로 열려도(Browser 도구 복귀) 복원 · 🔴 패키지판만(로컬 원본엔 없음) · 시험 devview/tests/test_restore.py
  - 그림 → 그대로 보기 · CSV → «표로 보기» · 바이너리 · 5MB 초과 → 안 엶
- **Git 탭**(Alt+9): 브랜치 그래프 · 커밋 상세 · 바뀐 파일 · 나란히/한 줄 diff · 파일 이력 · 커밋하지 않은 변경 · 검색 · 브랜치 고르기
  - 읽기 전용 — 커밋 · 스테이징은 터미널(Codex)로
- **설문 탭**(Alt+8): 설문 도구(survey.py)를 찾으면 나타남 — 배지 = 답하지 않은 설문 수
  - 왼쪽: 프로젝트 목록 → 고른 프로젝트의 대기 · 질문 · 완료(회색) / 오른쪽: 대기 설문은 답하는 폼, 완료 설문은 당시 답 · 메모를 읽기 전용으로
  - 대기 · 완료 = 설문 폼(선택지)만 · 질문 = 설명 폼 전부(답할 것이 위 · 끝난 것은 회색)
  - 새 설문이 등록되면 2초 안에 설문 탭 **안에서** 그 설문이 열림(쓰던 답이 있으면 알림만) — 보던 화면은 그대로 두고 아래 알림 «새 설문 — Alt+S» · 배지만
  - 열 때 첫 화면 = 마지막 보기(설문이었으면 코드) — 설문 주소(?sv=…)로 열어도 설문으로 바로 가지 않는다. Browser 도구가 다른 도구에서 돌아올 때마다 페이지를 새로 열어 그때마다 설문으로 튀었다(2026-10-30 유저 지정)
  - 🔴 이 두 줄은 이 패키지판만 그렇다 — 로컬 원본(probe_ide\tools\devview)은 지금도 설문으로 넘어간다. 원본에서 static/js/main.js 를 다시 복사할 때 이 동작을 되살리지 않는다
  - 설문 도구 찾는 순서: --survey 경로 → 작업 폴더/.agents/skills/survey/survey.py → devview 옆 ../.agents/skills/survey/survey.py → ~/.claude/skills/adr-survey/survey.py
  - 화면 · 저장은 survey.py 가 맡고 devview 는 /sv/ 아래로 연결만 한다 — survey.py 를 따로 띄워도 같은 화면
- **화면 캡처**(우상단 카메라 · Ctrl+Alt+P): 지금 보이는 화면(코드 · Git · 설문 · 팝업)을 PNG 로 그려 작업 폴더 docs/captures/날짜_시각_보기.png 에 저장 → Codex 가 그 파일을 열어 화면을 본다
  - html2canvas(static/html2canvas.min.js · MIT)가 화면을 다시 그림 — 권한 창 없이 IDE 미리보기 칸 안에서도 됨 · 0.6~3초

## 저장 규칙

- 코드: 입력이 멈추고 1초 뒤 자동 저장 · Ctrl+S 즉시 / md: 커서가 다른 블록으로 갈 때 · 포커스 이탈 · Ctrl+S(mdview 와 같음)
- 서버가 **디스크 내용 해시**를 대조 — 다른 곳(공식 IDE 편집기 · Codex)이 먼저 고쳤으면 덮어쓰지 않고 «외부 변경 충돌» 띠
  - 손대지 않은 파일이 밖에서 바뀌면 조용히 최신 내용으로
  - 띠의 «차이 보기» → 디스크 ↔ 내 내용 비교 창
- 인코딩(UTF-8 · UTF-8 BOM · CP949) · 줄바꿈(LF · CRLF) · 실행 권한은 원래 파일 그대로
- 🔴 같은 파일을 공식 IDE 편집기와 동시에 고치지 말 것 — 충돌 띠가 막아 주지만 한쪽에서만 고치는 게 안전

## 편의 기능 · 단축키 (F1 로 전체 표)

| 하는 일                     | 키                                       |
|-----------------------------|------------------------------------------|
| 파일 찾기(«이름:줄» 가능)   | Shift 두 번 · Ctrl+P                     |
| 최근 파일 · 내용 검색       | Ctrl+E · Ctrl+Shift+F                    |
| 정의로 이동 · 사용처        | Ctrl+B · F12 · Ctrl+클릭 / Alt+F7        |
| 파일 구조 · 줄로 이동       | Ctrl+F12 · Ctrl+G                        |
| 줄 주석 · 블록 주석         | Ctrl+/ · Ctrl+Shift+/                    |
| 줄 복제 · 줄 삭제 · 옮기기  | Ctrl+D · Ctrl+Shift+D · Alt+Shift+↑↓     |
| 다시 실행                   | Ctrl+Y · Ctrl+Shift+Z (유저 키맵)        |
| 이전/다음 위치 · 탭         | Ctrl+Alt+←→ · Alt+←→                     |
| 이전/다음 변경 · 경로:줄    | Ctrl+Alt+Shift+↑↓ · Ctrl+Alt+Shift+C     |
| 트리 · Git 탭               | Alt+1 · Alt+9                            |
| 글자 크기                   | Ctrl+휠                                  |

- 왼쪽 변경 막대(HEAD 대비 초록 · 파랑 · 회색 삼각) 클릭 → 옛 내용 · «되돌리기»(Ctrl+Z 로 취소 가능)
- 위쪽 «HEAD 비교»(그 창에서 고쳐도 됨) · «이력» · «주석»(줄마다 마지막 커밋 · 작성자, 줄 번호 클릭 → Git 탭)
- 자동 들여쓰기: «:» 다음 줄 4칸 · return · pass · break · continue · raise 다음 줄 내어쓰기
- 🔴 브라우저가 먼저 가져가는 키는 못 막음: Ctrl+W(탭이 닫힘!) · Ctrl+N · Ctrl+T · Ctrl+Shift+N/W/T · Ctrl+Tab. PyCharm 의 Ctrl+W(선택 넓히기) 대신 Alt+Shift+→
- F5 · Ctrl+R(새로고침) · Alt+← · 마우스 뒤로 버튼(뒤로 가기)은 devview 안에서 막아 둠 — IDE 페이지가 새로고침 · 뒤로 가기 되지 않게

## 구조

- devview.py — 서버(표준 라이브러리 · 파이썬 3.8+). API: info · tree · file · save · create · raw · search · symbols · poll · git/(info · log · commit · status · blob · file-log · blame)
  - git 은 읽기 명령만 · GIT_OPTIONAL_LOCKS=0(폴링이 index.lock 을 안 잡음 → Codex 커밋과 충돌 없음)
  - 쓰기 요청은 X-Devview 머리글 필수 · 작업 폴더 밖 경로(.. · 밖을 가리키는 링크) 차단
  - /api/ · /static/ 앞에 프록시 접두어가 붙어도 처리(화면도 상대 주소)
- static/ — 화면. js/(main · editor · docs · theme · tree · git · graph · changes · blame · search · popup · diffutil · api · util) · app.css · index.html
  - md.bundle.js · md.css — mdview 의 라이브 프리뷰 원본을 묶은 것(아래 빌드)
  - monaco/ — Monaco 0.52.2(probe_ide/web/vendor 에서 복사) · fonts/ — JetBrains Mono(OFL)
- web/ — 빌드 전용(실행에는 불필요): cd web · npm install · npm run build
  - mdview 원본(probe_desktop/tools/mdview/web/src)을 별칭으로 가져오고 CodeMirror 는 mdview 의 node_modules 한 벌로 고정(두 벌이면 빌드 실패로 멈춤)
  - mdview 를 고쳤으면 다시 빌드해야 devview 에 반영
- dv — 실행기(백그라운드 · PID 파일 ~/.devview/devview-<포트>.pid · 종료는 그 PID 만)

## 시험 (tests/)

- py -3 tests/test_api.py — 서버 API 76개(윈도우) · WSL 에서 python3 로 78개(실행 권한 · 심볼릭 링크 포함)
- py -3 tests/test_ui.py — 헤드리스 크롬 화면 72개(색 · 들여쓰기 · 주석 · 저장 · 충돌 · md · Git 탭 · 좁은 화면)
- py -3 tests/test_in_ide.py — 연습 IDE 시험 서버(6091) 터미널에서 띄우고 미리보기 칸(iframe) 안에서 조작 16개
- py -3 tests/shot.py [--open 파일] [--git] — 캡처만(tests/shots)
- 모두 임시 폴더 · 시험 서버만 쓴다(실제 ~/workspace · 6090 무관)

## 한계

- 파이썬 정의로 이동 · 구조는 정규식 기반(언어 서버 아님) — 같은 이름이 여러 곳이면 후보 목록
- 색은 글자 모양 기반이라 PyCharm 의 의미 분석 색(매개변수 · 안 쓰는 변수 회색)은 없음
- 아이콘 모양: Lucide(ISC) · 글꼴: JetBrains Mono(OFL, static/fonts/JetBrainsMono-OFL.txt)
