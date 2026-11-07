# 파이썬 코드 스캔 — 모듈 · 함수 · import · 호출 관계를 tree.auto.json 으로 기록
"""
flowtree 의 «코드가 쓰는 칸». 에이전트가 손으로 잇지 않고 코드에서 직접 감지
- 모듈: 파일 경로 → 점 이름(src/ui/admin.py → src.ui.admin)
- import: 모듈 → 모듈(프로젝트 안) · 모듈 → 외부 라이브러리
- 호출: 함수 → 함수. 이름 · 모듈 별칭 · self · 지역 변수 타입(x = Store()) · self.x 속성까지 추적
- 콜백: 호출하지 않고 넘긴 함수(on_click=handler)는 ref
- 층 규칙 위반: tree.json code.forbid(층 → 층) · code.forbid_lib(층 → 라이브러리) 기준
한계: getattr · 문자열 호출 · 반환값 타입 · 상속 메서드는 추적 안 함 → unresolved 개수로만 보고
파이썬 3.10 이상 · 표준 라이브러리만
"""
from __future__ import annotations

import argparse
import ast
import builtins
import json
import sys
import time
from pathlib import Path

# 스캔에서 빼는 폴더 이름
SKIP_DIRS = {".venv", "venv", "env", "__pycache__", "node_modules", ".git", "build", "dist",
             ".mypy_cache", ".pytest_cache", ".tox", "site-packages"}
# 파이썬 기본 함수 이름 — 해석 실패로 세지 않음
BUILTIN_NAMES = set(dir(builtins))
# 표준 라이브러리 이름 목록(3.10 이상에서 제공)
STDLIB = set(getattr(sys, "stdlib_module_names", ()))
# 해석 실패 예시 최대 개수
MAX_SAMPLES = 30


# 정의 하나 — 함수 · 클래스 · 메서드
class DefInfo:
    # module: 모듈 점 이름 / name: 이름 / qual: 전체 이름 / kind: function · class · method / node: AST / cls: 소속 클래스 이름
    def __init__(self, module, name, qual, kind, node, cls=None):
        # 모듈 점 이름
        self.module = module
        # 정의 이름
        self.name = name
        # 전체 이름(모듈.클래스.메서드)
        self.qual = qual
        # 종류
        self.kind = kind
        # AST 노드
        self.node = node
        # 소속 클래스 이름(메서드일 때)
        self.cls = cls


# 모듈 하나의 스캔 상태
class ModInfo:
    # name: 모듈 점 이름 / rel: 루트 기준 파일 경로 / is_pkg: __init__.py 여부 / tree: AST / lines: 소스 줄 목록
    def __init__(self, name, rel, is_pkg, tree, lines):
        # 모듈 점 이름
        self.name = name
        # 루트 기준 파일 경로(/ 구분)
        self.rel = rel
        # 패키지(__init__.py) 여부
        self.is_pkg = is_pkg
        # AST
        self.tree = tree
        # 소스 줄 목록
        self.lines = lines
        # 별칭 → 점 이름(import 로 생긴 이름)
        self.imports = {}
        # import 문 기록 — (대상 점 이름, 줄, 가져온 이름 목록)
        self.import_stmts = []
        # * 로 가져온 모듈 점 이름
        self.star = []
        # 최상위 이름 → 정의(함수 · 클래스)
        self.defs = {}
        # 클래스 이름 → {메서드 이름 → 정의}
        self.methods = {}
        # 클래스 이름 → {self 속성 이름 → 대입 식}
        self.self_attrs = {}


# 파일 경로 → 모듈 점 이름. __init__.py 는 패키지 이름
# root: 스캔 루트 / path: 파이썬 파일
def module_name(root, path):
    # 루트 기준 경로 조각
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


# 정의 바로 위 주석 묶음(데코레이터 위 포함) → 설명 줄 목록
# lines: 소스 줄 목록 / node: 정의 AST
def comment_above(lines, node):
    # 정의 시작 줄(데코레이터가 있으면 그 줄)
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    # 모은 주석 줄(아래 → 위)
    found = []
    # 살펴볼 줄 번호(0 기준)
    i = start - 2
    while i >= 0 and lines[i].strip().startswith("#"):
        found.append(lines[i].strip().lstrip("#").strip())
        i -= 1
    # 독스트링(있으면 첫 줄)
    doc = ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
    # 결과 줄 목록
    out = [t for t in reversed(found) if t and not t.startswith(("noqa", "type:"))]
    if doc:
        out.append(doc.strip().splitlines()[0])
    return out


