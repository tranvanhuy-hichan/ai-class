"""Dọn bộ dữ liệu YOLO đã gộp: bỏ ảnh trùng, ảnh rò rỉ giữa các tập, khung quá nhỏ.

  python scripts/clean_dataset.py --data data/behavior_all            # chỉ báo cáo, không xóa gì
  python scripts/clean_dataset.py --data data/behavior_all --apply    # xóa thật

Quy tắc (duyệt theo thứ tự train, val, test; giữ ảnh gặp trước):
  1. Ảnh giống hệt hoặc gần giống (dHash khác <= --hamming bit) với một ảnh đã giữ -> xóa.
     Vì train được duyệt trước nên ảnh val/test giống ảnh train bị xóa (hết "rò rỉ" làm điểm đo cao ảo).
  2. Khung có diện tích < --min-area (tỉ lệ so với ảnh) bị bỏ khỏi file nhãn.
  3. Ảnh vốn có khung nhưng sau bước 2 hết khung -> xóa (ảnh nền "smoke_" không có khung từ đầu thì giữ).
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

SPLITS = ("train", "val", "test")


POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def dhash(path):
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if g is None:
        return None
    g = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int(np.packbits(bits).view(">u8")[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/behavior_all")
    ap.add_argument("--hamming", type=int, default=4)
    ap.add_argument("--min-area", type=float, default=0.0002)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    root = Path(a.data)

    n_total = sum(1 for sp in SPLITS for _ in (root / sp / "images").iterdir())
    kept, n_kept = np.zeros(n_total, dtype=np.uint64), 0
    drop, report = [], {s: {"giu": 0, "trung": 0, "mat_khung": 0, "khung_nho": 0, "anh_loi": 0} for s in SPLITS}
    new_labels = {}
    for sp in SPLITS:
        for img in sorted((root / sp / "images").iterdir()):
            lab = root / sp / "labels" / (img.stem + ".txt")
            h = dhash(img)
            if h is None:
                drop.append((img, lab)); report[sp]["anh_loi"] += 1
                continue
            if n_kept:
                diff = (kept[:n_kept] ^ np.uint64(h)).view(np.uint8)   # số bit khác nhau, tính một lượt bằng numpy
                if POPCOUNT[diff].reshape(-1, 8).sum(axis=1).min() <= a.hamming:
                    drop.append((img, lab)); report[sp]["trung"] += 1
                    continue
            lines = lab.read_text().splitlines() if lab.exists() else []
            good = [ln for ln in lines if len(ln.split()) == 5
                    and float(ln.split()[3]) * float(ln.split()[4]) >= a.min_area]
            report[sp]["khung_nho"] += len(lines) - len(good)
            if lines and not good:
                drop.append((img, lab)); report[sp]["mat_khung"] += 1
                continue
            if len(good) != len(lines):
                new_labels[lab] = good
            kept[n_kept] = np.uint64(h)
            n_kept += 1
            report[sp]["giu"] += 1

    for sp, r in report.items():
        print(f"{sp:5s} giữ {r['giu']:5d} | xóa trùng/rò rỉ {r['trung']:4d} | xóa vì hết khung {r['mat_khung']:3d} "
              f"| ảnh lỗi {r['anh_loi']} | khung nhỏ bỏ {r['khung_nho']}")
    if not a.apply:
        print("Chạy thử, chưa xóa gì. Thêm --apply để xóa thật.")
        return
    for img, lab in drop:
        img.unlink()
        lab.unlink(missing_ok=True)
    for lab, lines in new_labels.items():
        lab.write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"Đã xóa {len(drop)} ảnh, sửa {len(new_labels)} file nhãn.")


if __name__ == "__main__":
    main()
