# devview — 코드 · md · git 이력 보기/편집 (웹 IDE 미리보기 칸용)

대회 웹 IDE 처럼 프로그램을 설치하기 어려운 곳에서, 작업 폴더를 **PyCharm 비슷하게** 보고 고치는 도구.
파이썬 표준 라이브러리 서버 하나 + 미리 빌드한 화면 파일이라 **pip · npm 설치 없이** 돈다. IDE 의 브라우저 미리보기 칸에 포트를 넣어 연다.

## 켜기 · 끄기

- 연습 IDE(probe_ide) 터미널에서
  - bash <키트 폴더>/devview/dv        (키트(AGENTS.md · docs 가 있는 곳)를 포트 8701 로 · 키트가 /home/user/kit 이면 bash /home/user/kit/devview/dv)
  - 미리보기 칸 PORT 에 8701 → 원형 화살표
  - 끄기: bash …/dv stop · 상태: bash …/dv status · 다른 포트: bash …/dv 8702
  - md 의 .html 링크(표 밖은 Ctrl+클릭 · 표 안은 클릭) · Book 탭의 책 → devview 와 같은 주소의 `/pg/<경로>` 에서(새 탭 · 주소도 복사) — 대회 브라우저는 다른 주소(포트) 이동이 막혀 페이지 서버(포트 + 100 · 기본 8801)는 흰 화면이었다(2026-11-05) · 페이지 서버는 예전 주소 호환으로만 남음(끄기 --page-port 0)
  - md 의 다른 링크(같은 누름) → 옆 칸에 열기(칸이 하나면 오른쪽을 펼치고 나뉘어 있으면 그 칸을 다시 씀 · md 는 그대로) · 자리 = `#제목` · `#L12`(줄) · CSV `#row=12&col=3`(row = 표 # 칸 · col = 열 번호나 열 이름 · 표로 보기로 바꿔 표시) · PDF `#page=3`
- 대회(키트를 ~/kit 에 clone 했다면): bash ~/kit/devview/dv
- 직접: python3 devview.py <작업 폴더> [--host 0.0.0.0] [--port 8701]
  - 0.0.0.0 에 묶어야 대회 미리보기가 열린다(응시 가이드 5장)
  - 서버 기록: ~/.devview/devview.log (작업 폴더 밖 — 제출물에 안 섞임)

## 화면

- **그래프 탭**(노드를 고르고 Alt+Q = MAIN 마법봉 · 그래프 안 · 편집기 · 책 안에서도): flowtree(작업 그래프 · 2차판 시점에 쉬운 것만 초안 · 논의 뒤 보강 — $graph)를 /ft/ 아래로 담음 — 서버 하나 · 포트 하나 · flowtree 는 devview/flowtree/(빌드된 화면 · npm 불필요)
  - 처음 연 브라우저(저장된 보기 없음) = 그래프 · Browser 도구 복귀(저장된 보기 있음) = 보던 보기 그대로 — 돌아올 때마다 그래프로 튀지 않게 · 🔴 패키지판만(로컬 원본은 열 때마다 그래프)
  - tree.json: --tree 경로 → 작업 폴더/docs/flowtree/tree.json(같은 폴더에 tree.auto.json · tree.user.json) · 노드 doc 경로의 기준 = 작업 폴더
  - tree.json 이 없어도 그래프 탭은 «그래프 파일 없음: <기대 경로>» 한 줄 · 생기면 2초 안에 그려짐
  - flowtree 찾는 순서: devview/flowtree → devview/../flowtree · 못 찾으면 그래프 탭에 «flowtree 없음» · 첫 화면은 코드
  - 노드를 고르고 ` (입력 칸 밖) → 오른쪽 절반에 연결 내용 · ` · Esc · 머리 × 로 원래 패널
    - 파일 노드(path) · doc 칸이 있는 노드 → 그 파일을 기존 보기(편집기 · md · PDF · 엑셀)로 · 앵커가 있으면 그 줄로 · 파일 트리는 숨김
    - 모듈 노드(기능 화면 모듈 · 코드 화면 모듈 · 함수 줄) → «모듈 설명»(함수마다 바로 위 주석 · 부르는 것 · 부르는 곳 · 연관 기능) — 파일로 저장 안 하고 그 자리에서 그림
    - 모듈 설명의 함수 이름 · 행 번호 → 그 파일 그 줄 · 부르는 것 · 부르는 곳 이름 → 같은 모듈이면 그 상자, 다른 모듈이면 그 모듈 설명
    - 연결 문서가 없는 노드 → 세부 보기(오른쪽 절반 · 노드 우하단 세부 단추와 같은 자리)
  - 작업 · 검증 · 질문 노드(상태 색 테두리 · 빙글 · 점멸) · 키 1 질문 노드 · 세부 단추 — 규칙 · 조작 정본은 키트 docs/flowtree.md
    - Codex 세션 · 서브는 python3 devview/flowtree/flowtree.py --role main|2nd|insp … 로만 tree.json 에 쓴다(잠금 · 역할 칸 강제 · insp = 검증 서브가 쓰는 역할 코드) · 화면의 질문은 /ft/api/act(역할 user)
  - --start-view code: 저장된 보기가 없을 때도 코드로 시작
  - 화면 전환 스위치 Main | 섹션0~8(유저 지정 11/04 · 위치는 화면마다 따로 · 규칙 정본 docs/flowtree.md 2절)
  - 시험 python3 devview/tests/test_flowtree.py · test_flowtree_screens.py (키트 루트에서 · 윈도우는 py -3)
- **코드 탭**: 파일 트리(git 상태 색) · 탭 · 편집기
  - 코드 → Monaco(VS Code 편집기) + **PyCharm 2025.2 «Dark» 색**(설치본의 색 구성 원본에서 뽑은 값) · PyCharm 키맵
  - md → mdview 라이브 프리뷰 편집기(옵시디언식 — 커서가 있는 줄만 원문, 나머지는 렌더)
    - 표: 칸을 누르면 표는 그린 채로 그 칸 원문만 고침 · Enter · 칸 밖 클릭 = 확정(바로 저장) · Esc = 취소 · Tab = 다음 칸 · 키보드로 들어가면 표 전체 원문
  - 보던 탭 · 열린 파일 · 보기를 서버 ~/.devview/state.json 에도 저장 — 빈 저장소로 새로 열려도(Browser 도구 복귀) 복원 · 🔴 패키지판만(로컬 원본엔 없음) · 시험 devview/tests/test_restore.py
  - 그림 → 그대로 보기 · CSV → «표로 보기» · 바이너리 · 5MB 초과 → 안 엶
  - PDF → 브라우저 내장 PDF 보기 · 엑셀(.xlsx · .xlsm) → 시트 탭 + 표(시트당 앞 2,000행 · 200열, 수식 칸은 저장된 계산값, 날짜 서식은 날짜) · 워드(.docx) → 제목 · 문단 · 표 순서대로 — 모두 읽기 전용(저장 · 편집 없음) · .xls · .doc 는 «미지원 형식» 한 줄 · 시험 devview/tests/test_office.py
- **Git 탭**(Alt+9): 브랜치 그래프 · 커밋 상세 · 바뀐 파일 · 나란히/한 줄 diff · 파일 이력 · 커밋하지 않은 변경 · 검색 · 브랜치 고르기
  - 읽기 전용 — 커밋 · 스테이징은 터미널(Codex)로
- **설문 탭**(Ctrl+Alt+2): 설문 도구(survey.py)를 찾으면 나타남 — 배지 = 답하지 않은 설문 수
  - 왼쪽: 프로젝트 목록 → 고른 프로젝트의 대기 · 질문 · 완료(회색) / 오른쪽: 대기 설문은 답하는 폼, 완료 설문은 당시 답 · 메모를 읽기 전용으로
  - 대기 · 완료 = 설문 폼(선택지)만 · 질문 = 설명 폼 전부(답할 것이 위 · 끝난 것은 회색)
  - 새 설문이 등록되면 2초 안에 설문 탭 **안에서** 그 설문이 열림(쓰던 답이 있으면 알림만) — 보던 화면은 그대로 두고 아래 알림 «새 설문 — Alt+S» · 배지만
  - 열 때 첫 화면 = 마지막 보기(설문이었으면 코드) — 설문 주소(?sv=…)로 열어도 설문으로 바로 가지 않는다. Browser 도구가 다른 도구에서 돌아올 때마다 페이지를 새로 열어 그때마다 설문으로 튀었다(2026-10-30 유저 지정)
  - 🔴 이 두 줄은 이 패키지판만 그렇다 — 로컬 원본(probe_ide\tools\devview)은 지금도 설문으로 넘어간다. 원본에서 static/js/main.js 를 다시 복사할 때 이 동작을 되살리지 않는다
  - 설문 도구 찾는 순서: --survey 경로 → 작업 폴더/.agents/skills/survey/survey.py → devview 옆 ../.agents/skills/survey/survey.py
  - 화면 · 저장은 survey.py 가 맡고 devview 는 /sv/ 아래로 연결만 한다 — survey.py 를 따로 띄워도 같은 화면
- **화면 캡처**(우상단 카메라 · Ctrl+Alt+P): 지금 보이는 화면(코드 · Git · 설문 · 팝업)을 PNG 로 그려 작업 폴더 docs/captures/날짜_시각_보기.png 에 저장 → Codex 가 그 파일을 열어 화면을 본다
  - html2canvas(static/html2canvas.min.js · MIT)가 화면을 다시 그림 — 권한 창 없이 IDE 미리보기 칸 안에서도 됨 · 0.6~3초
- **코덱스 허브**(모든 보기 좌하단 · 대화 보기 제외 · 아래 끝 = 그래프 미니맵 아래 끝 · 안쪽 800 × 150 · 30px 행 5개 · 넘치면 세로 스크롤)
  - 행 = Codex 세션(기본 MAIN · 2ND + 추가 등록 순) · 닉네임 | effort(○ low · ◐ medium · ● high · ◎ xhigh · 모르면 ?) | 맥락 «154k/258k (60%)» | 지금 작업(넘치면 … · 올리자마자 툴팁)
  - 행 테두리 = 상태: 작업 중 노랑 빙글 · 턴 끝(새 최종 답변) 녹색 점멸 · 오류(task_complete.error) 빨강 점멸 → 그 행을 누르면(확인) 테두리 사라짐 · 대기 = 없음
  - 행 클릭 = 누적창(허브 바로 위 · 같은 크기 · 줄마다 녹색 점 · 열면 맨 아래) + 행 오른쪽 허브 밖 아이콘 트레이(문서 = 직접 입력 · 마법봉 = 역할 magic · 추가 세션은 문서만) · Esc = 선택 해제
  - 입력창(허브 위 · Enter 줄바꿈 · 밖 오른쪽 아래 ✕ 취소 · ✈ 전송 · Esc 로 안 닫힘) → codex queue · 실패하면 빨간 알림 · 글 남김 · 모서리 작은 단추 = 접기(한 줄)
  - 마법봉: MAIN = 그래프에서 고른 노드(Ctrl+클릭 여럿 · 작업 · 검증 · 질문을 종류로 서브에게 나눔) · 2ND = 질문 입력창 → 누른 순간의 보기 · 선택(그래프 노드 · 코드 탭 파일 · 고른 줄 · md 표 칸 · Git 커밋 · 파일)으로 요청 · 입력하는 동안 고른 범위 덧칠
  - 2ND 그래프 · Git · 설문 · 앱 질문은 보내는 순간 devview 가 유저 이름으로 질문 노드를 등록(대상마다 선 · 고른 것 없으면 섬)
  - 세션 쪽: 키트 스킬 $codex-hub(hub.py register · status · log · send) · $main-magic · $2nd-magic(magic.py) — 파일은 작업 폴더 .codex-hub/(git 제외)
  - 마법봉 글 = `🪄 지시 본문` + 끝 줄 `$역할-magic 요청id`(유저 메시지로 기록 · 요청 파일 message 에도 저장) · 세션끼리 = `hub.py send --to 이름 '글'` → 글 앞 `@보낸이름` · 설문 알림 = `@설문` · 책 스티커 🪄 = 페이지 서버 `api/notes/<id>/magic`
- **대화 탭**(그래프와 코드 사이): 허브에 붙은 세션의 대화를 Codex 기록에서 바로(모델에게 시키지 않음) — 🚹 유저 메시지(줄 전체 강조) · 🔁 `@이름` 으로 시작하는 세션끼리 글(연녹색 + 이름 칩) · 🪄 마법봉 글(칩 + 보라 띠) · 🤖 최종 답변 · 오류만(주입 문서 · 도구 · 생각 뺌)
  - 위 = 세션 탭(테두리 규칙 = 허브 행 · 그 탭을 열면 점멸 꺼짐) · Alt+←→ 탭 전환 · 휠 · PageUp/PageDown 이력
  - 입력: Enter 줄바꿈 · 보내기 = Ctrl+Enter(codex queue · 보낸 글은 기록에 들어올 때까지 «보냄 · 대기열» 줄) · 작업 중 혼잣말(commentary)은 흐린 줄 · 기호 단축키 그대로 · 아래 = 맥락 · 모델 · effort · 이 보기에서는 허브 숨김
  - 서브 패널(대화 오른쪽 아래 · 입력창 바로 위 · 보기 전용 · 서브가 없으면 숨김 · 접기 단추): 고른 세션의 서브만 · 줄 = 이름 · 일함/쉼/중단 · 지금 일 한 줄(지시 → 도구 호출 → 혼잣말 · 쉼이면 마지막 결과) · 8줄 넘으면 스크롤 · 서브 기록(rollout)만 이어 읽음(모델 호출 없음 · 메모리에서 내려간 서브는 쉼과 구별 못 함 · 서브가 받은 지시는 암호화돼 있으면 못 읽음)

- **알림 종**(모든 보기 좌하단 맨 왼쪽 · 끌어서 옮김 · 더블클릭 = 기본 자리 · 허브(펼침 · 접힘 · 최소화) 기본 자리는 그 오른쪽 = css --dv-hub-left · --dv-hub-min-left 60px): 우상단 배지 = 안 읽은 개수 · 누르면 목록 창 → 하나 누르면 그 위치로 + 읽음 · «모두 읽음»
  - 자동 수집(서버가 1.5초마다): tree.json 작업 완료 · 이상(🔴) · 보류 / 검증 정상 · 비정상(🔴) / 질문 답 / 설문 반영 · 책 notes.json 답 · 꼬리 답 · 설문 도구 새 설문 · 전달 실패(🔴) · 허브 세션 입력 · 승인 대기 — 처음 보는 출처는 기준점만(지금 기록은 알림 안 함)
  - 세션 · 서브가 직접: `python3 devview/notify.py add --kind done --title "t3 완료" --to graph:t3` (윈도우 `py -3`) · --to = graph:<id> · book:<책>:<스티커>[:<꼬리>] · survey:<id> · hub:<닉> · file:<경로>[:<줄>] · view:<보기> · 종류 = done · block · hold · pass · fail · answer · decide · magic · queue-fail · report · info 등 · 서버가 꺼져 있어도 됨
  - 저장 = 키트 .codex-hub/notify.jsonl(덧붙이기 · 잠금 · 읽음 기록도 같은 파일) · 본 기록 열쇠 = notify_seen.json · 이동: 그래프 = iframe 에 {ft:'focus', node, screen?} · 책 = 책 주소#note=<id>[&t=<꼬리>]

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
| 트리 · Git 탭               | Alt+Shift+1 · Alt+9                      |
| 그래프 화면                 | Alt+` = Main · Alt+1~8 = 섹션1~8 · Alt+0 = 섹션0 (어느 보기에서든) |
| 연결 내용                   | ` (입력 칸 밖 · 다시 ` · Esc 닫기)       |
| MAIN 마법봉                 | Alt+Q (그래프에서 고른 노드로 · 허브 단추와 같음 · 그래프 · 편집기 · 책 안에서도) |
| 2ND 마법봉                  | Alt+W (허브 단추와 같음 · 그래프 · 편집기 · 책 안에서도 · 책은 고른 메모 · 편집기 찾기의 단어 단위 Alt+W 는 단추로) |
| 예비 마법봉                 | Alt+[ = MAIN · Alt+] = 2ND 즉시 · Alt+; = MAIN · Alt+' = 2ND 지시 붙음 (Alt+Q · W · E · R 과 같은 동작 · 그 키가 브라우저에 뺏길 때) |
| 지시 붙은 마법봉            | Alt+E = MAIN · Alt+R = 2ND (누른 순간의 선택 = 노드 · 파일 줄 · 글자 · Git · 책 스티커 → 허브 입력창에 지시 → ✈ · 노드 없어도 · 자동 전송 없음) |
| 글자 크기                   | Ctrl+휠                                  |

- 왼쪽 변경 막대(HEAD 대비 초록 · 파랑 · 회색 삼각) 클릭 → 옛 내용 · «되돌리기»(Ctrl+Z 로 취소 가능)
- 위쪽 «HEAD 비교»(그 창에서 고쳐도 됨) · «이력» · «주석»(줄마다 마지막 커밋 · 작성자, 줄 번호 클릭 → Git 탭)
- 자동 들여쓰기: «:» 다음 줄 4칸 · return · pass · break · continue · raise 다음 줄 내어쓰기
- 🔴 브라우저가 먼저 가져가는 키는 못 막음: Ctrl+W(탭이 닫힘!) · Ctrl+N · Ctrl+T · Ctrl+Shift+N/W/T · Ctrl+Tab. PyCharm 의 Ctrl+W(선택 넓히기) 대신 Alt+Shift+→
- F5 · Ctrl+R(새로고침) · Alt+← · 마우스 뒤로 버튼(뒤로 가기)은 devview 안에서 막아 둠 — IDE 페이지가 새로고침 · 뒤로 가기 되지 않게

## 구조

- devview.py — 서버(표준 라이브러리 · 파이썬 3.8+). API: info · tree · file · save · create · raw · office · search · symbols · poll · git/(info · log · commit · status · blob · file-log · blame)
  - office?path=&sheet= — xlsx · docx 를 zipfile + xml.etree 로 해석해 json(시트 이름 · 줄 / 블록). 옛 형식 415 · 깨진 파일 422 «읽기 실패: …»
  - git 은 읽기 명령만 · GIT_OPTIONAL_LOCKS=0(폴링이 index.lock 을 안 잡음 → Codex 커밋과 충돌 없음)
  - 쓰기 요청은 X-Devview 머리글 필수 · 작업 폴더 밖 경로(.. · 밖을 가리키는 링크) 차단
  - /api/ · /static/ 앞에 프록시 접두어가 붙어도 처리(화면도 상대 주소)
  - /ft/… — flowtree server.py 의 handle() 로 넘김(화면 · /ft/api/data · user · scan · source · act) · 쓰기는 X-Devview 머리글 필수
  - codex/sessions?limit=&thread= — Codex 세션 상태 목록(codex_sessions.py)
  - 보내기 = steer.py(앱 서버 소켓 ~/.codex/rs/app.sock → 턴 중 turn/steer · 쉬는 때 turn/start) → 안 되면 codex queue(턴 끝 뒤)
  - hub · hub/log?nick= · hub/chat?nick=&after=N · hub/subagents?nick=(GET) · hub/queue {nick, text} · hub/magic {nick, view, selection, question}(POST) — codex_hub.py · queue 는 셸 없이 인자 목록(윈도우는 codex.cmd 옆 node + codex.js · 시험은 DEVVIEW_CODEX)
- codex_hub.py — .codex-hub(등록 · 상태 줄 · 누적 · 요청) + rollout 결합 · 대화 뽑기(item_completed UserMessage 정본 · 옛 판은 유저 역할 글에서 주입 문서 거름 · phase final_answer · 없으면 턴 끝 답) · queue · magic(요청 파일 · 질문 노드 즉시 등록)
- codex_sessions.py — ~/.codex/sessions/**/rollout-*.jsonl 이벤트로 세션마다 상태(작업 중 · 대기 · 설문 · 권한 요청) · 연결(추정) · 맥락 % · 마지막 이벤트 시각 · 작업 폴더 · 세션 id
  - 맥락 % = 마지막 token_count 의 last_token_usage.total_tokens ÷ model_context_window · 세션 id = session_meta.id(= 파일 이름 끝 = CODEX_THREAD_ID)
  - 확실하지 않은 판정은 sure=false · basis 에 «추정» · 권한 요청은 승인 요청 이벤트(이름에 approval) 기준 · 대화 본문은 내보내지 않음
- flowtree/ — 그래프 화면(server.py · flowtree_store.py · flowtree.py · scan_code.py · tree_check.py · static/ 빌드 결과). 파이썬은 이 폴더가 정본 · 화면 소스는 로컬 probe_ide\tools\flowtree\web\src
  - 화면 빌드: cd probe_ide\tools\flowtree\web · node build.mjs --kit "<키트>/devview/flowtree/static/flowtree.js"(flowtree.css 도 같은 폴더에 나옴 · 온톨로지 화면을 뺀 키트판)
  - 🔴 npm run build 는 쓰지 않는다 — 로컬 static 을 덮어써서 로컬 파이썬과 어긋난다 · 로컬 파이썬(화면 전환 · 틀 없음)을 이 폴더로 복사하지 않는다
- static/ — 화면. js/(main · editor · docs · theme · tree · git · graph · changes · blame · search · popup · diffutil · api · util · flow · chat · hub) · app.css · index.html
  - flow.js — 그래프 탭(flowtree iframe) · 연결 문서 오른쪽 절반 열기/닫기 · flowtree 와 postMessage({ft: open · close · closed})
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
- py -3 tests/test_office.py — PDF · 엑셀 · 워드 보기(API 23 + 헤드리스 화면 20 · 캡처 tests/shots/office_*.png) · --api 는 API 만(WSL python3 23개)
- py -3 tests/test_flowtree.py — 그래프 탭(/ft/ API · 첫 화면 · Alt+Q MAIN 마법봉 · ` 파일 열기와 앵커 줄 · 닫기 · 모듈 설명 · tree 없음) · 캡처 tests/shots/ft_*.png
- py -3 tests/test_keys_links.py — md 링크 옆 칸 · 자리 옮기기 · 책 iframe 안 Alt+Q · W · B · 책 «새로» 막대(헤드리스 · 캡처 tests/shots/md_link_split.png · book_new_bar.png)
- py -3 tests/test_codex_sessions.py — Codex 세션 판정(가짜 jsonl 조각 · 상태별 · 맥락 %) · WSL python3 도 됨
- py -3 tests/test_hub.py — 코덱스 허브 · 대화 탭(API 41 + 헤드리스 화면 64 · 가짜 Codex 홈 · 가짜 codex) · --api-only 는 API 만(WSL python3) · 캡처 tests/shots/hub_*.png
- py -3 tests/test_hub_subs.py — 대화 탭 서브 패널(판정 · 부모별 묶음 · 증분 읽기 · 한 줄 · 헤드리스 화면) · --api-only 는 브라우저 없이(WSL python3) · 캡처 tests/shots/hub_subs_*.png
- 옛 화면 시험(test_office · test_doc_keys · test_restore)은 코드 보기 기준 — test_office 는 --start-view code 로 띄움
- py -3 -m pytest -q tests/test_notify.py — 알림 종 로직(스크립트 · 동시 덧붙이기 · 자동 수집 · 서버 API) · WSL python3 도 됨(서버 시험 빼고)
- py -3 tests/test_notify_ui.py — 알림 종 화면(배지 · 목록 · 이동 · 읽음 유지 · 끌기 · 모든 보기) · 캡처 tests/shots/notify_*.png
- 모두 임시 폴더 · 시험 서버만 쓴다(실제 ~/workspace · 6090 무관)

## 한계

- 파이썬 정의로 이동 · 구조는 정규식 기반(언어 서버 아님) — 같은 이름이 여러 곳이면 후보 목록
- 색은 글자 모양 기반이라 PyCharm 의 의미 분석 색(매개변수 · 안 쓰는 변수 회색)은 없음
- 아이콘 모양: Lucide(ISC) · 글꼴: JetBrains Mono(OFL, static/fonts/JetBrainsMono-OFL.txt)
