# kit 도구 시험 — 임시 폴더의 hand_off · WORKLOG 사본 · 임시 git 저장소로(실제 문서 · 저장소는 안 건드림)
#   python3 scripts/kit/test_kit.py        (윈도우는 py -3)
# 확인: 진입점 · --args JSON · handoff 8개 명령 · 🚹 줄 보존 · 한 줄 거부 · worklog 덧붙이기 · commit 좁은 선택자 · status
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import handoff  # noqa: E402

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail)[:300] if detail and not ok else ''}", flush=True)


def kit(*args, cwd=None, stdin=None):
    r = subprocess.run([sys.executable, str(HERE / "kit.py"), *args], capture_output=True, text=True, encoding="utf-8",
                       cwd=cwd, input=stdin, env=dict(os.environ, PYTHONUTF8="1"))
    return r.returncode, r.stdout + r.stderr


def main():
    tmp = Path(tempfile.mkdtemp(prefix="kit_test_"))
    try:
        ho = tmp / "hand_off.md"
        shutil.copy(KIT / "docs" / "hand_off.md", ho)
        wl = tmp / "WORKLOG.md"
        shutil.copy(KIT / "docs" / "WORKLOG.md", wl)
        D = ["--doc", str(ho)]

        # ① 양식과 뼈대 상수가 같은가(양식을 고치면 이 시험이 알려 준다)
        t = (KIT / "docs" / "hand_off.md").read_text(encoding="utf-8").split("\n")
        i = t.index(handoff.PLACE_HEAD)
        body = "\n".join(t[i + 2:]).rstrip("\n")
        check("① 섹션 뼈대 상수 = docs/hand_off.md 양식 섹션", body == handoff.SECTION_BODY)

        # ② 진입점 · 도움말
        c, o = kit("help")
        check("② kit help — 도구 목록", c == 0 and "handoff" in o and "status" in o)
        c, o = kit("nope")
        check("② 없는 도구 거부", c == 2)

        # ③ section-new — 첫 섹션은 양식 빈 섹션을 이어 씀 · 둘째는 끝에 덧붙임
        c, o = kit("handoff", *D, "section-new", "1-1", "주문 조회", "--risk", "민감")
        s = ho.read_text(encoding="utf-8")
        check("③ 첫 섹션 — 양식 제목 줄을 바꿈", c == 0 and "## 1-1 · 주문 조회 — 민감" in s and handoff.PLACE_HEAD not in s, o)
        check("③ 진행 기록 양식 줄 → 1-1 ⬜", "| 1-1 | 주문 조회 | 민감 | ⬜ | — |" in s)
        c, o = kit("handoff", *D, "section-new", "1-2", "현황 화면", "--risk", "저위험")
        s = ho.read_text(encoding="utf-8")
        check("③ 둘째 섹션 — 끝에 뼈대 블록 8개", c == 0 and s.count("> [!abstract] ✅ 목표") == 2 and s.count("## 1-2 · 현황 화면 — 저위험") == 1, o)
        c, o = kit("handoff", *D, "section-new", "1-2", "또", "--risk", "민감")
        check("③ 같은 번호 거부", c == 2)
        c, o = kit("handoff", *D, "section-new", "1-3", "이름\n둘째 줄", "--risk", "민감")
        check("③ 여러 줄 이름 거부(한 줄만)", c == 2 and "여러 줄" in o, o)

        # ④ scope-approve — 🚹 답에 «승인» 이 없으면 거부 · 있으면 초록 · --chat
        c, o = kit("handoff", *D, "scope-approve", "1-1")
        check("④ 답 줄이 빈 🚹 → 거부", c == 2 and "승인" in o, o)
        lines = ho.read_text(encoding="utf-8").split("\n")
        s1 = [k for k, l in enumerate(lines) if l == "## 1-1 · 주문 조회 — 민감"][0]
        k = next(k for k in range(s1, len(lines)) if lines[k] == "> > 🚹")
        lines[k] = "> > 🚹 승인"   # 유저가 쓴 답(시험에서는 사람 대신)
        ho.write_text("\n".join(lines), encoding="utf-8")
        c, o = kit("handoff", *D, "scope-approve", "1-1")
        s = ho.read_text(encoding="utf-8")
        check("④ «승인» 답 → success · 승인 🟢", c == 0 and "> [!success] ✅ 수정 범위 · 승인 🟢" in s and "> > 🚹 승인" in s, o)
        c, o = kit("handoff", *D, "scope-approve", "1-2", "--chat")
        sec2 = ho.read_text(encoding="utf-8").split("## 1-2 · 현황 화면 — 저위험")[1]
        check("④ --chat(대화 승인) — 빈 🚹 줄 그대로 · 상자 초록", c == 0 and "> [!success] ✅ 수정 범위 · 승인 🟢" in sec2 and "> > 🚹\n" in sec2, o)
        # CRLF 문서 — 줄 끝을 그대로 지킨다
        crlf = tmp / "crlf.md"
        crlf.write_bytes(ho.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        c, o = kit("handoff", "--doc", str(crlf), "order-add", "1-9", "--plan", "줄 끝 시험")
        raw = crlf.read_bytes()
        check("④ CRLF 문서 — 고친 뒤에도 전부 CRLF", c == 0 and raw.count(b"\n") == raw.count(b"\r\n") and "줄 끝 시험".encode() in raw, o)

        # ⑤ scope-change — 변경 1 등록 → 주황 · 답 없이는 재승인 거부
        c, o = kit("handoff", *D, "scope-change", "1-1", "src/ui/page.py", "결과 표시", "«확인 중» 을 보여야 해서")
        s = ho.read_text(encoding="utf-8")
        check("⑤ 변경 1 줄 + 빈 답 칸 · 상자 주황 · 제목 «변경 1 승인 대기 🟠»",
              c == 0 and "> - 🟠 **변경 1** · src/ui/page.py — 결과 표시" in s and "> [!warning] ✅ 수정 범위 · 변경 1 승인 대기 🟠" in s, o)
        c, o = kit("handoff", *D, "scope-approve", "1-1")
        check("⑤ 변경 1 답 없음 → 거부", c == 2, o)

        # ⑥ verify-log — 새 행 · 기존 행 갱신 · 상자 색 · 통과 커밋 덧붙이기 · 양식 예시 행 걷기
        c, o = kit("handoff", *D, "verify-log", "1-1", "UI-1", "--result", "통과", "--desc", "실패하면 버튼이 잘리지 않고 보인다",
                   "--file", "src/ui/app.py", "--func", "show_error", "--expect", "버튼 보임", "--actual", "버튼 보임", "--commit", "a1b2c3d")
        s = ho.read_text(encoding="utf-8")
        sec = s.split("## 1-1 · 주문 조회 — 민감")[1].split("## 1-2")[0]
        check("⑥ 새 행 UI-1 — 요약 · 상세 표 · 통과 커밋", c == 0 and "> | UI-1 | 실패하면 버튼이 잘리지 않고 보인다 |" in sec
              and "UI-1 | UI | src/ui/app.py | show_error | 버튼 보임 | 버튼 보임 | 🟢" in sec and "> > - 통과 커밋: a1b2c3d" in sec, o)
        check("⑥ 양식 예시 행(API-1 빈칸) 걷어 냄 · 모두 🟢 → 상자 초록", "(자연어로" not in sec and "[!decision-done]- ✅ 검증 기록 🟢" in sec, sec[sec.find("검증 기록") - 20:][:600])
        c, o = kit("handoff", *D, "verify-log", "1-1", "API-2", "--result", "실패", "--desc", "연결 실패 때 3번까지만 다시 시도", "--actual", "요청 5건")
        sec = ho.read_text(encoding="utf-8").split("## 1-1 · 주문 조회 — 민감")[1].split("## 1-2")[0]
        check("⑥ 실패 행 → 상자 빨강 · 새 카테고리 API 표", c == 0 and "[!decision-open]- ✅ 검증 기록 🔴" in sec and "> **API**" in sec and "🔴" in sec, o)
        c, o = kit("handoff", *D, "verify-log", "1-1", "API-2", "--result", "통과", "--actual", "요청 3건", "--action", "1회차 수정", "--commit", "d4e5f6a")
        sec = ho.read_text(encoding="utf-8").split("## 1-1 · 주문 조회 — 민감")[1].split("## 1-2")[0]
        check("⑥ 같은 행 갱신(새 줄 안 늘어남) · 커밋 덧붙임 · 초록", sec.count("API-2 | API") == 1 and "요청 3건" in sec and "a1b2c3d · d4e5f6a" in sec
              and "[!decision-done]- ✅ 검증 기록 🟢" in sec, o)
        c, o = kit("handoff", *D, "verify-log", "1-1", "API-3", "--result", "통과")
        check("⑥ 새 행인데 --desc 없음 → 거부", c == 2)
        c, o = kit("handoff", *D, "verify-log", "1-1", "API-3", "--result", "통과", "--desc", "a | b")
        check("⑥ 표 칸에 «|» 거부", c == 2)

        # ⑦ order-add · progress
        c, o = kit("handoff", *D, "order-add", "1-1", "--plan", "조회가 모든 기능의 바탕", "--actual", "1회차 · 대기 한도 · a1b2c3d", "--basis", "1-1 #1", "--next", "1-2")
        s = ho.read_text(encoding="utf-8")
        check("⑦ 순서 1 — 양식 줄 바꿈", c == 0 and "| 1 | 1-1 | 조회가 모든 기능의 바탕 | 1회차 · 대기 한도 · a1b2c3d | 1-1 #1 | 1-2 |" in s and "(왜 이 순서인가)" not in s, o)
        c, o = kit("handoff", *D, "order-add", "1-2", "--plan", "화면은 마지막")
        s = ho.read_text(encoding="utf-8")
        check("⑦ 순서 2 — 덧붙임 · 빈 칸 —", c == 0 and "| 2 | 1-2 | 화면은 마지막 | — | — | — |" in s, o)
        c, o = kit("handoff", *D, "progress", "1-1", "--result", "끝남", "--commit", "d4e5f6a")
        check("⑦ 진행 기록 1-1 🟢 · 통과 커밋", c == 0 and "| 1-1 | 주문 조회 | 민감 | 🟢 | d4e5f6a |" in ho.read_text(encoding="utf-8"), o)

        # ⑧ list · show · 🚹 줄 보존 · --args JSON
        c, o = kit("handoff", *D, "list")
        check("⑧ list — 두 섹션 상태", c == 0 and "1-1 · 주문 조회" in o and "1-2 · 현황 화면" in o, o)
        c, o = kit("handoff", *D, "show", "1-2")
        check("⑧ show 1-2 — 그 섹션만", c == 0 and "## 1-2 · 현황 화면" in o and "## 1-1" not in o, o[:200])
        human = [l for l in ho.read_text(encoding="utf-8").split("\n") if "🚹" in l]
        check("⑧ 🚹 줄 그대로(승인 줄 포함)", "> > 🚹 승인" in human)
        c, o = kit("handoff", "--args", json.dumps({"_": ["--doc", str(ho), "order-add", "1-3"], "plan": "따옴표 \"' · 한글"}, ensure_ascii=False))
        check("⑧ --args JSON 객체 — 따옴표 섞인 글", c == 0 and "| 3 | 1-3 | 따옴표 \"' · 한글 |" in ho.read_text(encoding="utf-8"), o)
        c, o = kit("handoff", "--args", "-", stdin=json.dumps(["--doc", str(ho), "show", "순서"]))
        check("⑧ --args - (표준입력 목록)", c == 0 and "섹션 작업 순서" in o, o)

        # ⑨ worklog
        before = wl.read_text(encoding="utf-8")
        c, o = kit("worklog", "--doc", str(wl), "add", "--section", "1-1", "--kind", "구현", "--did", "대기 한도 10초", "--files", "src/api/orders.py", "--commit", "a1b2c3d")
        s = wl.read_text(encoding="utf-8")
        check("⑨ add — 맨 끝 덧붙임 · 옛 내용 그대로", c == 0 and s.startswith(before.rstrip("\n")) and "· 1-1 · 구현" in s and "- **커밋**: a1b2c3d" in s, o)
        c, o = kit("worklog", "--doc", str(wl), "fact", "--type", "AI 제안 고침", "1-1 · 재시도 무한 → 3회 · a1b2c3d")
        s = wl.read_text(encoding="utf-8")
        fact_at = s.find("- [AI 제안 고침] 1-1 · 재시도 무한")
        check("⑨ fact — 서술형 재료 칸 안(기록 절보다 위)", c == 0 and 0 < fact_at < s.find("## 기록"), o)
        c, o = kit("worklog", "--doc", str(wl), "fact", "--type", "아무거나", "x")
        check("⑨ fact 유형 밖 거부", c == 2)
        c, o = kit("worklog", "--doc", str(wl), "add", "--section", "1-1", "--kind", "구현", "--did", "줄1\n줄2")
        check("⑨ 여러 줄 거부", c == 2)

        # ⑩ commit — 좁은 선택자만 · 그 파일만
        repo = tmp / "repo"
        repo.mkdir()
        g = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8")  # noqa: E731
        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        (repo / "a.txt").write_text("a", encoding="utf-8")
        (repo / "b.txt").write_text("b", encoding="utf-8")
        (repo / "d").mkdir()
        c, o = kit("commit", ".", "-m", "x", cwd=repo)
        check("⑩ «.» 거부", c == 2)
        c, o = kit("commit", "d", "-m", "x", cwd=repo)
        check("⑩ 폴더 거부", c == 2)
        c, o = kit("commit", "*.txt", "-m", "x", cwd=repo)
        check("⑩ 와일드카드 거부", c == 2)
        g("add", "b.txt")   # 다른 세션이 스테이지해 둔 파일 흉내
        c, o = kit("commit", "a.txt", "-m", "[시험] a 만 - 확인", "--role", "main", cwd=repo)
        files = g("show", "--name-only", "--format=", "HEAD").stdout.split()
        body = g("log", "-1", "--format=%B").stdout
        check("⑩ a.txt 만 커밋 · 스테이지된 b.txt 는 빠짐 · Kit-Role", c == 0 and files == ["a.txt"] and "Kit-Role: main" in body and "b.txt" in o, (o, files))

        # ⑫ config — 규칙 파일 «없는 것만» 넣기(임시 홈)
        home = tmp / "home" / ".codex"
        home.mkdir(parents=True)
        (home / "config.toml").write_text('model = "x"\n', encoding="utf-8")
        c, o = kit("config", "--target", str(home / "config.toml"))
        check("⑫ config 비교만 — 규칙 없음 안내 · 파일 안 생김", c == 0 and "kit.rules: 없음" in o and not (home / "rules" / "kit.rules").exists(), o[-300:])
        c, o = kit("config", "--target", str(home / "config.toml"), "--apply")
        rf = home / "rules" / "kit.rules"
        check("⑫ config --apply — 규칙 넣음(키트와 같은 내용)", c == 0 and rf.is_file() and rf.read_bytes() == (KIT / ".codex" / "rules" / "kit.rules").read_bytes(), o[-300:])
        rf.write_text("# 유저가 고친 규칙\n", encoding="utf-8")
        c, o = kit("config", "--target", str(home / "config.toml"), "--apply")
        check("⑫ 이미 있는 규칙은 다르면 그대로 둠", "다름(그대로 둠" in o and rf.read_text(encoding="utf-8") == "# 유저가 고친 규칙\n", o[-300:])

        # ⑪ status(실제 키트 · 읽기 전용)
        c, o = kit("status", "--role", "2nd", cwd=KIT)
        check("⑪ status — 칸 제목들", c == 0 and all(k in o for k in ("## 인계", "## 그래프 할 일", "## hand_off 섹션", "## 답 없는 설문", "## 답할 책 스티커", "## 커밋 안 된 파일")), o[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {sum(R)}/{len(R)}")
    return all(R)


def test_kit():
    assert main()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
