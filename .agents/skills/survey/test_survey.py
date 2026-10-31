#!/usr/bin/env python3
# HTML 설문 도구 끝-끝 시험 — 실제 서버를 임시 폴더 · 빈 포트로 띄우고 등록 → 화면 → 제출 → 대기 결과까지 확인
#   python3 .agents/skills/survey/test_survey.py
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("survey.py")
# 실패 목록
FAILS = []


# 확인 하나 — 통과/실패 출력, 실패는 목록에 모음
# name: 확인 이름 / ok: 결과
def check(name: str, ok: bool) -> None:
    print(("  통과 " if ok else "  실패 ") + name, flush=True)
    if not ok:
        FAILS.append(name)


# 비어 있는 포트 하나 얻기
def free_port() -> int:
    # 임시 소켓
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    # 운영체제가 준 포트
    port = s.getsockname()[1]
    s.close()
    return port


# 시험용 환경 — 등록 목록 파일을 임시 폴더에(실제 ~/.devview 목록을 건드리지 않게). main 이 채움
ENV = {}


# 도구 명령 실행 → (종료코드, 표준 출력)
# folder: 저장 폴더 / args: 하위 명령 인자
def run(folder: Path, *args) -> tuple:
    # 실행 결과
    r = subprocess.run([sys.executable, str(TOOL), "--dir", str(folder), *args],
                       capture_output=True, text=True, encoding="utf-8", timeout=30, env=ENV)
    return r.returncode, r.stdout


# HTTP 요청 → (상태 코드, 본문)
# url: 주소 / form: 보낼 폼(없으면 GET)
def http(url: str, form: dict = None) -> tuple:
    # 보낼 본문
    data = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    # 4xx · 5xx 응답
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8")


