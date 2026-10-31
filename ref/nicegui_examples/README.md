# NiceGUI 공식 예제 59개

출처 github.com/zauberzeug/nicegui/examples(커밋 2ac585d · 원본 그대로 · MIT, LICENSE). 참고용 — **필요한 함수만 꺼내 쓴다**(예제를 통째로 결과물로 쓰지 않는다 · 가져온 것과 이유를 WORKLOG 에 한 줄).
- ⭐ = 대회 과제(현황판 · 표 · 업로드 · API · DB · LLM)에 바로 쓸 만한 것
- 추가 설치 칸이 비어 있으면 nicegui 만으로 돈다. 칸이 차 있으면 🔴 pip · 외부 프로그램이 필요하다 — 대회장에서 설치가 막힐 수 있으니 고르기 전에 확인
- 실행: `cd ref/nicegui_examples/<예제> && python3 main.py` (포트 8080 기본 · 0.0.0.0 으로 보려면 ui.run(host="0.0.0.0"))
- 부품 하나의 사용법만 필요하면 ../nicegui_docs/ (부품별 공식 문서 예제)

| 예제 | 무엇 | 추가 설치 |
|---|---|---|
| ⭐ api_requests | 외부 API 를 불러 결과 표시(비동기 httpx) | |
| ⭐ chat_app | 말풍선 대화창 | |
| ⭐ chat_with_ai | AI 대화창(langchain) | 🔴 langchain_openai · html-sanitizer |
| ⭐ download_text_as_file | 메모리 안 문자열을 파일로 내려받기 | |
| ⭐ editable_ag_grid | AG Grid 행 추가 · 편집 · 삭제 | |
| ⭐ editable_table | ui.table 행 추가 · 편집 · 삭제 | |
| ⭐ fastapi | 기존 FastAPI 앱에 NiceGUI 붙이기 | |
| ⭐ global_worker | 무거운 계산을 일꾼 프로세스로 · 진행률 | |
| ⭐ local_file_picker | 서버 쪽 파일 고르기 대화상자 | |
| ⭐ menu_and_tabs | 상단 바 · 접히는 메뉴 · 탭 | |
| ⭐ modularization | 여러 파일로 나눈 앱 구조 | |
| ⭐ openai_assistant | OpenAI Assistant API 비동기 호출 | 🔴 openai |
| ⭐ pandas_dataframe | pandas 데이터프레임을 편집 가능한 표로 | |
| ⭐ progress | 무거운 계산 진행률 바 | |
| ⭐ pytests | NiceGUI 앱 pytest 시험 | 🔴 pytest-selenium(user 픽스처만 쓰면 불필요) |
| ⭐ script_executor | 고른 스크립트 실행 · 출력 표시 | |
| ⭐ search_as_you_type | 입력할 때마다 API 검색(디바운스) | |
| ⭐ single_page_app | 새로고침 없는 페이지 이동 | |
| ⭐ slots | Quasar 슬롯으로 부품 꾸미기 | |
| ⭐ sqlite_database | SQLite CRUD(비동기 ORM) | 🔴 tortoise-orm |
| ⭐ table_and_slots | 표 칸 안 단추 · 입력 · 검색 · 페이지 넘김 | |
| ⭐ todo_list | 체크 목록 · 입력 · 진행 표시 | |
| ⭐ trello_cards | 끌어 놓는 카드 열(칸반) | |
| 3d_scene | WebGL 3D 장면 · STL | |
| ai_interface | 음성 → 글자 · 이미지 생성(replicate) | 🔴 replicate |
| audio_recorder | 녹음 · 재생 · 내려받기 | |
| authentication | 세션 로그인 화면 | |
| custom_binding | 사용자 정의 바인딩 | |
| custom_vue_component | Vue 부품 직접 만들기 | |
| descope_auth | Descope 로그인 | 🔴 descope |
| device_control | IoT 장치 제어 화면 | |
| docker_image | 공식 Docker 이미지 사용 | 🔴 docker |
| ffmpeg_extract_images | 동영상에서 그림 뽑기 | 🔴 ffmpeg 프로그램 |
| fullcalendar | 달력(FullCalendar js 동봉) | |
| generate_pdf | 입력 폼 → SVG 미리보기 · PDF | 🔴 pycairo · html-sanitizer |
| google_oauth2 | 구글 OAuth2 로그인 | 🔴 authlib · 구글 키 |
| google_one_tap_auth | 구글 원탭 로그인 | 🔴 구글 키 |
| image_mask_overlay | 그림 위 마스크 겹치기 | |
| infinite_scroll | 무한 스크롤 그림 목록 | |
| lightbox | 썸네일 누르면 크게 | |
| nginx_https | NGINX 뒤 HTTPS | 🔴 nginx |
| nginx_subpath | 리버스 프록시 하위 경로 | 🔴 nginx |
| node_module_integration | NPM 모듈 여러 개 붙이기 | 🔴 node · npm |
| opencv_webcam | 웹캠 캡처 | 🔴 opencv-python · 카메라 |
| pyserial | 시리얼 장치 통신 | 🔴 pyserial · 장치 |
| reaktiv | 반응형 신호로 주문 계산기 | 🔴 reaktiv |
| redis_storage | 여러 인스턴스가 Redis 로 저장소 공유 | 🔴 redis 서버 |
| ros2 | ROS2 로봇 웹 화면 | 🔴 ROS2 |
| signature_pad | 서명 패드(NPM 부품) | 🔴 node · npm(빌드 시) |
| simpy | SimPy 신호등 시뮬레이션 | 🔴 simpy |
| slideshow | 키보드 슬라이드 쇼 | |
| stripe | Stripe 결제 | 🔴 stripe · 키 |
| svg_clock | ui.timer 로 SVG 시계 갱신 | |
| threaded_nicegui | 별도 스레드에서 NiceGUI 실행 | |
| vue_vite | Vite 로 Vue 단일 파일 부품 | 🔴 node · npm |
| webserial | 브라우저 WebSerial 통신 | 🔴 장치 |
| websockets | 웹소켓 서버 같이 띄우기 | 🔴 websockets(nicegui 가 이미 깔 수 있음) |
| xterm | 브라우저 터미널 ↔ Bash | |
| zeromq | ZeroMQ PUSH/PULL | 🔴 pyzmq |
