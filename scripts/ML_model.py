#!/usr/bin/env python3
import os
import glob
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.amp import autocast, GradScaler
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_class_weight
from sklearn.model_selection import StratifiedShuffleSplit # StratifiedShuffleSplit 추가
from tqdm import tqdm
import warnings
from pathlib import Path
import argparse

warnings.filterwarnings('ignore')

# ====================== 하이퍼파라미터 ======================
BATCH = 256              # 배치 크기
EPOCHS = 100             # 전체 에폭 수
HIDDEN_DIM1 = 64         # 첫 번째 LSTM 레이어 은닉 노드 수
HIDDEN_DIM2 = 16         # 두 번째 LSTM 레이어 은닉 노드 수
NUM_CLASSES = 4          # Hotness 분류 클래스 수
LEARNING_RATE = 0.001   # 학습률
USE_AMP = True           # AMP (혼합 정밀도) 사용 여부
PATIENCE = 10            # Early Stopping patience 기준
DROPOUT_RATE = 0.2       # 드롭아웃 비율 (과적합 방지용)

# ====================== 기본 출력 디렉토리 ======================
CHECK_DIR = "ckpt_np"    # 체크포인트 임시 저장 폴더
OUT_DIR = "outputs"      # 최종 모델 결과물 임시 저장 폴더