# 모듈 맨 위 설명 — 첫 주석 묶음 또는 독스트링 첫 줄
# lines: 소스 줄 목록 / tree: AST
def module_doc(lines, tree):
    # 모은 줄
    out = []
    # 줄 하나
    for line in lines:
        # 공백 뺀 줄
        s = line.strip()
        if s.startswith("#!") or s.startswith("# -*-"):
            continue
        if s.startswith("#"):
            out.append(s.lstrip("#").strip())
            continue
        break
    # 독스트링
    doc = ast.get_docstring(tree)
    if not out and doc:
        out = [doc.strip().splitlines()[0]]
    return " ".join(t for t in out if t)


# 함수 인자 → 짧은 글자(self · cls 제외)
# args: ast.arguments
def args_text(args):
    # 인자 이름 목록
    names = [a.arg for a in args.posonlyargs + args.args if a.arg not in ("self", "cls")]
    if args.vararg:
        names.append("*" + args.vararg.arg)
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    return ", ".join(names)


# 파일 목록 수집 — 숨김 · 가상환경 폴더 제외
# root: 스캔 루트
def collect_files(root):
    # 결과 파일 목록
    files = []
    # 파이썬 파일 하나
    for path in sorted(root.rglob("*.py")):
        # 루트 기준 폴더 조각
        rel_parts = path.relative_to(root).parts[:-1]
        if any(p in SKIP_DIRS or p.startswith(".") for p in rel_parts):
            continue
        files.append(path)
    return files


