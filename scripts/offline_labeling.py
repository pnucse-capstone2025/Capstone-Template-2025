#!/usr/bin/env python3
import sys
import os
import csv
import pickle
import numpy as np
import torch
import torch.nn as nn
from collections import defaultdict, deque
import argparse
import math

def open_csv_for_read(path):
    """Universal newlines: '\r\n','\r','\n' 모두 '\n'으로 읽음."""
    return open(path, 'r', encoding='utf-8', newline=None)

def open_csv_for_write(path):
    """Always write with Unix LF only."""
    return open(path, 'w', encoding='utf-8', newline='\n')

class StackedLSTMClassifier(nn.Module):
    """my_ssd_ttl_pipeline.py와 동일한 LSTM 구조"""
    def __init__(self, input_dim=4, hidden_dim1=64, hidden_dim2=16, num_classes=4, dropout_rate=0.2):
        super().__init__()
        self.lstm1 = nn.LSTM(input_dim, hidden_dim1, batch_first=True)
        self.lstm2 = nn.LSTM(hidden_dim1, hidden_dim2, batch_first=True)
        self.dropout = nn.Dropout(dropout_rate)
        self.fc = nn.Linear(hidden_dim2, num_classes)

    def forward(self, x):
        out1, _ = self.lstm1(x)
        out2, _ = self.lstm2(out1)
        out = out2[:, -1, :]
        out = self.dropout(out)
        return self.fc(out)

def offline_labeling(page_split_file, model_file, scaler_file, output_file):
    seq_len, feat_dim = 2, 4
    print("오프라인 라벨링 시작")
    print(f"   입력     : {page_split_file}")
    print(f"   모델     : {model_file}")
    print(f"   스케일러 : {scaler_file}")
    print(f"   출력     : {output_file}")
    print(f"   설정된 LSTM 시퀀스 길이: {seq_len}")

    scaler = None
    if os.path.exists(scaler_file):
        with open(scaler_file, 'rb') as f:
            scaler = pickle.load(f)
        print("   - 스케일러 로드 완료")
    else:
        print(f"오류: 스케일러 파일 없음 - {scaler_file}")
        sys.exit(1)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = StackedLSTMClassifier(input_dim=feat_dim, dropout_rate=0.2)
    model.load_state_dict(torch.load(model_file, map_location=device))
    model.to(device).eval()
    print(f"   - 모델 로드 완료 (device={device})")

    page_traces = []
    try:
        with open_csv_for_read(page_split_file) as fin:
            reader = csv.reader(fin, delimiter=' ')
            header = next(reader, None)
            for row in reader:
                if len(row) < 10:
                    continue
                fields = [f.strip() for f in row]
                device_id, cpu, seq, ts, pid, act, op, sec, plus, size = fields[:10]
                initial_hotness = -1 if op == 'R' else 0
                page_traces.append({
                    'device': device_id, 'cpu': cpu, 'seq': seq, 'timestamp': float(ts),
                    'pid': pid, 'action': act, 'op': op, 'sector': int(sec),
                    'plus': plus, 'size': int(size), 'access_op': 1 if op == 'R' else 0,
                    'hotness': initial_hotness, 'orig_idx': len(page_traces)
                })
    except UnicodeDecodeError as e:
        print(f"인코딩 오류: {e}")
        return False
    except FileNotFoundError:
        print(f"오류: 파일을 찾을 수 없습니다 – {page_split_file}")
        return False

    print(f"   - 페이지 접근 {len(page_traces):,} 건 로드 완료")

    # 학습 데이터 생성 코드와 동일한 구조로 변경 (maxlen=seq_len + 1)
    page_info = defaultdict(lambda: {
        'access_count': 0, 'time_gap_sum': 0.0, 'time_gap_sq_sum': 0.0,
        'request_size_sum': 0.0, 'last_access_time': 0.0, 'last_lifetime': 0.0,
        'history_features': deque(maxlen=seq_len + 1)
    })

    # 쓰기 요청만 필터링하여 타임스탬프 순으로 정렬
    writes = sorted([t for t in page_traces if t['access_op'] == 0], key=lambda x: x['timestamp'])
    
    labeled_cnt = 0

    for idx, tr in enumerate(writes, 1):
        sec, ts, pg_sz = tr['sector'], tr['timestamp'], tr['size']
        info = page_info[sec]
        
        gap = 0.0
        if info['access_count'] > 0:
            gap = ts - info['last_access_time']
            info['time_gap_sum'] += gap
            info['time_gap_sq_sum'] += gap ** 2
        
        info['access_count'] += 1
        info['request_size_sum'] += pg_sz
        info['last_access_time'] = ts
        info['last_lifetime'] = gap
        
        # 각 접근 시점의 특징 스냅샷을 계산
        features = [
            info['time_gap_sum'] / info['access_count'] if info['access_count'] > 1 else 0.0,
            # 학습 코드와 동일하게 표준편차 계산 로직 및 음수 방지 로직 적용
            math.sqrt(info['time_gap_sq_sum'] / (info['access_count'] - 1) - (info['time_gap_sum'] / (info['access_count'] - 1))**2) if info['access_count'] > 1 else 0.0,
            info['request_size_sum'] / info['access_count'],
            info['last_lifetime']
        ]
        
        # 표준편차 음수 방지
        if features[1] < 0:
            features[1] = 0
            
        # history_features deque에 현재 특징을 추가
        info['history_features'].append(features)

        # 학습에 필요한 시퀀스가 완성되면 라벨링 수행 (deque 길이가 seq_len + 1)
        if len(info['history_features']) == seq_len + 1:
            # deque에서 시퀀스 데이터만 추출 (마지막 데이터는 제외)
            seq_feats = list(info['history_features'])[:-1]
            arr = np.array(seq_feats).reshape(1, seq_len, feat_dim)
            
            # 스케일링
            if scaler is not None:
                arr_flat = arr.reshape(-1, feat_dim)
                arr_scaled_flat = scaler.transform(arr_flat)
                arr = arr_scaled_flat.reshape(1, seq_len, feat_dim)
            
            with torch.no_grad():
                inp = torch.from_numpy(arr).to(device).float()
                pred = model(inp).argmax(1).item()
            
            # 라벨링 결과 저장
            tr['hotness'] = pred
            labeled_cnt += 1
        else:
            # 시퀀스 길이가 부족하면 라벨링 불가능, 하지만 0으로 설정
            tr['hotness'] = 0

        if idx % 10000 == 0:
            print(f"   진행 {idx:,}/{len(writes):,} (라벨 {labeled_cnt:,})")

    print(f"   - 라벨링 완료: {labeled_cnt:,} 개 쓰기 요청 라벨 부여")

    # 원본 순서대로 정렬하여 출력 파일에 저장
    page_traces.sort(key=lambda x: x['orig_idx'])
    with open_csv_for_write(output_file) as fout:
        writer = csv.writer(fout, delimiter=' ', quoting=csv.QUOTE_NONE, escapechar='\\', lineterminator='\n')
        writer.writerow(header + ['Hotness_Label'])
        for t in page_traces:
            writer.writerow([
                t['device'], t['cpu'], t['seq'], f"{t['timestamp']:.9f}",
                t['pid'], t['action'], t['op'], t['sector'], t['plus'],
                t['size'], t['hotness']
            ])
    print(f"   - 라벨 포함 트레이스 저장 완료: {output_file}")

    dist = defaultdict(int)
    for t in page_traces:
        dist[t['hotness']] += 1
    print("\n라벨 분포")
    print(f"   읽기(-1): {dist[-1]:,}")
    for lvl in range(4):
        print(f"   레벨 {lvl}: {dist[lvl]:,}")

    return True