# 시험 본체
def main() -> int:
    # 출력 인코딩을 코드에서 고정
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    # 임시 저장 폴더
    folder = Path(tempfile.mkdtemp(prefix="survey_test_"))
    ENV.update(os.environ, SURVEY_REGISTRY=str(folder / "_registry.json"))
    # 시험 포트
    port = free_port()
    # 서버 프로세스
    server = subprocess.Popen([sys.executable, str(TOOL), "--dir", str(folder), "serve", "--port", str(port)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", env=ENV)
    try:
        # 서버 첫 줄(시작 알림)
        first = server.stdout.readline()
        check("서버 시작 · 0.0.0.0 바인딩", "0.0.0.0" in first)
        # 서버 기본 주소
        base = f"http://127.0.0.1:{port}"

        # 질문 파일
        qfile = Path(tempfile.mkdtemp(prefix="survey_q_")) / "q.json"
        qfile.write_text(json.dumps({"title": "시험 설문", "questions": [
            {"id": "1-1 #1", "question": "재시도 간격은?", "decide": "재시도 사이 간격을 정한다",
             "context": "줄바꿈\n두 번째 줄", "source": "원문 <b>태그</b>",
             "example": "| 칸 | 값 |\n|---|---|\n| a | b |\n\n- 위\n\t- 아래", "pros": ["**굵게** 장점"],
             "cons": ["단점 <i>기울임</i>"], "recommend": "1초 — 과제 규모에 충분",
             "options": [{"label": "(추천) 1초", "detail": "고정", "pros": ["빠름"], "cons": "느린 서버엔 부족"}, "2초"]},
            {"id": "1-1 #2", "question": "보류할 질문", "options": ["A", "B"]},
            {"id": "1-1 #3", "question": "기타 질문(옛 이름)", "options": ["A"]},
            {"id": "1-1 #4", "question": "질문할 질문", "options": ["A"]},
            {"id": "1-1 #5", "question": "새 기타 · 보류가 선택지에 적힌 질문", "options": ["A", "보류"]}]},
            ensure_ascii=False), encoding="utf-8")

        print("① 등록", flush=True)
        # 등록 결과
        code, out = run(folder, "new", str(qfile), "--project", "시험")
        # 설문 정보
        info = json.loads(out)
        # 설문 id
        sid = info["id"]
        # 프로젝트 폴더
        pdir = folder / "시험"
        check("등록 종료코드 0 · id 있음 · 프로젝트 폴더에 저장", code == 0 and bool(sid) and (pdir / f"{sid}.json").exists())
        check("등록 목록 파일에 저장 폴더", str(folder.resolve())
              in json.loads((folder / "_registry.json").read_text(encoding="utf-8")))

        print("② 화면", flush=True)
        # 화면 응답 — 옛 주소는 새 주소로 넘어감(urllib 가 따라감)
        status, page = http(f"{base}/survey/{sid}")
        check("화면 200(옛 주소 → 새 주소)", status == 200)
        check("왼쪽 목록: 프로젝트 · 대기 1 · 완료 0", "id='side'" in page and "시험" in page
              and "<span>대기</span><span>1</span>" in page and "<span>완료</span><span>0</span>" in page)
        # 새 주소로 바로
        status_b, page_b = http(base + "/" + info["path"].lstrip("/"))
        check("새 주소 화면 200 · 같은 설문", status_b == 200 and "재시도 간격은?" in page_b)
        # 주소 없이 열면 최근 대기 설문
        _, page_c = http(f"{base}/")
        check("주소 없이 열면 최근 대기 설문", "재시도 간격은?" in page_c and "a class='sv pend on'" in page_c)
        # 상태
        _, st = http(f"{base}/api/state")
        st = json.loads(st)
        check("상태: 대기 1 · 최근 설문 id", st["pending"] == 1 and st["newest"]["id"] == sid)
        check("좌우 폭 제한 없음(본문 · 질문 카드)", re.search(r"(main|body|\.q)\{[^}]*max-width", page) is None)
        check("원문 상자 · 태그 이스케이프", "<summary>원문</summary>" in page and "&lt;b&gt;태그" in page)
        check("결정할 것 상자(맨 위 · 보라)", "class='box decide'" in page and "#9d7bea" in page
              and "재시도 사이 간격을 정한다" in page)
        check("제안 노랑 상자", "class='box rec'><span class='bt'>제안</span>" in page)
        check("짧은 마크다운: 표 · 중첩 목록 · 굵게", "<th>칸</th>" in page and "<ul><li>위<ul><li>아래" in page
              and "<b>굵게</b>" in page)
        check("글 칸도 태그 이스케이프", "&lt;i&gt;기울임" in page and "<i>기울임" not in page)
        check("선택지 풀이 · 장단점은 툴팁 원본(숨김) 안에",
              "<div class=tipsrc><div class='box gray'><span class='bt'>풀이</span>" in page
              and "<div class='box pros'><span class='bt'>장점</span>" in page and "느린 서버엔 부족" in page)
        check("툴팁 없는 선택지엔 ⓘ 표시 없음", page.count("class=ti>") == 1)
        check("추천 = 노란 테두리 · «(추천)» 머리는 숨김", "label class='opt recd'" in page and ">(추천) 1초" not in page)
        check("메모 칸 + 기타 · 보류 · 질문 단추(선택지와 같은 묶음)", page.count("class='memo'") == 5
              and page.count("value='보류'") == 5 and page.count("value='기타'") == 5
              and page.count("value='질문'") == 5 and "<label><input type='radio' name='q1' value='기타'>" in page)
        check("선택지에 적힌 «보류»는 두 번 안 나옴", page.count("value='보류'") == 5)
        check("제출 주소 = 이 설문 주소(상대 «?s=…&p=…&id=…»)", "action='?s=" in page and f"id={sid}'" in page)
        check("주소 없이 연 첫 화면도 제출 주소에 설문 id(devview 설문 탭 첫 화면)", f"id={sid}'" in page_c)
        # 프록시 접두어가 붙은 주소
        status2, _ = http(f"{base}/proxy/{port}/survey/{sid}")
        check("접두어 붙은 주소에서도 화면", status2 == 200)

        print("②-2 쓰던 답(초안) — 다른 설문으로 갔다 와도 남음", flush=True)
        # 화면 주소 값(s · p · id)
        qs = info["path"].split("?", 1)[1]
        status_d, _ = http(f"{base}/api/draft?{qs}", {"q1": "2초", "q1_memo": "초안 메모", "extra": "초안 지시",
                                                     "_act": "submit"})
        check("초안 저장 200 · 파일 생김", status_d == 200 and (pdir / f"{sid}.draft.json").exists())
        _, page_d = http(base + "/" + info["path"].lstrip("/"))
        check("다시 열면 고른 답 · 메모 · 추가 지시가 채워짐", "value='2초' checked" in page_d
              and ">초안 메모</textarea>" in page_d and ">초안 지시</textarea>" in page_d)
        check("초안으로 제출이 되지는 않음(결과 파일 없음)", not (pdir / f"{sid}.result.json").exists())
        _, st_d = http(f"{base}/api/state")
        check("초안 파일은 설문 목록에 안 섞임(대기 1)", json.loads(st_d)["pending"] == 1)
        status_bad, _ = http(f"{base}/api/draft?id=20000101-000000", {"q1": "A"})
        check("없는 설문 초안 = 404", status_bad == 404)
        status_s, _ = http(f"{base}/api/draft?id={sid}", {"q1": "2초", "q1_memo": "초안 메모", "extra": "초안 지시"})
        check("열쇠 없이 id 만 와도 그 설문에 저장(devview 주소)", status_s == 200)

        print("③ 대기 · 제출", flush=True)
        # 대기 프로세스 — 제출 전에는 아무것도 출력하지 않아야 함
        waiter = subprocess.Popen([sys.executable, str(TOOL), "--dir", str(folder), "wait", sid],
                                  stdout=subprocess.PIPE, text=True, encoding="utf-8")
        time.sleep(1.5)
        check("제출 전 대기는 안 끝남", waiter.poll() is None)
        # 제출 응답
        status4, done = http(f"{base}/survey/{sid}", {"q1": "(추천) 1초", "q1_memo": "담당자 합의",
                                                     "q2_memo": "보류 이유",
                                                     "q3": "기타(메모에 적기)", "q3_memo": "직접 답",
                                                     "q4": "질문", "q4_memo": "이게 뭐지?",
                                                     "q5": "기타", "q5_other": "새 답", "q5_ask": "덤 질문",
                                                     "extra": "다음 할 일", "_act": "submit"})
        check("제출 → 같은 설문 기록 보기", status4 == 200 and "<span class='stamp'>완료</span>" in done)
        check("제출하면 초안 파일 지움", not (pdir / f"{sid}.draft.json").exists())
        status_late, _ = http(f"{base}/api/draft?{qs}", {"q1": "A"})
        check("제출 뒤 초안 저장 = 409(결과를 덮지 않음)", status_late == 409
              and not (pdir / f"{sid}.draft.json").exists())
        check("기록 보기: 고른 답 · 메모 · 읽기 전용", "value='(추천) 1초' checked disabled" in done
              and ">담당자 합의</textarea>" in done and "value='질문' checked disabled" in done
              and "name='_act'" not in done and ">다음 할 일</textarea>" in done)
        check("기록 보기: 왼쪽 완료 목록(회색)", "<span>완료</span><span>1</span>" in done and "a class='sv done on'" in done)
        # 대기 출력
        wout, _ = waiter.communicate(timeout=10)
        check("대기 종료코드 0", waiter.returncode == 0)
        # 결과 내용
        res = json.loads(wout)
        # 질문별 답
        ans = res["answers"]
        check("action accept", res["action"] == "accept")
        check("선택 + 덧붙일 말 문장 · kind option", ans[0]["text"] == "(추천) 1초 — 담당자 합의" and ans[0]["kind"] == "option")
        check("고르지 않음 = 보류 · 빈 답 · kind hold · 메모는 남음", ans[1]["choice"] == "보류"
              and ans[1]["text"] == "" and ans[1]["kind"] == "hold" and ans[1]["memo"] == "보류 이유")
        check("옛 기타 이름 = 기타 · 메모가 답", ans[2]["choice"] == "기타" and ans[2]["kind"] == "other"
              and ans[2]["text"] == "직접 답")
        check("질문 = 메모가 답 · kind ask", ans[3]["choice"] == "질문" and ans[3]["kind"] == "ask"
              and ans[3]["text"] == "이게 뭐지?")
        check("옛 화면 기타 칸 = 답 · 다른 칸 글도 남음", ans[4]["kind"] == "other" and ans[4]["text"] == "새 답"
              and ans[4]["ask"] == "덤 질문")
        check("추가 지시 반환", res["extra"] == "다음 할 일")
        check("결과 파일이 프로젝트 폴더에", (pdir / f"{sid}.result.json").exists())
        # 중복 제출 응답
        status5, _ = http(f"{base}/survey/{sid}", {"_act": "submit"})
        check("중복 제출 막음(410)", status5 == 410)
        # 조회 결과
        code6, out6 = run(folder, "result", sid)
        check("result 조회", code6 == 0 and json.loads(out6)["action"] == "accept")

        print("④ 취소 · 오류", flush=True)
        # 두 번째 설문
        _, out7 = run(folder, "new", str(qfile), "--project", "시험")
        # 두 번째 설문 id
        sid2 = json.loads(out7)["id"]
        check("같은 초 등록도 id 겹치지 않음", sid2 != sid)
        # 제출 전 조회
        _, out8 = run(folder, "result", sid2)
        check("제출 전 조회 = pending", json.loads(out8)["action"] == "pending")
        _, cpage = http(f"{base}/survey/{sid2}", {"_act": "cancel"})
        check("취소 결과 저장 · 취소됨 표시", json.loads((pdir / f"{sid2}.result.json").read_text(encoding="utf-8"))["action"]
              == "cancel" and "<span class='stamp'>취소됨</span>" in cpage)
        # 프로젝트 폴더 없는 옛 설문(저장 폴더 바로 아래) — «분류 없음» 프로젝트로 보임
        (folder / "20200101-000000.json").write_text(json.dumps({"id": "20200101-000000", "title": "옛 설문",
                                                                  "questions": [{"question": "옛", "options": ["A"]}],
                                                                  "created": "2020-01-01 00:00:00"}, ensure_ascii=False),
                                                      encoding="utf-8")
        _, side = http(f"{base}/api/side")
        check("옛 설문 = 분류 없음 프로젝트", "분류 없음" in side)
        # 없는 설문 대기
        code9, _ = run(folder, "wait", "없는id")
        check("없는 설문 대기 = 종료코드 2", code9 == 2)
        # 없는 설문 화면
        status10, _ = http(f"{base}/survey/nothing")
        check("없는 설문 화면 = 404", status10 == 404)
        # ======= 설명 모드 — 설명 폼 형식(items · title · body)을 그대로 받아 설명 카드 + 메모만 =======
        ex = folder / "ex.json"
        ex.write_text(json.dumps({"title": "설명 시험", "project": "시험", "intro": "머리 **설명**",
                                  "items": [{"id": "A", "title": "첫 항목", "body": "본문 <b>태그</b>", "source": "원문 줄"},
                                            {"id": "B", "title": "둘째 항목", "body": "- 목록"}]}, ensure_ascii=False),
                      encoding="utf-8")
        code_e, out_e = run(folder, "new", str(ex))
        eid = json.loads(out_e)["id"] if code_e == 0 else ""
        saved = json.loads((pdir / f"{eid}.json").read_text(encoding="utf-8")) if eid else {}
        check("설명 폼 형식 등록 → mode explain · 항목 제목이 질문", saved.get("mode") == "explain"
              and saved["questions"][0]["question"] == "첫 항목")
        _, epage = http(f"{base}/?s={urllib.parse.quote(st['newest']['s'])}&p={urllib.parse.quote('시험')}&id={eid}")
        check("설명 화면: 개요 · 설명 상자 · 메모 칸 둘 · 선택지 · 기타 단추 없음",
              "<span class='bt'>개요</span>" in epage and epage.count("<span class='bt'>설명</span>") == 2
              and epage.count("class='memo'") == 2 and "type='radio'" not in epage)
        check("설명 화면: 본문 태그 이스케이프 · 원문 상자", "&lt;b&gt;태그" in epage and "<summary>원문</summary>" in epage)
        heads = [epage.find(f"<span>{h}</span>") for h in ("대기", "질문", "완료")]
        check("왼쪽 목록: 대기 · 질문 · 완료 순 · 설명 폼은 질문 칸(대기 0 · 질문 1 · 완료 2 = 제출 · 취소한 설문 폼)",
              -1 < heads[0] < heads[1] < heads[2] and "<span>대기</span><span>0</span>" in epage
              and "<span>질문</span><span>1</span>" in epage and "<span>완료</span><span>2</span>" in epage
              and heads[1] < epage.find("a class='sv pend on'") < heads[2])
        _, edone = http(f"{base}/?s={urllib.parse.quote(st['newest']['s'])}&p={urllib.parse.quote('시험')}&id={eid}",
                        {"_act": "submit", "q1_memo": "왜 이렇게?", "q2_memo": "", "extra": "다음"})
        eres = json.loads((pdir / f"{eid}.result.json").read_text(encoding="utf-8"))
        check("설명 제출: accept · kind memo · 메모 · 빈 메모도 남음",
              eres["action"] == "accept" and [a["kind"] for a in eres["answers"]] == ["memo", "memo"]
              and eres["answers"][0]["memo"] == "왜 이렇게?" and eres["answers"][1]["memo"] == "")
        check("설명 기록 보기: 완료 · 메모 읽기 전용", "<span class='stamp'>완료</span>" in edone and "readonly" in edone
              and "왜 이렇게?" in edone)
        check("제출한 설명 폼도 질문 칸에 회색으로 남음(완료 칸은 설문 폼만 2)",
              "<span>질문</span><span>1</span>" in edone and "<span>완료</span><span>2</span>" in edone
              and edone.find("<span>질문</span>") < edone.find("a class='sv done on'") < edone.find("<span>완료</span>"))
        bad = folder / "bad.json"
        bad.write_text(json.dumps({"title": "x", "mode": "quiz", "questions": [{"question": "q"}]}), encoding="utf-8")
        check("모르는 mode = 종료코드 2", run(folder, "new", str(bad))[0] == 2)
    finally:
        server.terminate()
        server.wait(timeout=10)

    print("PASS" if not FAILS else f"FAIL {len(FAILS)} — " + " · ".join(FAILS), flush=True)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
