#!/usr/bin/env python3
# HTML 설문 도구 — 미논의 질문을 브라우저 설문으로 띄우고 답을 json 으로 받음(표준 라이브러리만 · 파이썬 3.8 이상)
#
# 사용
#   python3 ~/.codex/skills/survey/survey.py serve [--port 8600]      설문 서버(0.0.0.0) — devview 없이 따로 띄울 때
#   python3 ~/.codex/skills/survey/survey.py new 질문.json [--project 이름] [--open]
#                                                                     설문 등록 → 설문 id 출력(--open = devview 창에 띄움)
#   python3 ~/.codex/skills/survey/survey.py open 설문id               등록된 설문을 devview 창에 띄움
#   python3 ~/.codex/skills/survey/survey.py wait 설문id               제출될 때까지 조용히 대기 → 결과 json 출력
#   python3 ~/.codex/skills/survey/survey.py result 설문id             결과 조회(제출 전이면 pending)
#   devview 안에서는 위쪽 «설문» 탭이 같은 화면을 보여 준다(devview 가 이 파일을 불러와 /sv/ 아래로 연결)
#
# 저장: <저장소>/docs/surveys/<프로젝트>/설문id.json · 설문id.result.json — 저장소 안이라 커밋하면 기록으로 남음
#   저장소 = 지금 폴더가 속한 git 저장소(--dir 로 저장 폴더 직접 지정) · 프로젝트 = --project(없으면 저장소 이름)
#   한 번이라도 등록한 저장 폴더는 ~/.devview/survey_stores.json 에 올라가 화면 왼쪽 프로젝트 목록에 모두 보인다
#
# 질문 파일 형식(json) — question · options 말고는 모두 선택
#   {"title": "...", "questions": [{"id": "1-1 #1", "question": "한 줄 질문",
#     "decide": "유저가 결정할 것(카드 맨 위)", "context": "배경(회색)", "example": "적용 예시(회색)",
#     "pros": ["장점(초록)"], "cons": ["단점(빨강)"], "recommend": "추천과 이유(노랑)", "source": "원문(접힘)",
#     "images": ["그림 경로(png · jpg · gif · svg · webp) — 등록 때 설문 옆 «<id>_img» 로 복사해 질문 아래에 그림"],
#     "options": [{"label": "(추천) A안", "detail": "고르면 무엇이 바뀌나", "pros": [], "cons": [], "example": ""}, "B안"]}]}
#   글 칸은 짧은 마크다운: **굵게** · `코드` · - 목록(탭 들여쓰기 = 한 단계 아래) · 1. 번호 · | 표 | · ``` 코드 블록
#   화면: 결정할 것(보라) → 배경(회색) → 제안(노랑) → 선택지(글 길이만큼 · 풀이 · 장단점 · 예시는 올리면 바로 뜨는 툴팁)
#         → 메모 칸(글만큼 늘어남) · 그 왼쪽 아래 기타 · 보류 · 질문 단추(누르면 선택지 선택이 풀림)
#   답 = 선택지 하나 또는 기타 · 보류 · 질문, 메모 칸 글 → 결과 answers[].kind = option · other · hold · ask
#   왼쪽 목록: 프로젝트 → 고른 프로젝트의 대기 · 질문(설명 폼 전부) · 완료(회색) 설문. 완료 설문을 열면 당시 고른 답 · 메모를 읽기 전용으로 보여 줌
#
# 표 폼 — 설명이 필요 없고 항목이 많을 때(질문 파일에 rows 를 주면 표 폼)
#   {"title": "...", "columns": ["절", "동작"], "rows": [["0", "라이브러리 확인"], {"id": "1", "cells": ["1", "AGENTS"]}]}
#   화면: 표 오른쪽에 X(미대상) · △(보류) · O(대상) 세 칸 · 행마다 아래에 메모 줄
#   답 = answers[].choice X · △ · O(안 고르면 빈 값) · kind skip · hold · target · none · label 미대상 · 보류 · 대상 · 미선택
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

# 저장소 루트 — 이 파일이 ~/.codex/skills/survey/ 아래에 있다는 전제(git 저장소 밖에서 실행할 때만 씀)
REPO = Path(__file__).resolve().parents[3]
# 설문 · 결과 저장 폴더 대비값 — 지금 폴더가 git 저장소가 아닐 때
DEFAULT_DIR = REPO / "docs" / "surveys"
# 등록된 저장 폴더 목록 파일 — 환경변수로 바꿀 수 있음(시험이 실제 목록을 건드리지 않게)
REGISTRY = Path(os.environ.get("SURVEY_REGISTRY") or (Path.home() / ".devview" / "survey_stores.json"))
# 프로젝트 폴더 없이 저장 폴더 바로 아래 있는 옛 설문의 프로젝트 이름
LOOSE = "분류 없음"
# 화면이 붙어 있다고 보는 시간(초) — 마지막 상태 확인 뒤 이 안이면 새 창을 열지 않고 화면이 스스로 넘어감
CLIENT_GAP = 6
# 마지막 상태 확인 시각 — 화면(설문 페이지)이 2초마다 갱신
LAST_SEEN = [0.0]
# 목록에 늘 넣을 저장 폴더 — serve --dir · devview 작업 폴더의 docs/surveys
EXTRA_STORES = []
# devview 기본 포트
DEVVIEW_PORT = 8701
# 설문 파일 요약 캐시 — 경로 → (수정 시각, 요약). 화면이 2초마다 목록을 다시 읽어서
SUMMARY_CACHE = {}
# 보류 선택지 이름 — 모든 질문에 자동으로 붙음
HOLD = "보류"
# 기타 선택지 이름 — 고르면 메모 칸 글이 답
OTHER = "기타"
# 옛 기타 이름 — 예전 질문 파일 · 예전 화면에서 온 값도 기타로 받음
OTHER_OLD = "기타(메모에 적기)"
# 질문 선택지 이름 — 고르면 메모 칸 질문에 답한 뒤 새 설문으로 다시 묻는다
ASK = "질문"
# 옛 질문 이름 — 예전 화면에서 온 값도 질문으로 받음
ASK_OLD = "질문·논의"
# 자동으로 붙는 선택지 이름 묶음 — 질문 파일 선택지에 같은 이름이 있으면 겹치지 않게 뺌
FIXED = (OTHER, OTHER_OLD, HOLD, ASK, ASK_OLD)
# 설문 맨 끝 추가 지시 칸의 폼 이름
EXTRA = "extra"
# 주소에서 설문 id 를 찾는 패턴 — 앞에 프록시 접두어가 붙어도 찾게 끝부분만 봄
SURVEY_PATH = re.compile(r"survey/([0-9A-Za-z_-]+)/?$")
# 목록 줄 — «- » · «* »(앞 공백 · 탭 = 들여쓰기)
BULLET = re.compile(r"^(\s*)[-*] (.*)$")
# 번호 줄 — «1. »
NUMBERED = re.compile(r"^(\s*)\d+\. (.*)$")
# 표 구분 줄의 칸 — «---» · «:--:»
TABLE_RULE = re.compile(r":?-{2,}:?")

