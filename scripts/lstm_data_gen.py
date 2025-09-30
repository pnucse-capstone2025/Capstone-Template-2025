#!/usr/bin/env python3
import sys
import os
import csv
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict, deque
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import argparse
import pickle
import math
import matplotlib.pyplot as plt
import seaborn as sns

"""
3단계: 페이지별 분할 트레이스 → LSTM 학습 데이터 변환
- 입력 파일명 기반으로 출력 파일명 결정 (확장자 제외한 전체 파일명 사용)
- LSTM 학습에 필요한 시점의 데이터만 해시 테이블에 저장하여 메모리 사용량 최적화
- K-means 클러스터링 결과를 시각화하여 그래프로 출력
"""

def extract_base_name(file_path):
    """입력 파일명에서 확장자 제외한 이름만 추출"""
    return Path(file_path).stem

def open_csv_for_read(path):
    """Universal newlines: CRLF, CR, LF 모두 '\n'으로 읽음."""
    return open(path, 'r', encoding='utf-8', newline=None)

def create_lstm_training_data(input_file, output_dir, base_name, log_file):
    sequence_length = 2
    feature_dim = 4

    if log_file:
        original_stdout = sys.stdout
        sys.stdout = open(log_file, 'w')

    print(f"LSTM 학습 데이터 생성 시작: {input_file}")
    print(f"기본 이름: {base_name}")
    print(f"출력 디렉토리: {output_dir}")
    print(f"설정된 LSTM 시퀀스 길이: {sequence_length}")

    # 1. 페이지 정보 저장소 초기화 (누적 통계치 방식)
    # history_features를 deque로 변경하여 메모리 사용량을 최적화
    page_info = defaultdict(lambda: {
        'access_count': 0,
        'time_gap_sum': 0.0,
        'time_gap_sq_sum': 0.0,  # 표준편차 계산을 위한 제곱 합
        'request_size_sum': 0.0,
        'last_access_time': 0.0,
        'last_lifetime': 0.0,
        # history_features를 deque로 변경하여 최근 시점만 저장
        'history_features': deque(maxlen=sequence_length + 1)
    })

    total_read_requests = 0
    total_write_requests = 0
    
    # 3. K-means 및 LSTM 학습용 데이터 구성 (파일을 읽는 과정에서 바로 생성)
    X, y_raw = [], []

    # 2. 입력 파일 처리
    processed_lines = 0
    try:
        with open_csv_for_read(input_file) as fin:
            reader = csv.reader(fin, delimiter=' ')
            next(reader, None)  # 헤더 스킵

            for row in reader:
                processed_lines += 1
                if processed_lines % 100000 == 0:
                    print(f"처리된 라인 수: {processed_lines:,}")

                if len(row) < 10:
                    continue
                try:
                    sector = int(row[7].strip())
                    timestamp = float(row[3].strip())
                    op = row[6].strip()
                    page_size = int(row[9].strip())

                    if op == 'W':
                        total_write_requests += 1
                        info = page_info[sector]
                        gap = 0.0
                        
                        if info['access_count'] > 0:
                            gap = timestamp - info['last_access_time']
                            info['time_gap_sum'] += gap
                            info['time_gap_sq_sum'] += gap ** 2
                            
                        info['access_count'] += 1
                        info['request_size_sum'] += page_size
                        info['last_access_time'] = timestamp
                        info['last_lifetime'] = gap
                        
                        # 각 접근 시점의 특징 스냅샷을 계산
                        features = [
                            info['time_gap_sum'] / info['access_count'] if info['access_count'] > 1 else 0.0,
                            math.sqrt(info['time_gap_sq_sum'] / (info['access_count'] - 1) - (info['time_gap_sum'] / (info['access_count'] - 1))**2) if info['access_count'] > 1 else 0.0,
                            info['request_size_sum'] / info['access_count'],
                            info['last_lifetime']
                        ]
                        # 음수 방지
                        if features[1] < 0:
                            features[1] = 0
                            
                        # history_features deque에 현재 특징을 추가
                        info['history_features'].append(features)

                        # 학습에 필요한 시퀀스가 완성되면 X와 y_raw에 추가
                        # 최소 3회 접근 (sequence_length + 1)이 필요함
                        if len(info['history_features']) == sequence_length + 1:
                            seq_feats = list(info['history_features'])[:-1]
                            label_feat = info['history_features'][-1]
                            X.append(seq_feats)
                            y_raw.append(label_feat)
                    
                    elif op == 'R':
                        total_read_requests += 1

                except (ValueError, IndexError):
                    continue

        print(f"\n총 처리된 라인 수: {processed_lines:,}")
        print(f"고유 페이지 수: {len(page_info):,}")

    except FileNotFoundError:
        print(f"오류: 입력 파일 '{input_file}' 없음")
        if log_file:
            sys.stdout.close()
            sys.stdout = original_stdout
        return False
    
    print("\n=== 페이지 요청 읽기/쓰기 통계 ===")
    print(f"총 읽기 요청: {total_read_requests:,} 개")
    print(f"총 쓰기 요청: {total_write_requests:,} 개")
    if (total_read_requests + total_write_requests) > 0:
        read_ratio = (total_read_requests / (total_read_requests + total_write_requests)) * 100
        write_ratio = (total_write_requests / (total_read_requests + total_write_requests)) * 100
        print(f"읽기 요청 비율: {read_ratio:.2f}%")
        print(f"쓰기 요청 비율: {write_ratio:.2f}%")
    else:
        print("총 요청이 없어 비율을 계산할 수 없습니다.")

    print(f"\n생성된 LSTM 시퀀스 수: {len(X):,}")
    print(f"클러스터링용 다차원 데이터 수: {len(y_raw):,}")

    if not X or not y_raw:
        print("오류: LSTM 학습 시퀀스가 생성되지 않았습니다. 필터링 조건을 확인하세요.")
        if log_file:
            sys.stdout.close()
            sys.stdout = original_stdout
        return False

    # 4. 다차원 K-means 클러스터링
    y_raw_np = np.array(y_raw)
    scaler_y = StandardScaler()
    scaled_y_raw = scaler_y.fit_transform(y_raw_np)

    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    y_labels = kmeans.fit_predict(scaled_y_raw)

    # 5. 데이터 스케일링 및 저장
    X = np.array(X)
    samples = X.shape[0]
    X_flat = X.reshape(-1, feature_dim)
    scaler_X = StandardScaler()
    X_scaled_flat = scaler_X.fit_transform(X_flat)
    X_scaled = X_scaled_flat.reshape(samples, sequence_length, feature_dim)

    scaler_output_path = os.path.join(output_dir, f'scaler_{base_name}.pkl')
    with open(scaler_output_path, 'wb') as f:
        pickle.dump(scaler_X, f)
    print(f"- {scaler_output_path} 저장 완료")

    x_output_path = os.path.join(output_dir, f'X_{base_name}.npy')
    y_output_path = os.path.join(output_dir, f'y_{base_name}.npy')
    cluster_output_path = os.path.join(output_dir, f'cluster_centers_{base_name}.csv')

    np.save(x_output_path, X_scaled)
    np.save(y_output_path, y_labels)

    # 6. 클러스터 센터 저장 (4차원 특성을 역변환)
    centers = scaler_y.inverse_transform(kmeans.cluster_centers_)
    center_df = pd.DataFrame(centers, columns=['Mean(Time-gap)', 'Std.dev(Time-gap)', 'Mean(Request-size)', 'Last(Time-gap)'])
    center_df.to_csv(cluster_output_path, index=False, lineterminator='\n')
    
    # 7. 통계 출력
    unique_labels, counts = np.unique(y_labels, return_counts=True)
    print(f"\n=== 생성 완료 =====")
    print(f"- {x_output_path}")
    print(f"  Shape: {X_scaled.shape}")
    print(f"- {y_output_path}")
    print(f"  Length: {len(y_labels)}")
    print(f"- {cluster_output_path}")
    print("  클러스터 센터:")
    print(center_df)

    print(f"\n=== Hotness 레벨 분포 (총 쓰기 요청: {total_write_requests:,} 개) ===")
    hotness_labels = ['Cold(0)', 'Medium(1)', 'Warm(2)', 'Hot(3)']
    sorted_labels = np.sort(unique_labels)
    for label in sorted_labels:
        idx = np.where(unique_labels == label)[0][0]
        count = counts[idx]
        percentage = (count / len(y_labels)) * 100
        print(f"{hotness_labels[label]}: {count:,} ({percentage:.1f}%)")

    # --- 그래프 생성 및 저장 ---
    scaled_y_df = pd.DataFrame(scaled_y_raw, columns=['time_gap_avg', 'time_gap_std', 'size_avg', 'last_lifetime'])
    scaled_y_df['cluster'] = y_labels
    
    # K-means clustering 결과 그래프
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    features = ['time_gap_avg', 'time_gap_std', 'size_avg', 'last_lifetime']
    for i, feature in enumerate(features):
        sns.scatterplot(x=scaled_y_df[feature], y=scaled_y_df['cluster'], ax=axes[i], palette='viridis', legend=False)
        axes[i].set_xlabel(feature)
        axes[i].set_ylabel('cluster' if i == 0 else '')
        axes[i].set_yticks(np.arange(4))
    fig.suptitle('K-means clustering hotness distribution graph')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    graph_output_path = os.path.join(output_dir, f'cluster_hotness_distribution_{base_name}.png')
    plt.savefig(graph_output_path)
    print(f"- {graph_output_path} 저장 완료")

    if log_file:
        sys.stdout.close()
        sys.stdout = original_stdout

    return True


