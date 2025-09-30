#!/usr/bin/env python3
import argparse
import glob
import os
import csv
import sys

def open_csv_for_read(path):
    """Universal newlines: '\r', '\r', '\n' 모두 '\n'으로 읽음."""
    return open(path, 'r', encoding='utf-8', newline=None)

def open_csv_for_write(path):
    """Always write with Unix LF only."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return open(path, 'w', encoding='utf-8', newline='\n')

def normalize_timestamp(ts_str: str) -> str:
    """
    '초.소수부' 형태의 문자열을 9자리 나노초로 패딩해 돌려준다.
    Example: '12.345678' -> '12.345678000'
    """
    ts_str = ts_str.strip()
    if '.' not in ts_str:
        return ts_str + '.000000000'
    sec, frac = ts_str.split('.')
    frac = (frac + '000000000')[:9]
    return f"{sec}.{frac}"

def convert_ycsb_to_simplessd_sa(input_file, output_file):
    """
    YCSB RocksDB SSD 트레이스를 SimpleSSD-SA 형식으로 변환
    """
    DEVICE = '8,0'
    CPU    = '0'
    SEQ    = '0'
    PID    = '0'
    ACTION = 'D'

    converted_count = 0
    skipped_count   = 0

    print(f"[START] {input_file} → {output_file}")
    try:
        with open_csv_for_read(input_file) as fin, open_csv_for_write(output_file) as fout:
            writer = csv.writer(fout, delimiter=' ',
                                quoting=csv.QUOTE_NONE, escapechar='\\',
                                lineterminator='\n')
            writer.writerow(['Device','CPU','Seq','Timestamp','PID','Action','Op','Sector','+','Size'])

            for line_num, line in enumerate(fin, 1):
                line = line.rstrip('\r\n')
                if line.startswith('#') or not line.strip():
                    continue

                parts = [p for p in line.split() if p.strip()]
                if len(parts) < 10:
                    skipped_count += 1
                    continue

                raw_ts     = parts[3]
                trace_act  = parts[5]
                op_type    = parts[6]
                sector_str = parts[7]
                plus_sign  = parts[8]
                size_str   = parts[9]

                if trace_act != 'D' or plus_sign != '+':
                    skipped_count += 1
                    continue

                if op_type.startswith('R'):
                    op_flag = 'R'
                elif op_type.startswith('W'):
                    op_flag = 'W'
                else:
                    skipped_count += 1
                    continue

                try:
                    sector = int(sector_str)
                    size   = int(size_str)
                except ValueError:
                    skipped_count += 1
                    continue

                timestamp = normalize_timestamp(raw_ts)

                writer.writerow([DEVICE, CPU, SEQ, timestamp, PID,
                                 ACTION, op_flag, sector, '+', size])
                converted_count += 1

                if line_num % 1_000_000 == 0:
                    print(f"  lines processed: {line_num:,}, converted: {converted_count:,}")

    except FileNotFoundError:
        print(f"[ERROR] '{input_file}' not found.")
        return False
    except UnicodeDecodeError as e:
        print(f"[ERROR] Encoding error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Conversion failed: {e}")
        return False

    print(f"[DONE] converted {converted_count:,}, skipped {skipped_count:,}")
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Convert YCSB RocksDB SSD trace(s) to SimpleSSD-SA format."
    )
    parser.add_argument("src", help="Input file or directory containing 'ssdtrace-*.csv'")
    parser.add_argument("dst", help="Output file or directory for converted traces")
    args = parser.parse_args()

    if os.path.isdir(args.src):
        # batch mode: process all matching files
        os.makedirs(args.dst, exist_ok=True)
        files = sorted(glob.glob(os.path.join(args.src, "ssdtrace-*")))
        if not files:
            print(f"[ERROR] No files matching 'ssdtrace-*.csv' in {args.src}")
            sys.exit(1)
        for f in files:
            base = os.path.basename(f)
            name = os.path.splitext(base)[0]
            out = os.path.join(args.dst, f"simplessd_sa_{name}.csv")
            success = convert_ycsb_to_simplessd_sa(f, out)
            if not success:
                print(f"[WARN] Conversion failed for {f}")
    else:
        # single-file mode
        out_path = args.dst
        # if dst is directory, place file inside
        if os.path.isdir(out_path):
            base = os.path.basename(args.src)
            name = os.path.splitext(base)[0]
            out_path = os.path.join(out_path, f"simplessd_sa_{name}.csv")
        success = convert_ycsb_to_simplessd_sa(args.src, out_path)
        if not success:
            sys.exit(1)

if __name__ == "__main__":
    main()