# 화면 꾸밈 — 다크 배경 · 큰 글씨 · 좌우 폭 제한 없음
#   질문 카드 = 파랑 · 결정할 것 = 보라 · 제안 = 노랑 · 배경 · 원문 = 회색 · 툴팁 안 장점 = 초록 · 단점 = 빨강
PAGE_CSS = """
:root{color-scheme:dark}
body{margin:0;background:#1e1f22;color:#f2f2f2;font:18px/1.6 'Malgun Gothic','Noto Sans KR','Segoe UI',sans-serif}
.app{display:flex;min-height:100vh}
.side{width:300px;flex:none;position:sticky;top:0;height:100vh;overflow-y:auto;box-sizing:border-box;
 padding:12px 10px 24px;background:#17181b;border-right:1px solid #2f3136}
.pane{flex:1;min-width:0;margin:0;padding:24px 32px 80px}
.sh{display:flex;justify-content:space-between;font-size:13px;color:#9aa0a6;font-weight:700;margin:16px 6px 6px}
.sh:first-child{margin-top:4px}
a.proj{display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:8px;color:#e8eaed;text-decoration:none;font-size:16px}
a.proj:hover{background:#26282e}
a.proj.on{background:#2e436e}
.pn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.repo{color:#868a91;font-size:12px}
.cnt{background:#3574f0;color:#fff;border-radius:9px;font-size:12px;line-height:18px;padding:0 7px}
a.sv{display:block;padding:5px 14px;margin:5px 0;border-radius:999px;text-decoration:none;font-size:15px;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
a.sv.pend{background:#1a2b47;border:1px solid #3d5682;color:#e8eaed}
a.sv.done{background:#2b2d31;border:1px solid #44464c;color:#9aa0a6}
a.sv:hover{border-color:#8ab4f8}
a.sv.on{box-shadow:inset 0 0 0 2px #8ab4f8;color:#fff}
.sv small{color:#868a91;margin-left:4px}
.none{color:#868a91;font-size:14px;margin:4px 8px}
.empty{color:#9aa0a6;margin-top:40px}
h1{font-size:24px;margin:0 0 4px}
.sub{color:#b8b8b8;margin-bottom:24px}
.stamp{display:inline-block;background:#44464c;color:#e8eaed;border-radius:6px;padding:0 10px;font-size:15px;margin-right:8px}
.ro label.opt,.ro .seg label{cursor:default}
.ro label.opt:hover{border-color:#3d5682}
.ro label.opt.recd:hover{border-color:#e8c547}
.ro .q{background:#26272b;border-color:#44464c}
.ro .qid{color:#9aa0a6}
.ro label.opt{background:#2b2d31;border-color:#4a4d55}
#note{position:fixed;top:12px;right:16px;z-index:60;background:#3574f0;color:#fff;border-radius:8px;padding:6px 14px;font-size:15px}
.q{background:#15233b;border:1px solid #2f4a78;border-radius:12px;padding:18px 20px;margin:0 0 24px}
.qh{font-weight:700;font-size:21px;margin-bottom:12px;word-break:keep-all;overflow-wrap:anywhere}
.qid{color:#8ab4f8;margin-right:6px}
.box{display:block;border-radius:12px;padding:10px 14px;margin:0 0 12px;overflow-wrap:anywhere}
.bt{display:block;font-weight:700;font-size:15px;margin-bottom:2px}
.decide{background:#2a2045;border:1px solid #9d7bea}
.decide .bt{color:#cdb8ff}
.gray{background:#2b2d31;border:1px solid #4a4d55}
.gray .bt{color:#c4c7c5}
.pros{background:#15321f;border:1px solid #34a853}
.pros .bt{color:#81c995}
.cons{background:#3a1c1c;border:1px solid #e06c6c}
.cons .bt{color:#f28b82}
.rec{background:#3a3212;border:1px solid #e8c547}
.rec .bt{color:#fdd663}
.box p{margin:4px 0}
.box ul,.box ol{margin:4px 0;padding-left:22px}
.box pre{margin:6px 0;white-space:pre-wrap;font:15px/1.5 Consolas,monospace;color:#e3e3e3}
.box table{border-collapse:collapse;margin:6px 0;width:100%}
.box th,.box td{border:1px solid #5f6368;padding:4px 8px;text-align:left;vertical-align:top}
.box th{background:#26272b}
code{background:#26272b;border-radius:4px;padding:0 4px;font:15px Consolas,monospace}
.pair{display:flex;flex-wrap:wrap;gap:12px;margin:0 0 12px}
.pair>.box{flex:1 1 360px;margin:0}
.qimg{display:block;max-width:100%;margin:0 0 12px;border:1px solid #4a4d55;border-radius:8px;background:#fff}
details.src{margin:12px 0 0;border:1px solid #4a4d55;background:#232428;border-radius:10px}
details.src summary{cursor:pointer;color:#b8b8b8;padding:6px 12px}
details.src pre{margin:0;padding:4px 14px 12px;white-space:pre-wrap;overflow-wrap:anywhere;color:#c8c8c8;
 font:15px/1.55 Consolas,monospace;max-height:420px;overflow-y:auto}
.opts{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin:4px 0 12px}
label.opt{display:inline-block;max-width:100%;box-sizing:border-box;padding:6px 14px;border:1px solid #3d5682;
 border-radius:10px;cursor:pointer;background:#1a2b47;font-weight:700;overflow-wrap:anywhere}
label.opt:hover{border-color:#8ab4f8}
label.opt.recd{border:2px solid #e8c547}
label.opt:has(input:checked){background:#2c4f86;box-shadow:inset 0 0 0 2px #8ab4f8}
label.opt input,.seg input{position:absolute;opacity:0;width:0;height:0}
.ti{color:#8ab4f8;font-weight:400;font-size:14px;margin-left:6px}
.tipsrc{display:none}
#tip{position:fixed;display:none;z-index:50;max-width:min(640px,calc(100vw - 16px));box-sizing:border-box;
 background:#26272b;border:1px solid #5f6368;border-radius:10px;padding:8px 10px;box-shadow:0 10px 30px rgba(0,0,0,.55);font-size:16px}
#tip .box{padding:6px 10px;margin:0 0 6px}
#tip .box:last-child{margin-bottom:0}
.memo{border:1px solid #44464c;border-radius:8px;background:#1e1f22}
.memo:focus-within{border-color:#8ab4f8}
.memo textarea{display:block;width:100%;box-sizing:border-box;min-height:44px;resize:none;overflow:hidden;background:none;
 color:#f2f2f2;border:0;outline:none;padding:8px 10px 4px;font-family:inherit;font-size:16px;line-height:1.5}
.seg{display:inline-flex;margin:0 0 8px 8px;background:#26272b;border:1px solid #44464c;border-radius:8px;overflow:hidden}
.seg label{padding:4px 16px;font-size:15px;color:#9aa0a6;cursor:pointer;user-select:none}
.seg label+label{border-left:1px solid #44464c}
.seg label:has(input:checked){background:#44464c;color:#fff;font-weight:700}
textarea.extra{width:100%;box-sizing:border-box;min-height:120px;background:#1e1f22;color:#f2f2f2;border:1px solid #44464c;
 border-radius:8px;padding:8px;font-family:inherit;font-size:16px;line-height:1.5;margin-top:8px}
table.grid{border-collapse:collapse;width:100%;margin:0 0 24px;font-size:16px}
.grid th,.grid td{border:1px solid #3a3d44;padding:6px 10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
.grid thead th{background:#26272b;position:sticky;top:0;z-index:2}
.grid tr.row td{background:#15233b}
.grid th.mk,.grid td.mk{width:46px;text-align:center;padding:0;vertical-align:middle}
.grid td.mk label{display:flex;align-items:center;justify-content:center;min-height:40px;cursor:pointer;font-weight:700;color:#5f6368}
.grid td.mk label:hover{color:#e8eaed}
.grid td.mk input{position:absolute;opacity:0;width:0;height:0}
.grid td.mk.skip label:has(input:checked){background:#7a2f2f;color:#fff}
.grid td.mk.hold label:has(input:checked){background:#6b5714;color:#fff}
.grid td.mk.target label:has(input:checked){background:#23683a;color:#fff}
.grid tr.mrow td{padding:0 0 12px;border-top:0;background:#1e1f22}
.grid .memo textarea{min-height:34px;font-size:15px;padding:5px 10px 3px}
.bar{position:sticky;bottom:0;background:#1e1f22;padding:12px 0;display:flex;gap:12px}
button{font-size:18px;padding:10px 26px;border-radius:8px;border:0;cursor:pointer}
.ok{background:#8ab4f8;color:#111}
.no{background:#44464c;color:#f2f2f2}
a{color:#8ab4f8}
"""

# 화면 동작
#   메모 칸 — 글만큼 높이를 늘림(안에서 휠로 오르내리지 않게)
#   선택지 툴팁 — 마우스를 올리면 바로 뜸 · 화면 밖으로 넘치면 위 · 왼쪽으로 붙임
PAGE_JS = """
function grow(t){t.style.height='auto';t.style.height=t.scrollHeight+'px';}
document.querySelectorAll('.memo textarea').forEach(function(t){t.addEventListener('input',function(){grow(t);});grow(t);});
var tip=document.getElementById('tip');
document.querySelectorAll('label.opt').forEach(function(l){
 var src=l.querySelector('.tipsrc');if(!src)return;
 l.addEventListener('mouseenter',function(){
  tip.innerHTML=src.innerHTML;tip.style.display='block';
  var r=l.getBoundingClientRect(),w=tip.offsetWidth,h=tip.offsetHeight;
  var top=r.bottom+6;if(top+h>innerHeight-8&&r.top-h-6>8)top=r.top-h-6;
  tip.style.top=top+'px';tip.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';
 });
 l.addEventListener('mouseleave',function(){tip.style.display='none';});
});
"""

# 목록 · 새 설문 감시 — 2초마다 상태를 보고
#   목록이 바뀌면 왼쪽 목록만 다시 받음 · 새 대기 설문이 오면 그 설문으로 넘어감(쓰던 답이 있으면 알림만)
#   devview 안(iframe)이면 대기 개수 · 새 설문 소식을 devview 화면에 전함
APP_JS = """
var base=location.pathname.replace(/[^\\/]*$/,''),inFrame=window.parent!==window,dirty=false,sig=null,seen=null;
var fm=document.querySelector('form:not(.ro)'),dt=null,unsaved=false;
function saveDraft(){clearTimeout(dt);if(!fm||!unsaved)return;unsaved=false;
 fetch(base+'api/draft'+(fm.getAttribute('action')||location.search),{method:'POST',keepalive:true,headers:{'X-Devview':'1'},
  body:new URLSearchParams(new FormData(fm))}).catch(function(){});}
if(fm){['input','change'].forEach(function(ev){fm.addEventListener(ev,function(){dirty=true;unsaved=true;
  clearTimeout(dt);dt=setTimeout(saveDraft,400);});});
 fm.addEventListener('submit',function(){clearTimeout(dt);unsaved=false;});
 addEventListener('pagehide',saveDraft);}
function tell(m){if(inFrame)try{parent.postMessage(m,'*');}catch(e){}}
function poll(){
 fetch(base+'api/state',{cache:'no-store'}).then(function(r){return r.json();}).then(function(st){
  tell({sv:'state',pending:st.pending});
  if(sig!==null&&st.sig!==sig)fetch(base+'api/side'+location.search,{cache:'no-store'}).then(function(r){return r.text();})
   .then(function(h){document.getElementById('side').innerHTML=h;});
  sig=st.sig;
  var nw=st.newest,mark=nw?nw.created+' '+nw.id:'';
  if(seen===null)seen=mark;
  else if(mark>seen){seen=mark;tell({sv:'focus'});
   var to='?'+new URLSearchParams({s:nw.s,p:nw.p,id:nw.id}).toString();
   if(!dirty)location.href=to;else{var n=document.getElementById('note');n.hidden=false;n.textContent='새 설문 도착 — 왼쪽 대기 목록';}}
 }).catch(function(){}).then(function(){setTimeout(poll,2000);});
}
poll();
"""


