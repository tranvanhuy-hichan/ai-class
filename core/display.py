"""Vẽ kết quả lên khung hình, phát âm thanh, ghi nhật ký cảnh báo."""
import csv
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import signals as sg
from .rules import BEHAVIOR_NAMES

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]

GREEN, ORANGE, RED = (0, 200, 0), (0, 165, 255), (0, 0, 255)  # BGR

# Nối các điểm khung xương COCO-17 (mũi, mắt, tai, vai, khuỷu, cổ tay, hông, gối, cổ chân)
SKELETON = ((0, 1), (0, 2), (1, 3), (2, 4), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
            (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16))


def draw_skeleton(frame, kpts, color, thr=0.30):
    pts = {i: (int(k[0]), int(k[1])) for i, k in enumerate(kpts) if k[2] >= thr}
    for a, b in SKELETON:
        if a in pts and b in pts:
            cv2.line(frame, pts[a], pts[b], color, 2, cv2.LINE_AA)
    for pt in pts.values():
        cv2.circle(frame, pt, 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, pt, 4, color, 1, cv2.LINE_AA)


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

    def _pill(self, d, x, y, text, dot):
        """Nhãn kiểu "viên thuốc": nền tối nửa trong suốt, bo tròn, chấm màu bên trái."""
        l, t, r, b = d.textbbox((0, 0), text, font=self.font)
        h = b + 10
        w = r + h + 6
        d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=(11, 15, 23, 185))
        cy, rd = y + h / 2, max(3, h // 6)
        d.ellipse((x + h / 2 - rd, cy - rd, x + h / 2 + rd, cy + rd), fill=dot)
        d.text((x + h, y + 4), text, font=self.font, fill=(255, 255, 255, 255))
        return h

    def draw(self, frame, people, fps=None, header=True, skeleton=False):
        """Vẽ khung + nhãn từng học sinh. header=False khi giao diện đã hiện số liệu riêng (bản web)."""
        labels = []
        warn = 0
        by_id = {p["id"]: p for p in people}
        for p in people:
            other = by_id.get(p.get("fight_with"))
            if p["active"].get("fighting") and other is not None and p["id"] < other["id"]:
                cv2.line(frame, tuple(map(int, sg.center(p["box"]))), tuple(map(int, sg.center(other["box"]))),
                         RED, 3)
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
            if skeleton and p.get("kpts") is not None:
                draw_skeleton(frame, p["kpts"], color)
            for b in p.get("phone_boxes", []):
                cv2.rectangle(frame, tuple(map(int, b[:2])), tuple(map(int, b[2:])), (255, 0, 255), 2)
            label = f"#{p['id']}"
            if active:
                label += "  " + ", ".join(f"{BEHAVIOR_NAMES[b]} {d:.0f}s" for b, d in active.items())
            labels.append((x0, y0, label, color))

        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for x0, y0, text, color in labels:
            h = d.textbbox((0, 0), text, font=self.font)[3] + 10
            y = y0 - h - 4 if y0 - h - 4 >= 0 else y0 + 4  # sát trên khung, hết chỗ thì vào trong
            self._pill(d, max(x0, 0), y, text, color[::-1] + (255,))
        if header:
            text = f"Học sinh: {len(people)}  ·  Cảnh báo: {warn}" + (f"  ·  {fps:.1f} FPS" if fps else "")
            self._pill(d, 10, 10, text, (RED if warn else GREEN)[::-1] + (255,))
        img = Image.alpha_composite(img, layer).convert("RGB")
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


class FPSMeter:
    def __init__(self):
        self.last, self.fps = time.time(), None

    def tick(self):
        now = time.time()
        dt, self.last = now - self.last, now
        if dt > 0:
            self.fps = 1 / dt if self.fps is None else 0.9 * self.fps + 0.1 / dt
        return self.fps
