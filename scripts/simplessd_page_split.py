#!/usr/bin/env python3
"""
2_simplessd_page_split.py
SimpleSSD-SA 트레이스를 4 KB(8섹터) 페이지 단위로 분할한다.
사용 예:
    python3 2_simplessd_page_split.py \
        data/processed/groups/group_00_02.csv \
        data/processed/page/group_00_02_page.csv
"""
import argparse
import csv
import os
import sys


def open_csv_for_read(path):
    """Universal newlines: CRLF/CR/LF → LF."""
    return open(path, "r", encoding="utf-8", newline=None)


def open_csv_for_write(path):
    """항상 Unix LF 로 저장, 부모 폴더 자동 생성."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return open(path, "w", encoding="utf-8", newline="\n")


def split_simplessd_to_pages(inp: str, out: str) -> bool:
    SECTORS_PER_PAGE = 8          # 4 KB 페이지 = 8섹터
    total_req = split_cnt = skip_cnt = 0

    print(f"[PAGE-SPLIT] {inp} → {out}")
    try:
        with open_csv_for_read(inp) as fin, open_csv_for_write(out) as fout:
            reader = csv.reader(fin, delimiter=" ")
            writer = csv.writer(
                fout,
                delimiter=" ",
                quoting=csv.QUOTE_NONE,
                escapechar="\\",
                lineterminator="\n",
            )
            # 헤더
            writer.writerow(
                ["Device", "CPU", "Seq", "Timestamp", "PID",
                 "Action", "Op", "Sector", "+", "Size"]
            )

            # 본문
            for ln, row in enumerate(reader, 1):
                if ln == 1:        # 입력 헤더 스킵
                    continue
                if len(row) < 10:
                    skip_cnt += 1
                    continue

                dev, cpu, seq, ts, pid, act, op, sec_s, plus, size_s = (
                    f.strip() for f in row[:10]
                )
                if act != "D" or plus != "+":
                    skip_cnt += 1
                    continue
                try:
                    sector = int(sec_s)
                    io_sz = int(size_s)
                except ValueError:
                    skip_cnt += 1
                    continue

                start_lpn = sector // SECTORS_PER_PAGE
                end_lpn = (sector + io_sz - 1) // SECTORS_PER_PAGE
                total_req += 1

                for lpn in range(start_lpn, end_lpn + 1):
                    page_base = lpn * SECTORS_PER_PAGE
                    offset = sector - page_base if lpn == start_lpn else 0
                    remain = (sector + io_sz) - (page_base + offset)
                    page_sz = min(SECTORS_PER_PAGE - offset, remain)
                    page_sector = page_base + offset

                    writer.writerow(
                        [dev, cpu, seq, ts, pid,
                         act, op, page_sector, "+", page_sz]
                    )
                    split_cnt += 1

                if ln % 100_000 == 0:
                    print(f"  lines: {ln:,}  req: {total_req:,}  pages: {split_cnt:,}")

    except FileNotFoundError:
        print(f"[ERROR] 입력 파일 없음: {inp}")
        return False
    except Exception as e:
        print(f"[ERROR] 분할 중 예외: {e}")
        return False

    print(f"[DONE] 요청 {total_req:,}개 → 페이지 {split_cnt:,}개, 스킵 {skip_cnt:,}")
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Split SimpleSSD-SA trace into 4 KB page-granularity records"
    )
    ap.add_argument("input", help="그룹 CSV 입력 파일")
    ap.add_argument("output", help="분할된 CSV 출력 파일")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        ap.error(f"입력 파일이 존재하지 않습니다: {args.input}")

    success = split_simplessd_to_pages(args.input, args.output)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