# 선택지 라벨 — 문자열이면 그대로, {label, detail} 이면 label
# o: 선택지 하나
def opt_label(o) -> str:
    return str(o.get("label", "")) if isinstance(o, dict) else str(o)


# 선택지 풀이 — {label, detail} 의 detail, 문자열이면 빈 값
# o: 선택지 하나
def opt_detail(o) -> str:
    return str(o.get("detail", "")) if isinstance(o, dict) else ""


# 질문 파일에 적힌 선택지 — 자동으로 붙는 기타 · 보류 · 질문·논의와 같은 이름은 뺌(화면에 두 번 안 나오게)
# q: 질문 하나(dict)
def main_options(q: dict) -> list:
    return [o for o in q.get("options", []) if opt_label(o) not in FIXED]


# 추천 선택지인가 — 라벨 머리 «(추천)» 또는 recommended 참
# o: 선택지 하나
def is_recommended(o) -> bool:
    return opt_label(o).startswith("(추천)") or (isinstance(o, dict) and bool(o.get("recommended")))


# 줄 안 꾸밈 — 이스케이프 뒤 `코드` · **굵게**
# text: 한 줄 글
def inline(text: str) -> str:
    # 이스케이프한 글
    s = html.escape(text)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


# 표 줄들 → <table>. 둘째 줄이 구분 줄(---)이면 첫 줄을 머리로
# rows: «|» 로 시작하는 줄 목록
def render_table(rows: list) -> str:
    # 줄마다 칸 목록
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    # 머리 줄이 있나 — 둘째 줄이 전부 구분 칸
    has_head = len(cells) > 1 and all(TABLE_RULE.fullmatch(c) for c in cells[1] if c)
    # 머리 칸 / 본문 줄
    head, body = (cells[0], cells[2:]) if has_head else ([], cells)
    # 표 조각
    out = ["<table>"]
    if head:
        out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>")
    # 본문 줄 하나
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    return "".join(out) + "</table>"


# 목록 줄들 → 중첩 <ul>/<ol>. 들여쓰기(탭 하나 = 공백 두 칸)마다 한 단계 아래
# items: (단계, 태그, 글) 목록
def render_list(items: list) -> str:
    # 지금 열린 목록 태그(바깥 → 안쪽)
    stack = []
    # 목록 조각
    out = []
    # 단계 · 태그(ul/ol) · 글
    for level, tag, text in items:
        if not stack or level > len(stack) - 1:
            # 새 목록 — 맨 처음이거나 앞 항목 안쪽(한 번에 한 단계만 내려감)
            out.append(f"<{tag}>")
            stack.append(tag)
        else:
            # 같은 단계로 올라올 때까지 안쪽 목록을 닫고 앞 항목을 닫음
            while len(stack) - 1 > level:
                out.append(f"</li></{stack.pop()}>")
            out.append("</li>")
        out.append(f"<li>{inline(text)}")
    while stack:
        out.append(f"</li></{stack.pop()}>")
    return "".join(out)


