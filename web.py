"""Ứng dụng cảnh báo hành vi trong lớp học (chạy trên 1 máy).

  python web.py                 # mở http://localhost:8000
  python web.py --source 1      # bắt đầu với camera USB thứ 2
  python web.py --no-browser    # không tự mở trình duyệt

Chỉ người ngồi ở máy đang chạy app xem được (trang web chỉ mở trên localhost).
Điện thoại làm camera: quét mã QR trong Cài đặt. Điện thoại chỉ gửi được hình
(cổng HTTPS 8443, có mã bí mật), không xem được gì.
"""
import argparse
import asyncio
import csv
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from core.paths import DATA, FROZEN, res

if FROZEN:
    # App đã cài không có cửa sổ dòng lệnh (sys.stdout = None trên Windows). Phải chuyển thông tin
    # ra file TRƯỚC khi nạp thư viện AI, vì chúng in thông tin ngay lúc được nạp.
    _log = open(DATA / "app.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = _log

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core import cleanup
from core.fight import FightDetector
from core.pipeline import mode_behaviors
from core.focus import FocusTracker, label as focus_label
from core.camera import PushSource, VideoSource
from core.display import Drawer, EventLogger, FPSMeter
from core.pipeline import Pipeline, load_config
from core import signals as sg
from core.rules import BEHAVIOR_NAMES
from core.sound import play_alert
from core.window import open_window, wait_closed

WEB = res("web")
SETTINGS_FILE = DATA / "settings.json"
BOOT_ID = str(int(time.time()))   # đổi mỗi lần app khởi động, để trang web biết mà tải lại
UPLOADS = DATA / "uploads"
# Luôn hỏi lại máy chủ khi mở trang, để sau khi cập nhật app không bị kẹt giao diện bản cũ
NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}
STORAGE_DEFAULTS = {"save_snapshots": True, "keep_days": 7, "max_storage_mb": 1000}
# Mã bí mật trong mã QR của điện thoại: chỉ ai quét mã mới gửi hình vào được. Đổi mỗi lần mở app.
PHONE_KEY = secrets.token_urlsafe(8)
# Trùng với câu trong file âm thanh (scripts/make_voices.py)
ANNOUNCE = {"phone": "dùng điện thoại", "head_down": "nằm gục xuống bàn", "sleeping": "ngủ gật", "fighting": "đánh nhau", "smoking": "hút thuốc"}

# Các tham số giáo viên chỉnh được trên web: (nhóm trong config.yaml, khoá)
TUNABLE = {
    "head_down_ratio": ("rules", "head_down_ratio"),
    "phone_seconds": ("timing", "phone"),
    "head_down_seconds": ("timing", "head_down"),
    "sleeping_seconds": ("timing", "sleeping"),
    "cooldown": ("timing", "cooldown"),
    "imgsz": ("detection", "imgsz"),
}


