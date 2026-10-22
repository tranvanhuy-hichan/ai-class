"""Vẽ kết quả lên khung hình, phát âm thanh, ghi nhật ký cảnh báo."""
import csv
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .rules import BEHAVIOR_NAMES

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]

GREEN, ORANGE, RED = (0, 200, 0), (0, 165, 255), (0, 0, 255)  # BGR


def load_font(path, size):
    for p in ([path] if path else []) + FONT_CANDIDATES:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


class Drawer:
    """OpenCV không viết được tiếng Việt có dấu nên dùng Pillow để viết chữ."""

    def __init__(self, font_path="", size=18):
        self.font = load_font(font_path, size)

    def draw_text(self, frame, text, color=(255, 255, 255)):
        """Viết 1 dòng chữ ở giữa ảnh (dùng cho màn hình chờ)."""
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(img)
        l, t, r, b = d.textbbox((0, 0), text, font=self.font)
        d.text(((img.width - r) // 2, (img.height - b) // 2), text, font=self.font, fill=color)
        return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)

    def draw(self, frame, people, fps=None):
        texts = []
        warn = 0
        for p in people:
            x0, y0, x1, y1 = map(int, p["box"])
            active = p["active"]
            if active:
                color, warn = RED, warn + 1
            elif any(p["signals"].values()):
                color = ORANGE  # có dấu hiệu nhưng chưa đủ lâu
            else:
                color = GREEN
            cv2.rectangle(frame, (x0, y0), (x1, y1), color, 2)
            for b in p.get("phone_boxes", []):
                cv2.rectangle(frame, tuple(map(int, b[:2])), tuple(map(int, b[2:])), (255, 0, 255), 2)
            label = f"#{p['id']}"
            if active:
                label += " " + ", ".join(f"{BEHAVIOR_NAMES[b]} {d:.0f}s" for b, d in active.items())
            texts.append(((x0, max(y0 - 24, 0)), label, color))

        header = f"Học sinh: {len(people)} | Cảnh báo: {warn}"
        if fps:
            header += f" | {fps:.1f} FPS"
        texts.append(((10, 8), header, RED if warn else GREEN))

        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(img)
        for (x, y), text, color in texts:
            l, t, r, b = d.textbbox((x, y), text, font=self.font)
            d.rectangle((l - 3, t - 3, r + 3, b + 3), fill=color[::-1])
            d.text((x, y), text, font=self.font, fill=(255, 255, 255))
        return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


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
            self.writer.writerow(["thoi_gian", "id_hoc_sinh", "hanh_vi", "keo_dai_giay", "anh"])
        self.counts = {}

    def log(self, alert, frame):
        now = datetime.now()
        snap = ""
        if self.save_snapshots:
            snap = str(self.snap_dir / f"{now:%Y%m%d_%H%M%S}_id{alert['id']}_{alert['behavior']}.jpg")
            cv2.imwrite(snap, frame)
        self.writer.writerow([now.isoformat(timespec="seconds"), alert["id"],
                              BEHAVIOR_NAMES[alert["behavior"]], f"{alert['duration']:.1f}", snap])
        self.file.flush()
        self.counts[alert["behavior"]] = self.counts.get(alert["behavior"], 0) + 1
        print(f"[!] {now:%H:%M:%S} Học sinh #{alert['id']}: {BEHAVIOR_NAMES[alert['behavior']]} "
              f"({alert['duration']:.0f}s)")
        return snap

    def close(self):
        self.file.close()


class FPSMeter:
    def __init__(self):
        self.last, self.fps = time.time(), None

    def tick(self):
        now = time.time()
        dt, self.last = now - self.last, now
        if dt > 0:
            self.fps = 1 / dt if self.fps is None else 0.9 * self.fps + 0.1 / dt
        return self.fps
