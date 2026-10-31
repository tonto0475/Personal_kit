#!/usr/bin/env python3
# 인지 설문 시험 — 재료 → 질문 파일(10문항씩 · 선택지 예/아니오 · 메모 기본 글 없음) → 키트 survey.py 등록 → 결과 → 후속 설명 폼
#   python3 ~/.codex/skills/checking/test_cognition.py
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cognition  # noqa: E402

SURVEY = HERE.parent / "survey" / "survey.py"
FAILS = []


def check(name: str, ok: bool) -> None:
    print(("  통과 " if ok else "  실패 ") + name, flush=True)
    if not ok:
        FAILS.append(name)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cog_"))
    material = {"title": "08 연마 화면",
                "readme": [{"text": "검사자 이름은 화면 · 제출물에 남기지 않는다", "source": "검사 결과에는 검사자 이름이 들어 있습니다."}]
                          + [f"요구 {i}" for i in range(2, 9)],
                "do": ["설비별 불량률 표", "주차 비교"], "dont": ["로그인"]}
    (tmp / "m.json").write_text(json.dumps(material, ensure_ascii=False), encoding="utf-8")

    # 1) make — 11문항 → 10 + 1 두 파일
    r = subprocess.run([sys.executable, str(HERE / "cognition.py"), "make", str(tmp / "m.json"), "--out", str(tmp / "cog")],
                       capture_output=True, text=True, encoding="utf-8")
    check("make 종료코드 0", r.returncode == 0)
    out = json.loads(r.stdout)
    check("11문항 · 파일 2개", out["questions"] == 11 and len(out["files"]) == 2)
    s1 = json.loads(Path(out["files"][0]).read_text(encoding="utf-8"))
    s2 = json.loads(Path(out["files"][1]).read_text(encoding="utf-8"))
    check("1번 파일 10문항 · 2번 1문항", len(s1["questions"]) == 10 and len(s2["questions"]) == 1)
    q1 = s1["questions"][0]
    check("질문 문장 틀", q1["question"] == "문제에 «검사자 이름은 화면 · 제출물에 남기지 않는다» 이런 요구사항이 있었습니다. 이해했습니까?")
    check("선택지 = 예 · 아니오", q1["options"] == ["예", "아니오"])
    check("원문 칸 옮김", q1["source"].startswith("검사 결과에는"))
    keys = {k for q in s1["questions"] + s2["questions"] for k in q}
    check("설명 칸 없음(id · question · options · source 만)", keys <= {"id", "question", "options", "source"})
    check("id 머리 R · D · N", [q["id"] for q in s1["questions"]][-2:] == ["D1", "D2"] and s2["questions"][0]["id"] == "N1")
    check("안 함 문장", "구현하지 않습니다" in s2["questions"][0]["question"])

    # 2) 재료 오류
    (tmp / "bad.json").write_text(json.dumps({"readme": [""]}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(HERE / "cognition.py"), "make", str(tmp / "bad.json"), "--out", str(tmp / "bad")],
                       capture_output=True, text=True, encoding="utf-8")
    check("빈 text → 종료코드 2 · 파일 없음", r.returncode == 2 and "재료 오류" in r.stdout and not (tmp / "bad_1.json").exists())

    # 3) 키트 survey.py 로 등록 · 화면에 기본 메모 글이 지금 폼 그대로인지
    env = dict(os.environ, SURVEY_REGISTRY=str(tmp / "stores.json"))
    r = subprocess.run([sys.executable, str(SURVEY), "--dir", str(tmp / "sv"), "new", out["files"][0], "--project", "t"],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    check("survey.py new 등록", r.returncode == 0 and "id" in r.stdout)
    sys.path.insert(0, str(SURVEY.parent))
    import survey  # noqa: E402
    html = survey.render_form(s1["title"], s1["questions"])
    check("화면 메모 칸 = 기본 안내 글 그대로", "메모 — 기타 · 질문을 고르면 이 글이 답" in html)
    check("화면에 예 · 아니오 · 질문 단추", all(w in html for w in ("예", "아니오", "질문")))

    # 4) followup — 예 · 보류는 빠지고 질문 · 아니오 · 기타만
    result = {"action": "accept", "answers": [
        {"id": "R1", "question": q1["question"], "choice": "예", "kind": "option", "memo": "이름 열 삭제"},
        {"id": "R2", "question": "q2", "choice": "질문", "kind": "ask", "memo": "주차는 어떻게 세?"},
        {"id": "R3", "question": "q3", "choice": "아니오", "kind": "option", "memo": ""},
        {"id": "R4", "question": "q4", "choice": "보류", "kind": "hold", "memo": ""},
        {"id": "R5", "question": "q5", "choice": "기타", "kind": "other", "memo": "반만 이해"}]}
    fu = cognition.build_followup(result, s1)
    check("followup 3항목(R2 · R3 · R5)", [i["id"] for i in fu["items"]] == ["R2", "R3", "R5"])
    check("followup 설명 폼 · 유저 질문 옮김", fu["mode"] == "explain" and "주차는 어떻게 세?" in fu["items"][0]["example"])

    print("결과: " + ("전부 통과" if not FAILS else f"실패 {len(FAILS)}개 — " + " · ".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
