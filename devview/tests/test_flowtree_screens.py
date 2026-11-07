"""flowtree 화면 전환(Main | 섹션0 …) 시험 — test_hub 의 시험 세계(임시 폴더 · 가짜 codex · 빈 포트) + 헤드리스 크롬

    py -3 tests/test_flowtree_screens.py              결과 PASS/FAIL · 캡처 tests/shots/ft_screens_*.png
    CC_HEADED=1 py -3 tests/test_flowtree_screens.py  창을 띄워 눈으로 보기

단언 대상은 관측 결과: 화면의 노드 · 선 · 단추 크기 · tree.user.json · tree.json · 마법봉 요청 파일 · 가짜 codex 가 받은 인자
실제 ~/.codex · ~/.devview · 8701 무관
"""
import json
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

import test_hub as hub

# 캡처 폴더
SHOTS = hub.SHOTS
# 결과 기록 · 기다리기
check = hub.check
wait_for = hub.wait_for
# 단추로 만든 노드 제목(다음 노드는 옆자리에)
MADE = []
# Main 섬 질문 id
ISLAND = []


# 시험 재료 더하기 — 섹션 1 작업 t2 · 칸 없는 아래 작업 t3 · 검증 v2 · 설문 s1 · 질문 q1 · 파일 노드 f-sec(섹션 1) · t1 밑 v1 은 칸 없음
# tp: tree.json 경로
def seed(tp):
    sys.path.insert(0, str(hub.FLOWTREE))
    import flowtree_store as fs  # noqa: E402
    fs.apply(tp, "main", "add", parent="-", title="섹션 작업", summary="섹션 1", section=1)
    fs.apply(tp, "main", "add", parent="t2", title="아래 작업", summary="칸 없음")
    fs.apply(tp, "main", "verify-add", target="t2", what="섹션 검증")
    fs.apply(tp, "main", "survey-add", target="t2", question="섹션 설문", options=["가", "나"])
    fs.apply(tp, "user", "ask", text="섹션 질문", target="t2")
    # Main 에서 만든 섬 질문(섹션 · 대상 없음) — Main 에 보이고 섹션0 에는 안 보임(유저 지정 11/05)
    ISLAND.append(fs.apply(tp, "user", "ask", text="Main 섬 질문")["id"])
    # 파일 노드(쓰기 명령이 없어 시험 재료로 직접)
    tree = json.loads(tp.read_text(encoding="utf-8"))
    tree["nodes"].append({"id": "f-sec", "kind": "file", "title": "data.csv", "path": "data.csv", "screen": 1})
    tp.write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")


# 그래프 프레임
# page: 페이지
def frame(page):
    return page.frame(url=lambda u: "/ft/" in u)


# 그래프 프레임이 뜰 때까지 → 프레임 — page.frame 은 왕복이 없어 locator 호출로 이벤트를 받아 가며 기다림
# page: 페이지
def ready(page):
    page.wait_for_selector("html[data-ready='1']", timeout=30000)
    wait_for(lambda: page.locator("#hub").count() and frame(page) and frame(page).locator(".screens button").count() > 0, 20)
    return frame(page)


# 지금 화면의 노드 id 집합
# fr: 그래프 프레임
def shown(fr):
    return set(fr.evaluate("[...document.querySelectorAll('.react-flow__node')].map((x) => x.dataset.id)"))


# 틀이 아닌 노드 id 집합
# fr: 그래프 프레임
def real(fr):
    return {x for x in shown(fr) if not re.match(r"s\d-t\d", x)}


# 지금 화면의 선 id 집합
# fr: 그래프 프레임
def edges(fr):
    return set(fr.evaluate("[...document.querySelectorAll('.react-flow__edge')].map((x) => x.dataset.id)"))


# 눌린 스위치 글자
# fr: 그래프 프레임
def pressed(fr):
    return fr.locator('.screens button[aria-pressed="true"]').inner_text()


# 화면 바꾸기 — 눌러서 그 화면 노드가 그려질 때까지
# fr: 그래프 프레임 / s: main · 번호 / has: 있어야 할 노드 id(빈 화면이면 None)
def go(fr, s, has=None):
    fr.locator(f'.screens button[data-screen="{s}"]').click()
    wait_for(lambda: fr.locator(f'.screens button[data-screen="{s}"]').get_attribute("aria-pressed") == "true"
             and (has is None or has in shown(fr)), 5)
    time.sleep(0.5)


# 노드의 화면 좌표(그래프 좌표 · transform 값)
# fr: 그래프 프레임 / nid: 노드 id
def pos(fr, nid):
    # transform 글자
    t = fr.evaluate(f"document.querySelector('.react-flow__node[data-id=\"{nid}\"]').style.transform")
    return tuple(round(float(x)) for x in re.findall(r"-?[\d.]+", t)[:2])


# 노드 끌기 — 가운데로 옮긴 뒤 머리를 잡아 dx · dy 만큼
# page: 페이지 / fr: 그래프 프레임 / nid: 노드 id / dx · dy: 화면 픽셀
def drag(page, fr, nid, dx, dy):
    fr.evaluate(f"window.__flowtree.center({json.dumps(nid)}, 1)")
    time.sleep(0.4)
    # 노드 상자
    b = fr.locator(f'.react-flow__node[data-id="{nid}"]').bounding_box()
    x, y = b["x"] + 40, b["y"] + 10
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y + dy / 2, steps=5)
    page.mouse.move(x + dx, y + dy, steps=5)
    page.mouse.up()
    time.sleep(0.7)


# 노드 고르기
# fr: 그래프 프레임 / nid: 노드 id
def pick(fr, nid):
    fr.evaluate(f"window.__flowtree.center({json.dumps(nid)}, 1)")
    time.sleep(0.4)
    fr.locator(f'.react-flow__node[data-id="{nid}"]').click(position={"x": 40, "y": 10})
    time.sleep(0.3)


# 마법봉 한 번 → 요청 파일의 노드 id 목록
# page: 페이지 / w: 시험 세계
def wand(page, w):
    # 보내기 전 개수
    n0 = len(hub.queued(w))
    page.click('#hub .dv-hub-row[data-nick="main"]')
    page.click('#hub .dv-hub-tray [data-act="wand"]')
    if not wait_for(lambda: len(hub.queued(w)) == n0 + 1, 5):
        return None
    # 요청 파일
    req = hub.request_file(w, hub.queued(w)[-1][-1].split()[-1])
    page.click('#hub .dv-hub-row[data-nick="main"]')
    return [x["id"] for x in req["nodes"]]


# 노드 추가 단추로 만들기
# page: 페이지 / fr: 그래프 프레임 / name: work · insp · question · suggest / title: 제목
def add_node(page, fr, name, title):
    fr.locator(f'.addbar [data-add="{name}"]').click()
    # 그래프 빈 곳 — 멀리 줄여 노드를 가운데로 모은 뒤 왼쪽 위(왼쪽 아래는 허브 자리)
    fr.evaluate("window.__flowtree.zoomTo(0.1)")
    time.sleep(0.3)
    b = fr.locator(".flow").bounding_box()
    page.mouse.click(b["x"] + 30 + 60 * len(MADE), b["y"] + 30)
    MADE.append(title)
    # 제목 칸
    box = fr.locator('.react-flow__node[data-id="__draft"] textarea, .react-flow__node[data-id="__draft"] input').first
    box.fill(title)
    box.press("Enter")
    time.sleep(0.6)


