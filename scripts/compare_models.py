"""So sánh hai mô hình hành vi trên video lớp học của bạn.

  python scripts/compare_models.py --old weights/behavior.pt --new weights/behavior_lop.pt \\
         video1.mp4 video2.mp4 --out runs/so_sanh --every 1.0 --conf 0.35

Với mỗi video: lấy 1 khung mỗi --every giây, chạy cả hai mô hình, đếm số khung phát hiện theo từng lớp,
và lưu ảnh ghép (trái = mô hình cũ, phải = mô hình mới) vào <out>/ để bạn xem bằng mắt.
Chỉ lưu ảnh khi hai mô hình khác nhau ở khung đó, để bạn xem đúng chỗ khác biệt.
"""
import argparse
from collections import Counter
from pathlib import Path

import cv2
from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--old", default="weights/behavior.pt")
    ap.add_argument("--new", default="weights/behavior_lop.pt")
    ap.add_argument("--out", default="runs/so_sanh")
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--max-images", type=int, default=60, help="số ảnh ghép tối đa lưu cho mỗi video")
    a = ap.parse_args()

    models = {"cu": YOLO(a.old), "moi": YOLO(a.new)}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    for v, video in enumerate(a.videos):
        cap = cv2.VideoCapture(video)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step, i, saved = max(1, round(a.every * fps)), 0, 0
        counts = {k: Counter() for k in models}
        n = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                n += 1
                drawn, found = {}, {}
                for k, m in models.items():
                    r = m.predict(frame, conf=a.conf, imgsz=a.imgsz, verbose=False)[0]
                    found[k] = sorted(m.names[int(c)] for c in r.boxes.cls)
                    counts[k].update(found[k])
                    drawn[k] = r.plot(line_width=2, font_size=0.8)
                if found["cu"] != found["moi"] and saved < a.max_images:
                    h = 480
                    side = [cv2.resize(drawn[k], (int(drawn[k].shape[1] * h / drawn[k].shape[0]), h)) for k in ("cu", "moi")]
                    cv2.imwrite(str(out / f"v{v}_{i:05d}.jpg"), cv2.hconcat(side))
                    saved += 1
            i += 1
        cap.release()
        print(f"\n== {Path(video).name}: {n} khung")
        names = sorted(set(models["cu"].names.values()) | set(models["moi"].names.values()))
        print(f"{'lop':10s} {'cu':>6s} {'moi':>6s}   (so lan phat hien tren toan video)")
        for name in names:
            print(f"{name:10s} {counts['cu'][name]:6d} {counts['moi'][name]:6d}")
        print(f"Đã lưu {saved} ảnh ghép (trái = cũ, phải = mới) vào {out}")


if __name__ == "__main__":
    main()
