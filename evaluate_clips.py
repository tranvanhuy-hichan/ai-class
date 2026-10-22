"""Đánh giá độ chính xác của hệ thống trên các video mẫu do bạn tự quay.

Cách sắp xếp video (mỗi video ~15-30 giây, 1 hành vi chính):
  clips/
    phone/      *.mp4   học sinh dùng điện thoại
    head_down/  *.mp4   gục đầu xuống bàn (3-9 giây)
    sleeping/   *.mp4   ngủ gục (gục > 10 giây) hoặc nhắm mắt lâu
    normal/     *.mp4   ngồi học bình thường (để đo báo nhầm)

Chạy:  python evaluate_clips.py --clips clips
Kết quả: bảng tỉ lệ phát hiện đúng / báo nhầm + file logs/evaluation.csv
"""
import argparse
import csv
from pathlib import Path

import cv2

from core.pipeline import Pipeline, load_config
from core.rules import BEHAVIOR_NAMES

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv"}


def run_clip(pipe, path):
    pipe.reset()
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    found, i = set(), 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        _, alerts = pipe.process(frame, i / fps)
        found.update(a["behavior"] for a in alerts)
        i += 1
    cap.release()
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default="clips")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    pipe = Pipeline(load_config(args.config))
    rows, stats = [], {}
    for label_dir in sorted(p for p in Path(args.clips).iterdir() if p.is_dir()):
        label = label_dir.name
        for clip in sorted(f for f in label_dir.iterdir() if f.suffix.lower() in VIDEO_EXT):
            found = run_clip(pipe, clip)
            if label == "normal":
                correct = not found
            elif label == "sleeping":
                correct = "sleeping" in found
            else:
                correct = label in found
            # Ngủ gục luôn bắt đầu bằng gục đầu nên không tính "head_down" là báo nhầm
            allowed = {label, "head_down"} if label == "sleeping" else {label}
            false_alarm = bool(found - allowed)
            s = stats.setdefault(label, {"n": 0, "ok": 0, "fa": 0})
            s["n"] += 1
            s["ok"] += correct
            s["fa"] += false_alarm
            rows.append([label, clip.name, ";".join(sorted(found)), int(correct), int(false_alarm)])
            print(f"{'✔' if correct else '✘'} [{label}] {clip.name}: phát hiện = {sorted(found) or 'không có'}")

    if not rows:
        raise SystemExit(f"Không tìm thấy video nào trong {args.clips}/<hanh_vi>/")

    print("\n===== KẾT QUẢ ĐÁNH GIÁ =====")
    print(f"{'Nhóm':<12}{'Số video':>9}{'Đúng':>7}{'Tỉ lệ đúng':>12}{'Báo nhầm':>10}")
    total_n = total_ok = 0
    for label, s in stats.items():
        name = BEHAVIOR_NAMES.get(label, "Bình thường")
        print(f"{label:<12}{s['n']:>9}{s['ok']:>7}{s['ok'] / s['n']:>11.0%}{s['fa']:>10}   ({name})")
        total_n += s["n"]
        total_ok += s["ok"]
    print(f"{'TỔNG':<12}{total_n:>9}{total_ok:>7}{total_ok / total_n:>11.0%}")

    out = Path("logs/evaluation.csv")
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["nhan_that", "video", "he_thong_phat_hien", "dung", "bao_nham"])
        w.writerows(rows)
    print(f"Chi tiết: {out}")


if __name__ == "__main__":
    main()
