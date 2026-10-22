"""Gom ảnh mắt thành cấu trúc mà YOLO-classify cần:

  data/eyes/train/open/*.jpg   data/eyes/train/closed/*.jpg
  data/eyes/val/open/*.jpg     data/eyes/val/closed/*.jpg

Tự tìm mọi thư mục tên "Open"/"Closed" (không phân biệt hoa thường) bên trong --src,
nên dùng được cho bộ Kaggle yawn-eye-dataset-new, MRL Eye Dataset (sau khi chia
thư mục) hoặc ảnh bạn tự chụp. Ảnh được chuyển sang ảnh xám.
"""
import argparse
import random
import shutil
from pathlib import Path

import cv2

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
CLASSES = {"open": "open", "open_eyes": "open", "closed": "closed", "close": "closed", "closed_eyes": "closed"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", default="data/eyes")
    ap.add_argument("--val", type=float, default=0.2, help="Tỉ lệ ảnh dùng để kiểm tra")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-lowres", dest="lowres", action="store_false", help="Không thêm ảnh làm mờ")
    a = ap.parse_args()

    images = {"open": [], "closed": []}
    for d in Path(a.src).rglob("*"):
        if d.is_dir() and d.name.lower() in CLASSES:
            images[CLASSES[d.name.lower()]] += [f for f in d.iterdir() if f.suffix.lower() in IMG_EXT]

    dst = Path(a.dst)
    if dst.exists():
        shutil.rmtree(dst)
    random.seed(a.seed)
    for cls, files in images.items():
        if not files:
            raise SystemExit(f"Không tìm thấy ảnh lớp '{cls}' trong {a.src}")
        random.shuffle(files)
        n_val = int(len(files) * a.val)
        for i, f in enumerate(files):
            split = "val" if i < n_val else "train"
            out = dst / split / cls
            out.mkdir(parents=True, exist_ok=True)
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)  # ảnh xám, giống lúc chạy thật
            if img is None:
                continue
            cv2.imwrite(str(out / f"{i:06d}.jpg"), img)
            if split == "train" and a.lowres:
                # Thêm 1 bản bị làm mờ: thu nhỏ còn 16-40px rồi phóng to lại,
                # giống ảnh mắt cắt ra từ webcam ở xa
                s = random.randint(16, 40)
                small = cv2.resize(img, (s, s), interpolation=cv2.INTER_AREA)
                cv2.imwrite(str(out / f"{i:06d}_lr.jpg"), cv2.resize(small, img.shape[::-1]))
        print(f"{cls}: {len(files) - n_val} ảnh train (+ bản làm mờ), {n_val} ảnh val")
    print(f"Xong -> {dst}. Bước tiếp theo: python scripts/train_eye_classifier.py")


if __name__ == "__main__":
    main()
