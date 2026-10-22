"""Tải các bộ dữ liệu công khai về thư mục data/.

  python scripts/download_datasets.py eyes
      Bộ ảnh mắt mở/nhắm + ngáp (Kaggle: serenaraju/yawn-eye-dataset-new)
      -> dùng để huấn luyện mô hình phân loại mắt (ngủ gật).

  python scripts/download_datasets.py roboflow --api-key XXX \
         --workspace burak-koyfx --project student-behaviour --version 1
      Bộ ảnh hành vi học sinh trong lớp (định dạng YOLO) từ Roboflow Universe.
      Lấy API key miễn phí tại https://app.roboflow.com/settings/api

Bộ SCB-Dataset (lớn nhất về hành vi học sinh: cúi đầu, nằm bò ra bàn, dùng
điện thoại, giơ tay, đọc, viết...) phải tải thủ công theo hướng dẫn tại
https://github.com/Whiffe/SCB-dataset rồi giải nén vào data/scb/.
"""
import argparse
import shutil
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def download_eyes():
    import kagglehub
    path = kagglehub.dataset_download("serenaraju/yawn-eye-dataset-new")
    dst = DATA / "raw_eyes"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(path, dst)
    print(f"Đã tải về: {dst}")
    print("Bước tiếp theo: python scripts/prepare_eye_dataset.py --src data/raw_eyes")


def download_roboflow(a):
    from roboflow import Roboflow
    rf = Roboflow(api_key=a.api_key)
    ds = rf.workspace(a.workspace).project(a.project).version(a.version).download(
        "yolov8", location=str(DATA / a.project))
    print(f"Đã tải về: {ds.location}")
    print(f"Bước tiếp theo: python scripts/train_behavior.py --data {ds.location}/data.yaml")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("eyes")
    r = sub.add_parser("roboflow")
    r.add_argument("--api-key", required=True)
    r.add_argument("--workspace", default="burak-koyfx")
    r.add_argument("--project", default="student-behaviour")
    r.add_argument("--version", type=int, default=1)
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    if a.cmd == "eyes":
        download_eyes()
    else:
        download_roboflow(a)


if __name__ == "__main__":
    main()
