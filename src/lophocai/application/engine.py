"""Quản lý nhiều camera dùng chung bộ ghi nhật ký, cài đặt và cổng giới hạn xử lý AI.

Engine không import FastAPI/Qt: HTTP và desktop đều gọi cùng các phương thức này.
"""
import json
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import requests
from fastapi import HTTPException

from lophocai.detection.pipeline import mode_behaviors
from lophocai.detection.rules import BEHAVIOR_NAMES
from lophocai.domain.models import announcement, mask_source, view_key
from lophocai.integrations.audio import play_alert
from lophocai.runtime.camera_worker import Camera
from lophocai.runtime.scheduler import Gate
from lophocai.storage import cleanup
from lophocai.storage.events import EventLogger
from lophocai.storage.focus import label as focus_label
from lophocai.video.overlay import Drawer
from lophocai.video.sources import PushSource
from lophocai.video.transforms import clean_view

from .settings import STORAGE_DEFAULTS

# HTTPException chỉ dùng để báo lỗi 404 "không có camera này" cho lớp web; Engine không phụ
# thuộc FastAPI ngoài kiểu ngoại lệ này, desktop có thể bắt HTTPException như lỗi thường.


class Engine:
    """Quản lý nhiều camera dùng chung bộ ghi nhật ký, cài đặt và cổng giới hạn xử lý AI."""

    def __init__(self, cfg, settings, data_dir, uploads_dir, settings_file):
        self.cfg = cfg
        self.settings = settings
        self.data_dir = Path(data_dir)
        self.uploads_dir = Path(uploads_dir)
        self.settings_file = Path(settings_file)
        self.drawer = Drawer(cfg["output"].get("font", ""))
        self.logger = EventLogger(self.data_dir / cfg["output"]["log_dir"],
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
            self.settings_file.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

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
        removed += cleanup.clean([self.uploads_dir], st["keep_days"], st["max_storage_mb"],
                                 protect=[c.source for c in self.cameras.values()])
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