# 짧은 마크다운 → HTML(표준 라이브러리만): 문단 · 목록 · 번호 · 표 · 코드 블록 · 굵게 · 코드
# text: 글(문자열) 또는 줄 목록(목록이면 «- » 목록으로)
def md(text) -> str:
    if isinstance(text, (list, tuple)):
        text = "\n".join(f"- {t}" for t in text)
    # 줄 목록
    lines = str(text).splitlines()
    # 결과 조각 / 문단에 모으는 줄 / 지금 줄 번호
    out, para, i = [], [], 0

    # 모은 문단을 내보냄
    def flush():
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para.clear()

    while i < len(lines):
        # 지금 줄
        line = lines[i]
        if line.strip().startswith("```"):
            flush()
            # 코드 줄 모음
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre>" + html.escape("\n".join(code)) + "</pre>")
            i += 1
        elif line.lstrip().startswith("|"):
            flush()
            # 표 줄 모음
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows))
        elif BULLET.match(line) or NUMBERED.match(line):
            flush()
            # 목록 항목 모음
            items = []
            while i < len(lines):
                # 목록 줄 일치 결과
                m = BULLET.match(lines[i]) or NUMBERED.match(lines[i])
                if not m:
                    break
                items.append((len(m.group(1).expandtabs(2)) // 2, "ul" if BULLET.match(lines[i]) else "ol", m.group(2)))
                i += 1
            out.append(render_list(items))
        elif not line.strip():
            flush()
            i += 1
        else:
            para.append(line)
            i += 1
    flush()
    return "".join(out)


# 색 상자 하나 — 종류(class) · 제목 · 내용
# kind: decide · gray · pros · cons · rec / title: 상자 제목 / body: 내용(마크다운 · 목록) / tag: 감쌀 태그
def box(kind: str, title: str, body, tag: str = "div") -> str:
    return f"<{tag} class='box {kind}'><span class='bt'>{html.escape(title)}</span>{md(body)}</{tag}>"


# 설문 파일 경로
# folder: 저장 폴더 / sid: 설문 id
# 설문 그림 형식 — 확장자 → 내용 형식
IMG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
             ".svg": "image/svg+xml", ".webp": "image/webp"}


def survey_file(folder: Path, sid: str) -> Path:
    return folder / f"{sid}.json"


# 결과 파일 경로
# folder: 저장 폴더 / sid: 설문 id
def result_file(folder: Path, sid: str) -> Path:
    return folder / f"{sid}.result.json"


# 쓰던 답(초안) 파일 경로 — 다른 설문으로 넘어갔다 돌아와도 고른 답 · 메모가 남게. 제출 · 취소하면 지움
# folder: 저장 폴더 / sid: 설문 id
def draft_file(folder: Path, sid: str) -> Path:
    return folder / f"{sid}.draft.json"


# json 파일 쓰기 — 임시 파일에 쓴 뒤 교체(쓰다 끊겨도 반쪽 파일이 안 남음)
# path: 대상 파일 / data: 쓸 내용(dict · list)
def write_json(path: Path, data) -> None:
    # 임시 파일 경로
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# json 파일 읽기 — 없으면 None
# path: 대상 파일
def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# 선택지 하나 — 글 길이만큼의 단추 · 추천은 노란 테두리 · 풀이 · 장점 · 단점 · 적용 예시는 툴팁 원본(숨김)으로
# i: 질문 번호 / o: 선택지 하나 / checked: 고른 선택지(기록 보기) / ro: 기록 보기라 못 바꿈
def option_card(i: int, o, checked: bool = False, ro: bool = False) -> str:
    # 글자 이스케이프 함수(줄임)
    esc = html.escape
    # 라벨 / 추천 여부
    lab, rec = opt_label(o), is_recommended(o)
    # 화면에 보일 라벨 — «(추천)» 머리는 노란 테두리로 대신함
    shown = lab[len("(추천)"):].strip() if lab.startswith("(추천)") else lab
    # 툴팁 조각 — 풀이 · 장단점 · 예시
    inner = []
    if opt_detail(o):
        inner.append(box("gray", "풀이", opt_detail(o)))
    if isinstance(o, dict):
        if o.get("pros"):
            inner.append(box("pros", "장점", o["pros"]))
        if o.get("cons"):
            inner.append(box("cons", "단점", o["cons"]))
        if o.get("example"):
            inner.append(box("gray", "적용 예시", o["example"]))
    return (f"<label class='opt{' recd' if rec else ''}'><input type='radio' name='q{i}' value='{esc(lab, quote=True)}'"
            f"{' checked' if checked else ''}{' disabled' if ro else ''}>"
            f"{esc(shown)}{'<span class=ti>ⓘ</span><div class=tipsrc>' + ''.join(inner) + '</div>' if inner else ''}</label>")


# 기록의 고른 답 → 화면 단추 값(옛 이름은 새 이름으로). 답이 없으면 None
# a: 결과의 답 하나(dict) 또는 None
def answer_choice(a):
    if not a:
        return None
    # 고른 답
    c = a.get("choice")
    if c in (OTHER, OTHER_OLD):
        return OTHER
    if c in (ASK, ASK_OLD):
        return ASK
    return c


# 기록의 메모 글 — 메모 칸 글, 없으면 기타 · 질문의 답 글(옛 화면은 따로 칸이 있었음)
# a: 결과의 답 하나(dict) 또는 None
def answer_memo(a) -> str:
    if not a:
        return ""
    if a.get("memo"):
        return a["memo"]
    if answer_choice(a) in (OTHER, ASK):
        return a.get("other") or a.get("ask") or a.get("text") or ""
    return ""


# 설명 모드 상수 — 질문 파일 "mode": "explain" (선택지 없이 설명 카드 + 메모)
EXPLAIN = "explain"


# 설명 본문 HTML — 항목마다 제목 · 설명 · 예시 · 원문 + 메모 칸 하나(선택지 · 기타 · 보류 · 질문 단추 없음)
#   설명 · 비교 · 결과 보고처럼 «보여 주고 메모를 받는» 용도. result 가 있으면 기록 보기
# title: 제목 / questions: 항목 목록(question = 항목 제목 · body · context · example · source) / intro: 머리 설명
def render_explain(title: str, questions: list, result=None, draft=None, q: str = "", intro: str = "") -> str:
    esc = html.escape
    ro = result is not None
    answers = (result or {}).get("answers") or []
    if not ro:
        sub = f"설명 {len(questions)}개 · 항목마다 메모(선택) — 질문 · 지시를 적고 제출"
    elif result.get("action") == "cancel":
        sub = f"<span class='stamp'>취소됨</span>{esc(result.get('submitted', ''))}"
    else:
        sub = f"<span class='stamp'>완료</span>제출 {esc(result.get('submitted', ''))}"
    parts = [f"<h1>{esc(title)}</h1><div class='sub'>{sub}</div>"
             f"<form method='post' action='{esc(q, quote=True)}'{' class=ro' if ro else ''}>"]
    if intro:
        parts.append(f"<section class='q'>{box('gray', '개요', intro)}</section>")
    for i, item in enumerate(questions, 1):
        a = answers[i - 1] if i - 1 < len(answers) else None
        memo = (a or {}).get("memo", "") if ro else (draft or {}).get(f"q{i}_memo", "")
        qid = f"<span class='qid'>[{esc(str(item['id']))}]</span>" if item.get("id") else ""
        parts.append(f"<section class='q'><div class='qh'>{i}. {qid}{esc(item['question'])}</div>")
        body = item.get("body") or item.get("context")
        if body:
            parts.append(box("gray", "설명", body))
        if item.get("example"):
            parts.append(box("gray", "예시", item["example"]))
        if item.get("pros") or item.get("cons"):
            parts.append("<div class='pair'>" + (box("pros", "장점", item["pros"]) if item.get("pros") else "")
                         + (box("cons", "단점", item["cons"]) if item.get("cons") else "") + "</div>")
        if item.get("recommend"):
            parts.append(box("rec", "제안", item["recommend"]))
        parts.append(f"<div class='memo'><textarea name='q{i}_memo' rows='1'{' readonly' if ro else ''}"
                     f" placeholder='{'' if ro else '메모 — 질문 · 반론 · 지시(선택)'}'>{esc(memo)}</textarea></div>")
        if item.get("source"):
            parts.append(f"<details class='src' open><summary>원문</summary><pre>{esc(item['source'])}</pre></details>")
        parts.append("</section>")
    if not ro:
        parts.append(f"<section class='q'><div class='qh'>추가 지시 사항(선택)</div>"
                     f"<textarea class='extra' name='{EXTRA}'>{esc((draft or {}).get(EXTRA, ''))}</textarea></section>")
        parts.append("<div class='bar'><button class='ok' name='_act' value='submit'>제출</button>"
                     "<button class='no' name='_act' value='cancel' formnovalidate>취소</button></div>")
    elif result.get("extra"):
        parts.append(f"<section class='q'><div class='qh'>추가 지시 사항</div>"
                     f"<textarea class='extra' readonly>{esc(result['extra'])}</textarea></section>")
    return "".join(parts) + "</form>"


# 표 모드 상수 — 질문 파일 rows(→ "mode": "table") · 칸 표시 · 결과 kind · 이름
TABLE = "table"
MARKS = (("X", "skip", "미대상"), ("△", "hold", "보류"), ("O", "target", "대상"))


# 표 폼 HTML — 표 + 오른쪽 X · △ · O 칸 + 행마다 아래 메모 줄 · 추가 지시 · 제출/취소. result 가 있으면 기록 보기
# title: 제목 / columns: 머리 칸 이름 / questions: 행 목록(cells = 칸 글) / intro: 머리 설명
def render_grid(title: str, columns: list, questions: list, result=None, draft=None, q: str = "", intro: str = "") -> str:
    esc = html.escape
    ro = result is not None
    answers = (result or {}).get("answers") or []
    if not ro:
        sub = f"항목 {len(questions)}개 · X 미대상 · △ 보류 · O 대상 · 고르지 않은 항목은 미선택"
    elif result.get("action") == "cancel":
        sub = f"<span class='stamp'>취소됨</span>{esc(result.get('submitted', ''))}"
    else:
        sub = f"<span class='stamp'>완료</span>제출 {esc(result.get('submitted', ''))}"
    parts = [f"<h1>{esc(title)}</h1><div class='sub'>{sub}</div>"
             f"<form method='post' action='{esc(q, quote=True)}'{' class=ro' if ro else ''}>"]
    if intro:
        parts.append(box("gray", "개요", intro))
    # 칸 수 — 머리가 없으면 가장 긴 행 기준
    width = len(columns) or max((len(r.get("cells") or [r["question"]]) for r in questions), default=1)
    head = "".join(f"<th>{esc(str(c))}</th>" for c in columns) or "<th></th>" * width
    head += "".join(f"<th class='mk {k}' title='{lab}'>{m}</th>" for m, k, lab in MARKS)
    parts.append(f"<table class='grid'><thead><tr>{head}</tr></thead><tbody>")
    for i, row in enumerate(questions, 1):
        a = answers[i - 1] if i - 1 < len(answers) else None
        chosen = (a or {}).get("choice") if ro else (draft or {}).get(f"q{i}")
        memo = (a or {}).get("memo", "") if ro else (draft or {}).get(f"q{i}_memo", "")
        cells = [str(c) for c in (row.get("cells") or [row["question"]])]
        cells += [""] * (width - len(cells))
        tds = "".join(f"<td>{inline(c)}</td>" for c in cells)
        tds += "".join(f"<td class='mk {k}'><label title='{lab}'><input type='radio' name='q{i}' value='{m}'"
                       f"{' checked' if chosen == m else ''}{' disabled' if ro else ''}>{m}</label></td>"
                       for m, k, lab in MARKS)
        parts.append(f"<tr class='row'>{tds}</tr><tr class='mrow'><td colspan='{width + len(MARKS)}'><div class='memo'>"
                     f"<textarea name='q{i}_memo' rows='1'{' readonly' if ro else ''}"
                     f" placeholder='{'' if ro else '메모(선택)'}'>{esc(memo)}</textarea></div></td></tr>")
    parts.append("</tbody></table>")
    if not ro:
        parts.append(f"<section class='q'><div class='qh'>추가 지시 사항(선택)</div>"
                     f"<textarea class='extra' name='{EXTRA}'>{esc((draft or {}).get(EXTRA, ''))}</textarea></section>")
        parts.append("<div class='bar'><button class='ok' name='_act' value='submit'>제출</button>"
                     "<button class='no' name='_act' value='cancel' formnovalidate>취소</button></div>")
    elif result.get("extra"):
        parts.append(f"<section class='q'><div class='qh'>추가 지시 사항</div>"
                     f"<textarea class='extra' readonly>{esc(result['extra'])}</textarea></section>")
    return "".join(parts) + "</form>"


# 설문 본문 HTML — 질문 카드(결정할 것 · 배경 · 적용 예시 · 제안 · 선택지 · 메모 + 기타 · 보류 · 질문 · 원문) · 추가 지시 · 제출/취소
#   result 가 있으면 기록 보기 — 당시 고른 답 · 메모를 채워 읽기 전용으로
# title: 설문 제목 / questions: 질문 목록 / result: 결과(dict) 또는 None
#   draft(쓰던 답 · 폼 값)가 있으면 그 값을 채워 이어서 쓰게
def render_form(title: str, questions: list, result=None, draft=None, q: str = "", mode: str = "survey",
                intro: str = "") -> str:
    if mode == EXPLAIN:
        return render_explain(title, questions, result, draft, q, intro)
    # 글자 이스케이프 함수(줄임)
    esc = html.escape
    # 기록 보기 여부 / 질문 순서대로 답
    ro = result is not None
    answers = (result or {}).get("answers") or []
    if not ro:
        sub = f"질문 {len(questions)}개 · 고르지 않은 질문은 보류로 기록"
    elif result.get("action") == "cancel":
        sub = f"<span class='stamp'>취소됨</span>{esc(result.get('submitted', ''))}"
    else:
        sub = f"<span class='stamp'>완료</span>제출 {esc(result.get('submitted', ''))}"
    # 화면 조각 목록 — 마지막에 이어 붙임
    parts = [f"<h1>{esc(title)}</h1><div class='sub'>{sub}</div>"
             # 제출 주소를 비워 두면 지금 주소로 보냄 — 프록시 접두어가 붙어도 깨지지 않음
             # 제출 주소 = 이 설문 주소(상대 «?s=…&p=…&id=…») — 화면 주소에 설문 id 가 없어도(devview 설문 탭 첫 화면)
             # 제출 · 초안 저장이 이 설문으로 간다. 상대 주소라 프록시 접두어가 붙어도 깨지지 않음
             f"<form method='post' action='{esc(q, quote=True)}'{' class=ro' if ro else ''}>"]
    # 그림 주소에 붙일 설문 주소 값(아래 반복에서 q 이름을 질문으로 다시 씀)
    img_q = q
    # 질문 번호(1부터) / 질문 하나
    for i, q in enumerate(questions, 1):
        # 이 질문의 기록 답 / 고른 단추 값 / 메모
        a = answers[i - 1] if i - 1 < len(answers) else None
        chosen, memo = answer_choice(a), answer_memo(a)
        if not ro and draft:
            chosen, memo = draft.get(f"q{i}"), draft.get(f"q{i}_memo", "")
        # 질문 표식 조각 — id 가 있을 때만
        qid = f"<span class='qid'>[{esc(str(q['id']))}]</span>" if q.get("id") else ""
        parts.append(f"<section class='q'><div class='qh'>{i}. {qid}{esc(q['question'])}</div>")
        for name in q.get("images") or []:
            parts.append(f"<img class='qimg' alt='' src='{esc('api/img' + img_q + '&f=' + name, quote=True)}'>")
        if q.get("decide"):
            parts.append(box("decide", "결정할 것", q["decide"]))
        if q.get("context"):
            parts.append(box("gray", "배경", q["context"]))
        if q.get("example"):
            parts.append(box("gray", "적용 예시", q["example"]))
        if q.get("pros") or q.get("cons"):
            parts.append("<div class='pair'>" + (box("pros", "장점", q["pros"]) if q.get("pros") else "")
                         + (box("cons", "단점", q["cons"]) if q.get("cons") else "") + "</div>")
        if q.get("recommend"):
            parts.append(box("rec", "제안", q["recommend"]))
        # 질문 파일 선택지
        opts = main_options(q)
        if opts:
            parts.append("<div class='opts'>" + "".join(option_card(i, o, chosen == opt_label(o), ro) for o in opts)
                         + "</div>")
        # 메모 칸 + 왼쪽 아래 기타 · 보류 · 질문 단추 — 선택지와 같은 이름 묶음이라 누르면 선택지 선택이 풀림
        parts.append(f"<div class='memo'><textarea name='q{i}_memo' rows='1'{' readonly' if ro else ''}"
                     f" placeholder='{'' if ro else '메모 — 기타 · 질문을 고르면 이 글이 답'}'>{esc(memo)}</textarea>"
                     "<div class='seg'>"
                     + "".join(f"<label><input type='radio' name='q{i}' value='{v}'{' checked' if chosen == v else ''}"
                               f"{' disabled' if ro else ''}>{v}</label>" for v in (OTHER, HOLD, ASK))
                     + "</div></div>")
        if q.get("source"):
            parts.append(f"<details class='src' open><summary>원문</summary><pre>{esc(q['source'])}</pre></details>")
        parts.append("</section>")
    if not ro:
        parts.append(f"<section class='q'><div class='qh'>추가 지시 사항(선택)</div>"
                     f"{box('gray', '쓰는 곳', '설문 전체에 대한 지시 · 빠진 질문 · 다음 할 일')}"
                     f"<textarea class='extra' name='{EXTRA}'>{esc((draft or {}).get(EXTRA, ''))}</textarea></section>")
        parts.append("<div class='bar'><button class='ok' name='_act' value='submit'>제출</button>"
                     "<button class='no' name='_act' value='cancel' formnovalidate>취소</button></div>")
    elif result.get("extra"):
        parts.append(f"<section class='q'><div class='qh'>추가 지시 사항</div>"
                     f"<textarea class='extra' readonly>{esc(result['extra'])}</textarea></section>")
    return "".join(parts) + "</form>"


# 화면 한 장 — 왼쪽 목록 + 오른쪽 본문
# title: 창 제목 / side_html: 왼쪽 목록 / pane_html: 오른쪽 본문
def app_page(title: str, side_html: str, pane_html: str) -> str:
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{PAGE_CSS}</style></head><body><div class='app'>"
            f"<aside class='side' id='side'>{side_html}</aside><main class='pane'>{pane_html}</main></div>"
            f"<div id='tip'></div><div id='note' hidden></div><script>{PAGE_JS}{APP_JS}</script></body></html>")


