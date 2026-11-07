#!/usr/bin/env python3
# 데이터 세기 도구 시험 — 임시 폴더에 CSV 를 만들어 실제로 실행하고 출력 · 종료코드를 확인
#   python3 scripts/ontology/test_profile.py
import subprocess
import sys
import tempfile
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("profile.py")
# 실패 목록
FAILS = []


# 확인 하나 — 통과/실패 출력, 실패는 목록에 모음
def check(name, ok, detail=""):
    print(("  통과 " if ok else "  실패 ") + name + ("" if ok else "  → " + detail), flush=True)
    if not ok:
        FAILS.append(name)


# 파일을 쓰고 도구를 돌려 (종료코드, 출력) 을 돌려준다
def run(d, name, data, *args):
    p = Path(d) / name
    p.write_bytes(data)
    r = subprocess.run([sys.executable, str(TOOL), str(p)] + list(args), capture_output=True)
    return r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n")   # 윈도우 줄바꿈 맞춤


def main():
    with tempfile.TemporaryDirectory() as d:
        # ======= 정상 — 재검사 겹침 · 빈칸 · 이름 열 숨김 =======
        rows = ["inspected_at,lot_id,wafer_no,result,inspector"]
        rows += ["2026-10-19 09:%02d:00,L43%02d,%d,OK,김철수" % (i, i // 5 + 1, i % 5 + 1) for i in range(40)]
        rows += ["2026-10-19 10:00:00,L4301,1,NG,김철수", "2026-10-19 10:01:00,L4302,2,,이영희"]
        code, out = run(d, "ok.csv", ("\n".join(rows) + "\n").encode("utf-8"))
        check("정상 파일 종료코드 0", code == 0, str(code))
        check("구별 기준 짝 겹침을 잡는다", "lot_id + wafer_no : 겹치는 묶음 2개" in out, out[-600:])
        check("빈칸을 센다", "### result — 글자\n- 빈칸 1" in out, out)
        check("이름 열 값을 숨긴다", "김철수" not in out and "값을 숨긴 열: inspector" in out, out)
        code, out2 = run(d, "ok2.csv", ("\n".join(rows) + "\n").encode("utf-8"), "--show", "inspector")
        check("--show 로 숨김을 푼다", "김철수" in out2)

        # ======= cp949 · 세미콜론 =======
        code, out = run(d, "cp.csv", "로트;판정\nA1;합격\nA2;불합격\nA3;합격\n".encode("cp949"))
        check("cp949 · 세미콜론을 읽는다", code == 0 and "인코딩 cp949" in out and "«;»" in out, out[:300])

        # ======= 머리줄 앞 설명 줄 =======
        code, out = run(d, "desc.csv", "검사 결과 내보내기\nlot,result\nA,OK\nB,NG\nC,OK\n".encode("utf-8"))
        check("설명 줄을 건너뛴다", code == 0 and "머리줄 2번째 줄" in out and "1줄을 건너뜀" in out, out[:300])

        # ======= 못 읽는 파일은 이유를 찍고 2 =======
        code, out = run(d, "empty.csv", b"")
        check("빈 파일 → 2", code == 2 and "빈 파일" in out, out)
        code, out = run(d, "x.json", b'{"a": 1}')
        check("JSON → 2", code == 2 and "JSON" in out, out)
        code, out = run(d, "dup.csv", "a,a\n1,2\n3,4\n".encode("utf-8"))
        check("같은 이름 열 → 2", code == 2 and "같은 이름의 열" in out, out)
        code, out = run(d, "ragged.csv", "a,b,c\n1,2,3\n1,2\n1\n4,5,6\n".encode("utf-8"))
        check("열 수가 다른 줄이 많으면 → 2", code == 2 and "열 수가 다른 줄" in out, out)

        # ======= 시간대 표시 · 섞인 순서 =======
        code, out = run(d, "tz.csv", ("t,v\n2026-10-19T08:10:00+09:00,1\n2026-10-19T07:10:00+09:00,2\n"
                                      "2026-10-19T09:10:00+09:00,3\n").encode("utf-8"))
        check("시간대 표시 · 순서 섞임을 알린다", "시간대 표시 있음 3개" in out and "순서: 섞임" in out, out)

    print("\n=> 전체: 통과" if not FAILS else "\n=> 실패 %d건: %s" % (len(FAILS), ", ".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