os.makedirs(CHECK_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

# ====================== 최종 모델 저장 디렉토리 ======================
OUTPUT_MODEL_BASE_DIR = "/home/teamssdeep/ssd_project/models"
os.makedirs(OUTPUT_MODEL_BASE_DIR, exist_ok=True)

# ====================== 데이터셋 래퍼 ======================
class NumpyTrace(Dataset):
    """넘파이 형식의 (X, y) 데이터를 PyTorch Dataset으로 래핑"""
    def __init__(self, x, y):
        self.x = torch.tensor(x, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.long)
    def __len__(self):
        return len(self.x)
    def __getitem__(self, i):
        return self.x[i], self.y[i]

# ================= LSTM 분류기(모델 정의) =================
class StackedLSTMClassifier(nn.Module):
    """4→64→16→4 구조의 Stacked-LSTM (드롭아웃 추가)"""
    def __init__(self, input_dim=4, hidden_dim1=HIDDEN_DIM1, hidden_dim2=HIDDEN_DIM2,
                 num_classes=NUM_CLASSES, dropout_rate=DROPOUT_RATE):
        super().__init__()
        self.lstm1 = nn.LSTM(input_dim, hidden_dim1, num_layers=1,
                             batch_first=True)
        self.lstm2 = nn.LSTM(hidden_dim1, hidden_dim2, num_layers=1,
                             batch_first=True)
        self.dropout = nn.Dropout(dropout_rate) # 드롭아웃 레이어 추가
        self.fc = nn.Linear(hidden_dim2, num_classes)
    def forward(self, x):
        out1, _ = self.lstm1(x)
        out2, _ = self.lstm2(out1)
        out = out2[:, -1, :]
        out = self.dropout(out) # 드롭아웃 적용
        out = self.fc(out)
        return out

# ============== 클래스 불균형 가중치 계산 함수 =============
def compute_class_weights(y):
    """클래스별 데이터 수의 불균형을 보정하기 위한 sample weight 계산"""
    unique_classes = np.unique(y)
    weights = compute_class_weight('balanced', classes=unique_classes, y=y)
    class_weights = dict(zip(unique_classes, weights))
    print(f"클래스 가중치: {class_weights}")
    return class_weights

# === 데이터셋 셋 분할 함수 (계층적 샘플링) ===
def split_data_stratified(x, y, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2):
    """
    데이터를 계층적 샘플링을 사용하여 훈련/검증/테스트 셋으로 분할
    기본은 6:2:2 비율. 각 세트에 모든 클래스가 비율에 맞춰 포함되도록 보장함.
    """
    assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6
    
    # 훈련 + 검증 세트와 테스트 세트로 먼저 분할
    split1 = StratifiedShuffleSplit(n_splits=1, test_size=test_ratio, random_state=42)
    for train_val_index, test_index in split1.split(x, y):
        x_train_val, x_test = x[train_val_index], x[test_index]
        y_train_val, y_test = y[train_val_index], y[test_index]
    
    # 훈련 세트와 검증 세트로 다시 분할
    # train_val_size에 대한 검증 세트 비율 계산
    val_size_in_train_val = val_ratio / (train_ratio + val_ratio)
    split2 = StratifiedShuffleSplit(n_splits=1, test_size=val_size_in_train_val, random_state=42)
    for train_index, val_index in split2.split(x_train_val, y_train_val):
        x_train, x_val = x_train_val[train_index], x_train_val[val_index]
        y_train, y_val = y_train_val[train_index], y_train_val[val_index]
    
    print(f"데이터 분할 (계층적 샘플링): 훈련={len(x_train):,}, 검증={len(x_val):,}, 테스트={len(x_test):,}")
    
    return x_train, y_train, x_val, y_val, x_test, y_test


# ================ 모델 평가 함수 =========================
def evaluate_model(model, dataloader, criterion, device, phase="Test"):
    """주어진 데이터셋(phase: train/val/test)에 대해 손실과 정확도 반환"""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    all_predictions = []
    all_labels = []
    with torch.no_grad():
        for x_batch, y_batch in dataloader:
            x_batch, y_batch = x_batch.to(device), y_batch.to(device)
            with autocast(device_type="cuda", enabled=USE_AMP):
                outputs = model(x_batch)
                loss = criterion(outputs, y_batch)
            total_loss += loss.item()
            _, predicted = torch.max(outputs, 1)
            total += y_batch.size(0)
            correct += (predicted == y_batch).sum().item()
            all_predictions.extend(predicted.cpu().numpy())
            all_labels.extend(y_batch.cpu().numpy())
    avg_loss = total_loss / len(dataloader)
    accuracy = 100 * correct / total
    print(f"{phase} 결과: Loss={avg_loss:.4f}, Accuracy={accuracy:.2f}%")
    return avg_loss, accuracy, all_predictions, all_labels

# ============ 체크포인트(임시모델) 저장 및 로드 ===========
def save_ckpt_rot(path: str, epoch: int, step: int, model: nn.Module, scaler: GradScaler):
    """체크포인트를 저장, 최신 3개만 보관 후 나머지 삭제"""
    torch.save({"epoch": epoch, "step": step,
                 "model": model.state_dict(),
                 "scaler": scaler.state_dict()},
                 path)
    ckpts = sorted(glob.glob(f"{CHECK_DIR}/*.pt"), key=os.path.getmtime)
    for f in ckpts[:-3]:
        os.remove(f)

def load_ckpt(path: str, model: nn.Module, scaler: GradScaler):
    ck = torch.load(path, map_location="cpu")
    model.load_state_dict(ck["model"])
    scaler.load_state_dict(ck["scaler"])
    return ck["epoch"], ck["step"]

# ================ 학습 메인 함수 ==========================
def train(x_path: str, y_path: str, model_output_name: str, resume: str = None):
    print("=== SSD 페이지 Hotness 분류 모델 학습 ===")
    
    # --- 데이터 로딩 및 정보 출력 ---
    if not os.path.exists(x_path) or not os.path.exists(y_path):
        print(f"파일을 찾을 수 없습니다: {x_path} 또는 {y_path}")
        return
    x = np.load(x_path)
    y = np.load(y_path)
    print(f"데이터 로드 완료: X={x.shape}, y={y.shape}")
    print(f"입력 시퀀스 길이: {x.shape[1]}, 특성 수: {x.shape[2]}")

    # ===== 하이퍼파라미터 출력 추가 =====
    print(f"\n=== 학습 파라미터 ===")
    print(f"BATCH: {BATCH}")
    print(f"EPOCHS: {EPOCHS}")
    print(f"HIDDEN_DIM1: {HIDDEN_DIM1}")
    print(f"HIDDEN_DIM2: {HIDDEN_DIM2}")
    print(f"NUM_CLASSES: {NUM_CLASSES}")
    print(f"LEARNING_RATE: {LEARNING_RATE}")
    print(f"USE_AMP: {USE_AMP}")
    print(f"PATIENCE: {PATIENCE}")
    print(f"DROPOUT_RATE: {DROPOUT_RATE}")
    print("") # 가독성을 위한 빈 줄 추가
    # ============================================

    unique_labels, counts = np.unique(y, return_counts=True)
    print(f"\n=== 클래스 분포 ===")
    hotness_labels = ['Cold(0)', 'Medium(1)', 'Warm(2)', 'Hot(3)']
    for label, count in zip(unique_labels, counts):
        if label < len(hotness_labels):
            percentage = (count / len(y)) * 100
            print(f"{hotness_labels[label]}: {count:,}개 ({percentage:.1f}%)")
    
    # --- 데이터셋 분할 ---
    # 계층적 샘플링을 사용하는 함수 호출로 변경
    x_train, y_train, x_val, y_val, x_test, y_test = split_data_stratified(x, y, 0.6, 0.2, 0.2)
    
    # 클래스 가중치 계산
    class_weights_dict = compute_class_weights(y_train)
    class_weights = torch.FloatTensor([class_weights_dict.get(i, 1.0) for i in range(NUM_CLASSES)])
    
    # --- 데이터로더 생성 ---
    train_dataset = NumpyTrace(x_train, y_train)
    val_dataset = NumpyTrace(x_val, y_val)
    test_dataset = NumpyTrace(x_test, y_test)
    nw = min(4, os.cpu_count())
    train_loader = DataLoader(train_dataset, batch_size=BATCH, shuffle=True, # 훈련 데이터만 shuffle=True
                              num_workers=nw, pin_memory=True, persistent_workers=nw > 0)
    val_loader = DataLoader(val_dataset, batch_size=BATCH, shuffle=False,
                            num_workers=nw, pin_memory=True, persistent_workers=nw > 0)
    test_loader = DataLoader(test_dataset, batch_size=BATCH, shuffle=False,
                             num_workers=nw, pin_memory=True, persistent_workers=nw > 0)
    
    # --- 모델, 손실함수, 최적화기 설정 ---
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = StackedLSTMClassifier(input_dim=x.shape[2]).to(dev)
    class_weights = class_weights.to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', factor=0.5, patience=5)
    lossf = nn.CrossEntropyLoss(weight=class_weights)
    scaler = GradScaler(enabled=USE_AMP)
    print(f"\n=== 모델 구조 ===")
    print(f"LSTM1: {x.shape[2]} → {HIDDEN_DIM1}")
    print(f"LSTM2: {HIDDEN_DIM1} → {HIDDEN_DIM2}")
    print(f"FC: {HIDDEN_DIM2} → {NUM_CLASSES}")
    print(f"전체 파라미터 수: {sum(p.numel() for p in model.parameters()):,}")
    print(f"Device: {dev}")
    
    # --- 학습/복구 준비 ---
    start_ep, gstep = 1, 0
    if resume and os.path.exists(resume):
        start_ep, gstep = load_ckpt(resume, model, scaler)
        print(f"[RESUME] epoch {start_ep}, step {gstep}")
    best_val_loss = float('inf')
    patience_counter = 0
    
    # ============= 학습 루프 =============
    print(f"\n=== 학습 시작 ===")
    for ep in range(start_ep, EPOCHS + 1):
        model.train()
        total_loss, total, correct = 0, 0, 0
        pbar = tqdm(train_loader, desc=f"Epoch {ep}/{EPOCHS}")
        for batch_idx, (xb, yb) in enumerate(pbar):
            gstep += 1
            xb, yb = xb.to(dev), yb.to(dev)
            opt.zero_grad()
            # AMP(혼합정밀도) 사용
            with autocast(device_type="cuda", enabled=USE_AMP):
                logits = model(xb)
                loss = lossf(logits, yb)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            scaler.step(opt)
            scaler.update()
            total_loss += loss.item() * xb.size(0)
            preds = logits.argmax(dim=1)
            correct += (preds == yb).sum().item()
            total += xb.size(0)
            if batch_idx % 100 == 0:
                acc = correct / total
                pbar.set_postfix(loss=f"{loss.item():.3f}", acc=f"{acc:.3f}",
                                 lr=f"{opt.param_groups[0]['lr']:.6f}")
            if gstep % 5000 == 0:
                fname = f"{CHECK_DIR}/ep{ep}_step{gstep}.pt"
                save_ckpt_rot(fname, ep, gstep, model, scaler)
        train_acc = correct / total
        train_loss = total_loss / total

        # --- 검증 성능 평가 ---
        val_loss, val_acc, _, _ = evaluate_model(model, val_loader, lossf, dev, "Validation")
        scheduler.step(val_loss)
        print(f"Epoch {ep}: Train Loss={train_loss:.4f}, Train Acc={train_acc:.4f}, "
              f"Val Loss={val_loss:.4f}, Val Acc={val_acc:.4f}, "
              f"LR={opt.param_groups[0]['lr']:.6f}")
        # --- Early Stopping ---
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            # 임시 최적 모델 저장 (OUT_DIR에 저장)
            torch.save({
                'model_state_dict': model.state_dict(),
                'epoch': ep,
                'val_loss': val_loss,
                'val_acc': val_acc,
                'input_dim': x.shape[2],
                'hidden_dim1': HIDDEN_DIM1,
                'hidden_dim2': HIDDEN_DIM2,
                'num_classes': NUM_CLASSES
            }, f"{OUT_DIR}/best_ssd_hotness_model.pth")
            print(f"✓ 최적 모델 저장: Val Acc={val_acc:.2f}%")
        else:
            patience_counter += 1
            if patience_counter >= PATIENCE:
                print(f"조기 종료 at epoch {ep} (patience={PATIENCE})")
                break

    # ============= 최종 테스트 평가 및 모델 저장 =============
    print(f"\n=== 최종 테스트 평가 ===")
    # OUT_DIR에 저장된 임시 최적 모델을 로드하여 최종 테스트
    best_model_path = f"{OUT_DIR}/best_ssd_hotness_model.pth"
    if os.path.exists(best_model_path):
        checkpoint = torch.load(best_model_path)
        model.load_state_dict(checkpoint['model_state_dict'])
        print(f"최적 모델 로드 완료 (Epoch {checkpoint['epoch']})")
    else:
        print(f"경고: 최적 모델 체크포인트가 없습니다. 마지막 에폭 모델로 테스트를 진행합니다.")

    test_loss, test_acc, test_predictions, test_labels = evaluate_model(
        model, test_loader, lossf, dev, "Test")
        
    # --- classification_report 호출 ---
    print(f"\n=== 상세 분류 리포트 ===")
    target_names = ['Cold(0)', 'Medium(1)', 'Warm(2)', 'Hot(3)']
    unique_labels = np.unique(test_labels)
    # 실제 테스트 데이터에 존재하는 라벨과 그에 해당하는 이름만 사용
    print(f"테스트 데이터에 존재하는 고유 라벨: {unique_labels}")
    print(f"보고서 생성을 위해 사용된 이름: {[target_names[i] for i in unique_labels]}")
    print(classification_report(test_labels, test_predictions, target_names=[target_names[i] for i in unique_labels], labels=unique_labels))
    print(f"\n=== 혼동 행렬 ===")
    print(confusion_matrix(test_labels, test_predictions, labels=unique_labels))
    # ---------------------------------------------

    # 최종 모델 저장 (OUTPUT_MODEL_BASE_DIR에 저장)
    model_save_path = os.path.join(OUTPUT_MODEL_BASE_DIR, f"{model_output_name}.pth")
    torch.save(model.state_dict(), model_save_path)
    print(f"\n✅ 최종 모델 저장: {model_save_path}")
    print(f"\n🎉 학습 완료!")
    print(f"📊 최종 테스트 정확도: {test_acc:.2f}%")
    print(f"📁 모델 파일: {model_save_path}")
    print(f"📋 모델 구조: 4→64→16→4")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='SSD Hotness Classification Model Training')
    parser.add_argument('--x_path', type=str,
                        default='/home/teamssdeep/ssd_project/data/npy/X_sa00_page.npy',
                        help='Path to the input X_*.npy file.')
    parser.add_argument('--y_path', type=str,
                        default='/home/teamssdeep/ssd_project/data/npy/y_sa00_page.npy',
                        help='Path to the input y_*.npy file.')
    parser.add_argument('--model_name', type=str,
                        default='sa00_model',
                        help='Name for the output model file (without .pth extension).')
    parser.add_argument('--resume', type=str, default=None,
                        help='Path to a checkpoint to resume training from.')
    parser.add_argument('--log_dir', type=str,
                        default='/home/teamssdeep/ssd_project/logs',
                        help='Directory to save log files.')
    parser.add_argument('--log_name', type=str,
                        default='sa00_model.txt',
                        help='Name for the log file.')

    args = parser.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)
    
    print("SSD Hotness 분류 모델 학습을 시작합니다...")
    print("모델 구조: 4→64→16→4")

    train(x_path=args.x_path,
          y_path=args.y_path,
          model_output_name=args.model_name,
          resume=args.resume)