# 짧은 안내 화면(없음 등)
# text: 보일 문장 / extra_html: 아래에 붙일 HTML
def msg_page(text: str, extra_html: str = "") -> str:
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>{PAGE_CSS}</style></head>"
            f"<body><main class='pane'><h1>{html.escape(text)}</h1>{extra_html}</main></body></html>")


# ======= 저장 폴더 · 프로젝트 · 목록 =======

# 경로가 속한 git 저장소 맨 위 폴더 — 없으면 None(.git 파일 · 폴더를 위로 찾아감)
# path: 시작 경로
def git_top(path: Path):
    # 지금 보는 폴더
    for d in [path, *path.parents]:
        if (d / ".git").exists():
            return d
    return None


# 기본 저장 폴더 — 지금 폴더가 속한 저장소의 docs/surveys(저장소 밖이면 이 도구가 든 저장소)
def default_store() -> Path:
    # 지금 폴더의 저장소 · 지금 폴더가 저장소 안 작업 폴더(docs/ 가 있는 하위 폴더 — 키트 = 작업 폴더)면 그 docs/surveys
    here = Path.cwd().resolve()
    top = git_top(here)
    if top and here != top and top in here.parents and (here / "docs").is_dir():
        return here / "docs" / "surveys"
    return (top / "docs" / "surveys") if top else DEFAULT_DIR


# 저장 폴더 열쇠 — 주소에 넣는 짧은 이름(경로 해시 8자)
# store: 저장 폴더
def store_key(store: Path) -> str:
    return hashlib.sha1(os.path.normcase(str(store.resolve())).encode("utf-8")).hexdigest()[:8]


# 저장소 이름 — docs/surveys 면 그 위 저장소 폴더 이름, 아니면 저장 폴더 이름
# store: 저장 폴더
def repo_name(store: Path) -> str:
    return store.parent.parent.name if store.parent.name == "docs" else store.name


