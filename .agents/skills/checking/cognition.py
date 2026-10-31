#!/usr/bin/env python3
# 인지 설문 — 재료(README 요구 · 구현하는 것 · 안 하는 것)를 받아 «이해했습니까?» 설문 질문 파일을 만든다
#   make     재료.json → /tmp/cog_1.json … (10문항씩 나눔) — 등록은 $survey 의 survey.py new
#   followup 결과.json → 질문 · 아니오 · 기타를 고른 항목만 모은 설명 폼 뼈대(body 는 $checking 을 부른 세션이 채운다)
# 실패하면: 재료 칸이 틀리면 «재료 오류 — 무엇» 한 줄 · 종료코드 2 (파일은 만들지 않음)
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PER_SURVEY = 10  # $survey 2절 «한 설문은 10문항 이내»
OPTIONS = ["예", "아니오"]  # 기타 · 보류 · 질문 단추와 메모 칸은 survey.py 가 붙인다(메모 기본 글은 넣지 않는다)

# 칸 이름 → (id 머리, 질문 문장 틀)
KINDS = {
    "readme": ("R", "문제에 «{}» 이런 요구사항이 있었습니다. 이해했습니까?"),
    "do": ("D", "이번에 «{}» 를 구현합니다. 이해했습니까?"),
    "dont": ("N", "이번에 «{}» 는 구현하지 않습니다. 이해했습니까?"),
}


class MaterialError(Exception):
    pass


# 재료 한 줄 → (본문, 원문) — 글 한 줄 또는 {"text", "source"} 둘 다 받는다
def item_parts(kind: str, i: int, it) -> tuple:
    if isinstance(it, str):
        text, source = it, ""
    elif isinstance(it, dict):
        text, source = it.get("text", ""), it.get("source", "")
    else:
        raise MaterialError(f"{kind}[{i}] 는 글 또는 {{text, source}} 여야 한다")
    text = str(text).strip()
    if not text:
        raise MaterialError(f"{kind}[{i}] 의 text 가 비었다")
    return text, str(source or "").strip()


# 재료 → 질문 목록 — 칸 순서 readme → do → dont · id = R1 · D1 · N1
def build_questions(material: dict) -> list:
    if not isinstance(material, dict):
        raise MaterialError("재료는 json 객체여야 한다")
    qs = []
    for kind, (head, tmpl) in KINDS.items():
        items = material.get(kind, [])
        if not isinstance(items, list):
            raise MaterialError(f"{kind} 는 목록이어야 한다")
        for i, it in enumerate(items, 1):
            text, source = item_parts(kind, i, it)
            q = {"id": f"{head}{i}", "question": tmpl.format(text), "options": list(OPTIONS)}
            if source:
                q["source"] = source
            qs.append(q)
    if not qs:
        raise MaterialError("readme · do · dont 가 모두 비었다")
    return qs


# 질문 목록 → 설문 여러 개(10문항씩) — 제목 «인지 확인 · 주제 · 1/2»
def build_surveys(material: dict) -> list:
    qs = build_questions(material)
    topic = str(material.get("title") or "작업 흐름").strip()
    chunks = [qs[i:i + PER_SURVEY] for i in range(0, len(qs), PER_SURVEY)]
    return [{"title": f"인지 확인 · {topic} · {n}/{len(chunks)}", "questions": c} for n, c in enumerate(chunks, 1)]


# 결과 → 설명 폼 뼈대 — 예 · 보류가 아닌 항목(질문 · 아니오 · 기타)만, 유저 글은 «유저 질문» 칸에
def build_followup(result: dict, survey: dict = None) -> dict:
    sources = {q.get("id"): q.get("source", "") for q in (survey or {}).get("questions", [])}
    items = []
    for a in result.get("answers", []):
        kind, choice = a.get("kind"), a.get("choice")
        if kind == "hold" or (kind == "option" and choice == "예"):
            continue
        memo = (a.get("memo") or a.get("ask") or a.get("other") or "").strip()
        it = {"id": a.get("id", ""), "title": a.get("question", ""),
              "body": "", "example": f"유저 답: {choice or kind}" + (f" — {memo}" if memo else "")}
        if sources.get(a.get("id")):
            it["source"] = sources[a["id"]]
        items.append(it)
    return {"title": "인지 확인 · 설명", "mode": "explain", "items": items}


def read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="인지 설문 질문 파일 만들기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="재료.json → 설문 질문 파일(10문항씩)")
    m.add_argument("material")
    m.add_argument("--out", default="/tmp/cog", help="파일 이름 머리(→ 머리_1.json …)")
    f = sub.add_parser("followup", help="결과.json → 설명 폼 뼈대")
    f.add_argument("result")
    f.add_argument("--survey", help="원래 설문 json(원문 칸을 옮겨 붙임)")
    f.add_argument("--out", default="/tmp/cog_followup.json")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "make":
            surveys = build_surveys(read_json(a.material))
            paths = []
            for n, s in enumerate(surveys, 1):
                p = Path(f"{a.out}_{n}.json")
                write_json(p, s)
                paths.append(str(p))
            print(json.dumps({"files": paths, "questions": sum(len(s["questions"]) for s in surveys)}, ensure_ascii=False))
        else:
            fu = build_followup(read_json(a.result), read_json(a.survey) if a.survey else None)
            write_json(Path(a.out), fu)
            print(json.dumps({"file": a.out, "items": len(fu["items"])}, ensure_ascii=False))
    except MaterialError as e:
        print(f"재료 오류 — {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
