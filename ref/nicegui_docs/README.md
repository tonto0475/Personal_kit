# NiceGUI 공식 문서 예제 — 부품별

출처 github.com/zauberzeug/nicegui/website/documentation(커밋 2ac585d · 원본 그대로 · MIT, LICENSE). 인터넷 문서를 못 볼 때 부품 사용법을 찾는 곳.

- `content/<부품>_documentation.py` 하나 = 부품 하나(135개). 안의 `@doc.demo(...)` 함수 본문이 **그대로 돌릴 수 있는 사용 예**다 — 함수 본문만 복사해 `@ui.page("/")` 안에 넣으면 된다
- 파일 자체는 실행하지 않는다(문서 사이트 내부 모듈 `doc` 를 import 함)
- 찾기: `grep -l "ui.aggrid" ref/nicegui_docs/content/*.py` · 기능 이름으로 `grep -rn "def .*filter" ref/nicegui_docs/content/`
- 자주 볼 것: aggrid · echart · table · upload · chat_message · dialog · notify · linear_progress · timer · storage · page_layout · splitter · tabs · select · input · run
- 앱 하나가 통째로 필요하면 ../nicegui_examples/
