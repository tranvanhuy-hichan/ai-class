"""Ghi mỗi cảnh báo vào logs/events.csv và (tuỳ chọn) lưu ảnh chụp."""
import csv
import re
import threading
from datetime import datetime
from pathlib import Path

import cv2

from lophocai.detection.rules import BEHAVIOR_NAMES


class EventLogger:
    """Ghi mỗi cảnh báo vào logs/events.csv và (tuỳ chọn) lưu ảnh chụp."""

    def __init__(self, log_dir="logs", save_snapshots=True):
        self.dir = Path(log_dir)
        self.snap_dir = self.dir / "snapshots"
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        self.save_snapshots = save_snapshots
        self.path = self.dir / "events.csv"
        new = not self.path.exists()
        self.file = open(self.path, "a", newline="", encoding="utf-8-sig")
        self.writer = csv.writer(self.file)
        if new:
            self.writer.writerow(["thoi_gian", "id_hoc_sinh", "hanh_vi", "keo_dai_giay", "anh", "luot_chay", "camera"])
        self.counts = {}
        self.lock = threading.Lock()   # nhiều camera cùng ghi nhật ký
        # Mỗi lần mở ứng dụng là một "lượt chạy"; ghi vào từng dòng để xem lại lịch sử theo lượt
        self.session = datetime.now().isoformat(timespec="seconds")

    def log(self, alert, frame, camera="", cam_id=""):
        now = datetime.now()
        snap = ""
        tag = f"_{re.sub(r'[^A-Za-z0-9]', '', cam_id)}" if cam_id else ""
        if self.save_snapshots:
            snap = str(self.snap_dir / f"{now:%Y%m%d_%H%M%S}{tag}_id{alert['id']}_{alert['behavior']}.jpg")
            cv2.imwrite(snap, frame)
        with self.lock:
            self.writer.writerow([now.isoformat(timespec="seconds"), alert["id"],
                                  BEHAVIOR_NAMES[alert["behavior"]], f"{alert['duration']:.1f}", snap,
                                  self.session, camera])
            self.file.flush()
            self.counts[alert["behavior"]] = self.counts.get(alert["behavior"], 0) + 1
        print(f"[!] {now:%H:%M:%S} {camera + ': ' if camera else ''}Học sinh #{alert['id']}: "
              f"{BEHAVIOR_NAMES[alert['behavior']]} ({alert['duration']:.0f}s)")
        return snap

    def close(self):
        self.file.close()
