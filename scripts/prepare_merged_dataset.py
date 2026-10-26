"""Gộp các bộ dữ liệu đã tải thành 1 bộ YOLO 3 lớp: phone, sleep, study (khớp custom_class_map).
Thêm --with-smoking để có lớp thứ 4: smoking (mặc định tắt vì hút thuốc thuộc app ngoài sân).

  python scripts/prepare_merged_dataset.py
  python scripts/train_behavior.py --data data/behavior_all/data.yaml --model yolo11m.pt --imgsz 960 --batch 6 \\
         --epochs 50 --name behavior_all

Nguồn:
  student-classroom-activity   phone, sleep, study (giữ nguyên)
  phone-in-hand-detection      phone
  student-behaviour (Burak)    looking at phone -> phone, sleeping -> sleep, listening to lesson -> study
  classroom-cell-phone-detection  phone (camera giám sát lớp, điện thoại nhỏ); bỏ lớp person; miễn dọn trùng (tiền tố cctv_)
  smoking_raw                  chỉ giữ khung điếu thuốc; ảnh uống nước giữ làm ảnh nền
  student-behavior-analysis    Sleeping -> sleep, Reading -> study (các lớp khác bỏ khung)
  student-behaviors (prcv)     Sleeping -> sleep, Focusing -> study; Using Phone -> phone chỉ khi có --prcv-phone
  Hai bộ Roboflow này đã được nhân 3 bằng augmentation nên rất nhiều ảnh gần giống nhau: luôn chạy clean_dataset.py sau khi gộp.
  Lưu ý: "Using Phone" của prcv khoanh cả NGƯỜI đang dùng điện thoại, không khoanh riêng cái điện thoại.
Không dùng SCB BowHead: "cúi đầu" của SCB gồm cả cúi viết/đọc bài, sẽ khiến mô hình báo gục đầu cho bạn đang viết.
"""
import argparse
import shutil

from prepare_smoking_dataset import CLASSIFY, ROOT, copy_set


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", default="data/behavior_all")
    ap.add_argument("--smoking", default="data/nguon/smoking_raw/smoking-and-drinking-dataset-for-yolo/Dataset")
    ap.add_argument("--with-smoking", action="store_true", help="thêm ảnh hút thuốc (lớp smoking)")
    ap.add_argument("--prcv-phone", action="store_true",
                    help="giữ nhãn 'Using Phone' của prcv (khoanh cả NGƯỜI); mặc định bỏ vì lẫn với nhãn khoanh vật điện thoại")
    a = ap.parse_args()
    classes = CLASSIFY if a.with_smoking else CLASSIFY[:3]
    dst = ROOT / a.dst
    if dst.exists():
        shutil.rmtree(dst)
    print("Gộp dữ liệu ->", dst)
    copy_set(ROOT / "data/nguon/student-classroom-activity", dst, "class", lambda c: c)
    copy_set(ROOT / "data/nguon/phone-in-hand-detection", dst, "phonehand", lambda c: 0)
    # student-behaviour: 0 doesn't listen, 1 listening, 2 looking at phone, 3 sleeping
    copy_set(ROOT / "data/nguon/student-behaviour", dst, "burak", {1: 2, 2: 0, 3: 1}.get)
    # student-behavior-analysis: 0 Looking Forward, 1 Raising Hand, 2 Reading, 3 Sleeping, 4 Turning Around
    # Các ảnh còn lại (giơ tay, nhìn thẳng, quay đầu) không có điện thoại hay nằm gục nên là ảnh nền hợp lệ, chỉ giữ một ít
    copy_set(ROOT / "data/nguon/student-behavior-analysis-a6nde", dst, "sba", {2: 2, 3: 1}.get, max_empty=300)
    # student-behaviors: 0 Distracting, 1 Focusing, 2 Hand Raising, 3 Sleeping, 4 Using Phone, 5 Walking
    prcv_map = {1: 2, 3: 1, **({4: 0} if a.prcv_phone else {})}
    # Bỏ hẳn ảnh có Distracting (hay kèm điện thoại) và, nếu không giữ nhãn điện thoại, cả ảnh có Using Phone
    prcv_skip = {0} if a.prcv_phone else {0, 4}
    copy_set(ROOT / "data/nguon/student-behaviors", dst, "prcv", prcv_map.get, skip_classes=prcv_skip, max_empty=0)
    # Camera giám sát lớp học từ góc cao, điện thoại rất nhỏ (lớp 0 = cell-phones, lớp 1 = person bỏ). Đúng kiểu camera xa của bài toán
    copy_set(ROOT / "data/nguon/classroom-cell-phone-detection", dst, "cctv", {0: 0}.get, max_empty=0)
    if a.with_smoking:
        copy_set(ROOT / a.smoking, dst, "smoke", lambda c: 3 if c == 1 else None)
    (dst / "data.yaml").write_text(
        f"path: {dst}\ntrain: train/images\nval: val/images\ntest: test/images\n"
        f"nc: {len(classes)}\nnames: {classes}\n", encoding="utf-8")
    print("Xong. Các lớp:", classes)


if __name__ == "__main__":
    main()
