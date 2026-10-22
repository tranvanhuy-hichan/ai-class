"""Chạy AI cho nhiều lớp học cùng lúc trên 1 máy.

Mỗi lớp có 1 luồng đọc camera riêng (luôn giữ khung hình mới nhất). Một bộ lập lịch duy nhất
lần lượt lấy khung hình của từng lớp đưa vào AI, nên CPU được chia đều và không bị quá tải:
  - lớp đang có người xem trực tiếp: fps_watch khung/giây (video mượt)
  - lớp không ai xem: fps_background khung/giây (đủ để phát hiện hành vi kéo dài vài giây)
"""
import threading
import time
from collections import Counter
from datetime import datetime

import cv2

from core.camera import PushSource, VideoSource
from core.display import Drawer, FPSMeter
from core.pipeline import Pipeline
from core.rules import BEHAVIOR_NAMES

ANNOUNCE = {"phone": "dùng điện thoại", "head_down": "nằm gục xuống bàn", "sleeping": "ngủ gật"}


def announcement(behavior, count=1):
    """Câu thông báo chung, không nêu số thứ tự học sinh."""
    who = "Có học sinh" if count == 1 else f"Có {count} học sinh"
    return f"{who} {ANNOUNCE[behavior]}"


def encode(img, width=None, quality=75):
    if width and img.shape[1] > width:
        img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])))
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


class ClassroomWorker:
    def __init__(self, room, manager):
        self.id = room["id"]
        self.name = room["name"]
        self.source = room["source"]
        self.manager = manager
        self.phone = PushSource()
        self.streamer, self.stream_owner = "", None  # ai đang phát camera thiết bị cho lớp
        self.src = None
        self.pipe = None
        self.state = "starting"   # starting | running | waiting | error | off
        self.error = ""
        self.retry_at = 0.0
        self.opening = False
        self.viewers = 0
        self.next_due = 0.0
        self.fps = FPSMeter()
        self.frame_lock = threading.Lock()
        self.jpeg, self.jpeg_id = None, 0
        self.thumb, self.last_thumb = None, 0.0
        self.status = {"people": 0, "warning": 0, "fps": 0.0, "announcements": []}

    # ------------------------------------------------------------ mở / đóng nguồn
    def open_async(self):
        """Mở camera trong luồng riêng (camera IP có thể mất vài chục giây mới báo lỗi)."""
        if self.opening:
            return
        self.opening = True

        def run():
            try:
                if self.pipe is None:
                    self.pipe = Pipeline(self.manager.cfg)
                if not self.source:
                    self.state, self.error = "off", "Chưa chọn nguồn camera"
                elif self.source == "phone":
                    self.src, self.state = self.phone, "waiting"
                else:
                    self.src, self.state, self.error = VideoSource(self.source, loop=True), "running", ""
            except RuntimeError as e:
                self.state, self.error = "error", str(e).split("\n")[0]
                self.retry_at = time.time() + 15
            except Exception as e:
                self.state, self.error = "error", f"Lỗi: {e}"
                self.retry_at = time.time() + 15
            finally:
                self.opening = False
        threading.Thread(target=run, daemon=True).start()

    def close(self):
        if self.src is not None and self.src is not self.phone:
            self.src.release()
        self.src = None

    # ------------------------------------------------------------ xử lý 1 khung hình
    def step(self, now):
        """Gọi bởi bộ lập lịch. Trả về True nếu đã xử lý 1 khung hình."""
        if self.src is None:
            if self.state == "error" and now > self.retry_at and self.source:
                self.open_async()  # tự thử kết nối lại
            return False
        if self.src is self.phone:
            self.state = "running" if now - self.phone.last_push < 3 else "waiting"
        frame = self.src.latest()
        if frame is None:
            return False

        people, alerts = self.pipe.process(frame, now)
        fps = self.fps.tick()
        need_thumb = now - self.last_thumb > 2
        if self.viewers or alerts or need_thumb:
            out = self.manager.drawer.draw(frame, people, fps)
            if self.viewers:
                data = encode(out)
                with self.frame_lock:
                    self.jpeg, self.jpeg_id = data, self.jpeg_id + 1
            if need_thumb or alerts:
                self.thumb, self.last_thumb = encode(out, width=480, quality=70), now
            for a in alerts:
                self.manager.on_alert(self, a, out)

        self.status = {
            "people": len(people),
            "warning": sum(1 for p in people if p["active"]),
            "fps": round(fps or 0, 1),
            "announcements": [announcement(b, n) for b, n in
                              Counter(b for p in people for b in p["active"]).items()],
        }
        return True

    def info(self):
        return {"id": self.id, "state": self.state, "error": self.error, "viewers": self.viewers,
                "phone_connected": time.time() - self.phone.last_push < 3, **self.status}


class Manager:
    def __init__(self, cfg, db, on_alert):
        self.cfg = cfg
        self.db = db
        self.on_alert_cb = on_alert
        self.drawer = Drawer(cfg["output"].get("font", ""))
        self.workers = {}
        self.lock = threading.Lock()
        self.running = True
        self.sync()
        threading.Thread(target=self._loop, daemon=True).start()

    def sync(self):
        """Khớp danh sách camera đang chạy với danh sách lớp trong cơ sở dữ liệu."""
        rooms = {r["id"]: r for r in self.db.all("SELECT * FROM classrooms")}
        with self.lock:
            for cid in list(self.workers):
                w, r = self.workers[cid], rooms.get(cid)
                if r is None or not r["enabled"] or r["source"] != w.source:
                    w.close()
                    del self.workers[cid]
                elif r["name"] != w.name:
                    w.name = r["name"]
            for cid, r in rooms.items():
                if r["enabled"] and cid not in self.workers:
                    w = ClassroomWorker(r, self)
                    self.workers[cid] = w
                    w.open_async()

    def get(self, cid):
        return self.workers.get(cid)

    def on_alert(self, worker, alert, frame):
        try:
            self.on_alert_cb(worker, alert, frame)
        except Exception as e:
            print(f"[!] Lỗi khi lưu cảnh báo: {e}")

    def _loop(self):
        while self.running:
            s = self.db.settings()
            fps_bg = float(s.get("fps_background", 2))
            fps_watch = float(s.get("fps_watch", 8))
            now = time.time()
            busy = False
            with self.lock:
                workers = list(self.workers.values())
            # Lớp nào "đến lượt" lâu nhất thì xử lý trước -> chia đều cho các lớp
            for w in sorted(workers, key=lambda w: w.next_due):
                if now < w.next_due:
                    continue
                try:
                    if w.step(now):
                        w.next_due = now + 1 / (fps_watch if w.viewers else fps_bg)
                        busy = True
                except Exception as e:
                    w.state, w.error = "error", f"Lỗi xử lý: {e}"
                    w.next_due = now + 2
                now = time.time()
            if not busy:
                time.sleep(0.01)

    def stop(self):
        self.running = False
        with self.lock:
            for w in self.workers.values():
                w.close()


def today():
    return datetime.now().strftime("%Y-%m-%d")


__all__ = ["Manager", "announcement", "BEHAVIOR_NAMES", "today"]
