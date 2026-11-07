"""키트 devview 시험 — PDF · 엑셀(xlsx) · 워드(docx) 읽기 전용 보기

    python3 devview/tests/test_office.py           (키트 루트에서 · 윈도우는 py -3) — 서버 API + 화면(헤드리스)
    python3 devview/tests/test_office.py --api     — 서버 API 만(Playwright 없는 곳 · WSL)

- 픽스처(xlsx · docx · pdf)는 이 파일이 zipfile 로 직접 만든다(외부 라이브러리 없음)
- 홈 폴더를 임시로 바꿔(~/.devview) 유저 기록과 안 섞인다 · 시험 서버는 빈 포트에 띄우고 그 PID 만 끈다
- 단언 대상은 관측 결과: API 응답 값 · 화면에 보이는 글자 · 콘솔 오류
- 화면 창은 CC_HEADED=1 일 때만 띄운다
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote

# devview 서버 파일
DEVVIEW = Path(__file__).resolve().parent.parent / "devview.py"
# 캡처 저장 폴더
SHOTS = Path(__file__).resolve().parent / "shots"
# (시험 이름, 통과 여부) 목록
RESULTS = []


# 결과 한 줄 기록
def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail)[:200] if detail else ''}", flush=True)


# 비어 있는 포트 번호
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ======= 픽스처 =======
# 엑셀 공통 머리 파일(콘텐츠 형식 · 꾸러미 관계)
def xlsx_common(zf, n_sheets):
    # 시트별 형식 선언
    over = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   for i in range(1, n_sheets + 1))
    zf.writestr("[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                f'{over}</Types>')
    zf.writestr("_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>')


# 엑셀 통합 문서 · 관계 파일(시트 이름 목록)
def xlsx_book(zf, names):
    # 엑셀 본문 이름공간 선언
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    # 시트 요소들
    sheets = "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
    zf.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8"?><workbook {ns}><sheets>{sheets}</sheets></workbook>')
    # 시트 관계 요소들(하나는 / 로 시작하는 절대 경로로 — 두 꼴 모두 해석하는지)
    rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                   f'Target="{"/xl/" if i == 2 else ""}worksheets/sheet{i}.xml"/>' for i in range(1, len(names) + 1))
    zf.writestr("xl/_rels/workbook.xml.rels",
                f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')


# 시트 XML(줄 요소 글자)
def sheet_xml(rows_xml):
    return ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{rows_xml}</sheetData></worksheet>')


# 시트 2개 엑셀 — 한글 · 숫자 · 수식 계산값 · 날짜 · 불린 · 빈 줄 건너뜀
def make_xlsx(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        xlsx_common(zf, 2)
        xlsx_book(zf, ["매출", "둘째"])
        zf.writestr("xl/sharedStrings.xml",
                    '<?xml version="1.0" encoding="UTF-8"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">'
                    '<si><t>이름</t></si><si><t>수량</t></si><si><r><t>사</t></r><r><t>과</t></r></si><si><t>끝 줄</t></si></sst>')
        zf.writestr("xl/styles.xml",
                    '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd\\ hh:mm"/></numFmts>'
                    '<cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/></cellXfs></styleSheet>')
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml(
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="inlineStr"><is><t>두 배</t></is></c>'
            '<c r="D1" t="inlineStr"><is><t>날짜</t></is></c><c r="E1" t="inlineStr"><is><t>여부</t></is></c></row>'
            '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>3</v></c><c r="C2"><f>B2*2</f><v>6</v></c>'
            '<c r="D2" s="1"><v>45292</v></c><c r="E2" t="b"><v>1</v></c><c r="F2" s="2"><v>45292.5</v></c></row>'
            '<row r="5"><c r="A5" t="s"><v>3</v></c><c r="C5"><v>0.25</v></c></row>'))
        zf.writestr("xl/worksheets/sheet2.xml", sheet_xml(
            '<row r="1"><c r="A1" t="inlineStr"><is><t>둘째 시트 글자</t></is></c><c r="B1"><v>3.5</v></c></row>'))


# 큰 시트 하나(2,500줄) — 앞 2,000줄만 보내는지
def make_big_xlsx(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        xlsx_common(zf, 1)
        xlsx_book(zf, ["큰 시트"])
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml(
            "".join(f'<row r="{i}"><c r="A{i}"><v>{i}</v></c></row>' for i in range(1, 2501))))


# 워드 — 제목 2개(스타일 이름 · 스타일 id) · 문단 · 표 · 표 뒤 문단
def make_docx(path):
    # 워드 본문 이름공간 선언
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    # 칸 하나 XML
    cell = lambda t: f"<w:tc><w:p><w:r><w:t>{t}</w:t></w:r></w:p></w:tc>"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        zf.writestr("word/styles.xml",
                    f'<?xml version="1.0" encoding="UTF-8"?><w:styles {w}>'
                    '<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/></w:style>'
                    '<w:style w:type="paragraph" w:styleId="a"><w:name w:val="Normal"/></w:style></w:styles>')
        zf.writestr("word/document.xml",
                    f'<?xml version="1.0" encoding="UTF-8"?><w:document {w}><w:body>'
                    '<w:p><w:pPr><w:pStyle w:val="1"/></w:pPr><w:r><w:t>제목 하나</w:t></w:r></w:p>'
                    '<w:p><w:pPr><w:pStyle w:val="a"/></w:pPr><w:r><w:t xml:space="preserve">본문 </w:t></w:r><w:r><w:t>문단입니다</w:t></w:r></w:p>'
                    '<w:p></w:p>'
                    '<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>작은 제목</w:t></w:r></w:p>'
                    f'<w:tbl><w:tr>{cell("가")}{cell("나")}</w:tr><w:tr>{cell("다")}{cell("라")}</w:tr></w:tbl>'
                    '<w:p><w:r><w:t>표 뒤 문단</w:t></w:r></w:p>'
                    '<w:sectPr/></w:body></w:document>')


# 손으로 쓴 최소 PDF 1쪽(xref 위치는 계산)
def make_pdf(path):
    # PDF 객체 본문 목록
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    # 쪽 그리기 명령
    stream = b"BT /F1 24 Tf 40 100 Td (Hello PDF) Tj ET"
    objs[3] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    # 파일 바이트
    out = bytearray(b"%PDF-1.4\n")
    # 객체마다 시작 위치
    offs = []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    # xref 시작 위치
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    Path(path).write_bytes(bytes(out))


# 시험 작업 폴더 만들기
def make_root(root):
    make_xlsx(root / "표.xlsx")
    make_big_xlsx(root / "big.xlsx")
    make_docx(root / "문서.docx")
    make_pdf(root / "doc.pdf")
    (root / "broken.xlsx").write_bytes(b"this is not a zip file")
    (root / "old.xls").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64)
    with zipfile.ZipFile(root / "nodoc.docx", "w") as zf:
        zf.writestr("word/other.xml", "<x/>")
    (root / "note.md").write_text("# 메모\n", encoding="utf-8")


# ======= 서버 API =======
# GET 요청 → (상태 코드, json)
def get(base, route):
    try:
        with urllib.request.urlopen(base + route, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def test_api(base):
    # 엑셀 첫 시트 응답
    code, r = get(base, "api/office?path=" + quote("표.xlsx"))
    check("엑셀 200 · 시트 이름 2개", code == 200 and r.get("sheets") == ["매출", "둘째"], (code, r.get("sheets")))
    # 줄 번호 → 칸 목록
    rows = {n: cells for n, cells in r.get("rows", [])}
    check("공유 문자열 · 서식 조각 이어 붙임", rows.get(1, [])[:2] == ["이름", "수량"] and rows.get(2, [""])[0] == "사과", rows)
    check("인라인 문자열", rows.get(1, ["", "", ""])[2] == "두 배", rows.get(1))
    check("숫자 · 수식 계산값", rows.get(2, [None, None, None])[1:3] == ["3", "6"], rows.get(2))
    check("날짜 서식(14) → 날짜", rows.get(2, [""] * 4)[3] == "2024-01-01", rows.get(2))
    check("불린 → TRUE", rows.get(2, [""] * 5)[4] == "TRUE", rows.get(2))
    check("사용자 날짜 서식 → 날짜 시각", rows.get(2, [""] * 6)[5] == "2024-01-01 12:00", rows.get(2))
    check("빈 줄 건너뛴 줄 번호 5 · 소수", rows.get(5) == ["끝 줄", "", "0.25"], rows.get(5))
    check("열 수 · 전체 줄 수 · 안 끊김", r.get("cols") == 6 and r.get("total") == 3 and r.get("cut") is False, (r.get("cols"), r.get("total"), r.get("cut")))
    code, r = get(base, "api/office?sheet=1&path=" + quote("표.xlsx"))
    check("둘째 시트(절대 경로 관계)", code == 200 and r.get("sheet") == 1 and r.get("rows") == [[1, ["둘째 시트 글자", "3.5"]]], r.get("rows"))
    code, r = get(base, "api/office?path=big.xlsx")
    check("큰 시트 → 앞 2,000줄 · 전체 2,500", code == 200 and len(r.get("rows", [])) == 2000 and r.get("total") == 2500 and r.get("cut") is True,
          (len(r.get("rows", [])), r.get("total"), r.get("cut")))
    # 워드 응답
    code, r = get(base, "api/office?path=" + quote("문서.docx"))
    # 블록 목록
    blocks = r.get("blocks", [])
    check("워드 200 · 블록 5개(빈 문단 제외)", code == 200 and len(blocks) == 5, blocks)
    check("제목(스타일 이름 heading 1)", blocks[:1] == [{"t": "h", "level": 1, "text": "제목 하나"}], blocks[:1])
    check("문단 조각 이어 붙임", len(blocks) > 1 and blocks[1] == {"t": "p", "text": "본문 문단입니다"}, blocks[1:2])
    check("제목(스타일 id Heading2)", len(blocks) > 2 and blocks[2] == {"t": "h", "level": 2, "text": "작은 제목"}, blocks[2:3])
    check("표 칸 · 순서", len(blocks) > 4 and blocks[3] == {"t": "table", "rows": [["가", "나"], ["다", "라"]]} and blocks[4]["text"] == "표 뒤 문단", blocks[3:])
    code, r = get(base, "api/office?path=broken.xlsx")
    check("깨진 파일 → 422 읽기 실패", code == 422 and r.get("error", "").startswith("읽기 실패"), (code, r))
    code, r = get(base, "api/office?path=nodoc.docx")
    check("document.xml 없는 docx → 422", code == 422 and "document.xml" in r.get("error", ""), (code, r))
    code, r = get(base, "api/office?path=old.xls")
    check(".xls → 415 미지원 형식(.xls)", code == 415 and r.get("error") == "미지원 형식(.xls)", (code, r))
    code, r = get(base, "api/office?path=" + quote("../outside.xlsx"))
    check("작업 폴더 밖 경로 → 403", code == 403, (code, r))
    code, r = get(base, "api/office?path=none.xlsx")
    check("없는 파일 → 404", code == 404, (code, r))
    code, r = get(base, "api/info")
    check("깨진 파일 뒤에도 서버 살아 있음", code == 200, code)
    with urllib.request.urlopen(base + "api/raw?path=doc.pdf", timeout=10) as resp:
        # PDF 원본 응답 형식 · 표시 방식 · 첫 바이트
        ctype, disp, head = resp.headers.get("Content-Type"), resp.headers.get("Content-Disposition"), resp.read(8)
    check("PDF 원본 = application/pdf · inline · 파일 이름", ctype == "application/pdf" and head.startswith(b"%PDF")
          and disp == "inline; filename*=UTF-8''doc.pdf", (ctype, disp, head))


# ======= 화면 =======
def test_ui(base):
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(exist_ok=True)
    # 콘솔 오류 목록
    errors = []
    with sync_playwright() as pw:
        # 창 띄우기 여부(CC_HEADED=1 일 때만)
        headless = os.environ.get("CC_HEADED") != "1"
        try:
            # 브라우저 — channel chromium(새 헤드리스)만 PDF 내장 보기를 그린다. 없으면 기본(헤드리스 셸)
            br = pw.chromium.launch(headless=headless, channel="chromium")
            pdf_render = True
        except Exception:
            br = pw.chromium.launch(headless=headless)
            pdf_render = False
        pg = br.new_context(viewport={"width": 1400, "height": 900}).new_page()
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base)
        pg.wait_for_function("document.documentElement.dataset.ready === '1'", timeout=40000)
        # 보이는 보기 상자
        other = "#paneL .dv-other"

        # 트리 아이콘
        pg.wait_for_selector('.dv-tr[data-p="doc.pdf"]')
        # 확장자별 트리 표식 글자
        badges = pg.evaluate("""() => Object.fromEntries(['doc.pdf', '표.xlsx', '문서.docx', 'old.xls'].map(
            p => [p, document.querySelector(`.dv-tr[data-p="${p}"] .dv-fb`)?.textContent || '']))""")
        check("트리 표식 Pd · X · W", badges == {"doc.pdf": "Pd", "표.xlsx": "X", "문서.docx": "W", "old.xls": "X"}, badges)

        # PDF
        pg.evaluate("p => window.devview.openFile(p, {})", "doc.pdf")
        pg.wait_for_selector(f"{other} iframe.dv-pdf", state="visible", timeout=5000)
        # PDF 보기 요소 주소 · 크기
        info = pg.evaluate(f"""() => {{ const f = document.querySelector('{other} iframe.dv-pdf'); const r = f.getBoundingClientRect();
            return {{ src: f.getAttribute('src'), w: r.width, h: r.height }}; }}""")
        check("PDF 보기 iframe · 원본 주소 · 칸을 채움", "api/raw?path=doc.pdf" in info["src"] and info["w"] > 600 and info["h"] > 400, info)
        check("PDF 는 저장 표시 · 인코딩 표시 없음", pg.locator('#status [data-st="save"]').count() == 0
              and "UTF-8" not in pg.locator("#status").inner_text(), pg.locator("#status").inner_text())
        if pdf_render:
            # 내장 PDF 보기(크롬 확장 화면) 프레임이 붙었나
            ok = False
            for _ in range(50):
                ok = any(f.url.startswith("chrome-extension://") for f in pg.frames)
                if ok:
                    break
                pg.wait_for_timeout(100)
            check("PDF 내장 보기 프레임 붙음", ok, [f.url[:60] for f in pg.frames])
        else:
            print("SKIP | PDF 내장 보기 렌더 — channel chromium 없음(헤드리스 셸은 PDF 를 안 그림)", flush=True)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(SHOTS / "office_pdf.png"))

        # 엑셀
        pg.evaluate("p => window.devview.openFile(p, {})", "표.xlsx")
        pg.wait_for_selector(f"{other} .dv-sheetview td:text-is('사과')", state="visible", timeout=8000)
        # 시트 탭 글자
        tabs = pg.locator(f"{other} .dv-sheet").all_inner_texts()
        check("시트 탭 2개(매출 · 둘째) · 첫 탭 선택", tabs == ["매출", "둘째"] and pg.locator(f"{other} .dv-sheet.is-on").inner_text() == "매출", tabs)
        # 표 글자
        txt = pg.locator(f"{other} .dv-table").inner_text()
        check("엑셀 칸 글자(사과 · 6 · 2024-01-01 · TRUE)", all(x in txt for x in ("사과", "6", "2024-01-01", "TRUE", "끝 줄")), txt[:200])
        check("열 머리 A~F · 줄 번호 5", pg.locator(f"{other} th").all_inner_texts() == ["#", "A", "B", "C", "D", "E", "F"]
              and "5" in pg.locator(f"{other} td.is-n").all_inner_texts())
        check("정보 줄 «행 3 · 열 6»", pg.locator(f"{other} .dv-table-info").inner_text() == "행 3 · 열 6",
              pg.locator(f"{other} .dv-table-info").inner_text())
        check("엑셀은 저장 표시 없음 · 편집기 숨김", pg.locator('#status [data-st="save"]').count() == 0 and not pg.locator("#paneL .dv-monaco").is_visible())
        pg.screenshot(path=str(SHOTS / "office_xlsx_1.png"))
        pg.locator(f"{other} .dv-sheet", has_text="둘째").click()
        pg.wait_for_selector(f"{other} td:text-is('둘째 시트 글자')", state="visible", timeout=5000)
        check("시트 탭 전환 → 다른 칸 글자 보임 · 첫 시트 글자 사라짐",
              pg.locator(f"{other} td:text-is('둘째 시트 글자')").is_visible() and pg.locator(f"{other} td:text-is('사과')").count() == 0
              and pg.locator(f"{other} .dv-sheet.is-on").inner_text() == "둘째")
        pg.screenshot(path=str(SHOTS / "office_xlsx_2.png"))

        # 큰 시트
        pg.evaluate("p => window.devview.openFile(p, {})", "big.xlsx")
        pg.wait_for_selector(f"{other} .dv-table-info", state="visible", timeout=8000)
        check("큰 시트 정보 줄 «2,500행 중 앞 2,000행»", pg.locator(f"{other} .dv-table-info").inner_text().startswith("2,500행 중 앞 2,000행"),
              pg.locator(f"{other} .dv-table-info").inner_text())

        # 워드
        pg.evaluate("p => window.devview.openFile(p, {})", "문서.docx")
        pg.wait_for_selector(f"{other} .dv-word h1", state="visible", timeout=8000)
        check("워드 제목 h1 · h2", pg.locator(f"{other} .dv-word h1").inner_text() == "제목 하나"
              and pg.locator(f"{other} .dv-word h2").inner_text() == "작은 제목")
        check("워드 문단 글자", pg.locator(f"{other} .dv-word p", has_text="본문 문단입니다").is_visible())
        check("워드 표 칸 글자(가 · 라)", pg.locator(f"{other} .dv-word-table td:text-is('라')").is_visible()
              and pg.locator(f"{other} .dv-word-table td").all_inner_texts() == ["가", "나", "다", "라"])
        # 블록 순서(태그 · 글자)
        order = pg.evaluate(f"() => [...document.querySelector('{other} .dv-word').children].map(e => e.tagName)")
        check("순서 h1 · p · h2 · table · p", order == ["H1", "P", "H2", "TABLE", "P"], order)
        pg.screenshot(path=str(SHOTS / "office_docx.png"))

        # 옛 형식 · 깨진 파일
        pg.evaluate("p => window.devview.openFile(p, {})", "old.xls")
        pg.wait_for_selector(f"{other} .dv-placeholder", state="visible", timeout=5000)
        check("옛 형식 한 줄 «미지원 형식(.xls)»", pg.locator(f"{other} .dv-placeholder p").inner_text() == "미지원 형식(.xls)",
              pg.locator(f"{other} .dv-placeholder p").inner_text())
        pg.evaluate("p => window.devview.openFile(p, {})", "broken.xlsx")
        pg.wait_for_selector(f"{other} .dv-placeholder p:has-text('읽기 실패')", state="visible", timeout=5000)
        check("깨진 파일 한 줄 «읽기 실패: …»", pg.locator(f"{other} .dv-placeholder p").inner_text().startswith("읽기 실패:"),
              pg.locator(f"{other} .dv-placeholder p").inner_text())
        pg.screenshot(path=str(SHOTS / "office_broken.png"))

        # 탭 오가기 — 엑셀로 돌아오면 보던 시트(둘째) 그대로
        pg.evaluate("p => window.devview.openFile(p, {})", "표.xlsx")
        pg.wait_for_selector(f"{other} td:text-is('둘째 시트 글자')", state="visible", timeout=5000)
        check("탭 돌아오면 보던 시트 유지", pg.locator(f"{other} .dv-sheet.is-on").inner_text() == "둘째")
        pg.evaluate("p => window.devview.openFile(p, {})", "note.md")
        pg.wait_for_timeout(300)
        check("md 로 바꾸면 오피스 보기 숨김", not pg.locator(other).is_visible())

        # 422(깨진 파일)는 의도한 응답이라 콘솔의 자원 오류 한 줄은 제외
        bad = [e for e in errors if "status of 422" not in e]
        check("콘솔 오류 없음", not bad, bad)
        br.close()


def main():
    # 서버 API 만 돌리나
    api_only = "--api" in sys.argv
    # 임시 폴더
    tmp = Path(tempfile.mkdtemp(prefix="dv_office_"))
    # 시험 작업 폴더
    root = tmp / "ws"
    root.mkdir()
    make_root(root)
    (tmp / "outside.xlsx").write_bytes((root / "표.xlsx").read_bytes())
    # 임시 홈(보던 상태 · 로그 분리)
    home = tmp / "home"
    home.mkdir()
    # 시험 서버 환경 변수
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    # 시험 서버 포트
    port = free_port()
    # 시험 서버 프로세스(이 PID 만 끈다)
    # 코드 보기 기준 시험 — 첫 화면 그래프(2026-11-01) 이전처럼 코드로 시작
    proc = subprocess.Popen([sys.executable, str(DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port), "--start-view", "code"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 시험 서버 주소
    base = f"http://127.0.0.1:{port}/"
    while proc.poll() is None:
        try:
            urllib.request.urlopen(base + "api/info", timeout=1).read()
            break
        except OSError:
            time.sleep(0.1)
    try:
        print(f"파이썬 {sys.version.split()[0]} · 서버 PID {proc.pid} · 포트 {port}", flush=True)
        test_api(base)
        if not api_only:
            test_ui(base)
    finally:
        proc.kill()
        proc.wait(5)
    # 실패한 시험 이름
    bad = [n for n, ok in RESULTS if not ok]
    print(f"결과: {'모두 통과' if not bad else '실패 ' + str(len(bad)) + '개'} ({len(RESULTS)}개)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