def lan_ip():
    """Địa chỉ IP của máy trong mạng Wi-Fi/LAN (không gửi dữ liệu ra ngoài)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_local(host):
    """Yêu cầu đến từ chính máy này?"""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


DEFAULT_VIEW = {"flip_h": True, "flip_v": False, "rotate": 0, "brightness": 0, "zoom": 1.0}


def view_key(source):
    """Mỗi camera nhớ cách chỉnh hình riêng. Băm tên nguồn để không lưu mật khẩu camera dạng chữ."""
    return hashlib.sha1(source.encode()).hexdigest()[:10]


def clean_view(v):
    """Ép giá trị về khoảng hợp lệ (dữ liệu từ web không đáng tin)."""
    out = dict(DEFAULT_VIEW)
    out["flip_h"], out["flip_v"] = bool(v.get("flip_h")), bool(v.get("flip_v"))
    out["rotate"] = int(v.get("rotate", 0) or 0) // 90 % 4 * 90
    out["brightness"] = max(-80, min(80, int(float(v.get("brightness", 0) or 0))))
    out["zoom"] = max(1.0, min(3.0, round(float(v.get("zoom", 1) or 1), 2)))
    return out


def adjust(frame, v):
    """Chỉnh hình trước khi đưa vào AI: xoay, lật, phóng to giữa khung, tăng/giảm sáng.
    Chỉnh trước nên khung nhận diện và hình hiển thị luôn khớp nhau."""
    if v["rotate"]:
        frame = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                                   270: cv2.ROTATE_90_COUNTERCLOCKWISE}[v["rotate"]])
    if v["flip_h"]:
        frame = cv2.flip(frame, 1)
    if v["flip_v"]:
        frame = cv2.flip(frame, 0)
    if v["zoom"] > 1:
        h, w = frame.shape[:2]
        ch, cw = int(h / v["zoom"]), int(w / v["zoom"])
        y, x = (h - ch) // 2, (w - cw) // 2
        frame = cv2.resize(frame[y:y + ch, x:x + cw], (w, h), interpolation=cv2.INTER_LINEAR)
    if v["brightness"]:
        frame = cv2.convertScaleAbs(frame, alpha=1.0 + max(v["brightness"], 0) / 160, beta=v["brightness"])
    return frame


def display_name(source):
    """Tên ngắn để hiện trên web. Không bao giờ hiện mật khẩu camera."""
    if source.isdigit():
        return f"Webcam {source}"
    if "://" in source:
        return f"Camera IP {urlparse(source).hostname or ''}".strip()
    return f"Video: {Path(source).name}"


def announcement(behavior, count=1):
    """Câu thông báo chung, không nêu số thứ tự học sinh."""
    who = "Có học sinh" if count == 1 else f"Có {count} học sinh"
    return f"{who} {ANNOUNCE[behavior]}"


def placeholder(text):
    img = np.full((360, 640, 3), 40, np.uint8)
    return Drawer(size=22).draw_text(img, text)


def mask_source(source):
    """Che mật khẩu camera khi gửi ra giao diện."""
    return re.sub(r"(//[^/@:]+):[^/@]*@", r"\1:***@", source)


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    import platform
    return platform.processor() or platform.machine()


_hw_cache = (0.0, None)


def hardware():
    """Cấu hình máy và mức đang dùng (RAM, VRAM). Lưu tạm 3 giây vì được hỏi mỗi giây."""
    global _hw_cache
    if time.time() - _hw_cache[0] < 3 and _hw_cache[1]:
        return _hw_cache[1]
    gb = 2 ** 30
    hw = {"cpu": cpu_name(), "cores": os.cpu_count() or 1, "ram_gb": 0.0, "ram_used_gb": 0.0, "ram_free_gb": 0.0,
          "gpu": "", "vram_gb": 0.0, "vram_free_gb": 0.0}
    try:
        import psutil
        vm = psutil.virtual_memory()
        hw.update(ram_gb=vm.total / gb, ram_free_gb=vm.available / gb, ram_used_gb=(vm.total - vm.available) / gb)
    except ImportError:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            hw.update(gpu=torch.cuda.get_device_name(0), vram_gb=total / gb, vram_free_gb=free / gb)
    except Exception:
        pass
    hw = {k: round(v, 1) if isinstance(v, float) else v for k, v in hw.items()}
    _hw_cache = (time.time(), hw)
    return hw


def recommended_cameras(hw, gpu):
    """Số camera nên chạy cùng lúc, tính theo bộ nhớ còn trống và sức mạnh xử lý.
    Đo thực tế trên RTX 3050 Laptop 4 GB: mỗi camera thêm khoảng 0,15 GB RAM và 0,2 GB VRAM; tổng khoảng 44 hình/giây;
    mỗi camera chỉ cần xử lý ~5 hình/giây (hành vi kéo dài vài giây) nên chạy được khoảng 8 camera. Máy chỉ có CPU tốn nặng hơn nhiều."""
    if gpu and hw["gpu"]:
        by_mem = int(min((hw["vram_free_gb"] - 0.3) / 0.25, (hw["ram_free_gb"] - 1.0) / 0.3))
        by_speed = 8 if hw["vram_gb"] < 7 else 12
        return max(1, min(by_mem, by_speed))
    by_mem = int((hw["ram_free_gb"] - 1.5) / 0.8)
    by_cpu = hw["cores"] // 6
    return max(1, min(by_mem, by_cpu, 3))


class Gate:
    """Giới hạn số camera được chạy AI cùng một lúc. Xếp hàng công bằng (ai đến trước xử lý trước),
    nên camera chạy nhanh không chiếm hết lượt của camera khác."""

    def __init__(self, limit=1):
        self.limit, self.used = max(1, limit), 0
        self.cond = threading.Condition()
        self.queue = deque()

    def set_limit(self, n):
        with self.cond:
            self.limit = max(1, int(n))
            self.cond.notify_all()

    def __enter__(self):
        ticket = object()
        with self.cond:
            self.queue.append(ticket)
            self.cond.wait_for(lambda: self.used < self.limit and self.queue[0] is ticket)
            self.queue.popleft()
            self.used += 1
            self.cond.notify_all()

    def __exit__(self, *exc):
        with self.cond:
            self.used -= 1
            self.cond.notify_all()


class Camera:
    """Một camera: nguồn video + bộ AI + luồng xử lý riêng. Web chỉ đọc kết quả mới nhất."""

    def __init__(self, engine, d):
        self.engine = engine
        self.id = d["id"]
        self.name = d.get("name") or "Camera"
        self.source = d.get("source", "")
        self.enabled = bool(d.get("enabled", True))   # tự chạy khi mở app
        self.view = clean_view(d.get("view", {}))
        self.pipe = None
        self.src = None
        self.thread = None
        self.running = False
        self.state = "stopped"      # stopped | starting | running | error
        self.error = ""
        self.lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.jpeg_id = 0
        self.jpeg = engine._encode(placeholder("Camera chưa chạy"))
        self.focus = FocusTracker(DATA / engine.cfg["output"]["log_dir"] / f"focus_{self.id}.csv")
        self.status = self._idle_status()
        self.last_frame = 0.0
        self.watch_ts = 0.0     # lần cuối có người xem camera này (video trực tiếp / ảnh xem trước)
        self.last_t = -1e9
        self.motion_t, self.boost_until = -1e9, -1e9   # tăng tốc xử lý tạm thời (đánh nhau) đến thời điểm này
        self.last_people = []   # kết quả AI gần nhất, vẽ lên video xem giữa 2 lần xử lý
        self.touching = False    # có 2 người đứng sát/chồng nhau (nghi xô đẩy) -> cần xử lý dày hơn
        self.prev_small = None
        self.empty_since = None  # từ lúc nào trong khung không có học sinh

    def watched(self):
        return time.time() - self.watch_ts < 3.0

    @staticmethod
    def _idle_status():
        return {"focus": None, "people": 0, "warning": 0, "fps": 0.0, "active": [], "announcements": []}

    def to_dict(self):
        return {"id": self.id, "name": self.name, "source": mask_source(self.source), "enabled": self.enabled,
                "kind": source_kind(self.source), "state": self.state, "error": self.error, "view": self.view,
                **self.status}

    def persist(self):
        return {"id": self.id, "name": self.name, "source": self.source, "enabled": self.enabled, "view": self.view}

    # ---------------------------------------------------------- chạy / dừng
    def start(self):
        with self.lock:
            if self.running:
                return
            if not self.source:
                raise RuntimeError("Camera chưa có nguồn video")
            eng = self.engine
            if eng.mode is None and eng.cfg.get("modes"):
                raise RuntimeError("Chưa chọn chế độ (Lớp học / Hành lang)")
            if sum(1 for c in eng.cameras.values() if c.running) >= eng.max_cameras():
                raise RuntimeError(
                    f"Đang chạy {eng.max_cameras()} camera. Hãy dừng bớt một camera" if eng.multi() else
                    "Đang ở chế độ 1 camera. Dừng camera đang chạy, hoặc bật “Chạy nhiều camera” "
                    "ở Cài đặt → Nâng cao (chỉ nên bật trên máy mạnh).")
            for c in eng.cameras.values():
                if c is not self and c.running and c.source == self.source:
                    raise RuntimeError(f"Nguồn này đang được dùng bởi camera “{c.name}”")
            if self.source == "phone":
                src = eng.phone
            else:
                src = VideoSource(self.source)   # lỗi thì ném RuntimeError, camera giữ nguyên trạng thái
            self.src = src
            self.error = ""
            self.state, self.running = "starting", True
            self.status = self._idle_status()
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.running = False
            th, self.thread = self.thread, None
        if th and th is not threading.current_thread():
            th.join(timeout=5)
        if self.src is not None and self.src is not self.engine.phone:
            self.src.release()
        self.src = None
        self.state = "error" if self.error else "stopped"
        self.status = self._idle_status()
        self._show(placeholder("Camera đã dừng"))

    def set_view(self, patch):
        new = clean_view({**self.view, **patch})
        if self.pipe is not None and (new["rotate"], new["flip_h"], new["flip_v"], new["zoom"]) != \
                (self.view["rotate"], self.view["flip_h"], self.view["flip_v"], self.view["zoom"]):
            self.pipe.reset()  # đổi hướng/khung hình thì mã số học sinh cũ không còn đúng
        self.view = new
        self.engine.save()
        return new

    def _prep(self, frame):
        """Thu nhỏ khung quá lớn rồi xoay/lật/chỉnh sáng theo cài đặt camera (dùng chung cho AI và video xem)."""
        if frame.shape[1] > MAX_WIDTH:
            h = int(frame.shape[0] * MAX_WIDTH / frame.shape[1])
            frame = cv2.resize(frame, (MAX_WIDTH, h), interpolation=cv2.INTER_AREA)
        return adjust(frame, self.view)

    def _show_live(self, frame):
        """Video cho người xem: chạy mượt theo tốc độ camera, vẽ khung/nhãn từ kết quả AI gần nhất."""
        if cv2.mean(frame)[:3] == (0.0, 0.0, 0.0):   # khung đen hoàn toàn (webcam mới mở): giữ hình trước đó
            return
        people = self.last_people if time.time() - self.last_frame < STALE_OVERLAY else []
        eng = self.engine
        self._show(eng.drawer.draw(self._prep(frame), people, None, header=False,
                                   skeleton=eng.settings.get("show_skeleton", False)))

    def _moving(self, frame):
        """Hình có đang chuyển động mạnh không (so sánh ảnh xám thu nhỏ, rất nhẹ)."""
        if frame is None:
            return False
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
        prev, self.prev_small = self.prev_small, small
        return prev is not None and float(cv2.absdiff(small, prev).mean()) > MOTION_THRESHOLD

    def _show(self, img):
        data = self.engine._encode(img)
        with self.frame_lock:
            self.jpeg, self.jpeg_id = data, self.jpeg_id + 1

    # ---------------------------------------------------------- vòng lặp AI
    def _loop(self):
        eng = self.engine
        try:
            if self.pipe is None:
                self._show(placeholder("Đang nạp mô hình AI..."))
                self.pipe = Pipeline(eng.cfg, eng.mode)
            else:
                self.pipe.reset()
        except Exception as e:
            self.error, self.running, self.state = f"Không nạp được mô hình AI: {e}", False, "error"
            return
        self.state = "running"
        self.last_t, self.last_people, self.empty_since, self.boost_until, self.motion_t = -1e9, [], None, -1e9, -1e9   # xóa trạng thái của nguồn trước
        fps_meter = FPSMeter()
        t0, idx = time.time(), 0
        src = self.src
        while self.running:
            frame = src.read(timeout=1.0)
            if frame is None:
                if src is eng.phone:
                    self._show(placeholder("Đang chờ điện thoại gửi hình..."))
                    continue
                if src.live:
                    continue
                # Hết video -> phát lại từ đầu (tiện khi demo)
                src.release()
                src = self.src = VideoSource(self.source)
                self.pipe.reset()
                t0, idx = time.time(), 0
                self.last_t = self.boost_until = self.motion_t = -1e9   # video phát lại từ đầu: thời gian quay về 0
                continue

            if cv2.mean(frame)[:3] == (0.0, 0.0, 0.0):   # khung đen hoàn toàn: bỏ qua, không xử lý
                continue
            t = time.time() - t0 if src.live else idx / src.fps
            idx += 1
            started = time.time()
            max_fps = eng.settings.get("max_fps", DEFAULT_FPS)
            if not src.live and max_fps and max_fps < BOOST_FPS and self.touching and t - self.motion_t >= 0.2:
                self.motion_t = t
                if self._moving(frame):   # video demo: cũng tự tăng tốc khi nghi xô đẩy
                    self.boost_until = t + BOOST_HOLD
            eff_fps = BOOST_FPS if (max_fps and max_fps < BOOST_FPS and t < self.boost_until) else max_fps
            if not src.live and eff_fps and 0 <= t - self.last_t < 1.0 / eff_fps - 1e-6:
                if self.watched():
                    self._show_live(frame)
                wait = t - (time.time() - t0)   # video demo: bỏ bớt khung cho đúng tốc độ xử lý, vẫn phát đúng tốc độ thật
                if wait > 0:
                    time.sleep(wait)
                continue
            self.last_t = t
            if src.live and self.empty_since is not None and started - self.empty_since > IDLE_AFTER:
                # Lớp trống lâu thì chỉ kiểm tra 2 lần/giây, nhường máy cho camera khác; có người là chạy lại bình thường
                if started - self.last_frame < IDLE_INTERVAL:
                    if self.watched():
                        self._show_live(frame)
                    time.sleep(0.03)
                    continue
            try:
                frame = self._prep(frame)
                with eng.gate:
                    people, alerts = self.pipe.process(frame, t)
                self.error = ""
            except Exception as e:  # không để 1 lỗi làm sập cả hệ thống
                self.error = str(e)
                continue
            fps_meter.tick()
            self.last_people = people
            # Chỉ vẽ và nén ảnh khi có người đang xem hoặc cần chụp cảnh báo (tiết kiệm nhiều khi chạy nhiều camera)
            out = None
            if alerts or self.watched():
                out = eng.drawer.draw(frame, people, fps_meter.fps, header=False,
                                      skeleton=eng.settings.get("show_skeleton", False))
                if self.watched():
                    self._show(out)
            self.last_frame = time.time()
            self.empty_since = None if people else (self.empty_since or self.last_frame)
            self.touching = "fighting" in eng.behaviors() and any(
                FightDetector.near(a["box"], b["box"]) for i, a in enumerate(people) for b in people[i + 1:])

            for a in alerts:
                eng.on_alert(self, a, out)

            focus = self.focus.update(people)
            self.status = {
                "focus": None if focus is None else round(focus),
                "people": len(people),
                "warning": sum(1 for p in people if p["active"]),
                "fps": round(fps_meter.fps or 0, 1),
                "active": [{"student": p["id"], "behaviors": [BEHAVIOR_NAMES[b] for b in p["active"]]}
                           for p in people if p["active"]],
                "announcements": [announcement(b, n) for b, n in
                                  Counter(b for p in people for b in p["active"]).items()],
            }

            if src.live and max_fps:
                # Mọi hành vi kéo dài vài giây nên xử lý thưa là đủ. Riêng đánh nhau cần hình dày hơn: khi có người đứng
                # sát nhau VÀ hình đang chuyển động mạnh thì xử lý ngay (tối đa BOOST_FPS hình/giây) rồi lại nghỉ.
                now_t = time.time() - t0
                boosted = max_fps < BOOST_FPS and now_t < self.boost_until
                deadline = started + 1.0 / (BOOST_FPS if boosted else max_fps)
                while self.running and time.time() < deadline:
                    tick = time.time()
                    watched = self.watched()
                    frame2 = src.latest() if (watched or (max_fps < BOOST_FPS and self.touching and not boosted)) else None
                    if frame2 is not None:
                        if watched:
                            self._show_live(frame2)
                        if max_fps < BOOST_FPS and self.touching and not boosted and self._moving(frame2):
                            self.boost_until = time.time() - t0 + BOOST_HOLD
                            break
                    time.sleep(max(0.0, min(deadline - time.time(), (1.0 / DISPLAY_FPS if watched else 1.0 / BOOST_FPS) - (time.time() - tick))))
            if not src.live:  # video: phát đúng tốc độ thật để demo trông tự nhiên
                wait = t - (time.time() - t0)
                if wait > 0:
                    time.sleep(wait)


DISPLAY_FPS = 20      # tốc độ video cho người xem (độc lập với tốc độ AI)
STALE_OVERLAY = 2.5   # khung/nhãn AI cũ hơn mức này (giây) thì không vẽ nữa
BOOST_FPS = 8         # khi nghi xô đẩy: xử lý dày tới mức này dù đang đặt thấp hơn
BOOST_HOLD = 3.0       # giữ chế độ xử lý dày thêm ngần này giây sau lần phát hiện cuối
MOTION_THRESHOLD = 6.0  # độ chênh trung bình (0-255) giữa 2 ảnh liên tiếp coi là chuyển động mạnh
DEFAULT_FPS = 2       # số hình xử lý mỗi giây cho mỗi camera (0 = không giới hạn)
MAX_WIDTH = 1280      # khung hình rộng hơn mức này được thu nhỏ trước khi xử lý
IDLE_AFTER = 8.0      # giây không thấy học sinh nào thì chuyển sang chế độ nghỉ
IDLE_INTERVAL = 0.5   # chế độ nghỉ: giây giữa 2 lần kiểm tra


def source_kind(source):
    if source == "phone":
        return "phone"
    if source.isdigit():
        return "webcam"
    if source.startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if "://" in source:
        return "ip"
    return "file"


class Engine:
    """Quản lý nhiều camera dùng chung bộ ghi nhật ký, cài đặt và cổng giới hạn xử lý AI."""

    def __init__(self, cfg, settings):
        self.cfg = cfg
        self.settings = settings
        self.drawer = Drawer(cfg["output"].get("font", ""))
        self.logger = EventLogger(DATA / cfg["output"]["log_dir"],
                                  settings.get("save_snapshots", cfg["output"]["save_snapshots"]))
        self.phone = PushSource()
        self.mode = None   # chế độ đang chạy (lop / hanhlang), chọn mỗi lần mở app
        self.cameras = {}
        self.gate = Gate(self.parallel())
        self.events = deque(maxlen=500)
        self.event_id = 0
        self.ev_lock = threading.Lock()
        self.save_lock = threading.Lock()
        for d in settings.get("cameras", []):
            if d.get("id"):
                self.cameras[d["id"]] = Camera(self, d)

    def behaviors(self):
        return mode_behaviors(self.cfg, self.mode)

    def modes_info(self):
        return {"mode": self.mode, "last": self.settings.get("mode_last"),
                "modes": [{"id": k, "ten": v.get("ten", k), "mo_ta": v.get("mo_ta", ""), "behaviors": v.get("behaviors", [])}
                          for k, v in (self.cfg.get("modes") or {}).items()]}

    def set_mode(self, mode):
        if mode not in (self.cfg.get("modes") or {}):
            raise ValueError("Chế độ không hợp lệ")
        if mode != self.mode:
            self.stop_all()
            for cam in self.cameras.values():
                cam.pipe = None   # nạp lại mô hình đúng chế độ khi camera chạy lại
            self.mode = mode
        self.settings["mode_last"] = mode
        self.save()
        threading.Thread(target=self.autostart, daemon=True).start()

    @staticmethod
    def _encode(img):
        return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes()

    # ---------------------------------------------------------- cài đặt chung
    def parallel(self):
        """Số camera được chạy AI cùng lúc: máy có GPU nhiều hơn máy chỉ có CPU."""
        n = self.settings.get("parallel")
        if n:
            return int(n)
        return 2 if self.has_gpu() else 1

    def has_gpu(self):
        dev = self.cfg["models"].get("device")
        if dev:
            return str(dev).lower() not in ("cpu", "-1")
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def multi(self):
        """Chế độ nhiều camera mặc định TẮT: chỉ chạy 1 camera, tránh làm máy yếu bị quá tải."""
        return bool(self.settings.get("multi_camera", False))

    def max_cameras(self):
        return int(self.settings.get("max_cameras", 4)) if self.multi() else 1

    def save(self):
        with self.save_lock:
            self.settings["cameras"] = [c.persist() for c in self.cameras.values()]
            SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------------------- quản lý camera
    def get(self, cam_id):
        cam = self.cameras.get(cam_id)
        if cam is None:
            raise HTTPException(404, "Không có camera này")
        return cam

    def add_camera(self, name, source, enabled=True):
        source = source.strip()
        if not source:
            raise ValueError("Chưa nhập nguồn camera")
        legacy = self.settings.get("views", {}).get(view_key(source), {})
        if self.cameras and not self.multi():
            # Chế độ 1 camera: "thêm" nghĩa là đổi sang nguồn khác, camera cũ được thay thế
            cam = next(iter(self.cameras.values()))
            cam.stop()
            cam.name = name.strip() or cam.name
            cam.source, cam.enabled, cam.error = source, enabled, ""
            cam.view = clean_view(legacy)
            self.save()
            return cam
        cam_id = "c" + secrets.token_hex(3)
        cam = Camera(self, {"id": cam_id, "name": name.strip() or f"Camera {len(self.cameras) + 1}",
                            "source": source, "enabled": enabled, "view": legacy})
        self.cameras[cam_id] = cam
        self.save()
        return cam

    def update_camera(self, cam, body):
        if "name" in body and str(body["name"]).strip():
            cam.name = str(body["name"]).strip()[:60]
        if "enabled" in body:
            cam.enabled = bool(body["enabled"])
        if body.get("source"):
            new = str(body["source"]).strip()
            if new != mask_source(cam.source):   # giao diện chỉ thấy bản đã che mật khẩu: không đổi thì giữ nguyên
                was = cam.running
                cam.stop()
                cam.source = new
                cam.error = ""
                if was:
                    cam.start()
        self.save()

    def remove_camera(self, cam):
        cam.stop()
        cam.focus.close()
        self.cameras.pop(cam.id, None)
        self.save()

    def stop_all(self):
        for cam in list(self.cameras.values()):
            cam.stop()

    def autostart(self):
        """Mở app: bật lần lượt các camera được đặt tự chạy (nạp mô hình mất vài giây mỗi camera)."""
        if not self.settings.get("autostart", True) or (self.mode is None and self.cfg.get("modes")):
            return   # chưa chọn chế độ thì chưa nạp mô hình
        for cam in list(self.cameras.values()):
            if cam.enabled and not cam.running and sum(c.running for c in self.cameras.values()) < self.max_cameras():
                try:
                    cam.start()
                except RuntimeError as e:
                    cam.error, cam.state = str(e), "error"
                    print(f"[i] Không mở được camera “{cam.name}”: {e}")

    # ---------------------------------------------------------- cảnh báo
    def on_alert(self, cam, a, frame):
        snap = self.logger.log(a, frame, cam.name, cam.id)
        with self.ev_lock:
            self.event_id += 1
            ev = {
                "id": self.event_id, "time": datetime.now().isoformat(timespec="seconds"),
                "camera": cam.id, "camera_name": cam.name,
                "student": a["id"], "behavior": a["behavior"], "name": BEHAVIOR_NAMES[a["behavior"]],
                "duration": round(a["duration"], 1), "text": announcement(a["behavior"]),
                "snapshot": f"/snapshots/{Path(snap).name}" if snap else "",
            }
            self.events.append(ev)
        self._telegram(ev, snap)
        if self.settings.get("server_sound", self.cfg["output"]["sound"]):
            play_alert(a["behavior"])

    # ---------------------------------------------------------- tổng hợp nhiều camera
    def overview(self):
        cams = list(self.cameras.values())
        people = sum(c.status["people"] for c in cams)
        scored = [(c.status["focus"], c.status["people"]) for c in cams if c.status["focus"] is not None]
        w = sum(p for _, p in scored)
        focus = round(sum(f * p for f, p in scored) / w) if w else None
        return {"people": people, "warning": sum(c.status["warning"] for c in cams), "focus": focus,
                "running": sum(1 for c in cams if c.running)}

    def focus_summary(self, minutes, cam_id=""):
        if cam_id:
            return self.get(cam_id).focus.summary(minutes)
        cams = list(self.cameras.values())
        if len(cams) == 1:
            return cams[0].focus.summary(minutes)
        series = [c.focus.series(minutes) for c in cams]
        points = []
        for i in range(minutes):
            rows = [s[i] for s in series if s and s[i]["score"] is not None]
            n = sum(r["students"] or 0 for r in rows)
            points.append({"label": series[0][i]["label"] if series else "",
                           "score": round(sum(r["score"] * (r["students"] or 0) for r in rows) / n, 1) if n else None,
                           "students": round(n, 1) if rows else None})
        scores = [p["score"] for p in points if p["score"] is not None]
        low = min((p for p in points if p["score"] is not None), key=lambda p: p["score"], default=None)
        now = self.overview()["focus"]
        return {"now": now, "label": focus_label(now), "avg": round(sum(scores) / len(scores)) if scores else None,
                "low": low, "minutes_with_data": len(scores), "points": points}

    # ---------------------------------------------------------- dọn ổ cứng
    def storage(self):
        return {**STORAGE_DEFAULTS, **{k: self.settings[k] for k in STORAGE_DEFAULTS if k in self.settings}}

    def clean_storage(self, everything=False):
        """Xoá ảnh cảnh báo và video tải lên cũ. everything=True: xoá hết ảnh (giữ video đang chạy)."""
        st = self.storage()
        days, mb = (0, 0) if everything else (st["keep_days"], st["max_storage_mb"])
        removed = cleanup.clean([self.logger.snap_dir], days, mb)
        removed += cleanup.clean([UPLOADS], st["keep_days"], st["max_storage_mb"], protect=[c.source for c in self.cameras.values()])
        if removed:
            print(f"[i] Đã dọn {removed} file cũ")
        return removed

    def cleanup_loop(self):
        while True:
            try:
                self.clean_storage()
            except Exception as e:
                print(f"[!] Lỗi khi dọn ổ cứng: {e}")
            time.sleep(1800)  # 30 phút dọn 1 lần

    # ---------------------------------------------------------- Telegram
    def _telegram(self, ev, snap):
        token, chat = self.settings.get("telegram_token"), self.settings.get("telegram_chat_id")
        if not (token and chat):
            return
        caption = f"⚠️ {ev['text']}" + (f" — {ev['camera_name']}" if ev.get("camera_name") else "") + f"\n🕒 {ev['time'][11:]}"

        def send():
            try:
                url = f"https://api.telegram.org/bot{token}/"
                if snap:
                    with open(snap, "rb") as f:
                        requests.post(url + "sendPhoto", data={"chat_id": chat, "caption": caption},
                                      files={"photo": f}, timeout=15)
                else:
                    requests.post(url + "sendMessage", data={"chat_id": chat, "text": caption}, timeout=15)
            except requests.RequestException as e:
                print(f"[!] Gửi Telegram lỗi: {e}")
        threading.Thread(target=send, daemon=True).start()


# ====================================================================== web
def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply_settings(cfg, settings):
    for key, (group, name) in TUNABLE.items():
        if key in settings:
            cfg[group][name] = type(cfg[group][name])(settings[key])


def create_app(engine, urls):
    app = FastAPI(title="Cảnh báo hành vi lớp học")
    Path(engine.logger.snap_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/snapshots", StaticFiles(directory=engine.logger.snap_dir), name="snapshots")
    app.mount("/sounds", StaticFiles(directory=WEB / "sounds"), name="sounds")

    @app.middleware("http")
    async def only_this_computer(request: Request, call_next):
        """Máy khác trong mạng (vd điện thoại) chỉ được mở trang gửi hình, có đúng mã bí mật."""
        if not is_local(request.client.host):
            if request.url.path != "/phone" or request.query_params.get("k") != PHONE_KEY:
                return Response("Chỉ xem được trên máy đang chạy ứng dụng. Điện thoại: hãy quét lại mã QR mới.",
                                status_code=403, media_type="text/plain; charset=utf-8")
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return FileResponse(WEB / "index.html", headers=NO_CACHE)

    @app.get("/phone", response_class=HTMLResponse)
    def phone_page():
        return FileResponse(WEB / "phone.html", headers=NO_CACHE)

    @app.get("/video/{cam_id}")
    async def video(cam_id: str):
        cam = engine.get(cam_id)

        async def gen():
            last = -1
            while cam_id in engine.cameras:
                cam.watch_ts = time.time()
                with cam.frame_lock:
                    data, fid = cam.jpeg, cam.jpeg_id
                if fid != last:
                    last = fid
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                await asyncio.sleep(0.03)
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/cameras/{cam_id}/frame.jpg")
    def frame(cam_id: str):
        """Ảnh mới nhất của camera (dùng cho ô xem nhỏ, đỡ tốn kết nối so với video liên tục)."""
        cam = engine.get(cam_id)
        cam.watch_ts = time.time()
        with cam.frame_lock:
            data = cam.jpeg
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/status")
    def status(after: int = 0):
        cams = list(engine.cameras.values())
        per_cam = {}
        for e in engine.events:
            per_cam.setdefault(e["camera"], {b: 0 for b in BEHAVIOR_NAMES})[e["behavior"]] += 1
        return {
            "boot": BOOT_ID,
            "counts_by_camera": per_cam,
            "cameras": [c.to_dict() for c in cams],
            "overview": engine.overview(),
            "hw": {**hardware(), "recommended": recommended_cameras(hardware(), engine.has_gpu())},
            "phone_connected": time.time() - engine.phone.last_push < 3,
            "events": [e for e in engine.events if e["id"] > after][-50:],
            "counts": {b: engine.logger.counts.get(b, 0) for b in BEHAVIOR_NAMES},
        }

    @app.get("/api/focus")
    def focus(minutes: int = 60, camera: str = ""):
        return engine.focus_summary(max(5, min(minutes, 24 * 60)), camera)

    @app.get("/api/stats")
    def stats(minutes: int = 30, camera: str = ""):
        now = datetime.now()
        events = [e for e in engine.events if not camera or e["camera"] == camera]
        buckets = [{"label": (now - timedelta(minutes=i)).strftime("%H:%M"),
                    **{b: 0 for b in BEHAVIOR_NAMES}} for i in reversed(range(minutes))]
        index = {b["label"]: b for b in buckets}
        for e in events:
            label = e["time"][11:16]
            if label in index:
                index[label][e["behavior"]] += 1
        students = {}
        for e in events:
            key = (e["camera"], e["student"])
            students.setdefault(key, {"camera_name": e["camera_name"], **{b: 0 for b in BEHAVIOR_NAMES}})[e["behavior"]] += 1
        top = sorted(students.items(), key=lambda kv: -sum(kv[1][b] for b in BEHAVIOR_NAMES))[:10]
        by_camera = {}
        for e in engine.events:
            by_camera.setdefault(e["camera"], {"camera_name": e["camera_name"], **{b: 0 for b in BEHAVIOR_NAMES}})[e["behavior"]] += 1
        return {"timeline": buckets, "events": [{"behavior": e["behavior"]} for e in events],
                "students": [{"student": k[1], **v} for k, v in top],
                "cameras": [{"camera": k, **v} for k, v in by_camera.items()], "names": BEHAVIOR_NAMES}

    @app.get("/api/info")
    def info():
        return {"urls": urls, "cameras": list_cameras(), "settings": current_settings(engine), **engine.modes_info()}

    @app.get("/api/mode")
    def get_mode():
        return engine.modes_info()

    @app.post("/api/mode")
    def set_mode(body: dict):
        try:
            engine.set_mode(str(body.get("mode", "")))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, **engine.modes_info()}

    # ---------------------------------------------------------- quản lý camera
    @app.get("/api/cameras")
    def cameras():
        return {"cameras": [c.to_dict() for c in engine.cameras.values()], "limit": engine.max_cameras()}

    @app.post("/api/cameras")
    def add_camera(body: dict):
        try:
            cam = engine.add_camera(str(body.get("name", "")), str(body.get("source", "")), bool(body.get("enabled", True)))
        except ValueError as e:
            raise HTTPException(400, str(e))
        err = ""
        if body.get("start", True):
            try:
                cam.start()
            except RuntimeError as e:
                cam.error, cam.state, err = str(e), "error", str(e)
        return {"ok": True, "camera": cam.to_dict(), "warning": err}

    @app.post("/api/cameras/test")
    def test_camera(body: dict):
        """Thử mở nguồn video để biết địa chỉ/camera có dùng được không (không lưu gì)."""
        source = str(body.get("source", "")).strip()
        if not source or source == "phone":
            raise HTTPException(400, "Chưa nhập nguồn camera")
        for c in engine.cameras.values():
            if c.running and c.source == source:
                return {"ok": True, "message": f"Đang chạy trong camera “{c.name}”"}
        try:
            src = VideoSource(source)
            frame = src.read(timeout=8.0) if src.live else src.read()
            h, w = (frame.shape[:2] if frame is not None else (0, 0))
            src.release()
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        if frame is None:
            raise HTTPException(400, "Mở được nhưng không nhận được hình. Kiểm tra lại địa chỉ hoặc mật khẩu.")
        return {"ok": True, "message": f"Kết nối tốt, hình {w}×{h}"}

    @app.post("/api/cameras/{cam_id}")
    def edit_camera(cam_id: str, body: dict):
        cam = engine.get(cam_id)
        try:
            engine.update_camera(cam, body)
        except RuntimeError as e:
            engine.save()
            raise HTTPException(400, str(e))
        return {"ok": True, "camera": cam.to_dict()}

    @app.post("/api/cameras/{cam_id}/start")
    async def start_camera(cam_id: str):
        cam = engine.get(cam_id)
        try:
            await asyncio.to_thread(cam.start)
        except RuntimeError as e:
            cam.error, cam.state = str(e), "error"
            raise HTTPException(400, str(e))
        return {"ok": True, "camera": cam.to_dict()}

    @app.post("/api/cameras/{cam_id}/stop")
    async def stop_camera(cam_id: str):
        cam = engine.get(cam_id)
        await asyncio.to_thread(cam.stop)
        return {"ok": True, "camera": cam.to_dict()}

    @app.delete("/api/cameras/{cam_id}")
    async def delete_camera(cam_id: str):
        cam = engine.get(cam_id)
        await asyncio.to_thread(engine.remove_camera, cam)
        return {"ok": True}

    @app.post("/api/cameras/{cam_id}/view")
    def set_view(cam_id: str, body: dict):
        try:
            return {"ok": True, "view": engine.get(cam_id).set_view(body)}
        except (ValueError, TypeError):
            raise HTTPException(400, "Giá trị không hợp lệ")

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        UPLOADS.mkdir(exist_ok=True)
        dst = UPLOADS / Path(file.filename).name
        with open(dst, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"ok": True, "path": str(dst), "name": dst.name}

    @app.post("/api/settings")
    def save_settings(body: dict):
        for key in TUNABLE:
            if key in body:
                engine.settings[key] = float(body[key]) if key != "imgsz" else int(body[key])
        for key in ("telegram_token", "telegram_chat_id"):
            if key in body:
                engine.settings[key] = str(body[key]).strip()
        if "server_sound" in body:
            engine.settings["server_sound"] = bool(body["server_sound"])
        if "save_snapshots" in body:
            engine.settings["save_snapshots"] = engine.logger.save_snapshots = bool(body["save_snapshots"])
        if "keep_days" in body:
            engine.settings["keep_days"] = max(1, int(float(body["keep_days"])))
        if "max_storage_mb" in body:
            engine.settings["max_storage_mb"] = max(50, int(float(body["max_storage_mb"])))
        threading.Thread(target=engine.clean_storage, daemon=True).start()  # áp dụng giới hạn mới ngay
        if "show_skeleton" in body:
            engine.settings["show_skeleton"] = bool(body["show_skeleton"])
        if "autostart" in body:
            engine.settings["autostart"] = bool(body["autostart"])
        for key, lo, hi in (("parallel", 1, 8), ("max_cameras", 1, 16), ("max_fps", 0, 30)):
            if key in body:
                engine.settings[key] = max(lo, min(hi, int(float(body[key] or 0))))
        if "multi_camera" in body:
            engine.settings["multi_camera"] = bool(body["multi_camera"])
            if not engine.multi():   # tắt chế độ nhiều camera -> chỉ giữ lại 1 camera đang chạy
                for extra in [c for c in engine.cameras.values() if c.running][1:]:
                    extra.stop()
        engine.gate.set_limit(engine.parallel())
        apply_settings(engine.cfg, engine.settings)
        SETTINGS_FILE.write_text(json.dumps(engine.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        engine.save()
        return {"ok": True, "settings": current_settings(engine)}

    @app.post("/api/telegram/find-chat")
    def find_chat(body: dict):
        token = str(body.get("token", "")).strip()
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
        except requests.RequestException as e:
            raise HTTPException(400, f"Không kết nối được Telegram: {e}")
        if not r.get("ok"):
            raise HTTPException(400, "Token không đúng")
        chats = [u["message"]["chat"] for u in r["result"] if "message" in u]
        if not chats:
            raise HTTPException(400, "Chưa thấy tin nhắn nào. Hãy mở bot trên Telegram, bấm Start rồi thử lại.")
        chat = chats[-1]
        return {"chat_id": str(chat["id"]), "name": chat.get("first_name") or chat.get("title", "")}

    @app.post("/api/sound/test")
    def test_sound(body: dict):
        play_alert(str(body.get("behavior", "phone")))
        return {"ok": True}

    @app.post("/api/telegram/test")
    def test_telegram():
        engine._telegram({"text": "Thử thông báo từ hệ thống giám sát lớp học", "camera_name": "",
                          "time": datetime.now().isoformat(timespec="seconds")}, "")
        return {"ok": True}

    @app.get("/api/storage")
    def storage():
        files, mb = cleanup.usage([engine.logger.snap_dir, UPLOADS])
        return {"files": files, "mb": round(mb, 1), **engine.storage()}

    @app.post("/api/storage/clear")
    def clear_storage():
        return {"removed": engine.clean_storage(everything=True)}

    @app.post("/api/quit")
    def quit_app():
        """Nút "Tắt ứng dụng" trên giao diện."""
        threading.Timer(0.5, request_exit).start()
        return {"ok": True}

    @app.get("/api/history")
    def history(session: str = "", behavior: str = "", camera: str = "", limit: int = 50, offset: int = 0):
        """Lịch sử cảnh báo của mọi lượt chạy (đọc từ events.csv nên còn nguyên sau khi tắt/bật lại)."""
        by_name = {v: k for k, v in BEHAVIOR_NAMES.items()}
        sessions, rows, legacy = {}, [], None
        try:
            with open(engine.logger.path, newline="", encoding="utf-8-sig") as f:
                for r in csv.reader(f):
                    if len(r) < 5 or r[2] not in by_name:
                        continue
                    sess = r[5] if len(r) > 5 else ""
                    if not sess:   # dữ liệu cũ chưa ghi lượt chạy: cách nhau quá 30 phút thì coi là lượt khác
                        try:
                            gap = (datetime.fromisoformat(r[0]) - datetime.fromisoformat(legacy[1])).total_seconds()
                        except (ValueError, TypeError):
                            gap = 0
                        legacy = (r[0] if legacy is None or gap > 1800 else legacy[0], r[0])
                        sess = legacy[0]
                    info_s = sessions.setdefault(sess, {"session": sess, "count": 0, "first": r[0], "last": r[0],
                                                       "by": {b: 0 for b in BEHAVIOR_NAMES}})
                    info_s["count"] += 1
                    info_s["last"] = r[0]
                    info_s["by"][by_name[r[2]]] += 1
                    if session in ("", "all") or sess == session:
                        rows.append({"time": r[0], "student": r[1], "behavior": by_name[r[2]], "name": r[2],
                                     "duration": float(r[3] or 0),
                                     "snapshot": f"/snapshots/{Path(r[4]).name}" if r[4] else "", "session": sess,
                                     "camera": r[6] if len(r) > 6 else ""})
        except FileNotFoundError:
            pass
        if behavior:
            rows = [r for r in rows if r["behavior"] == behavior]
        cams = sorted({r["camera"] for r in rows if r["camera"]})
        if camera:
            rows = [r for r in rows if r["camera"] == camera]
        rows.reverse()
        return {"sessions": sorted(sessions.values(), key=lambda x: x["first"], reverse=True),
                "cameras": cams, "events": rows[max(0, offset):max(0, offset) + max(1, min(limit, 500))], "total": len(rows),
                "current": engine.logger.session}

    @app.get("/api/events.csv")
    def events_csv():
        return FileResponse(engine.logger.path, filename="canh_bao.csv", media_type="text/csv")

    @app.get("/api/qr")
    def qr(url: str):
        import qrcode
        import qrcode.image.svg
        svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).to_string()
        return Response(svg, media_type="image/svg+xml")

    @app.websocket("/ws/phone")
    async def ws_phone(ws: WebSocket):
        await ws.accept()
        if not is_local(ws.client.host) and ws.query_params.get("k") != PHONE_KEY:
            await ws.send_text(json.dumps({"error": "Mã QR đã cũ (app vừa mở lại). Hãy quét lại mã QR mới."},
                                          ensure_ascii=False))
            await ws.close()
            return
        phone_cam = next((c for c in engine.cameras.values() if c.source == "phone"), None)
        if phone_cam is None:   # chưa có camera điện thoại -> tự tạo
            phone_cam = engine.add_camera("Camera điện thoại", "phone")
        if not phone_cam.running:
            try:
                await asyncio.to_thread(phone_cam.start)
            except RuntimeError as e:
                await ws.send_text(json.dumps({"error": str(e)}, ensure_ascii=False))
                await ws.close()
                return
        try:
            while True:
                engine.phone.push_jpeg(await ws.receive_bytes())
                await ws.send_text(json.dumps({"announcements": phone_cam.status["announcements"]}, ensure_ascii=False))
        except WebSocketDisconnect:
            pass

    return app


def current_settings(engine):
    s = {key: engine.cfg[g][n] for key, (g, n) in TUNABLE.items()}
    s["telegram_token"] = engine.settings.get("telegram_token", "")
    s["telegram_chat_id"] = engine.settings.get("telegram_chat_id", "")
    s["show_skeleton"] = engine.settings.get("show_skeleton", False)
    s["autostart"] = engine.settings.get("autostart", True)
    s["parallel"] = engine.parallel()
    s["multi_camera"] = engine.multi()
    s["max_cameras"] = int(engine.settings.get("max_cameras", 4))
    s["max_fps"] = engine.settings.get("max_fps", DEFAULT_FPS)
    s["gpu"] = engine.has_gpu()
    s["hw"] = {**hardware(), "recommended": recommended_cameras(hardware(), engine.has_gpu())}
    s["server_sound"] = engine.settings.get("server_sound", engine.cfg["output"]["sound"])
    s.update(engine.storage())
    return s


_camera_cache = None


def list_cameras(max_index=4):
    """Tìm các webcam đang cắm (chỉ dò 1 lần vì mở camera khá chậm)."""
    global _camera_cache
    if _camera_cache is None:
        found = []
        for i in range(max_index):
            if engine_ref and any(c.running and c.source == str(i) for c in engine_ref.cameras.values()):
                found.append(i)  # đang dùng thì không mở lại được, nhưng chắc chắn có
                continue
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and cap.read()[0]:
                found.append(i)
            cap.release()
        _camera_cache = found
    return _camera_cache


def make_cert(ip):
    """Tạo chứng chỉ HTTPS tự ký để điện thoại được phép dùng camera trong trình duyệt."""
    cert_dir = DATA / "certs"
    key_file, cert_file, ip_file = cert_dir / "key.pem", cert_dir / "cert.pem", cert_dir / "ip.txt"
    if key_file.exists() and cert_file.exists() and ip_file.exists() and ip_file.read_text() == ip:
        return str(key_file), str(cert_file)  # đổi mạng Wi-Fi (IP khác) thì tạo lại
    try:
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return None
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "khkt-lop-hoc")])
    alt = x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                       x509.IPAddress(ipaddress.ip_address(ip))])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now() - timedelta(days=1))
            .not_valid_after(datetime.now() + timedelta(days=3650))
            .add_extension(alt, critical=False).sign(key, hashes.SHA256()))
    cert_dir.mkdir(parents=True, exist_ok=True)
    ip_file.write_text(ip)
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(key_file), str(cert_file)


engine_ref = None
servers = []


def request_exit():
    for s in servers:
        s.should_exit = True


def already_running(port):
    """App đã mở rồi (vd bấm biểu tượng lần 2)?"""
    try:
        return requests.get(f"http://127.0.0.1:{port}/api/status", timeout=1).ok
    except requests.RequestException:
        return False


def main():
    global engine_ref
    if FROZEN:
        print(f"\n===== Mở app lúc {datetime.now():%Y-%m-%d %H:%M:%S} =====")
    ap = argparse.ArgumentParser(description="Web cảnh báo hành vi lớp học")
    ap.add_argument("--source", default="0", help='Nguồn ban đầu: "0" webcam, link camera, file video, "none"')
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--https-port", type=int, default=8443)
    ap.add_argument("--no-browser", action="store_true", help="Không mở cửa sổ giao diện (chạy nền)")
    args = ap.parse_args()

    if already_running(args.port):  # chỉ mở lại cửa sổ, không chạy thêm bản thứ 2
        if not args.no_browser:
            proc = open_window(f"http://localhost:{args.port}")
            print("App đang chạy sẵn, đã mở lại cửa sổ.")
            if proc:
                proc.wait()
        return

    cfg = load_config(args.config)
    settings = load_settings()
    apply_settings(cfg, settings)
    engine = engine_ref = Engine(cfg, settings)
    threading.Thread(target=engine.cleanup_loop, daemon=True).start()
    if not engine.cameras and args.source != "none":   # lần đầu mở app: tạo sẵn 1 camera
        engine.add_camera("Camera 1", args.source)
    threading.Thread(target=engine.autostart, daemon=True).start()

    ip = lan_ip()
    cert = make_cert(ip)
    urls = {"local": f"http://localhost:{args.port}",
            "phone": f"https://{ip}:{args.https_port}/phone?k={PHONE_KEY}" if cert else ""}
    app = create_app(engine, urls)

    # Trang xem chỉ mở trên máy này (127.0.0.1). Cổng HTTPS mở ra mạng Wi-Fi chỉ để
    # điện thoại gửi hình (đã chặn mọi trang khác bằng only_this_computer).
    # Luồng video trực tiếp không bao giờ tự đóng, nên khi tắt chỉ chờ 2 giây rồi tắt hẳn.
    opts = dict(log_level="warning", timeout_graceful_shutdown=2)
    servers.append(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, **opts)))
    if cert:
        servers.append(uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=args.https_port,
                                                     ssl_keyfile=cert[0], ssl_certfile=cert[1], **opts)))
    print("\n" + "=" * 60)
    print(" HỆ THỐNG CẢNH BÁO HÀNH VI LỚP HỌC ĐANG CHẠY")
    print(f"   Mở trên máy này: {urls['local']}")
    print(f"   Dữ liệu lưu ở:   {DATA}")
    print(" Đóng cửa sổ app (hoặc nhấn Ctrl+C) để tắt.")
    print("=" * 60 + "\n")
    if not args.no_browser:
        def window():
            # Đóng cửa sổ app = tắt app (nếu theo dõi được cửa sổ)
            time.sleep(1.0)
            proc = open_window(urls["local"])
            if proc and wait_closed(proc):
                print("Cửa sổ đã đóng -> tắt app.")
                request_exit()
        threading.Thread(target=window, daemon=True).start()

    async def serve():
        # Ctrl+C chỉ báo cho 1 server, nên khi 1 cái dừng thì dừng luôn cái còn lại
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for s in servers:
            s.should_exit = True
        await asyncio.gather(*pending)
    try:
        asyncio.run(serve())
    finally:
        engine.stop_all()
        for cam in engine.cameras.values():
            cam.focus.close()
        engine.logger.close()


if __name__ == "__main__":
    main()