def main():
    parser = argparse.ArgumentParser(description='Offline Hotness Labeling for SSD Traces.')
    parser.add_argument('page_split_file', type=str,
                        help='Path to the input page-split CSV trace file (e.g., simplessd_page_split.csv).')
    parser.add_argument('model_file', type=str,
                        help='Path to the trained PyTorch LSTM model file (e.g., ssd_ttl_model.pth).')
    parser.add_argument('--scaler_file', type=str, default='scaler.pkl',
                        help='Path to the scaler.pkl file for data normalization.')
    parser.add_argument('output_file', type=str,
                        help='Path to the output CSV file with hotness labels (e.g., simplessd_labeled_trace.csv).')
    
    args = parser.parse_args()

    if not os.path.exists(args.page_split_file):
        print(f"오류: 입력 파일 없음 – {args.page_split_file}")
        sys.exit(1)
    if not os.path.exists(args.model_file):
        print(f"오류: 모델 파일 없음 – {args.model_file}")
        sys.exit(1)
    if not os.path.exists(args.scaler_file):
        print(f"오류: 스케일러 파일 없음 – {args.scaler_file}")
        print("모델 학습 시 정규화를 사용했다면, 이 파일이 없으면 라벨링 결과가 부정확합니다.")
        sys.exit(1)

    success = offline_labeling(args.page_split_file, args.model_file, args.scaler_file, args.output_file)
    print("\n완료!" if success else "\n실패!")

if __name__ == "__main__":
    main()