# 코드 스캐너 — 두 단계(정의 · import 수집 → 호출 해석)
class Scanner:
    # root: 스캔 루트 / config: tree.json 의 code 칸(층 · 규칙)
    def __init__(self, root, config=None):
        # 스캔 루트
        self.root = Path(root)
        # 층 · 규칙 설정
        self.config = config or {}
        # 모듈 점 이름 → 모듈 상태
        self.mods = {}
        # 패키지 점 이름(모듈 이름의 모든 접두어 — __init__.py 없는 폴더 포함)
        self.packages = set()
        # 전체 이름 → 정의
        self.index = {}
        # 파싱 실패 기록
        self.errors = []
        # 해석 실패 개수 · 예시
        self.unresolved = 0
        self.samples = []
        # 호출 기록 — (출발, 도착, 종류) → {줄, 횟수, 확신}
        self.calls = {}

    # 1단계 — 파일 파싱 · 정의 · import 수집
    def parse_all(self):
        # 파이썬 파일 하나
        for path in collect_files(self.root):
            # 모듈 점 이름
            name = module_name(self.root, path)
            if not name:
                continue
            try:
                # 소스 바이트(인코딩 선언 · BOM 은 ast 가 처리)
                raw = path.read_bytes()
                # AST
                tree = ast.parse(raw, filename=str(path))
            # 문법 오류 · 인코딩 오류 — 기록하고 계속
            except (SyntaxError, ValueError, UnicodeDecodeError) as err:
                self.errors.append({"file": path.relative_to(self.root).as_posix(), "error": f"{type(err).__name__}: {err}"})
                continue
            # 소스 줄 목록(주석 추출용)
            lines = raw.decode("utf-8-sig", errors="replace").splitlines()
            # 모듈 상태
            mod = ModInfo(name, path.relative_to(self.root).as_posix(), path.name == "__init__.py", tree, lines)
            self.mods[name] = mod
            self._collect_defs(mod)
            self._collect_imports(mod)
        # 모듈 하나
        for mod in self.mods.values():
            # 모듈 점 이름 조각
            parts = mod.name.split(".")
            # 접두어 길이
            for i in range(1, len(parts)):
                self.packages.add(".".join(parts[:i]))
            # 정의 하나
            for d in mod.defs.values():
                self.index[d.qual] = d
            # 클래스 이름 · 메서드 묶음
            for cls, methods in mod.methods.items():
                # 메서드 하나
                for d in methods.values():
                    self.index[d.qual] = d

    # 최상위 함수 · 클래스 · 메서드 · self 속성 대입 수집
    # mod: 모듈 상태
    def _collect_defs(self, mod):
        # 최상위 문장 하나
        for node in mod.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                mod.defs[node.name] = DefInfo(mod.name, node.name, f"{mod.name}.{node.name}", "function", node)
            elif isinstance(node, ast.ClassDef):
                mod.defs[node.name] = DefInfo(mod.name, node.name, f"{mod.name}.{node.name}", "class", node)
                # 이 클래스의 메서드 묶음
                methods = mod.methods.setdefault(node.name, {})
                # self 속성 → 대입 식
                attrs = mod.self_attrs.setdefault(node.name, {})
                # 클래스 본문 문장 하나
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods[item.name] = DefInfo(mod.name, item.name, f"{mod.name}.{node.name}.{item.name}",
                                                     "method", item, cls=node.name)
                        # 메서드 안 대입문 — self.x = Store() 같은 속성 타입 단서
                        for sub in ast.walk(item):
                            if isinstance(sub, ast.Assign):
                                # 대입 대상 하나
                                for tgt in sub.targets:
                                    if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                                            and tgt.value.id == "self"):
                                        attrs.setdefault(tgt.attr, sub.value)

    # import 문 수집 — 별칭 → 점 이름. 상대 import 는 패키지 기준으로 풀기
    # mod: 모듈 상태
    def _collect_imports(self, mod):
        # 이 모듈이 속한 패키지 점 이름
        pkg = mod.name if mod.is_pkg else mod.name.rpartition(".")[0]
        # AST 노드 하나(함수 안 import 도 포함)
        for node in ast.walk(mod.tree):
            if isinstance(node, ast.Import):
                # 가져온 이름 하나
                for alias in node.names:
                    if alias.asname:
                        mod.imports[alias.asname] = alias.name
                    else:
                        # import a.b.c → 이름 a 가 생김
                        mod.imports[alias.name.split(".")[0]] = alias.name.split(".")[0]
                    mod.import_stmts.append((alias.name, node.lineno, []))
            elif isinstance(node, ast.ImportFrom):
                # 가져올 모듈 점 이름
                base = node.module or ""
                if node.level:
                    # 올라갈 패키지 조각
                    up = pkg.split(".") if pkg else []
                    up = up[: len(up) - (node.level - 1)] if node.level > 1 else up
                    base = ".".join(p for p in up + ([base] if base else []) if p)
                # 가져온 이름 목록
                names = []
                # 가져온 이름 하나
                for alias in node.names:
                    if alias.name == "*":
                        mod.star.append(base)
                        continue
                    mod.imports[alias.asname or alias.name] = f"{base}.{alias.name}" if base else alias.name
                    names.append(alias.name)
                mod.import_stmts.append((base, node.lineno, names))

    # 점 이름 분류 — 프로젝트 정의 · 모듈 · 프로젝트 안 못 찾음 · 외부
    # dotted: 점 이름 / depth: 재수출 추적 깊이
    def classify(self, dotted, depth=0):
        if dotted in self.index:
            return "def", dotted
        if dotted in self.mods:
            return "module", dotted
        if dotted in self.packages:
            return "package", dotted
        # 점 이름 조각
        parts = dotted.split(".")
        # 접두어 길이(긴 것부터)
        for i in range(len(parts) - 1, 0, -1):
            # 모듈 후보 접두어
            pre = ".".join(parts[:i])
            if pre in self.mods:
                # 모듈 안 남은 경로
                rest = parts[i:]
                # 접두어 모듈 상태
                m = self.mods[pre]
                # 그 모듈이 import 로 다시 내보낸 이름이면 따라감(재수출)
                if rest[0] in m.imports and depth < 5:
                    return self.classify(".".join([m.imports[rest[0]]] + rest[1:]), depth + 1)
                return "missing", dotted
        if parts[0] in self.packages or parts[0] in self.mods:
            return "missing", dotted
        return "external", parts[0]

    # 식 → 참조. ("path", 점 이름) 또는 ("inst", 클래스 전체 이름)
    # expr: AST 식 / mod: 모듈 상태 / scope: {"cls": 클래스 이름, "types": 지역 변수 → 클래스 전체 이름}
    def resolve(self, expr, mod, scope):
        if isinstance(expr, ast.Name):
            # 이름
            name = expr.id
            if name in scope["types"]:
                return "inst", scope["types"][name]
            if name in mod.defs:
                return "path", mod.defs[name].qual
            if name in mod.imports:
                return "path", mod.imports[name]
            # * 로 가져온 모듈 하나
            for star in mod.star:
                if f"{star}.{name}" in self.index:
                    return "path", f"{star}.{name}"
            return None
        if isinstance(expr, ast.Attribute):
            # self · cls 의 메서드 · 속성
            if isinstance(expr.value, ast.Name) and expr.value.id in ("self", "cls") and scope["cls"]:
                # 클래스 이름
                cls = scope["cls"]
                if expr.attr in mod.methods.get(cls, {}):
                    return "path", f"{mod.name}.{cls}.{expr.attr}"
                # self 속성 대입 식
                assigned = mod.self_attrs.get(cls, {}).get(expr.attr)
                if assigned is not None:
                    # 대입 식의 타입(클래스 생성일 때만)
                    t = self.instance_type(assigned, mod, {"cls": cls, "types": {}})
                    if t:
                        return "inst", t
                return None
            # 앞부분 참조
            base = self.resolve(expr.value, mod, scope)
            if base is None:
                return None
            if base[0] == "inst":
                return "path", f"{base[1]}.{expr.attr}"
            return "path", f"{base[1]}.{expr.attr}"
        if isinstance(expr, ast.Call):
            # 호출 결과가 클래스 인스턴스면 그 타입
            t = self.instance_type(expr, mod, scope)
            if t:
                return "inst", t
        return None

    # 식이 프로젝트 클래스 생성이면 그 클래스 전체 이름
    # expr: AST 식 / mod: 모듈 상태 / scope: 해석 범위
    def instance_type(self, expr, mod, scope):
        if not isinstance(expr, ast.Call):
            return None
        # 호출 대상 참조
        ref = self.resolve(expr.func, mod, scope)
        if ref is None or ref[0] != "path":
            return None
        # 분류 결과
        kind, qual = self.classify(ref[1])
        if kind == "def" and self.index[qual].kind == "class":
            return qual
        return None

    # 호출 · 콜백 기록
    # src: 출발 전체 이름 / dst: 도착 전체 이름 / kind: call · ref / line: 줄 / conf: high · medium
    def add_call(self, src, dst, kind, line, conf):
        # 기록 키
        key = (src, dst, kind)
        # 기존 기록
        rec = self.calls.get(key)
        if rec is None:
            self.calls[key] = {"line": line, "count": 1, "confidence": conf}
        else:
            rec["count"] += 1
            if conf == "high":
                rec["confidence"] = "high"

    # 해석 실패 기록
    # src: 출발 / expr: 식 / line: 줄
    def miss(self, src, expr, line):
        self.unresolved += 1
        if len(self.samples) < MAX_SAMPLES:
            try:
                # 식 글자
                text = ast.unparse(expr)
            # unparse 실패
            except Exception:
                text = type(expr).__name__
            self.samples.append({"source": src, "expr": text[:80], "line": line})

    # 함수 본문 · 모듈 본문의 호출 해석
    # mod: 모듈 상태 / src: 출발 전체 이름 / body: 문장 목록 / cls: 소속 클래스 / fn: 함수 AST(인자 타입 단서)
    def walk_body(self, mod, src, body, cls=None, fn=None):
        # 지역 변수 → 클래스 전체 이름
        types = {}
        # 해석 범위
        scope = {"cls": cls, "types": types}
        # 인자 타입 표기(store: Store) 단서
        if fn is not None:
            # 인자 하나
            for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs:
                if a.annotation is not None:
                    # 표기 참조
                    ref = self.resolve(a.annotation, mod, scope)
                    if ref and ref[0] == "path":
                        # 분류 결과
                        kind, qual = self.classify(ref[1])
                        if kind == "def" and self.index[qual].kind == "class":
                            types[a.arg] = qual
        # 처리할 노드 목록(본문 문장 순서 유지 — 대입이 호출보다 먼저 보이게)
        nodes = []
        # 문장 하나
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and fn is None:
                continue  # 모듈 본문에서는 최상위 정의 안쪽을 따로 처리
            nodes.extend(ast.walk(stmt))
        # 지역 이름(인자 · 안쪽 함수 · 대입된 이름) — 이름 호출 해석 실패로 세지 않음
        local_names = set()
        if fn is not None:
            local_names |= {a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs}
            local_names |= {a.arg for a in (fn.args.vararg, fn.args.kwarg) if a}
        # 노드 하나(지역 이름 수집용)
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                local_names.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                local_names.add(node.id)
            elif isinstance(node, ast.arg):
                local_names.add(node.arg)
        scope["locals"] = local_names
        # 노드 하나
        for node in nodes:
            # 지역 변수 타입 단서 — x = Store(...) · with Store() as x
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                # 대입 식의 타입
                t = self.instance_type(node.value, mod, scope)
                if t:
                    types[node.targets[0].id] = t
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                # with 항목 하나
                for item in node.items:
                    if isinstance(item.optional_vars, ast.Name):
                        # with 식의 타입
                        t = self.instance_type(item.context_expr, mod, scope)
                        if t:
                            types[item.optional_vars.id] = t
            elif isinstance(node, ast.Call):
                self._record_call(mod, src, node, scope)

    # 호출 하나 해석 · 기록. 인자로 넘긴 함수는 콜백(ref)
    # mod: 모듈 상태 / src: 출발 / node: 호출 AST / scope: 해석 범위
    def _record_call(self, mod, src, node, scope):
        # 호출 대상 참조
        ref = self.resolve(node.func, mod, scope)
        if ref is None:
            if (isinstance(node.func, ast.Name) and node.func.id not in BUILTIN_NAMES
                    and node.func.id not in scope.get("locals", ())):
                self.miss(src, node.func, node.lineno)
        else:
            # 확신 — 인스턴스 타입 추적을 거치면 medium
            conf = "medium" if self._via_instance(node.func, mod, scope) else "high"
            # 분류 결과
            kind, qual = self.classify(ref[1])
            if kind == "def":
                self.add_call(src, qual, "call", node.lineno, conf)
            elif kind == "missing":
                self.miss(src, node.func, node.lineno)
        # 인자 · 키워드 값 하나
        for arg in list(node.args) + [k.value for k in node.keywords]:
            if isinstance(arg, (ast.Name, ast.Attribute)):
                # 인자 참조
                aref = self.resolve(arg, mod, scope)
                if aref and aref[0] == "path":
                    # 분류 결과
                    akind, aqual = self.classify(aref[1])
                    if akind == "def" and self.index[aqual].kind in ("function", "method"):
                        self.add_call(src, aqual, "ref", node.lineno, "medium")

    # 호출 대상 식이 인스턴스 타입 추적을 거쳤는지
    # func: 호출 대상 식 / mod: 모듈 상태 / scope: 해석 범위
    def _via_instance(self, func, mod, scope):
        if isinstance(func, ast.Attribute):
            # 앞부분 참조
            base = self.resolve(func.value, mod, scope)
            return bool(base and base[0] == "inst")
        return False

    # 2단계 — 모든 정의 · 모듈 본문의 호출 해석
    def resolve_calls(self):
        # 모듈 하나
        for mod in self.mods.values():
            self.walk_body(mod, mod.name, mod.tree.body)
            # 최상위 정의 하나
            for d in mod.defs.values():
                if d.kind == "function":
                    self.walk_body(mod, d.qual, d.node.body, fn=d.node)
                elif d.kind == "class":
                    # 클래스 본문의 메서드가 아닌 문장(속성 기본값 등)
                    self.walk_body(mod, d.qual, [s for s in d.node.body
                                                 if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))],
                                   cls=d.name)
                    # 메서드 하나
                    for m in mod.methods.get(d.name, {}).values():
                        self.walk_body(mod, m.qual, m.node.body, cls=d.name, fn=m.node)

    # 모듈 → 층 이름. 설정 접두어가 우선, 없으면 src.<층> · <층>
    # name: 모듈 점 이름
    def layer_of(self, name):
        # 접두어 · 층 짝 목록(긴 접두어 우선)
        rules = sorted(self.config.get("layers", []), key=lambda r: -len(r.get("prefix", "")))
        # 규칙 하나
        for rule in rules:
            # 접두어
            pre = rule.get("prefix", "")
            if name == pre or name.startswith(pre + "."):
                return rule.get("layer", "")
        # 점 이름 조각
        parts = name.split(".")
        if len(parts) > 1 and parts[0] == "src":
            return parts[1]
        return parts[0]

    # 결과 사전 만들기
    def result(self):
        # 금지 층 짝 집합
        forbid = {(a, b) for a, b in self.config.get("forbid", [])}
        # 층 → 금지 라이브러리 집합
        forbid_lib = {k: set(v) for k, v in self.config.get("forbid_lib", {}).items()}
        # 모듈 목록 · import 선 · 위반 목록
        modules, imports, violations = [], [], []
        # 모듈 이름 · 상태
        for name, mod in sorted(self.mods.items()):
            # 이 모듈의 층
            layer = self.layer_of(name)
            # 정의 목록(함수 · 클래스 · 메서드 순서 = 소스 순서)
            defs = []
            # 최상위 정의 하나(소스 줄 순서)
            for d in sorted(mod.defs.values(), key=lambda x: x.node.lineno):
                defs.append(self._def_json(mod, d))
                if d.kind == "class":
                    # 메서드 하나
                    for m in sorted(mod.methods.get(d.name, {}).values(), key=lambda x: x.node.lineno):
                        defs.append(self._def_json(mod, m))
            # 외부 라이브러리 사용 · 프로젝트 import 대상
            externals, targets = {}, {}
            # import 문 하나
            for target, line, names in mod.import_stmts:
                # 분류 결과
                kind, qual = self.classify(target) if target else ("external", "")
                if kind in ("def", "module", "missing", "package"):
                    # 대상 모듈(정의면 그 정의의 모듈)
                    tmod = self.index[qual].module if kind == "def" else (qual if kind == "module" else None)
                    if kind == "missing":
                        tmod = self._module_prefix(qual)
                    # from 패키지 import 모듈 — 가져온 이름이 모듈이면 그 모듈로
                    sub_targets = ([f"{qual}.{n}" for n in names if f"{qual}.{n}" in self.mods]
                                   if kind in ("module", "package") else [])
                    # 대상 모듈 하나 — 모듈 자체를 가져왔으면 이름 목록 없음
                    for t in (sub_targets or ([tmod] if tmod else [])):
                        if t and t != name:
                            # 기존 기록
                            rec = targets.setdefault(t, {"line": line, "names": []})
                            if not sub_targets:
                                rec["names"] += [n for n in names if n not in rec["names"]]
                elif qual:
                    externals.setdefault(qual, line)
            # 대상 모듈 · 기록
            for t, rec in sorted(targets.items()):
                # 대상 층
                tl = self.layer_of(t)
                # 위반 여부
                bad = (layer, tl) in forbid
                imports.append({"source": name, "target": t, "line": rec["line"], "names": rec["names"],
                                "violation": bad})
                if bad:
                    violations.append({"kind": "layer", "source": name, "target": t, "line": rec["line"],
                                       "file": mod.rel, "rule": f"{layer} ↛ {tl}"})
            # 외부 라이브러리 목록
            ext_list = []
            # 라이브러리 이름 · 줄
            for lib, line in sorted(externals.items()):
                # 금지 여부
                bad = lib in forbid_lib.get(layer, set())
                ext_list.append({"lib": lib, "line": line, "stdlib": lib in STDLIB, "violation": bad})
                if bad:
                    violations.append({"kind": "lib", "source": name, "target": lib, "line": line,
                                       "file": mod.rel, "rule": f"{layer} ↛ {lib}"})
            modules.append({"name": name, "file": mod.rel, "layer": layer, "is_pkg": mod.is_pkg,
                            "doc": module_doc(mod.lines, mod.tree), "lines": len(mod.lines),
                            "defs": defs, "externals": ext_list})
        # 호출 목록
        calls = []
        # 기록 키 · 기록
        for (src, dst, kind), rec in sorted(self.calls.items()):
            # 출발 · 도착 모듈
            sm, dm = self._module_of(src), self._module_of(dst)
            # 층 위반 여부
            bad = bool(sm and dm and sm != dm and (self.layer_of(sm), self.layer_of(dm)) in forbid)
            calls.append({"source": src, "target": dst, "kind": kind, "line": rec["line"], "count": rec["count"],
                          "confidence": rec["confidence"], "source_module": sm, "target_module": dm,
                          "violation": bad})
        return {
            "version": 1,
            "root": self.root.as_posix(),
            "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": len(self.mods),
            "modules": modules,
            "imports": imports,
            "calls": calls,
            "violations": violations,
            "unresolved": {"count": self.unresolved, "samples": self.samples},
            "errors": self.errors,
        }

    # 정의 → 사전
    # mod: 모듈 상태 / d: 정의
    def _def_json(self, mod, d):
        # 데코레이터 글자 목록
        decos = []
        # 데코레이터 하나
        for deco in getattr(d.node, "decorator_list", []):
            try:
                decos.append(ast.unparse(deco))
            # unparse 실패
            except Exception:
                decos.append("?")
        return {
            "name": d.name, "qual": d.qual, "kind": d.kind, "cls": d.cls,
            "line": d.node.lineno, "end": getattr(d.node, "end_lineno", d.node.lineno),
            "args": args_text(d.node.args) if d.kind != "class" else "",
            "doc": comment_above(mod.lines, d.node), "decorators": decos,
            "async": isinstance(d.node, ast.AsyncFunctionDef),
        }

    # 전체 이름 → 모듈 점 이름
    # qual: 전체 이름(모듈 자체일 수도)
    def _module_of(self, qual):
        if qual in self.mods:
            return qual
        if qual in self.index:
            return self.index[qual].module
        return self._module_prefix(qual)

    # 점 이름의 가장 긴 모듈 접두어
    # dotted: 점 이름
    def _module_prefix(self, dotted):
        # 점 이름 조각
        parts = dotted.split(".")
        # 접두어 길이
        for i in range(len(parts), 0, -1):
            if ".".join(parts[:i]) in self.mods:
                return ".".join(parts[:i])
        return None