# 프로젝트 이름을 폴더 이름으로 쓸 수 있게 — 경로 · 금지 글자를 _ 로
# name: 프로젝트 이름
def safe_project(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", str(name)).strip(" .") or "기본"


# 저장 폴더를 목록 파일에 올림 — 쓸 수 없는 곳(샌드박스 등)이면 조용히 건너뜀(목록은 편의 기능)
# store: 저장 폴더
def register_store(store: Path) -> None:
    try:
        # 지금 목록
        items = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else []
        # 등록할 경로
        path = str(store.resolve())
        if path not in items:
            REGISTRY.parent.mkdir(parents=True, exist_ok=True)
            write_json(REGISTRY, items + [path])
    except (OSError, ValueError):
        pass


# 보이는 저장 폴더 전부 — (열쇠, 경로). 늘 넣을 폴더 + 목록 파일, 같은 폴더는 한 번 · 없어진 폴더는 뺌
def stores() -> list:
    # 후보 경로
    paths = list(EXTRA_STORES)
    try:
        if REGISTRY.exists():
            paths += [Path(p) for p in json.loads(REGISTRY.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        pass
    # 결과 / 이미 넣은 열쇠
    out, keys = [], set()
    # 저장 폴더 하나
    for p in paths:
        if not p.is_dir():
            continue
        # 열쇠
        k = store_key(p)
        if k not in keys:
            keys.add(k)
            out.append((k, p.resolve()))
    return out


# 열쇠 → 저장 폴더(없으면 None)
# key: 저장 폴더 열쇠
def store_by_key(key: str):
    return next((p for k, p in stores() if k == key), None)


# 프로젝트 폴더 경로 — 분류 없음이면 저장 폴더 자신
# store: 저장 폴더 / project: 프로젝트 이름
def project_dir(store: Path, project: str) -> Path:
    return store if project == LOOSE else store / project


# 폴더 안 설문 파일(결과 · 임시 파일 · 설문이 아닌 json 제외 — 설문은 questions 칸이 있는 dict)
# folder: 프로젝트 폴더
def survey_files(folder: Path) -> list:
    if not folder.is_dir():
        return []
    return [p for p in folder.glob("*.json") if not p.name.endswith((".result.json", ".draft.json", ".tmp")) and summary(p)]


# 저장 폴더의 프로젝트 이름 목록 — 설문이 든 하위 폴더 + 바로 아래 옛 설문(분류 없음)
# store: 저장 폴더
def projects(store: Path) -> list:
    # 하위 폴더 프로젝트
    names = sorted(d.name for d in store.iterdir() if d.is_dir() and not d.name.startswith(".") and survey_files(d))
    return names + ([LOOSE] if survey_files(store) else [])


# 설문 파일 요약 — id · 제목 · 만든 시각 · 상태(pending · done · cancel) · 제출 시각. 수정 시각이 같으면 캐시
#   설문이 아닌 json(목록 파일 등)이나 깨진 파일은 None
# path: 설문 파일
def summary(path: Path):
    # 결과 파일
    rf = path.with_name(path.stem + ".result.json")
    # 캐시 열쇠 — 두 파일의 수정 시각
    stamp = (path.stat().st_mtime_ns, rf.stat().st_mtime_ns if rf.exists() else 0)
    # 캐시 값
    hit = SUMMARY_CACHE.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        # 설문 · 결과 내용
        item, res = read_json(path), read_json(rf)
    except (OSError, ValueError):
        item, res = None, None
    if not isinstance(item, dict) or "questions" not in item:
        SUMMARY_CACHE[str(path)] = (stamp, None)
        return None
    # 상태
    state = "pending" if res is None else ("cancel" if res.get("action") == "cancel" else "done")
    # 요약
    s = {"id": path.stem, "title": item.get("title", path.stem), "created": item.get("created", ""),
         "state": state, "submitted": (res or {}).get("submitted", ""), "mode": item.get("mode", "survey")}
    SUMMARY_CACHE[str(path)] = (stamp, s)
    return s


# 프로젝트의 설문 요약 목록 — 최근 것이 위
# store: 저장 폴더 / project: 프로젝트 이름
def project_surveys(store: Path, project: str) -> list:
    return sorted((summary(p) for p in survey_files(project_dir(store, project))),
                  key=lambda s: (s["created"], s["id"]), reverse=True)


# 보이는 모든 설문 — (열쇠, 저장 폴더, 프로젝트, 요약) 목록
def all_surveys() -> list:
    return [(k, st, pr, s) for k, st in stores() for pr in projects(st) for s in project_surveys(st, pr)]


# 설문 id 로 찾기 — (열쇠, 저장 폴더, 프로젝트) 또는 None. 저장 폴더를 주면 그 안에서만
# sid: 설문 id / store: 찾을 저장 폴더(없으면 보이는 전부) / project: 프로젝트(알면)
def find_survey(sid: str, store: Path = None, project: str = None):
    # 찾을 저장 폴더 목록
    pool = [(store_key(store), store.resolve())] if store else stores()
    # 저장 폴더 하나
    for k, st in pool:
        if not st.is_dir():
            continue
        # 프로젝트 하나
        for pr in ([project] if project else projects(st)):
            if survey_file(project_dir(st, pr), sid).exists():
                return k, st, pr
    return None


# 목록 주소 조각 — ?s=열쇠&p=프로젝트&id=설문
# key: 저장 폴더 열쇠 / project: 프로젝트 / sid: 설문 id(없으면 뺌)
def target_query(key: str, project: str, sid: str = None) -> str:
    return "?" + urlencode({"s": key, "p": project, **({"id": sid} if sid else {})})


# 고른 저장 폴더 · 프로젝트 · 설문 정하기 — 주소에 없으면 최근 대기 설문 → 최근 설문 순으로
# q: 주소 값(s · p · id)
def pick(q: dict):
    # 모든 설문
    every = all_surveys()
    # 주소의 저장 폴더 · 프로젝트
    key, project = q.get("s"), q.get("p")
    if not (key and project and store_by_key(key)):
        # 대기 설문 중 최근 / 없으면 전체 중 최근
        pend = [x for x in every if x[3]["state"] == "pending"]
        top = max(pend or every, key=lambda x: (x[3]["created"], x[3]["id"]), default=None)
        if top is None:
            return None, None, None
        key, project = top[0], top[2]
    # 설문 id — 주소에 없으면 그 프로젝트의 최근 대기 설문
    sid = q.get("id")
    if not sid:
        mine = [x[3] for x in every if x[0] == key and x[2] == project and x[3]["state"] == "pending"]
        sid = mine[0]["id"] if mine else None
    return key, project, sid


# 왼쪽 목록 HTML — 프로젝트 목록 → 고른 프로젝트의 대기 · 질문(설명 폼) · 완료(회색) 설문
# key · project · sid: 고른 것
def render_side(key, project, sid) -> str:
    # 글자 이스케이프 함수(줄임)
    esc = html.escape
    # 저장 폴더 목록 / 저장소가 둘 이상이면 프로젝트 옆에 저장소 이름
    sts = stores()
    many = len(sts) > 1
    # 프로젝트 줄 — (최근 시각, HTML)
    rows = []
    # 저장 폴더 하나
    for k, st in sts:
        # 프로젝트 하나
        for pr in projects(st):
            # 그 프로젝트 설문
            items = project_surveys(st, pr)
            # 대기 개수
            n = sum(1 for s in items if s["state"] == "pending")
            rows.append((items[0]["created"] if items else "",
                         f"<a class='proj{' on' if (k, pr) == (key, project) else ''}' href='{esc(target_query(k, pr))}'>"
                         f"<span class='pn'>{esc(pr)}{(' <span class=repo>' + esc(repo_name(st)) + '</span>') if many else ''}"
                         f"</span>{f'<span class=cnt>{n}</span>' if n else ''}</a>"))
    # 화면 조각
    out = ["<div class='sh'>프로젝트</div>"]
    out += [h for _, h in sorted(rows, key=lambda r: r[0], reverse=True)] or ["<div class='none'>설문 없음</div>"]
    # 고른 프로젝트의 저장 폴더
    st = store_by_key(key) if key else None
    if st is not None:
        # 그 프로젝트 설문
        items = project_surveys(st, project)
        # 묶음 — 대기 · 질문 · 완료(취소 포함). 설명 폼은 상태와 상관없이 질문 칸에 모은다(대기 먼저)
        #   설문 폼(선택지)만 대기 · 완료로 나뉜다 — 2026-10-30 유저 지정
        forms = [s for s in items if s.get("mode") != EXPLAIN]
        asks = sorted((s for s in items if s.get("mode") == EXPLAIN), key=lambda s: s["state"] != "pending")
        for head, group in (("대기", [s for s in forms if s["state"] == "pending"]), ("질문", asks),
                            ("완료", [s for s in forms if s["state"] != "pending"])):
            out.append(f"<div class='sh'><span>{head}</span><span>{len(group)}</span></div>")
            if not group:
                out.append("<div class='none'>없음</div>")
            # 설문 하나
            for s in group:
                # 짧은 시각(월-일 시:분) / 회색 = 끝난 것
                when = (s["submitted"] or s["created"])[5:16]
                tag = " · 취소" if s["state"] == "cancel" else ""
                cls = "pend" if s["state"] == "pending" else "done"
                out.append(f"<a class='sv {cls}{' on' if s['id'] == sid else ''}' title='{esc(s['title'])}'"
                           f" href='{esc(target_query(key, project, s['id']))}'>{esc(s['title'])}"
                           f"<small>{esc(when)}{tag}</small></a>")
    return "".join(out)


# 오른쪽 본문 HTML — 대기 설문은 답하는 폼, 완료 설문은 기록 보기
# key · project · sid: 고른 것
def render_pane(key, project, sid) -> tuple:
    # 저장 폴더
    st = store_by_key(key) if key else None
    if st is None:
        return "설문", "<div class='empty'>설문 없음</div>"
    if not sid:
        return project, "<div class='empty'>왼쪽 목록에서 설문을 고른다</div>"
    # 프로젝트 폴더 / 설문 · 결과
    folder = project_dir(st, project)
    item, res = read_json(survey_file(folder, sid)), read_json(result_file(folder, sid))
    if item is None:
        return "설문 없음", "<div class='empty'>설문 없음</div>"
    # 쓰던 답 — 제출 전일 때만
    draft = read_json(draft_file(folder, sid)) if res is None else None
    if item.get("mode") == TABLE:
        return item["title"], render_grid(item["title"], item.get("columns") or [], item["questions"], res, draft,
                                          target_query(key, project, sid), item.get("intro", ""))
    return item["title"], render_form(item["title"], item["questions"], res, draft, target_query(key, project, sid),
                                       item.get("mode", "survey"), item.get("intro", ""))


# 폼 응답 → 결과(dict). 고르지 않은 질문은 보류
#   kind: option(선택지) · other(기타 — 메모가 답) · hold(보류 — 빈 답) · ask(질문 — 답을 받은 뒤 다시 묻기)
# questions: 질문 목록 / form: 폼 값(이름 → 값)
def collect(questions: list, form: dict, mode: str = "survey") -> dict:
    if mode == EXPLAIN:
        # 설명 모드 — 항목마다 메모만(kind = memo · 빈 메모도 남김)
        return {"action": "accept", "extra": (form.get(EXTRA) or "").strip(),
                "answers": [{"id": q.get("id", ""), "question": q["question"], "choice": "", "kind": "memo",
                             "text": (form.get(f"q{i}_memo") or "").strip(),
                             "memo": (form.get(f"q{i}_memo") or "").strip()} for i, q in enumerate(questions, 1)]}
    if mode == TABLE:
        # 표 모드 — 행마다 X · △ · O(안 고르면 미선택) + 메모
        marks = {m: (k, lab) for m, k, lab in MARKS}
        rows = []
        for i, q in enumerate(questions, 1):
            c = form.get(f"q{i}") or ""
            kind, lab = marks.get(c, ("none", "미선택"))
            memo = (form.get(f"q{i}_memo") or "").strip()
            rows.append({"id": q.get("id", ""), "question": q["question"], "choice": c if c in marks else "",
                         "kind": kind, "label": lab, "text": f"{lab} — {memo}" if memo else lab, "memo": memo})
        return {"action": "accept", "answers": rows, "extra": (form.get(EXTRA) or "").strip()}
    # 질문별 답 목록
    answers = []
    # 질문 번호(1부터) / 질문 하나
    for i, q in enumerate(questions, 1):
        # 고른 선택지 — 없으면 보류
        choice = form.get(f"q{i}") or HOLD
        # 메모 / 옛 화면의 기타 칸 글 / 옛 화면의 질문·논의 칸 글
        memo = (form.get(f"q{i}_memo") or "").strip()
        other = (form.get(f"q{i}_other") or "").strip()
        ask = (form.get(f"q{i}_ask") or "").strip()
        # 답 종류와 답 문장 — 기타 · 질문은 메모(옛 화면이면 그 칸) · 보류는 빈 값 · 그 외는 «선택 — 메모»
        if choice in (OTHER, OTHER_OLD):
            choice, kind, text = OTHER, "other", other or memo
        elif choice in (ASK, ASK_OLD):
            choice, kind, text = ASK, "ask", ask or memo
        elif choice == HOLD:
            kind, text = "hold", ""
        else:
            kind, text = "option", (f"{choice} — {memo}" if memo else choice)
        # 고르지 않은 칸의 글도 버리지 않고 같이 남김(질문을 써 놓고 다른 답을 고른 경우 등)
        answers.append({"id": q.get("id", ""), "question": q["question"], "choice": choice, "kind": kind,
                        "text": text, "memo": memo, "other": other, "ask": ask})
    return {"action": "accept", "answers": answers, "extra": (form.get(EXTRA) or "").strip()}


# 응답 묶음 — (상태 코드, 형식, 본문 바이트, 덧붙일 머리)
# code: 상태 코드 / body: 문자열(HTML) 또는 dict(json) / headers: 덧붙일 머리
def reply(code: int, body, headers: dict = None) -> tuple:
    if isinstance(body, (dict, list)):
        return code, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"), headers or {}
    return code, "text/html; charset=utf-8", str(body).encode("utf-8"), headers or {}


# 상태 — 목록 지문 · 대기 개수 · 가장 최근 대기 설문 · 마지막 화면 확인 뒤 지난 초
#   probe 가 없으면 화면이 확인한 것으로 보고 시각을 갱신(open 명령이 «화면이 붙어 있나» 를 볼 때는 probe=1)
# q: 주소 값
def api_state(q: dict) -> dict:
    # 모든 설문 / 대기 설문
    every = all_surveys()
    pend = [x for x in every if x[3]["state"] == "pending"]
    # 가장 최근 대기 설문
    top = max(pend, key=lambda x: (x[3]["created"], x[3]["id"]), default=None)
    # 마지막 확인 뒤 지난 초
    ago = time.time() - LAST_SEEN[0]
    if not q.get("probe"):
        LAST_SEEN[0] = time.time()
    return {"sig": hashlib.sha1(json.dumps([(k, pr, s["id"], s["state"]) for k, _, pr, s in every]).encode()).hexdigest()[:12],
            "pending": len(pend), "seen_ago": round(ago, 1),
            "newest": {"s": top[0], "p": top[2], "id": top[3]["id"], "created": top[3]["created"]} if top else None}


# 요청 하나 처리 — 따로 띄운 서버 · devview 가 같이 씀(devview 는 /sv 뒤 경로만 넘김)
#   /api/state · /api/side · 옛 주소 /survey/설문id · 그 밖 = 화면(?s=열쇠&p=프로젝트&id=설문)
# method: GET · POST / path: 경로 + 주소 값 / body: POST 본문 바이트
def handle(method: str, path: str, body: bytes = b"") -> tuple:
    # 경로 · 주소 값
    u = urlsplit(path)
    q = {k: v[-1] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
    if u.path.endswith("/api/state") or u.path == "api/state":
        return reply(200, api_state(q))
    if u.path.endswith("/api/img") or u.path == "api/img":
        return serve_img(q)
    if u.path.endswith("/api/side") or u.path == "api/side":
        return reply(200, render_side(*pick(q)))
    if (u.path.endswith("/api/draft") or u.path == "api/draft") and method == "POST":
        return save_draft(q, body)
    # 옛 주소(/survey/설문id) — 새 주소로 넘김. 제출이면 처리한 뒤 넘김
    m = SURVEY_PATH.search(u.path)
    # 옛 주소 기준 화면 주소(상대) — …/survey/설문id 에서 두 단계 위
    up = "../" if not u.path.endswith("/") else "../../"
    if m:
        hit = find_survey(m.group(1))
        if hit is None:
            return reply(404, msg_page("설문 없음"))
        q = {"s": hit[0], "p": hit[2], "id": m.group(1)}
    else:
        up = ""
    if method == "POST":
        return submit(q, body, up)
    if m:
        return reply(303, "", {"Location": up + target_query(q["s"], q["p"], q["id"])})
    # 고른 것 / 본문
    key, project, sid = pick(q)
    title, pane = render_pane(key, project, sid)
    return reply(200, app_page(title, render_side(key, project, sid), pane))


# 설문 그림 — 등록 때 복사해 둔 «<설문id>_img» 폴더의 파일만(이름 형식도 등록 때 만든 것만)
# q: 주소 값(s · p · id · f)
def serve_img(q: dict) -> tuple:
    # 저장 폴더 / 설문 id / 파일 이름
    st, sid, name = store_by_key(q.get("s") or ""), q.get("id") or "", q.get("f") or ""
    if st is None or not re.fullmatch(r"[0-9A-Za-z_-]+", sid) or not re.fullmatch(r"\d+_\d+\.[a-z]+", name):
        return reply(404, {"error": "그림 없음"})
    # 그림 파일
    p = project_dir(st, q.get("p") or LOOSE) / f"{sid}_img" / name
    if p.suffix not in IMG_TYPES or not p.is_file():
        return reply(404, {"error": "그림 없음"})
    return 200, IMG_TYPES[p.suffix], p.read_bytes(), {"Cache-Control": "max-age=3600"}


# 제출 · 취소 → 결과 파일 저장 → 같은 설문 화면(이제 기록 보기)으로 넘김
# q: 주소 값(s · p · id) / body: 폼 본문 / up: 화면 주소 앞에 붙일 상대 경로
def submit(q: dict, body: bytes, up: str) -> tuple:
    # 저장 폴더 / 설문 id
    st, sid = store_by_key(q.get("s") or ""), q.get("id") or ""
    if st is None or not re.fullmatch(r"[0-9A-Za-z_-]+", sid):
        return reply(404, msg_page("설문 없음"))
    # 프로젝트 폴더 / 설문 내용
    folder = project_dir(st, q.get("p") or LOOSE)
    item = read_json(survey_file(folder, sid))
    if item is None:
        return reply(404, msg_page("설문 없음"))
    if result_file(folder, sid).exists():
        return reply(410, msg_page("이미 제출됨"))
    # 폼 값(이름 → 첫 값)
    form = {k: v[0] for k, v in parse_qs(body.decode("utf-8"), keep_blank_values=True).items()}
    # 결과 공통 머리
    head = {"id": sid, "title": item["title"], "project": item.get("project", q.get("p")),
            "submitted": time.strftime("%Y-%m-%d %H:%M:%S")}
    if form.get("_act") == "cancel":
        write_json(result_file(folder, sid), {**head, "action": "cancel", "answers": [], "extra": ""})
    else:
        write_json(result_file(folder, sid), {**head, **collect(item["questions"], form, item.get("mode", "survey"))})
    draft_file(folder, sid).unlink(missing_ok=True)
    return reply(303, "", {"Location": up + target_query(q["s"], q["p"], sid)})


# 쓰던 답 저장 — 화면이 입력할 때마다 폼 값을 보냄. 제출 전 설문에만
# q: 주소 값(s · p · id) / body: 폼 본문
def save_draft(q: dict, body: bytes) -> tuple:
    # 설문 id 로 찾음 — devview 가 저장 폴더 열쇠 없이 프로젝트 · id 만 넘길 때가 있음
    sid = q.get("id") or ""
    hit = find_survey(sid) if re.fullmatch(r"[0-9A-Za-z_-]+", sid) else None
    st = store_by_key(hit[0]) if hit else None
    if st is None:
        return reply(404, {"ok": False})
    # 프로젝트 폴더
    folder = project_dir(st, hit[2])
    if not survey_file(folder, sid).exists() or result_file(folder, sid).exists():
        return reply(409, {"ok": False})
    # 폼 값(이름 → 첫 값) — 제출 단추 값은 빼고
    form = {k: v[0] for k, v in parse_qs(body.decode("utf-8"), keep_blank_values=True).items() if k != "_act"}
    write_json(draft_file(folder, sid), form)
    return reply(200, {"ok": True})


# 따로 띄운 서버의 요청 처리 클래스 — handle 에 넘기기만
class Handler(BaseHTTPRequestHandler):
    # 요청 로그를 줄임(터미널을 덮지 않게)
    # fmt: 로그 형식 / args: 값들
    def log_message(self, fmt, *args):
        if "/api/state" not in self.path:
            sys.stderr.write("[survey] " + (fmt % args) + "\n")

    # 응답 보내기
    # res: handle 의 응답 묶음
    def send(self, res: tuple) -> None:
        # 상태 코드 · 형식 · 본문 · 덧붙일 머리
        code, ctype, data, headers = res
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    # GET — 화면 · 상태
    def do_GET(self):
        self.send(handle("GET", self.path))

    # POST — 제출 · 취소
    def do_POST(self):
        # 본문 길이
        size = int(self.headers.get("Content-Length") or 0)
        self.send(handle("POST", self.path, self.rfile.read(size)))


# serve — 설문 서버 실행
# args: 명령 인자
def cmd_serve(args) -> int:
    # 저장 폴더
    store = Path(args.dir) if args.dir else default_store()
    store.mkdir(parents=True, exist_ok=True)
    EXTRA_STORES.append(store)
    # 서버 객체 — 요청마다 스레드
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"설문 서버 · http://{args.host}:{args.port}/ · 저장 {store}", flush=True)
    print(f"Browser 도구: PORT {args.port} · 경로 / (프로젝트 · 설문 목록)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# 설문 상태 주소에 GET — 설문 상태(seen_ago 칸이 있는 json)가 아니면 None(다른 프로그램 · 옛 devview)
# url: 주소
def probe(url: str):
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            # 응답 json
            data = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and "seen_ago" in data else None


# 그 포트에 무언가 떠 있나 — 연결만 해 봄
# port: 포트
def port_busy(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


# 서버를 창 없이 따로 띄우고 응답할 때까지 기다림 — 띄운 프로세스가 먼저 끝나면 실패(출력 끝부분 보여 줌)
# cmd: 실행 명령 목록 / url: 응답을 확인할 주소 / log: 출력 파일
def spawn(cmd: list, url: str, log: Path) -> bool:
    log.parent.mkdir(parents=True, exist_ok=True)
    # 윈도우 — 콘솔 창 없이 · 이 프로세스와 따로 / 그 밖 — 새 세션
    extra = ({"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True})
    with open(log, "w", encoding="utf-8") as out:
        # 띄운 프로세스
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **extra)
    for _ in range(100):
        if probe(url) is not None:
            return True
        if proc.poll() is not None:
            print("서버 실행 실패:\n" + log.read_text(encoding="utf-8", errors="replace")[-1500:], file=sys.stderr)
            return False
        time.sleep(0.2)
    print(f"서버 응답 없음 — {log} 확인", file=sys.stderr)
    return False


# devview 위치 — 지정값 → 이 도구가 든 저장소의 devview/ (없으면 None)
# given: --devview 값
def devview_path(given):
    # 후보
    for p in ([Path(given)] if given else []) + [REPO / "devview" / "devview.py"]:
        if p.is_file():
            return p
    return None


# 설문을 화면에 띄움
#   devview 가 떠 있고 화면이 붙어 있으면 → 아무것도 열지 않음(설문 탭 안에서 2초 안에 새 설문이 열림 · devview 보기는 안 바뀜)
#   떠 있는데 화면이 없으면 → 브라우저로 devview 를 설문 탭으로 엶
#   꺼져 있으면 → devview(없으면 설문 서버)를 띄우고 엶
# store: 저장 폴더 / project: 프로젝트 / sid: 설문 id / port: 포트 / devview: --devview 값
def open_view(store: Path, project: str, sid: str, port: int, devview) -> None:
    # 주소 조각
    target = target_query(store_key(store), project, sid)[1:]
    # devview 안 설문 상태 / 따로 띄운 설문 서버 상태
    st = probe(f"http://127.0.0.1:{port}/sv/api/state?probe=1")
    alone = None if st else probe(f"http://127.0.0.1:{port}/api/state?probe=1")
    if (st or alone) and (st or alone)["seen_ago"] < CLIENT_GAP:
        print("열린 화면의 설문 탭에 새 설문이 들어감 — 화면은 안 넘어감(유저에게 «설문 탭 Alt+S» 안내)", flush=True)
        return
    # 열 주소
    url = f"http://127.0.0.1:{port}/?sv=1&{target}" if st else f"http://127.0.0.1:{port}/?{target}"
    if not (st or alone) and port_busy(port):
        print(f"포트 {port} 를 설문이 없는 프로그램(옛 devview 등)이 쓰는 중 — 그 서버를 다시 띄우거나 --port 로 다른 포트",
              file=sys.stderr)
        return
    if not (st or alone):
        # 띄울 devview / 출력 파일
        dv = devview_path(devview)
        log = Path.home() / ".devview" / f"survey-open-{port}.out"
        if dv:
            ok = spawn([sys.executable, str(dv), str(git_top(store) or store.parent), "--host", "127.0.0.1",
                        "--port", str(port), "--survey", str(Path(__file__).resolve())],
                       f"http://127.0.0.1:{port}/sv/api/state?probe=1", log)
            url = f"http://127.0.0.1:{port}/?sv=1&{target}"
        else:
            ok = spawn([sys.executable, str(Path(__file__).resolve()), "--dir", str(store), "serve", "--host", "127.0.0.1",
                        "--port", str(port)], f"http://127.0.0.1:{port}/api/state?probe=1", log)
            url = f"http://127.0.0.1:{port}/?{target}"
        if not ok:
            return
    print(f"화면 열기 — {url}", flush=True)
    webbrowser.open(url)


# new — 질문 파일을 설문으로 등록
# args: 명령 인자
def cmd_new(args) -> int:
    # 질문 파일 내용
    spec = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    # 설명 폼 형식(로컬 adr-explain 과 같은 items · title · body) → 설명 모드 질문 목록으로
    if not spec.get("questions") and spec.get("items"):
        spec["mode"] = EXPLAIN
        spec["questions"] = [dict(it, question=it.get("title") or it.get("question", "")) for it in spec["items"]]
    # 표 폼 형식(columns · rows) → 표 모드 행 목록으로. 행 = 칸 글 목록 또는 {id, cells}
    if not spec.get("questions") and spec.get("rows"):
        spec["mode"] = TABLE
        spec["questions"] = []
        for i, r in enumerate(spec["rows"], 1):
            cells = [str(c) for c in (r.get("cells") or [])] if isinstance(r, dict) else [str(c) for c in r]
            rid = str(r.get("id", i)) if isinstance(r, dict) else str(i)
            spec["questions"].append({"id": rid, "question": " · ".join(c for c in cells[:2] if c) or rid, "cells": cells})
    if spec.get("mode", "survey") not in ("survey", EXPLAIN, TABLE):
        print(f"오류: mode 는 survey · {EXPLAIN} · {TABLE} 중 하나", file=sys.stderr)
        return 2
    if not spec.get("questions"):
        print("오류: questions 가 비어 있음", file=sys.stderr)
        return 2
    # 저장 폴더 / 프로젝트 / 프로젝트 폴더
    store = Path(args.dir) if args.dir else default_store()
    project = safe_project(args.project or spec.get("project") or repo_name(store))
    folder = store / project
    folder.mkdir(parents=True, exist_ok=True)
    register_store(store)
    # 설문 id — 시각 기반 · 같은 초면 번호를 붙여 겹치지 않게
    sid = time.strftime("%Y%m%d-%H%M%S")
    # 겹칠 때 붙일 번호
    n = 1
    while survey_file(folder, sid).exists():
        n += 1
        sid = time.strftime("%Y%m%d-%H%M%S") + f"-{n}"
    # 그림 — 질문의 images(경로)를 «<id>_img» 로 복사하고 파일 이름만 남김(화면은 이 폴더 그림만 내보냄)
    for i, qq in enumerate(spec["questions"], 1):
        # 이 질문의 그림 경로 목록 / 복사한 이름
        imgs, names = qq.get("images") or ([qq["image"]] if qq.get("image") else []), []
        for j, src in enumerate(imgs, 1):
            p = Path(src)
            if not p.is_file() or p.suffix.lower() not in IMG_TYPES:
                print(f"오류: 그림 파일이 없거나 형식이 아님: {src}", file=sys.stderr)
                return 2
            (folder / f"{sid}_img").mkdir(exist_ok=True)
            names.append(f"{i}_{j}{p.suffix.lower()}")
            shutil.copyfile(p, folder / f"{sid}_img" / names[-1])
        if imgs:
            qq["images"] = names
            qq.pop("image", None)
    write_json(survey_file(folder, sid), {"id": sid, "title": spec.get("title", sid), "project": project,
                                          "questions": spec["questions"], "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                                          "mode": spec.get("mode", "survey"), "intro": spec.get("intro", ""),
                                          **({"columns": [str(c) for c in spec.get("columns") or []]}
                                             if spec.get("mode") == TABLE else {})})
    print(json.dumps({"id": sid, "project": project, "path": "/" + target_query(store_key(store), project, sid),
                      "questions": len(spec["questions"]), "file": str(survey_file(folder, sid)),
                      # 다음 할 일 — 기다리지 않기(폴링 한 번 = 모델 요청 한 번)를 규칙 문서 대신 여기서 알린다
                      "next": f"기다리지 말 것 — 남은 일을 끝내고 마지막 줄에 «devview 설문 탭(Alt+S) · 질문 {len(spec['questions'])}개 · "
                              f"제출하면 '제출' 한마디» 를 남기고 턴을 끝낸다 → 다음 턴 맨 처음 survey.py result {sid}"},
                     ensure_ascii=False),
          flush=True)
    if args.open:
        open_view(store, project, sid, args.port, args.devview)
    return 0


# 명령의 설문 찾기 — (저장 폴더, 프로젝트 폴더) 또는 None(오류 출력)
# args: 명령 인자(dir · id · project)
def locate(args):
    # 저장 폴더
    store = Path(args.dir) if args.dir else default_store()
    # 찾은 것
    hit = find_survey(args.id, store, getattr(args, "project", None)) if store.is_dir() else None
    if hit is None:
        print(f"오류: 설문 없음 · {args.id} · {store}", file=sys.stderr)
        return None
    return store, hit[2]


# open — 등록된 설문을 화면에 띄움
# args: 명령 인자
def cmd_open(args) -> int:
    # 찾은 것
    hit = locate(args)
    if hit is None:
        return 2
    open_view(hit[0], hit[1], args.id, args.port, args.devview)
    return 0


# wait — 제출될 때까지 아무것도 출력하지 않고 기다렸다가 결과 json 을 한 번 출력
# args: 명령 인자
def cmd_wait(args) -> int:
    # 찾은 것
    hit = locate(args)
    if hit is None:
        return 2
    # 결과 파일
    rf = result_file(project_dir(*hit), args.id)
    while not rf.exists():
        time.sleep(1)
    print(rf.read_text(encoding="utf-8"))
    return 0


# result — 결과 조회. 제출 전이면 pending
# args: 명령 인자
def cmd_result(args) -> int:
    # 찾은 것
    hit = locate(args)
    if hit is None:
        return 2
    # 결과 내용
    data = read_json(result_file(project_dir(*hit), args.id))
    print(json.dumps(data, ensure_ascii=False, indent=1) if data else json.dumps({"id": args.id, "action": "pending"}))
    return 0


# 명령 인자 해석 · 실행
# argv: 명령 인자 목록(시험용 · 없으면 실제 인자)
def main(argv=None) -> int:
    # 출력 인코딩을 코드에서 고정 — 로캘이 C · cp949 여도 한글이 깨지지 않게
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    # 최상위 해석기
    ap = argparse.ArgumentParser(description="HTML 설문 도구")
    ap.add_argument("--dir", default=None, help="설문 저장 폴더(기본 = 지금 저장소의 docs/surveys)")
    # 하위 명령 해석기 묶음
    sub = ap.add_subparsers(dest="cmd", required=True)
    # serve 해석기
    p = sub.add_parser("serve")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8600)
    p.set_defaults(fn=cmd_serve)
    # new · open 해석기 — 화면 띄우기 인자 공통
    for name, fn in (("new", cmd_new), ("open", cmd_open)):
        p = sub.add_parser(name)
        p.add_argument("questions" if name == "new" else "id")
        p.add_argument("--project", default=None, help="프로젝트 이름(기본 = 질문 파일 project → 저장소 이름)")
        if name == "new":
            p.add_argument("--open", action="store_true", help="등록한 뒤 devview 창에 띄움")
        p.add_argument("--port", type=int, default=DEVVIEW_PORT, help="devview(또는 설문 서버) 포트")
        p.add_argument("--devview", default=None, help="devview.py 경로(꺼져 있으면 이걸 띄움)")
        p.set_defaults(fn=fn)
    # wait · result 해석기
    for name, fn in (("wait", cmd_wait), ("result", cmd_result)):
        p = sub.add_parser(name)
        p.add_argument("id")
        p.add_argument("--project", default=None)
        p.set_defaults(fn=fn)
    # 해석된 인자
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