def main():
    parser = argparse.ArgumentParser(description="LSTM 학습 데이터 생성 및 클러스터링.")
    parser.add_argument("--input_file", type=str, required=True,
                        help="입력 CSV 파일의 경로.")
    parser.add_argument("--output_dir", type=str, default=str(Path.home() / "ssd_project" / "data" / "npy"),
                        help="생성된 .npy 및 .csv 파일이 저장될 출력 디렉토리.")
    parser.add_argument("--log_dir", type=str, default=str(Path.home() / "ssd_project" / "logs"),
                        help="로그 파일이 저장될 디렉토리.")
    parser.add_argument("--log_name", type=str,
                        help="로그 파일의 이름 (예: sa00_model.txt). 이 인자가 주어지면 모든 콘솔 출력이 해당 파일로 리다이렉트됩니다.")

    args = parser.parse_args()

    input_file = args.input_file
    output_dir = Path(args.output_dir)
    log_dir = Path(args.log_dir)
    log_file_name = args.log_name

    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    base_name = extract_base_name(input_file)

    log_full_path = None
    if log_file_name:
        log_full_path = str(log_dir / log_file_name)

    if not os.path.exists(input_file):
        print(f"오류: 입력 파일 '{input_file}'을 찾을 수 없습니다.")
        return

    print(f"입력 파일: {input_file}")
    print(f"기본 이름: {base_name}")
    print(f"출력 디렉토리: {output_dir}")
    if log_full_path:
        print(f"로그 파일 경로: {log_full_path}")

    success = create_lstm_training_data(input_file, str(output_dir), base_name, log_full_path)

    if success:
        print(f"\n완료: LSTM 학습 데이터 생성 성공!")
        print(f"{base_name}의 npy 파일들이 생성되었습니다.")
    else:
        print(f"\n실패: LSTM 학습 데이터 생성 실패")


if __name__ == "__main__":
    main()
