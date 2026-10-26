"""Gộp dữ liệu hút thuốc với dữ liệu hành vi lớp học thành 1 bộ YOLO 4 lớp: phone, sleep, study, smoking.

  python scripts/download_datasets.py smoking
  python scripts/prepare_smoking_dataset.py
  python scripts/train_behavior.py --data data/behavior_smoking/data.yaml --model weights/behavior.pt \\
         --imgsz 960 --batch 6 --epochs 60 --name behavior_smoking --no-install

- Bộ hút thuốc gốc có 2 lớp (drinking, smoking). Chỉ giữ khung "smoking" (điếu thuốc), bỏ khung "drinking".
  Ảnh uống nước vẫn được giữ làm ảnh nền (không có khung) để mô hình không nhầm cốc/chai với điếu thuốc.
- Bộ lớp học (student-classroom-activity) giữ nguyên 3 lớp phone, sleep, study.
"""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSIFY = ["phone", "sleep", "study", "smoking"]
SPLITS = {"train": "train", "valid": "val", "test": "test"}
IMG_EXT = {".jpg", ".jpeg", ".png"}


def copy_set(src, dst, prefix, remap):
    """remap: hàm (lớp gốc) -> lớp mới hoặc None (bỏ khung)."""
    n_img = n_box = 0
    for sp_src, sp_dst in SPLITS.items():
        img_dir = src / sp_src / "images"
        if not img_dir.exists():
            continue
        (dst / sp_dst / "images").mkdir(parents=True, exist_ok=True)
        (dst / sp_dst / "labels").mkdir(parents=True, exist_ok=True)
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() not in IMG_EXT:
                continue
            lines = []
            lab = src / sp_src / "labels" / (img.stem + ".txt")
            if lab.exists():
                for ln in lab.read_text().splitlines():
                    parts = ln.split()
                    if len(parts) < 5:
                        continue
                    new = remap(int(parts[0]))
                    if new is not None:
                        lines.append(" ".join([str(new)] + parts[1:]))
            name = f"{prefix}_{img.name}"
            shutil.copy(img, dst / sp_dst / "images" / name)
            (dst / sp_dst / "labels" / (Path(name).stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
            n_img += 1
            n_box += len(lines)
    print(f"  {prefix}: {n_img} ảnh, {n_box} khung")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classroom", default="data/student-classroom-activity")
    ap.add_argument("--smoking", default="data/smoking_raw/smoking-and-drinking-dataset-for-yolo/Dataset")
    ap.add_argument("--dst", default="data/behavior_smoking")
    a = ap.parse_args()
    dst = ROOT / a.dst
    if dst.exists():
        shutil.rmtree(dst)
    print("Gộp dữ liệu ->", dst)
    copy_set(ROOT / a.classroom, dst, "class", lambda c: c)
    copy_set(ROOT / a.smoking, dst, "smoke", lambda c: 3 if c == 1 else None)   # 1 = smoking, 0 = drinking
    (dst / "data.yaml").write_text(
        f"path: {dst}\ntrain: train/images\nval: val/images\ntest: test/images\n"
        f"nc: {len(CLASSIFY)}\nnames: {CLASSIFY}\n", encoding="utf-8")
    print("Xong. Các lớp:", CLASSIFY)


if __name__ == "__main__":
    main()
