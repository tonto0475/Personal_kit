# 결과물 출력 — matplotlib PNG 저장 · 마크다운 보고서 · CSV(utf-8-sig)
#   역할: 그래프를 out/ 에 PNG 로(한글 글꼴 Pretendard 등록 · 화면 없는 Agg) · 제목 · 표 · 그림 경로로 마크다운 보고서 · 엑셀에서 한글이 안 깨지는 CSV
#   어디에: 제출 결과물(out/) — 화면 그래프는 ECharts, 보고서에 붙일 그림만 matplotlib
#   실패하면: 글꼴 파일 없음 · 표 형식 아님 · 알 수 없는 보고서 블록이면 InputError(한글이 네모로 깨진 PNG 를 조용히 만들지 않음)
import os

import matplotlib

# 화면 없는 그리기 백엔드 — 서버 · 컨테이너에서 창을 띄우지 않음(pyplot import 전에 지정)
matplotlib.use("Agg")

from matplotlib import font_manager  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from src.core.errors import InputError  # noqa: E402

# 한글 글꼴 기본 경로 — 저장소 루트 기준(run.sh 가 루트에서 실행)
FONT_PATH = "assets/fonts/Pretendard-Regular.ttf"


# 한글 글꼴 등록 + 기본 글꼴로 지정. 돌려줌: 글꼴 이름
# font_path: ttf 경로
def setup_korean_font(font_path=FONT_PATH):
    if not os.path.isfile(font_path):
        raise InputError("한글 글꼴 없음: {}".format(font_path))
    font_manager.fontManager.addfont(font_path)
    # 글꼴 파일에 적힌 이름(예: Pretendard)
    name = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams["font.family"] = name
    # 음수 기호를 유니코드 마이너스 대신 하이픈으로 — 한글 글꼴에 없는 글자라 네모가 됨
    plt.rcParams["axes.unicode_minus"] = False
    return name


# 그림을 PNG 로 저장하고 닫음(닫지 않으면 메모리가 쌓임). 돌려줌: 저장 경로
# fig: matplotlib 그림 / name: 파일 이름(.png 없으면 붙임) / out_dir: 저장 폴더 / dpi: 해상도
def save_png(fig, name, out_dir="out", dpi=150):
    os.makedirs(out_dir, exist_ok=True)
    # 저장 경로
    path = os.path.join(out_dir, name if name.endswith(".png") else name + ".png")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# 표 → 마크다운 표 문자열. DataFrame 또는 dict 목록
# rows: 표 / columns: 열 순서(없으면 표의 열 순서)
def md_table(rows, columns=None):
    # 표 객체
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    if columns is not None:
        df = df[list(columns)]
    if df.columns.empty:
        raise InputError("표 열 없음")
    # 칸 문자열 변환 — 결측은 빈칸, 세로줄은 표를 깨므로 이스케이프
    # v: 칸 값
    def cell(v):
        return "" if pd.isna(v) else str(v).replace("|", "\\|").replace("\n", " ")
    # 출력 줄 목록 — 머리 · 구분선
    lines = ["| " + " | ".join(cell(c) for c in df.columns) + " |",
             "|" + "---|" * len(df.columns)]
    # 행 값 튜플
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    return "\n".join(lines)


# 마크다운 보고서 파일 쓰기. 그림 경로는 보고서 파일 기준 상대 경로로 바꿔 넣음. 돌려줌: 보고서 경로
# path: 보고서 경로(예: out/report.md) / title: 제목
# blocks: [("h2", 소제목) · ("text", 문단) · ("table", 표) · ("image", PNG 경로, 설명)] 순서대로
def write_report(path, title, blocks):
    # 보고서 폴더
    base = os.path.dirname(os.path.abspath(path))
    # 출력 조각 목록
    parts = ["# " + title]
    # 블록 하나
    for block in blocks:
        # 블록 종류
        kind = block[0]
        if kind == "h2":
            parts.append("## " + block[1])
        elif kind == "text":
            parts.append(block[1])
        elif kind == "table":
            parts.append(md_table(block[1]))
        elif kind == "image":
            # 보고서 기준 상대 경로 — 윈도우 구분자도 / 로
            rel = os.path.relpath(os.path.abspath(block[1]), base).replace("\\", "/")
            parts.append("![{}]({})".format(block[2] if len(block) > 2 else "", rel))
        else:
            raise InputError("보고서 블록 종류 오류: {}".format(kind))
    os.makedirs(base, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n\n".join(parts) + "\n")
    return path


# CSV 저장 — utf-8-sig(엑셀에서 한글 안 깨짐) · 행 번호 열 없음. 돌려줌: 경로
# df: 표 / path: 저장 경로
def save_csv(df, path):
    # 저장 폴더
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