# 알림 종이 보내는 focus 메시지
# page: 페이지 / nid: 노드 id
def focus(page, nid):
    page.evaluate("(id) => document.querySelector('#ftView iframe').contentWindow.postMessage({ ft: 'focus', node: id }, '*')", nid)
    time.sleep(0.8)


# 스위치 글자 잘림 검사 — 잘린 단추 글자 목록
# fr: 그래프 프레임
def clipped(fr):
    return fr.evaluate("""[...document.querySelectorAll('.screens button')].filter((b) => {
      const r = b.getBoundingClientRect();
      return b.scrollWidth > b.clientWidth || b.scrollHeight > b.clientHeight || r.right > innerWidth || r.width === 0;
    }).map((b) => b.textContent)""")


def run(w, base):
    # 그래프 · 유저 칸 경로
    tp = w["tree"]
    up = tp.with_name("tree.user.json")
    user = lambda: json.loads(up.read_text(encoding="utf-8"))  # noqa: E731
    node = lambda nid: next((n for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n["id"] == nid), None)  # noqa: E731
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=not hub.HEADED)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=not hub.HEADED)
        page = br.new_page(viewport={"width": 1600, "height": 960})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base + "/")
        fr = ready(page)
        wait_for(lambda: "t2" in shown(fr), 10)

        # ======= 스위치 =======
        # 글자 목록
        names = fr.locator(".screens button").all_inner_texts()
        check("스위치 10개 — Main · 섹션0~8", names == ["Main"] + [f"섹션{i}" for i in range(9)], names)
        check("처음은 Main", pressed(fr) == "Main")
        check("글자 잘림 없음(1600)", not clipped(fr), clipped(fr))

        # ======= Main =======
        ids = shown(fr)
        check("Main — 작업 · 파일 · 옛 노드 보임", {"t1", "t2", "t3", "f-sec", "root", "r-one"} <= ids, sorted(ids)[:30])
        check("Main — 질문 · 설문 · 검증 안 보임", not ids & {"v1", "v2", "s1", "q1"}, ids & {"v1", "v2", "s1", "q1"})
        check("Main — 섹션 없는 섬 질문은 Main 에 보임", ISLAND[0] in ids, (ISLAND, sorted(ids)[:30]))
        check("Main — 숨은 노드의 선 안 그림", not [e for e in edges(fr) if "v2" in e or "s1" in e or "q1" in e], sorted(edges(fr)))
        check("Main — 빈 틀 안 보임", not (ids - real(fr)), sorted(ids - real(fr))[:5])
        page.screenshot(path=str(SHOTS / "ft_screens_main.png"))

        # ======= 섹션 =======
        go(fr, 1, "q1")
        ids = real(fr)
        check("섹션1 — 모든 종류 보임", ids == {"t2", "t3", "v2", "s1", "q1", "f-sec"}, sorted(ids))
        check("섹션1 — 빈 틀 28개 함께", len(shown(fr) - ids) == 28, len(shown(fr)))
        check("섹션1 — 이 화면 안 선은 그림", {"h:t2>t3", "h:t2>v2"} <= edges(fr), sorted(edges(fr)))
        page.screenshot(path=str(SHOTS / "ft_screens_section1.png"))
        go(fr, 0, "v1")
        check("칸 없는 검증(칸 없는 대상) → 섹션0 에 보임 · 섬 질문은 섹션0 에 안 겹침", real(fr) == {"v1"}, sorted(real(fr)))
        check("섹션0 — 안 보이는 대상의 선 안 그림", not [e for e in edges(fr) if "v1" in e and "s0" not in e], sorted(edges(fr))[:6])
        go(fr, 5, "s5-t1")
        check("빈 섹션 — 틀만", not real(fr), sorted(real(fr)))
        # 틀 배치 — 왼쪽 설문 세로 줄 · 오른쪽 검증 세로 줄 · 아래로 작업
        p = {i: pos(fr, i) for i in ("s5-t1", "s5-t2", "s5-t1-s1", "s5-t1-s2", "s5-t1-v1", "s5-t1-v2", "s5-t1-v3", "s5-t1-v4")}
        check("틀 배치 — 설문 왼쪽 세로 · 검증 오른쪽 세로 · 작업 세로",
              p["s5-t1-s1"][0] == p["s5-t1-s2"][0] < p["s5-t1"][0] < p["s5-t1-v1"][0] == p["s5-t1-v4"][0]
              and p["s5-t1-s1"][1] < p["s5-t1-s2"][1] and p["s5-t1-v1"][1] < p["s5-t1-v2"][1] < p["s5-t1-v3"][1] < p["s5-t1-v4"][1]
              and p["s5-t2"][1] > p["s5-t1-v4"][1] - 300 and p["s5-t2"][0] == p["s5-t1"][0], p)
        check("틀 선 — 설문 · 검증이 작업에 직접(병렬)", {"t:fe-s5-t1-s1", "t:fe-s5-t1-s2", "t:fe-s5-t2", "t:fe-s5-t1-v1", "t:fe-s5-t1-v2", "t:fe-s5-t1-v3", "t:fe-s5-t1-v4"} <= edges(fr), sorted(edges(fr))[:8])
        tr = json.loads(w["tree"].read_text(encoding="utf-8"))
        fe = {e["id"]: e for e in tr["edges"]}
        check("틀 선 끝점 — 설문 → 작업 · 작업 → 검증", all(fe[f"fe-s5-t1-s{i}"]["target"] == "s5-t1" for i in (1, 2)) and all(fe[f"fe-s5-t1-v{j}"]["source"] == "s5-t1" for j in (1, 2, 3, 4)))
        fr.locator('.react-flow__controls, .top button[aria-label="전체 보기"]').first.click()
        time.sleep(0.5)
        page.screenshot(path=str(SHOTS / "ft_screens_frame.png"))

        # ======= 화면별 위치 =======
        go(fr, "main", "t2")
        a0 = pos(fr, "t2")
        drag(page, fr, "t2", 140, 90)
        a1 = pos(fr, "t2")
        check("Main 끌기 — 움직임 · feature 칸에 저장", a1 != a0 and wait_for(lambda: tuple(user()["positions"]["feature"]["t2"]) == a1, 3), (a0, a1))
        go(fr, 1, "t2")
        b0 = pos(fr, "t2")
        drag(page, fr, "t2", -200, 160)
        b1 = pos(fr, "t2")
        check("섹션1 끌기 — s1 칸에 저장", b1 != b0 and wait_for(lambda: tuple(user()["positions"]["s1"]["t2"]) == b1, 3), (b0, b1))
        check("같은 노드 위치가 화면마다 다름", a1 != b1, (a1, b1))
        go(fr, "main", "t2")
        check("Main 으로 돌아옴 — Main 위치 유지", pos(fr, "t2") == a1, pos(fr, "t2"))
        go(fr, 1, "t2")
        check("섹션1 로 돌아옴 — 섹션 위치 유지", pos(fr, "t2") == b1, pos(fr, "t2"))

        # 다른 노드가 들어와도 끌어 둔 자리는 그대로
        sys.path.insert(0, str(hub.FLOWTREE))
        import flowtree_store as fs  # noqa: E402
        fs.apply(tp, "main", "add", parent="t2", title="새로 온 작업", summary="배치 시험", section=1)
        wait_for(lambda: "t4" in shown(fr), 6)
        time.sleep(0.4)
        check("새 노드가 와도 끌어 둔 위치 그대로", "t4" in shown(fr) and pos(fr, "t2") == b1, pos(fr, "t2"))

        # ======= 새로고침 =======
        wait_for(lambda: user().get("screen") == 1, 3)
        page.reload()
        fr = ready(page)
        wait_for(lambda: "t2" in shown(fr), 10)
        check("새로고침 — 고른 화면 유지", pressed(fr) == "섹션1", pressed(fr))
        check("새로고침 — 끌어 둔 위치 유지", pos(fr, "t2") == b1, pos(fr, "t2"))

        # ======= 노드 추가 단추 =======
        add_node(page, fr, "work", "섹션에서 만든 작업")
        # 새 노드 id
        new = next((n for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n.get("title") == "섹션에서 만든 작업"), None)
        check("섹션 화면 추가 — 그 섹션 소속", bool(new) and new.get("screen") == 1 and new["id"] in shown(fr), new)
        add_node(page, fr, "question", "섹션에서 만든 질문")
        # 새 질문
        nq = next((n for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n.get("title") == "섹션에서 만든 질문"), None)
        check("섹션 화면 질문 — 그 섹션 소속 · view 칸 그대로", bool(nq) and nq.get("screen") == 1 and "view" not in nq and nq["id"] in shown(fr), nq)
        go(fr, "main", "t2")
        add_node(page, fr, "work", "메인에서 만든 작업")
        # 새 노드
        nm = next((n for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n.get("title") == "메인에서 만든 작업"), None)
        check("Main 추가 — 칸 없음 · Main 에 보임", bool(nm) and "screen" not in nm and nm["id"] in shown(fr), nm)
        go(fr, 1, "t2")
        check("Main 에서 만든 노드 — 섹션에 안 보임", nm["id"] not in shown(fr), sorted(shown(fr)))

        # ======= 선택 · 자세히 =======
        pick(fr, "v2")
        page.wait_for_timeout(200)
        fr.locator(".flow").press("`")
        check("섹션1 — 검증 자세히 열림", wait_for(lambda: fr.locator("main.doc-mod").count() == 1, 3))
        go(fr, "main", "t2")
        check("Main 으로 — 자세히 그대로", fr.locator("main.doc-mod").count() == 1 and "섹션 검증" in fr.locator("main").inner_text())
        check("Main 으로 — 선택 그대로", [n["id"] for n in page.evaluate("window.devview.flowSelection().nodes")] == ["v2"],
              page.evaluate("window.devview.flowSelection()"))
        check("숨은 노드를 고른 채 — 노드가 흐려지지 않음", fr.locator(".react-flow__node .fdim, .react-flow__node.fdim").count() == 0)

        # ======= 마법봉 =======
        check("Main — 섹션에서 고른 검증으로 마법봉", wand(page, w) == ["v2"])
        fr.locator(".flow").press("Escape")
        fr.locator(".flow").press("Escape")
        pick(fr, "t1")
        check("Main — 작업 마법봉", wand(page, w) == ["t1"])
        go(fr, 1, "q1")
        pick(fr, "q1")
        check("섹션1 — 질문 마법봉", wand(page, w) == ["q1"])
        pick(fr, "v2")
        check("섹션1 — 검증 마법봉", wand(page, w) == ["v2"])
        pick(fr, "t3")
        check("섹션1 — 작업 마법봉", wand(page, w) == ["t3"])

        # ======= 삭제 · 건너가기 =======
        pick(fr, new["id"])
        fr.locator(".flow").press("Delete")
        check("섹션 화면 Delete — 노드 지움", wait_for(lambda: node(new["id"]) is None, 3))
        fs.apply(tp, "main", "section-set", node="t4", section=7)
        check("section-set — 다음 불러오기에 그 화면으로 옮겨감", wait_for(lambda: "t4" not in shown(fr), 6), sorted(shown(fr)))
        go(fr, 7, "t4")
        check("옮긴 노드가 새 섹션에 보임", "t4" in shown(fr))

        # ======= 알림 종 focus =======
        focus(page, "v2")
        check("focus — 그 섹션으로 · 선택 · 자세히", pressed(fr) == "섹션1" and fr.locator("main.doc-mod").count() == 1
              and [n["id"] for n in page.evaluate("window.devview.flowSelection().nodes")] == ["v2"], pressed(fr))
        focus(page, "t1")
        check("focus — 칸 없는 노드는 Main 으로", pressed(fr) == "Main" and "t1" in shown(fr)
              and [n["id"] for n in page.evaluate("window.devview.flowSelection().nodes")] == ["t1"], pressed(fr))
        focus(page, "없는노드")
        check("focus — 없는 노드는 무시", pressed(fr) == "Main"
              and [n["id"] for n in page.evaluate("window.devview.flowSelection().nodes")] == ["t1"], pressed(fr))

        # 데이터 오기 전 focus — 데이터 응답을 붙잡아 둔 새 창에서 보냄
        p2 = br.new_page(viewport={"width": 1600, "height": 960})
        held = []
        gate = []
        p2.route("**/ft/api/data*", lambda r: r.continue_() if gate else held.append(r))
        p2.goto(base + "/")
        p2.wait_for_selector("html[data-ready='1']", timeout=30000)
        check("데이터 오기 전 — 응답 붙잡힘 · 그래프 안 그려짐", wait_for(lambda: p2.locator("#hub").count() and held and frame(p2).locator(".screens").count() == 0, 10))
        focus(p2, "v2")
        gate.append(1)
        for r in held:
            r.continue_()
        f2 = frame(p2)
        check("데이터 오기 전 focus — 데이터 뒤 처리", wait_for(lambda: f2.locator(".screens button").count() > 0 and pressed(f2) == "섹션1"
              and f2.locator("main.doc-mod").count() == 1 and "v2" in shown(f2), 8), f2.locator(".screens").count())
        p2.close()

        # ======= devview → {ft:'screen', screen} =======
        # 부모 창에서 그래프 iframe 으로 보냄
        post = lambda pg, s: pg.evaluate("(s) => document.querySelector('#ftView iframe').contentWindow.postMessage({ ft: 'screen', screen: s }, '*')", s)  # noqa: E731
        wait_for(lambda: pressed(fr) == "섹션1", 5)
        post(page, 2)
        check("screen 2 → 섹션2", wait_for(lambda: pressed(fr) == "섹션2", 3), pressed(fr))
        post(page, 0)
        check("screen 0 → 섹션0", wait_for(lambda: pressed(fr) == "섹션0", 3), pressed(fr))
        post(page, None)
        check("screen null → Main", wait_for(lambda: pressed(fr) == "Main", 3), pressed(fr))
        post(page, 99)
        post(page, "1")
        time.sleep(0.3)
        check("없는 번호 · 숫자 아닌 값 → 무시", pressed(fr) == "Main", pressed(fr))
        # 데이터 오기 전 screen — 데이터 응답을 붙잡아 둔 새 창에서 보냄
        p3 = br.new_page(viewport={"width": 1600, "height": 960})
        held = []
        gate = []
        p3.route("**/ft/api/data*", lambda r: r.continue_() if gate else held.append(r))
        p3.goto(base + "/")
        p3.wait_for_selector("html[data-ready='1']", timeout=30000)
        wait_for(lambda: p3.locator("#hub").count() and held and frame(p3).locator(".screens").count() == 0, 10)
        post(p3, 3)
        gate.append(1)
        for r in held:
            r.continue_()
        f3 = frame(p3)
        check("데이터 오기 전 screen — 데이터 뒤 그 화면", wait_for(lambda: f3.locator(".screens button").count() > 0 and pressed(f3) == "섹션3", 8), f3.locator(".screens").count())
        p3.close()
        go(fr, "main", "t2")
        go(fr, 1, "t2")

        # ======= 틀 채우기 · 양식 · 확대 =======
        go(fr, 3, "s3-t1")
        pick(fr, "s3-t1-v1")
        fr.locator('[data-edit="summary"]').first.fill("결과 파일 확인")
        fr.locator('[data-edit="script"]').first.fill("tests/test_out.py")
        fr.locator('[data-edit="script"]').first.press("Enter")
        check("검증 양식 — 화면에서 칸 고침 → 일반 노드", wait_for(lambda: (node("s3-t1-v1").get("edit") or {}).get("script") == "tests/test_out.py"
              and "frame" not in node("s3-t1-v1"), 4), node("s3-t1-v1"))
        fr.locator('[data-mark="pass"]').first.click()
        check("검증 성공 표시 → 초록 상태", wait_for(lambda: fr.locator('.react-flow__node[data-id="s3-t1-v1"] [data-status="pass"]').count() == 1, 4))
        pick(fr, "s3-t1")
        fr.locator('[data-edit="summary"]').first.fill("입력 파일을 읽는다")
        fr.locator('[data-edit="summary"]').first.press("Enter")
        fr.get_by_text("+ 행 추가").first.click()
        fr.locator('[data-edit="fn-new-file"]').fill("src/load.py")
        fr.locator('[data-edit="fn-new-file"]').press("Enter")
        check("작업 양식 — 기능 설명 · 파일명 칸", wait_for(lambda: (node("s3-t1").get("edit") or {}).get("summary") == "입력 파일을 읽는다"
              and (node("s3-t1").get("funcs") or [{}])[0].get("user", {}).get("file") == "src/load.py", 4), node("s3-t1"))
        fs.apply(tp, "main", "fill", node="s3-t1-s1", title="어느 방식으로 읽나", options=["한 번에|전체", "조금씩|부분"], recommend=1)
        wait_for(lambda: "어느 방식" in fr.locator('.react-flow__node[data-id="s3-t1-s1"]').inner_text(), 6)
        fr.locator(".flow").press("Escape")
        fr.locator(".flow").press("Escape")
        fr.evaluate("window.__flowtree.center('s3-t1-s1', 6)")
        time.sleep(0.6)
        # 설문 노드
        sv = fr.locator('.react-flow__node[data-id="s3-t1-s1"]')
        check("확대 — 노드 안 선택지 표 · 추천 ⭐ + 노란 테두리", wait_for(lambda: sv.locator(".sv-sw").count() == 1, 3)
              and "⭐" in sv.locator('.sv-tbl tr[data-opt="1"]').inner_text()
              and sv.locator('.sv-tbl tr[data-opt="1"]').evaluate("(b) => getComputedStyle(b).outlineColor") == "rgb(244, 211, 94)")
        check("확대 — 기타 · 보류 · 질문", sv.locator('.sv-sw [data-sw="other"]').is_visible() and sv.locator('.sv-sw [data-sw="hold"]').is_visible()
              and sv.locator('.sv-sw [data-sw="ask"]').is_visible())
        page.screenshot(path=str(SHOTS / "ft_screens_survey_zoom.png"))
        sv.locator('.sv-tbl tr[data-opt="1"]').click()
        check("스위치 선택 → 답 기록", wait_for(lambda: (node("s3-t1-s1").get("votes") or [{}])[-1].get("pick") == 1, 4), node("s3-t1-s1").get("votes"))
        sv.locator('.sv-sw [data-sw="ask"]').click()
        # 쓰는 중 칸
        box = fr.locator('.react-flow__node[data-id="__draft"] textarea')
        check("질문 단추 → 쓰는 중 노드가 화면에", wait_for(lambda: box.count() == 1 and box.is_visible(), 3))
        box.fill("왜 조금씩?")
        box.press("Enter")
        time.sleep(0.8)
        # 그 질문 · 선
        tr = json.loads(tp.read_text(encoding="utf-8"))
        qn = next((n for n in tr["nodes"] if n.get("title") == "왜 조금씩?"), None)
        check("설문 질문 — 그 노드에 이어진 질문 노드", bool(qn) and any(e["source"] == qn["id"] and e["target"] == "s3-t1-s1" for e in tr["edges"]) and qn["id"] in shown(fr), qn)
        fr.evaluate("window.__flowtree.center('s3-t1', 1.6)")
        time.sleep(0.5)
        fr.locator('.react-flow__node[data-id="s3-t1"] [data-sw="ask"]').click()
        box = fr.locator('.react-flow__node[data-id="__draft"] textarea')
        wait_for(lambda: box.count() == 1, 3)
        box.fill("작업 질문")
        box.press("Enter")
        time.sleep(0.8)
        tr = json.loads(tp.read_text(encoding="utf-8"))
        qn = next((n for n in tr["nodes"] if n.get("title") == "작업 질문"), None)
        check("작업 노드 질문 단추", bool(qn) and any(e["source"] == qn["id"] and e["target"] == "s3-t1" for e in tr["edges"]), qn)
        fr.evaluate("window.__flowtree.center('s3-t2-v1', 6)")
        time.sleep(0.6)
        check("검증 노드 확대 — 질문 단추", fr.locator('.react-flow__node[data-id="s3-t2-v1"] [data-sw="ask"]').is_visible())
        pick(fr, "s3-t2-s2")
        check("틀 노드도 마법봉", wand(page, w) == ["s3-t2-s2"])
        fr.evaluate("window.__flowtree.zoomTo(0.5)")
        time.sleep(0.4)

        # ======= 틀 밖 새 노드 =======
        go(fr, 6)
        fs.apply(tp, "main", "add", parent="-", title="틀 밖 작업", summary="새 작업", section=6)
        out_t = next(n["id"] for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n.get("title") == "틀 밖 작업")
        fs.apply(tp, "main", "verify-add", target=out_t, what="틀 밖 검증", section=6)
        fs.apply(tp, "main", "survey-add", target=out_t, question="틀 밖 설문", options=["가", "나"], section=6)
        fs.apply(tp, "main", "add", parent="s6-t2", title="틀 작업 밑 가지", section=6)
        # 그린 상자들
        boxes = lambda: fr.evaluate("""[...document.querySelectorAll('.react-flow__node')].map((e) => {
          const [x, y] = e.style.transform.match(/-?[\\d.]+/g).map(Number);
          return { id: e.dataset.id, x, y, w: e.offsetWidth, h: e.offsetHeight };
        })""")  # noqa: E731
        # 틀 상자와 겹치는 틀 밖 노드 id
        def overlaps():
            bs = boxes()
            fb = [b for b in bs if re.fullmatch(r"s\d-t\d(-[sv]\d)?", b["id"])]
            return [(o["id"], f["id"]) for o in bs if o not in fb for f in fb
                    if o["x"] < f["x"] + f["w"] and f["x"] < o["x"] + o["w"] and o["y"] < f["y"] + f["h"] and f["y"] < o["y"] + o["h"]]
        wait_for(lambda: len(real(fr)) >= 4, 6)
        check("틀 밖 새 노드 — 4개 다 보임", len(real(fr)) == 4, sorted(real(fr)))
        check("틀 밖 새 노드 — 빈 틀과 안 겹침", not overlaps(), overlaps()[:4])
        check("틀 밖 새 노드 — 틀 오른쪽 밖", all(pos(fr, x)[0] > pos(fr, "s6-t1-v1")[0] for x in real(fr)), [pos(fr, x) for x in real(fr)])
        check("틀 밖 — 틀 노드 처음 위치 그대로", pos(fr, "s6-t1") == (0, 0), pos(fr, "s6-t1"))
        fr.locator(".flow").press("Escape")
        fr.evaluate(f"window.__flowtree.center({json.dumps(out_t)}, 0.5)")
        time.sleep(0.6)
        page.screenshot(path=str(SHOTS / "ft_screens_outside.png"))
        drag(page, fr, out_t, 120, 90)
        moved = pos(fr, out_t)
        check("틀 밖 끌기 — s6 칸에 저장", wait_for(lambda: tuple(user()["positions"]["s6"][out_t]) == moved, 3), moved)
        fs.apply(tp, "main", "add", parent="-", title="틀 밖 작업 둘", section=6)
        wait_for(lambda: len(real(fr)) >= 5, 6)
        check("새 노드가 와도 끌어 둔 위치 그대로 · 틀과 안 겹침", pos(fr, out_t) == moved and not overlaps(), (moved, pos(fr, out_t), overlaps()[:3]))
        fs.apply(tp, "main", "add", parent="s6-t4", title="다음 섹션 잇기", section=7)
        fs.apply(tp, "main", "fill", node="s6-t4", title="섹션 끝 작업")
        go(fr, "main", has="s6-t4")
        check("섹션 사이 — Main 에 계층 선 · 화면을 바꾸는 저장 직전의 쓰기도 그려짐", wait_for(lambda: any(e.startswith("h:s6-t4>") for e in edges(fr)), 4), sorted(edges(fr))[:6])

        # ======= 카드 줌 질문 단추 =======
        go(fr, 3)
        fr.locator(".flow").press("Escape")
        fr.evaluate("window.__flowtree.center('s3-t1', 0.8)")
        time.sleep(0.6)
        for nid in ("s3-t1", "s3-t1-s1"):
            check(f"카드 줌 — 질문 단추 {nid}", fr.locator(f'.react-flow__node[data-id="{nid}"] .wk-card [data-sw="ask"]').is_visible())
        fs.apply(tp, "main", "fill", node="s3-t1-v2", title="카드 검증")
        wait_for(lambda: fr.locator('.react-flow__node[data-id="s3-t1-v2"] .wk-card [data-sw="ask"]').count() == 1, 6)
        check("카드 줌 — 질문 단추 검증", fr.locator('.react-flow__node[data-id="s3-t1-v2"] .wk-card [data-sw="ask"]').is_visible())
        check("카드 줌 — 빈 틀에는 단추 없음", fr.locator('.react-flow__node[data-id="s3-t1-v3"] [data-sw="ask"]').count() == 0)
        check("카드 줌 — 글자 안 넘침", not fr.evaluate("""[...document.querySelectorAll('.wk-cfoot')].filter((e) => {
          const r = e.getBoundingClientRect(), n = e.closest('.react-flow__node').getBoundingClientRect();
          return r.bottom > n.bottom + 1 || r.right > n.right + 1 || e.scrollWidth > e.clientWidth + 1;
        }).map((e) => e.closest('.react-flow__node').dataset.id)"""))
        page.screenshot(path=str(SHOTS / "ft_screens_card_ask.png"))
        fr.locator('.react-flow__node[data-id="s3-t1-v2"] .wk-card [data-sw="ask"]').click()
        box = fr.locator('.react-flow__node[data-id="__draft"] textarea')
        wait_for(lambda: box.count() == 1, 3)
        box.fill("카드 질문")
        box.press("Enter")
        time.sleep(0.8)
        tr = json.loads(tp.read_text(encoding="utf-8"))
        qn = next((n for n in tr["nodes"] if n.get("title") == "카드 질문"), None)
        check("카드 줌 — 질문 단추로 이어진 질문 노드", bool(qn) and any(e["source"] == qn["id"] and e["target"] == "s3-t1-v2" for e in tr["edges"]), qn)

        # ======= 펼침 표 =======
        go(fr, 8)
        fs.apply(tp, "main", "fill", node="s8-t1", title="앱 진입 · 빈 상태", summary="자료 적용 전 안내가 보인다", doc="docs/hand_off.md#1-1",
                 funcs=["src/ui/app.py | index | 승인 뒤 첫 화면의 빈 상태를 연결한다 | ⭐", "src/core/아주_긴_폴더_이름/입력_검사_모음.py | 요청_파일_전부_읽기 | 줄마다 형식 문제를 모은다 |"])
        fs.apply(tp, "main", "fill", node="s8-t1-v1", title="자료 적용 전 안내와 기본 포트가 보인다", script="tests/test_진입.py")
        fs.apply(tp, "main", "fill", node="s8-t1-s1", title="이 범위로 시작할까?", options=[
            "이 범위로 시작|네 작업을 그대로 구현한다|바로 시작한다;첫 조각이 빨리 돈다|저장 방식은 다음 설문을 따른다",
            "범위를 줄인다|메모에 뺄 작업을 적는다|더 빨리 돈다|뺀 작업은 다음 섹션으로 밀린다",
            "범위를 고친다|메모에 더할 것을 적는다|빠진 요구를 넣는다|시작이 늦어진다"], recommend=0,
                 why="담당자 답 없이 만들 수 있는 것만 넣었다",
                 detail="지금 범위는 앱 틀과 요청 읽기까지다. 정비 중 장비 처리는 담당자 답을 기다린다. 이 범위로 시작하면 첫 결과를 먼저 본다.")
        wait_for(lambda: "앱 진입" in fr.locator('.react-flow__node[data-id="s8-t1"]').inner_text(), 6)
        # 그 노드의 펼침 줌으로
        def open_page(nid):
            pz = fr.evaluate(f"parseFloat(document.querySelector('.react-flow__node[data-id=\"{nid}\"] .wk').style.getPropertyValue('--pz'))")
            fr.evaluate(f"window.__flowtree.center({json.dumps(nid)}, {pz + 0.05})")
            time.sleep(0.7)
            return fr.locator(f'.react-flow__node[data-id="{nid}"]')
        # 표 칸 넘침 · 노드 상자 밖으로 나간 내용
        def spill(nid):
            return fr.evaluate(f"""(() => {{
              const n = document.querySelector('.react-flow__node[data-id="{nid}"]'), b = n.getBoundingClientRect(), bad = [];
              for (const e of n.querySelectorAll('.pg, .pg td, .pg th, .sv-sw button')) {{
                const r = e.getBoundingClientRect();
                if (r.top < b.top - 1 || r.bottom > b.bottom + 1 || r.left < b.left - 1 || r.right > b.right + 1 || e.scrollWidth > e.clientWidth + 1) bad.push(e.textContent.slice(0, 20));
              }}
              return bad;
            }})()""")
        # 표 폭 ÷ 상자 안쪽 폭(표마다) — 안쪽 폭 = 펼침 칸에서 좌우 여백을 뺀 값 · 여러 단이면 단 폭 기준
        def table_ratio(nid):
            return fr.evaluate(f"""(() => {{
              const p = document.querySelector('.react-flow__node[data-id="{nid}"] .ft-page'), c = p.querySelector('.ft-cols'), s = getComputedStyle(c);
              const k = p.getBoundingClientRect().width / p.offsetWidth, pad = parseFloat(getComputedStyle(p).paddingLeft) * 2 * k;
              const cols = parseInt(s.columnCount) || 1, gap = (parseFloat(s.columnGap) || 0) * k;
              // 상자가 그래프 칸보다 넓으면 내용은 칸 폭까지만 — 보이는 안쪽 폭 기준
              const box = Math.min(p.getBoundingClientRect().width - pad, document.querySelector('.flow').getBoundingClientRect().width - 28);
              const inner = (box - gap * (cols - 1)) / cols;
              return [...p.querySelectorAll('table')].map((t) => t.getBoundingClientRect().width / inner);
            }})()""")
        # 상자 바깥 흐름 — 내용 왼쪽 · 오른쪽 여백(화면 px)
        def side_gaps(nid):
            return fr.evaluate(f"""(() => {{
              const n = document.querySelector('.react-flow__node[data-id="{nid}"]').getBoundingClientRect();
              const c = document.querySelector('.react-flow__node[data-id="{nid}"] .ft-cols').getBoundingClientRect();
              return [c.left - n.left, n.right - c.right];
            }})()""")
        # 표 칸이 몇 줄로 꺾였나(칸 안 글 높이 ÷ 줄 높이의 최대)
        def cell_lines(nid, sel):
            return fr.evaluate(f"""(() => Math.max(...[...document.querySelectorAll('.react-flow__node[data-id="{nid}"] {sel}')].map((t) => {{
              const r = document.createRange(); r.selectNodeContents(t);
              return new Set([...r.getClientRects()].map((x) => Math.round(x.top))).size;
            }})))()""")
        # 상자가 그래프 화면 안에 다 들어가나
        def in_view(nid):
            return fr.evaluate(f"""(() => {{
              const n = document.querySelector('.react-flow__node[data-id="{nid}"]').getBoundingClientRect(), f = document.querySelector('.flow').getBoundingClientRect();
              return n.width <= f.width + 1 && n.height <= f.height + 1 ? '' : [n.width, n.height, f.width, f.height].join(' ');
            }})()""")
        # 내용 영역이 그래프 칸 밖으로 나간 값(없으면 빈 글자)
        def content_out(nid):
            return fr.evaluate(f"""(() => {{
              const c = document.querySelector('.react-flow__node[data-id="{nid}"] .ft-cols').getBoundingClientRect(), f = document.querySelector('.flow').getBoundingClientRect();
              return c.left >= f.left - 1 && c.right <= f.right + 1 && c.top >= f.top - 1 && c.bottom <= f.bottom + 1 ? '' : [c.left, c.right, c.top, c.bottom, f.left, f.right, f.top, f.bottom].map(Math.round).join(' ');
            }})()""")
        tk = open_page("s8-t1")
        check("작업 펼침 — 표 폭 90% 이상", min(table_ratio("s8-t1")) >= 0.9, table_ratio("s8-t1"))
        check("작업 펼침 — 좌우 여백 작게 고정", max(side_gaps("s8-t1")) <= 24, side_gaps("s8-t1"))
        check("작업 펼침 — 표 칸 글이 안 꺾임", cell_lines("s8-t1", ".pg-vr td") == 1, cell_lines("s8-t1", ".pg-vr td"))
        check("작업 펼침 — 함수 표 머리줄", tk.locator(".pg-fn th").all_inner_texts() == ["함수", "설명", "파일"], tk.locator(".pg-fn th").all_inner_texts())
        cs = lambda loc, k: loc.evaluate(f"(e) => getComputedStyle(e).{k}")  # noqa: E731
        name_td, desc_td, file_td = (tk.locator(".pg-fn tbody tr").first.locator("td").nth(i) for i in range(3))
        check("작업 펼침 — 함수 · 파일 파랑", cs(name_td, "color") == cs(file_td, "color") == "rgb(108, 182, 255)", cs(file_td, "color"))
        check("작업 펼침 — 파일 글자가 본문보다 작지 않음", float(cs(file_td, "fontSize")[:-2]) >= float(cs(desc_td, "fontSize")[:-2]))
        check("작업 펼침 — 표 테두리", cs(file_td, "boxShadow") != "none")
        check("작업 펼침 — 검증 표 머리줄", tk.locator(".pg-vr th").all_inner_texts() == ["상태", "내용", "스크립트"])
        check("작업 펼침 — 빈 틀은 «빈 칸 3» · id 안 보임", "빈 칸 3" in tk.inner_text() and "s8-t1-v2" not in tk.inner_text(), tk.inner_text()[-80:])
        check("작업 펼침 — 잘림 없음", not spill("s8-t1"), spill("s8-t1"))
        page.screenshot(path=str(SHOTS / "ft_screens_task_page.png"))
        fr.evaluate("window.__flowtree.zoomTo(1)")
        time.sleep(0.3)
        pick(fr, "s8-t1")
        pn = fr.locator("aside.panel")
        check("패널 — 함수 표 열 순서", pn.locator(".fn-tbl[data-funcs] th").all_inner_texts()[:3] == ["함수", "설명", "파일"], pn.locator(".fn-tbl[data-funcs] th").all_inner_texts())
        check("패널 — 파일 파랑 · 크게", cs(pn.locator("td[data-cell='fn-f1-file']"), "color") == "rgb(108, 182, 255)"
              and float(cs(pn.locator("td[data-cell='fn-f1-file']"), "fontSize")[:-2]) >= float(cs(pn.locator("td[data-cell='fn-f1-desc']"), "fontSize")[:-2]))
        check("패널 — 검증 표 · 빈 칸 묶음", pn.locator("[data-verifies] th").all_inner_texts() == ["상태", "내용", "스크립트"]
              and pn.locator('[data-verifies] [data-empty="3"]').inner_text() == "빈 칸 3" and "s8-t1-v2" not in pn.inner_text())
        check("패널 — 표 잘림 없음", not pn.evaluate("(p) => [...p.querySelectorAll('.fn-tbl td, .fn-tbl th')].filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent)"))
        page.screenshot(path=str(SHOTS / "ft_screens_panel_table.png"))
        fr.locator(".flow").press("Escape")

        sp = open_page("s8-t1-s1")
        order = sp.inner_text()
        check("설문 펼침 — 한 칸 흐름 순서", -1 < order.find("배경") < order.find("선택지") < order.find("기타") < order.find("추천 이유") < order.find("유저 답"), order[:200])
        check("설문 펼침 — 단이 하나", fr.evaluate("getComputedStyle(document.querySelector('.react-flow__node[data-id=\"s8-t1-s1\"] .ft-cols')).columnCount") == "1")
        check("설문 펼침 — 표 폭 90% 이상", min(table_ratio("s8-t1-s1")) >= 0.9, table_ratio("s8-t1-s1"))
        check("설문 펼침 — 좌우 여백 작게 고정", max(side_gaps("s8-t1-s1")) <= 24, side_gaps("s8-t1-s1"))
        check("설문 펼침 — 표 머리줄", sp.locator(".sv-tbl th").all_inner_texts() == ["선택", "내용", "장점", "단점"])
        check("설문 펼침 — 단추 줄 중복 없음", sp.locator(".sv-sw > button[data-opt]").count() == 0 and sp.locator(".sv-tbl tr[data-opt]").count() == 3)
        rec = sp.locator('.sv-tbl tr[data-opt="0"]')
        check("설문 펼침 — 추천 ⭐ + 노란 테두리", "⭐" in rec.inner_text() and cs(rec, "outlineColor") == "rgb(244, 211, 94)", cs(rec, "outlineColor"))
        sp.locator('.sv-tbl tr[data-opt="1"]').click()
        check("설문 펼침 — 줄을 누르면 고름 · 강조", wait_for(lambda: (node("s8-t1-s1").get("votes") or [{}])[-1].get("pick") == 1
              and "picked" in (sp.locator('.sv-tbl tr[data-opt="1"]').get_attribute("class") or ""), 4))
        check("설문 펼침 — 잘림 없음", not spill("s8-t1-s1"), spill("s8-t1-s1"))
        check("설문 펼침 — 아래 틀 설문이 안 가림", pos(fr, "s8-t1-s2")[1] >= pos(fr, "s8-t1-s1")[1] + sp.evaluate("(e) => e.offsetHeight"), (pos(fr, "s8-t1-s1"), pos(fr, "s8-t1-s2")))
        page.screenshot(path=str(SHOTS / "ft_screens_survey_page.png"))

        fr.evaluate("window.__flowtree.zoomTo(1)")
        vp = open_page("s8-t1-v1")
        order = vp.inner_text()
        check("검증 펼침 — 순서", -1 < order.find("스크립트") < order.find("성공") < order.find("실행 기록") < order.find("질문"), order[:200])
        check("검증 펼침 — 제목이 곧 내용이면 «검증할 내용» 줄 없음", "검증할 내용" not in order, order[:200])
        check("검증 펼침 — 표 폭 90% 이상", min(table_ratio("s8-t1-v1")) >= 0.9, table_ratio("s8-t1-v1"))
        check("검증 펼침 — 좌우 여백 작게 고정", max(side_gaps("s8-t1-v1")) <= 24, side_gaps("s8-t1-v1"))
        vp.locator('[data-mark="fail"]').click()
        check("검증 펼침 — 실패 단추 → 실행 기록 표", wait_for(lambda: vp.locator(".pg-rn tbody tr td").count() == 3 and "비정상" in vp.locator(".pg-rn").inner_text(), 4), vp.inner_text()[-120:])
        check("검증 펼침 — 표 머리줄", vp.locator(".pg-rn th").all_inner_texts() == ["시각", "결과", "근거"])
        vp = open_page("s8-t1-v1")
        check("검증 펼침 — 잘림 없음", not spill("s8-t1-v1"), spill("s8-t1-v1"))
        page.screenshot(path=str(SHOTS / "ft_screens_verify_page.png"))

        fr.evaluate("window.__flowtree.zoomTo(1)")
        fs.apply(tp, "user", "ask", text="왜 기본 포트가 3000 인가", target="s8-t1-v1", section=8)
        q8 = next(n["id"] for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n.get("title") == "왜 기본 포트가 3000 인가")
        fs.apply(tp, "2nd", "answer", question=q8, short="과제 글의 기본값이다", text="실행 안내에 적힌 값을 그대로 썼다.")
        wait_for(lambda: q8 in shown(fr), 6)
        time.sleep(0.5)
        qp = open_page(q8)
        order = qp.inner_text()
        check("질문 펼침 — 순서", -1 < order.find("대상") < order.find("답 1") < order.find("상태"), order[:200])
        check("질문 펼침 — 잘림 없음", not spill(q8), spill(q8))
        check("질문 펼침 — 좌우 여백 작게 고정", max(side_gaps(q8)) <= 24, side_gaps(q8))
        page.screenshot(path=str(SHOTS / "ft_screens_question_page.png"))

        # ======= 작은 창 · 넓은 창 — 펼침 폭 =======
        for wide in (1280, 2000):
            page.set_viewport_size({"width": wide, "height": 720 if wide == 1280 else 1100})
            time.sleep(0.5)
            for nid, name in (("s8-t1", "task"), ("s8-t1-s1", "survey"), ("s8-t1-v1", "verify"), (q8, "question")):
                fr.evaluate("window.__flowtree.zoomTo(1)")
                open_page(nid)
                if name != "question":
                    check(f"{wide} 폭 {name} — 표 폭 90% 이상", min(table_ratio(nid)) >= 0.9, table_ratio(nid))
                check(f"{wide} 폭 {name} — 잘림 없음", not spill(nid), spill(nid))
                # 상자는 내용이 들어가는 가장 작은 줌의 크기 — 작은 창에서 상자 테두리가 칸을 넘을 수 있어도 내용은 칸 안
                check(f"{wide} 폭 {name} — 내용이 화면 안", not content_out(nid), content_out(nid))
                if wide == 2000:
                    check(f"{wide} 폭 {name} — 상자가 화면 안", not in_view(nid), in_view(nid))
                page.screenshot(path=str(SHOTS / f"ft_page_{wide}_{name}.png"))
            # 더 확대해도 잘리지 않음(글자 배율 · 단 단계)
            pz = fr.evaluate("parseFloat(document.querySelector('.react-flow__node[data-id=\"s8-t1\"] .wk').style.getPropertyValue('--pz'))")
            fr.evaluate(f"window.__flowtree.center('s8-t1', {pz * 1.6})")
            time.sleep(0.6)
            check(f"{wide} 폭 확대 — 잘림 없음 · 한 단", not spill("s8-t1") and
                  fr.evaluate("getComputedStyle(document.querySelector('.react-flow__node[data-id=\"s8-t1\"] .ft-cols')).columnCount") == "1", spill("s8-t1"))
        page.set_viewport_size({"width": 1600, "height": 960})
        fr.evaluate("window.__flowtree.zoomTo(0.5)")
        time.sleep(0.4)

        # ======= 여러 단 · 넘침 =======
        # 작은 블록이 많으면 여러 단 — 답 30개
        for i in range(30):
            fs.apply(tp, "2nd", "answer", question=q8, short=f"답 {i}", text="실행 안내에 적힌 값을 그대로 썼다.")
        wait_for(lambda: "답 29" in fr.evaluate(f"document.querySelector('.react-flow__node[data-id=\"{q8}\"]').textContent") or
                 fr.evaluate(f"document.querySelector('.react-flow__node[data-id=\"{q8}\"] .wk').style.getPropertyValue('--pz')") not in ("", "3"), 6)
        time.sleep(0.5)
        open_page(q8)
        cols = fr.evaluate(f"parseInt(getComputedStyle(document.querySelector('.react-flow__node[data-id=\"{q8}\"] .ft-cols')).columnCount)")
        check("내용이 상자 높이보다 많으면 여러 단", cols >= 2, cols)
        check("여러 단 — 잘림 없음", not spill(q8), spill(q8))
        # 한 블록이 상자보다 크면 최대 줌 + 넘침 표시
        fs.apply(tp, "main", "add", parent="-", title="아주 긴 작업", text="가나다라 " * 9000, section=8)
        big = next(n["id"] for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n.get("title") == "아주 긴 작업")
        wait_for(lambda: big in shown(fr), 6)
        time.sleep(0.5)
        open_page(big)
        check("넘침 — 최대 줌 · 넘침 표시 · 상자 안에서 잘림", fr.locator(f'.react-flow__node[data-id="{big}"] .ft-page.over').count() == 1
              and fr.evaluate(f"""(() => {{
                const n = document.querySelector('.react-flow__node[data-id="{big}"]').getBoundingClientRect(), c = document.querySelector('.react-flow__node[data-id="{big}"] .ft-cols').getBoundingClientRect();
                return c.top >= n.top - 1 && c.bottom <= n.bottom + 1;
              }})()"""))
        fr.evaluate("window.__flowtree.zoomTo(0.5)")
        time.sleep(0.4)

        # ======= ` — 일 노드는 문서가 걸려 있어도 자세히 =======
        # 문서 파일을 실제로 만들어 «파일을 열 수 있는데도 안 연다» 를 본다
        doc = tp.parents[1] / "hand_off.md"
        doc.write_text("# 문서\n\n## 1-1\n\n내용\n", encoding="utf-8")
        fs.apply(tp, "user", "edit", node="s8-t1", summary="자료 적용 전 안내가 보인다.")
        check("` 시험 재료 — 문서 파일이 찾아짐", wait_for(lambda: "파일 없음: docs/hand_off.md" not in fr.evaluate("document.body.innerText"), 6))
        for scr in ("main", 8):
            go(fr, scr, "s8-t1")
            pick(fr, "s8-t1")
            page.keyboard.press("Backquote")
            opened = wait_for(lambda: fr.locator("main.doc-mod").count() == 1, 3)
            check(f"` {scr} — 작업 노드는 자세히 패널", opened and "앱 진입" in fr.locator("main").inner_text())
            check(f"` {scr} — 문서 파일은 안 열림", page.evaluate("window.devview.activePath()") != "docs/hand_off.md"
                  and not page.evaluate("document.querySelector('.dv-main').classList.contains('is-ftsplit')"), page.evaluate("window.devview.activePath()"))
            page.keyboard.press("Backquote")
            wait_for(lambda: fr.locator("main.doc-mod").count() == 0, 3)
            fr.locator(".flow").press("Escape")
        fr.evaluate("window.__flowtree.zoomTo(0.5)")
        time.sleep(0.4)

        # ======= 진행 색 — 착수 · 검증 중 · 답변 준비 중 = 노랑 빙글 · 5분 넘음 = 주황 빙글 · 완료 = 녹색 =======
        import flowtree_store as fs  # noqa: E402
        mk = lambda title: fs.apply(tp, "main", "add", parent="-", title=title, summary="진행 색", section=1)["id"]  # noqa: E731
        c_doing, c_late, c_done = mk("진행 작업"), mk("늦은 작업"), mk("끝난 작업")
        for t in (c_doing, c_late, c_done):
            fs.apply(tp, "main", "start", task=t)
        fs.apply(tp, "main", "done", task=c_done)
        c_ver = fs.apply(tp, "main", "verify-add", target=c_done, what="진행 색 검증", section=1)["id"]
        fs.apply(tp, "insp", "verify-start", verify=c_ver)
        c_q = fs.apply(tp, "user", "ask", text="진행 색 질문", target=c_done)["id"]
        fs.apply(tp, "2nd", "answer-start", question=c_q)
        # 늦은 작업 — 착수 기록 시각을 7분 전으로(화면이 착수 시각으로 계산)
        tree = json.loads(tp.read_text(encoding="utf-8"))
        late_node = next(n for n in tree["nodes"] if n["id"] == c_late)
        late_node["events"][-1]["ts"] = time.time() - 420
        tp.write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
        go(fr, "main", "t2")
        go(fr, 1, c_q)
        ids = [c_doing, c_late, c_done, c_ver, c_q]
        wait_for(lambda: fr.evaluate(f"(() => {{ const e = document.querySelector('.react-flow__node[data-id=\"{c_late}\"] .wk'); return !!e && e.dataset.status === 'late'; }})()"), 8)
        st = fr.evaluate("""(ids) => Object.fromEntries(ids.map((id) => { const e = document.querySelector(`.react-flow__node[data-id="${id}"] .wk`);
          if (!e) return [id, null]; const s = getComputedStyle(e); return [id, [e.dataset.status, e.classList.contains('m-spin'), s.getPropertyValue('--s').trim(),
          getComputedStyle(e, '::before').backgroundImage]]; }))""", ids)
        want = {c_doing: ("doing", True, "#f4d35e"), c_late: ("late", True, "#ff9f43"), c_done: ("done", False, "#5fcf73"),
                c_ver: ("checking", True, "#f4d35e"), c_q: ("answering", True, "#f4d35e")}
        for nid, (s0, spin, col) in want.items():
            g = st.get(nid)
            check(f"진행 색 — {nid} {s0} = {'빙글' if spin else '점등'} {col}", g and (g[0], g[1], g[2]) == (s0, spin, col), g)
        check("진행 색 — 빙글 그라디언트 = 노랑 rgb(244, 211, 94) · 늦음 = 주황 rgb(255, 159, 67)(눈으로 구분되는 다른 색)",
              st[c_doing] and "rgb(244, 211, 94)" in st[c_doing][3] and "rgb(255, 159, 67)" in st[c_late][3], (st[c_doing], st[c_late]))
        fr.evaluate(f"window.__flowtree.center('{c_late}', 0.9)")
        time.sleep(0.5)
        page.screenshot(path=str(SHOTS / "ft_progress_colors.png"))

        # ======= 좁은 창 =======
        page.set_viewport_size({"width": 620, "height": 800})
        time.sleep(0.5)
        check("좁은 창 — 스위치 줄바꿈 · 잘림 없음", not clipped(fr), clipped(fr))
        page.screenshot(path=str(SHOTS / "ft_screens_narrow.png"))
        check("화면 오류 없음", not errs, errs[:3])
        br.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="dv_fts_"))
    proc = None
    try:
        w = hub.make_world(tmp)
        seed(w["tree"])
        proc, base = hub.start(w)
        # 서버 출력 비우기 — 안 읽으면 파이프가 차서 로그 찍는 요청이 응답 전에 멈춤
        threading.Thread(target=proc.stdout.read, daemon=True).start()
        run(w, base)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(5)
            except Exception:  # noqa: BLE001
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    # 결과 목록
    res = hub.RESULTS
    bad = [n for n, ok in res if not ok]
    print(f"결과: {len(res) - len(bad)}/{len(res)} 통과" + (f" · 실패 {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
