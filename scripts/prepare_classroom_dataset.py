"""Cắt khung hình từ video lớp học của bạn và gán nhãn NHÁP bằng mô hình lớn, xuất ra định dạng YOLO.

  python scripts/prepare_classroom_dataset.py video1.mp4 video2.mp4 --out data/lop_cua_toi --every 0.4

Kết quả:
  <out>/images/{train,val}/*.jpg     ảnh (chia theo video, không chia theo khung để số đo không bị ảo)
  <out>/labels/{train,val}/*.txt     nhãn nháp YOLO: 0 = phone, 1 = head_down
  <out>/review/*.jpg                 ảnh đã vẽ khung để xem nhanh nhãn nháp
  <out>/data.yaml

Nhãn này CHƯA đáng tin: mô hình nặng cũng sót điện thoại bị che và nhầm vật khác. Hãy mở <out> bằng CVAT hoặc
Roboflow, sửa nhãn rồi mới huấn luyện (scripts/train_behavior.py). Ảnh không có nhãn nào vẫn được giữ làm ảnh nền.
"""
import argparse
import shutil
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from core import signals as sg

ROOT = Path(__file__).resolve().parent.parent
COCO_PHONE = 67
NAMES = ["phone", "head_down"]


def yolo_line(cls, box, w, h):
    x0, y0, x1, y1 = box
    return f"{cls} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}"


def sample_frames(path, every):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step, i = max(1, round(every * fps)), 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield i, frame
        i += 1
    cap.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--out", default="data/lop_cua_toi")
    ap.add_argument("--every", type=float, default=0.4, help="lấy 1 khung mỗi N giây")
    ap.add_argument("--pose", default="yolo11x-pose.pt")
    ap.add_argument("--obj", default="yolo11x.pt")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--phone-conf", type=float, default=0.15, help="thấp để ít sót, đổi lại phải sửa nhãn thừa")
    ap.add_argument("--head-ratio", type=float, default=0.15, help="tỉ lệ đầu/vai dưới mức này coi là gục đầu")
    ap.add_argument("--val-videos", type=int, default=1, help="số video cuối dùng làm tập kiểm tra")
    ap.add_argument("--device", default="")
    a = ap.parse_args()

    out = (ROOT / a.out) if not Path(a.out).is_absolute() else Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    for sub in ("images/train", "images/val", "labels/train", "labels/val", "review"):
        (out / sub).mkdir(parents=True)

    pose, obj = YOLO(a.pose), YOLO(a.obj)
    n_val_from = len(a.videos) - a.val_videos
    counts = {"train": 0, "val": 0, "phone": 0, "head_down": 0, "empty": 0}
    for vi, video in enumerate(a.videos):
        split = "val" if vi >= n_val_from else "train"
        for fi, frame in sample_frames(video, a.every):
            h, w = frame.shape[:2]
            lines, drawn = [], frame.copy()
            res = pose.predict(frame, conf=0.25, imgsz=a.imgsz, device=a.device, verbose=False)[0]
            if res.boxes is not None and len(res.boxes):
                for box, kp in zip(res.boxes.xyxy.cpu().numpy(), res.keypoints.data.cpu().numpy()):
                    ratio = sg.head_ratio(kp, 0.30, box)
                    if ratio is not None and ratio < a.head_ratio:
                        lines.append(yolo_line(1, box, w, h))
                        counts["head_down"] += 1
                        cv2.rectangle(drawn, tuple(int(v) for v in box[:2]), tuple(int(v) for v in box[2:]), (0, 0, 255), 2)
            res = obj.predict(frame, classes=[COCO_PHONE], conf=a.phone_conf, imgsz=a.imgsz,
                              device=a.device, verbose=False)[0]
            if res.boxes is not None and len(res.boxes):
                for box in res.boxes.xyxy.cpu().numpy():
                    lines.append(yolo_line(0, box, w, h))
                    counts["phone"] += 1
                    cv2.rectangle(drawn, tuple(int(v) for v in box[:2]), tuple(int(v) for v in box[2:]), (0, 255, 255), 2)
            stem = f"v{vi}_{fi:05d}"
            cv2.imwrite(str(out / "images" / split / f"{stem}.jpg"), frame)
            (out / "labels" / split / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            if lines:
                cv2.imwrite(str(out / "review" / f"{stem}.jpg"), drawn)
            else:
                counts["empty"] += 1
            counts[split] += 1
        print(f"[{vi + 1}/{len(a.videos)}] {Path(video).name}: xong")

    (out / "data.yaml").write_text(
        f"path: {out}\ntrain: images/train\nval: images/val\nnc: {len(NAMES)}\nnames: {NAMES}\n")
    print(f"Ảnh train {counts['train']}, val {counts['val']}; nhãn nháp phone {counts['phone']}, "
          f"head_down {counts['head_down']}; ảnh không nhãn {counts['empty']}")
    print(f"Mở {out} để sửa nhãn (CVAT/Roboflow), xem nhanh ở {out / 'review'}")


if __name__ == "__main__":
    main()