# 스캔 실행 → 결과 사전
# root: 스캔 루트 / config: tree.json 의 code 칸
def scan(root, config=None):
    # 스캐너
    sc = Scanner(root, config)
    sc.parse_all()
    sc.resolve_calls()
    return sc.result()


# tree.json 에서 코드 루트 · 설정 읽기
# tree_path: tree.json 경로
def config_from_tree(tree_path):
    # tree.json 내용
    tree = json.loads(Path(tree_path).read_text(encoding="utf-8"))
    # code 칸
    code = tree.get("code", {})
    return (Path(tree_path).parent / code.get("root", ".")).resolve(), code


# 명령줄 — 실패 · 위반만 출력 + 요약 한 줄
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    # 명령줄 해석기
    ap = argparse.ArgumentParser(description="파이썬 코드 → tree.auto.json(모듈 · import · 호출 · 층 위반)")
    ap.add_argument("root", nargs="?", help="스캔할 코드 폴더(--tree 를 주면 생략 · tree.json code.root)")
    ap.add_argument("--tree", help="tree.json — 층 · 규칙 설정과 기본 출력 위치")
    ap.add_argument("-o", "--out", help="출력 파일(기본: tree.json 옆 tree.auto.json, 없으면 표준 출력)")
    # 해석 결과
    args = ap.parse_args(argv)
    # 코드 루트 · 설정
    root, config = (config_from_tree(args.tree) if args.tree else (None, {}))
    if args.root:
        root = Path(args.root).resolve()
    if root is None:
        ap.error("코드 폴더 또는 --tree 필요")
    # 스캔 결과
    res = scan(root, config)
    # 출력 경로
    out = Path(args.out) if args.out else (Path(args.tree).with_name("tree.auto.json") if args.tree else None)
    # 결과 글자
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    # 문제 한 줄씩
    for v in res["violations"]:
        print(f"🔴 위반 {v['rule']} — {v['source']} → {v['target']} ({v['file']}:{v['line']})", file=sys.stderr)
    # 파싱 실패 하나
    for e in res["errors"]:
        print(f"🔴 파싱 실패 {e['file']} — {e['error']}", file=sys.stderr)
    # 정의 개수
    n_defs = sum(len(m["defs"]) for m in res["modules"])
    print(f"모듈 {len(res['modules'])} · 정의 {n_defs} · import {len(res['imports'])} · 호출 {len(res['calls'])}"
          f" · 위반 {len(res['violations'])} · 해석 못 한 호출 {res['unresolved']['count']}"
          + (f" → {out}" if out else ""), file=sys.stderr)
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
