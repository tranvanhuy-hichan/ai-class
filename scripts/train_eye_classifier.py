"""Huấn luyện mô hình phân loại mắt MỞ / NHẮM (YOLO11-cls).

  python scripts/train_eye_classifier.py --epochs 20
Kết quả được chép ra weights/eye_cls.pt -> app.py tự dùng ở lần chạy sau.
Máy không có GPU vẫn chạy được (ảnh nhỏ 64x64), mất khoảng 15-40 phút.
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/eyes")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--device", default="", help='"" tự chọn, "cpu" hoặc "0"')
    a = ap.parse_args()

    model = YOLO("yolo11n-cls.pt")
    model.train(data=str(Path(a.data).resolve()), epochs=a.epochs, imgsz=64, batch=a.batch,
                device=a.device or None, project=str(ROOT / "runs"), name="eye_cls", exist_ok=True,
                hsv_s=0.0, fliplr=0.5)  # ảnh đã được chuyển sang ảnh xám
    metrics = model.val(project=str(ROOT / "runs"), name="eye_cls_val", exist_ok=True)
    print(f"Độ chính xác trên tập kiểm tra (top-1): {metrics.top1:.2%}")

    best = Path(model.trainer.best)
    (ROOT / "weights").mkdir(exist_ok=True)
    shutil.copy(best, ROOT / "weights/eye_cls.pt")
    print("Đã lưu mô hình: weights/eye_cls.pt")


if __name__ == "__main__":
    main()
