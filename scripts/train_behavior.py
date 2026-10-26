"""Huấn luyện mô hình phát hiện hành vi (YOLO11 detect) trên bộ dữ liệu định dạng YOLO
(Roboflow, SCB-Dataset, hoặc ảnh lớp học tự gán nhãn).

  python scripts/train_behavior.py --data data/student-behaviour/data.yaml --epochs 50

Sau khi xong:
  1. Mô hình được chép ra weights/behavior.pt
  2. Trong config.yaml đặt  models.custom_behavior: weights/behavior.pt
  3. Kiểm tra custom_class_map khớp tên lớp in ra bên dưới.
Nên có GPU (Google Colab miễn phí cũng được). Máy chỉ có CPU: giảm --epochs, --imgsz 416.
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Đường dẫn file data.yaml")
    ap.add_argument("--model", default="yolo11n.pt", help="yolo11n.pt (nhanh) hoặc yolo11s.pt (chính xác hơn)")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="")
    ap.add_argument("--name", default="behavior", help="Tên thư mục kết quả trong runs/")
    ap.add_argument("--no-install", action="store_true", help="Không chép kết quả đè lên weights/behavior.pt")
    a = ap.parse_args()

    model_path = a.model
    if not Path(model_path).exists() and (ROOT / "weights" / a.model).exists():
        model_path = str(ROOT / "weights" / a.model)

    model = YOLO(model_path)
    model.train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, device=a.device or None,
                project=str(ROOT / "runs"), name=a.name, exist_ok=True)
    m = model.val(project=str(ROOT / "runs"), name=a.name + "_val", exist_ok=True)
    print(f"\nmAP50 = {m.box.map50:.3f} | mAP50-95 = {m.box.map:.3f}")
    print("Các lớp của mô hình:", model.names)
    print("Biểu đồ kết quả (đưa vào báo cáo KHKT): runs/<--name>/ (results.png, confusion_matrix.png, ...)")

    if a.no_install:
        print(f"Mô hình tốt nhất: {model.trainer.best} (chưa chép vào weights/)")
        return
    (ROOT / "weights").mkdir(exist_ok=True)
    shutil.copy(model.trainer.best, ROOT / "weights/behavior.pt")
    print("Đã lưu mô hình: weights/behavior.pt")


if __name__ == "__main__":
    main()
