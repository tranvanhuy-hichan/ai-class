"""Một camera: nguồn video + bộ AI + luồng xử lý riêng. Giao diện chỉ đọc kết quả mới nhất."""
import threading
import time
from collections import Counter

import cv2
import numpy as np

from lophocai.detection.fight import FightDetector
from lophocai.detection.pipeline import Pipeline
from lophocai.detection.rules import BEHAVIOR_NAMES
from lophocai.domain.models import announcement, mask_source, source_kind
from lophocai.storage.focus import FocusTracker
from lophocai.video.sources import VideoSource
from lophocai.video.transforms import adjust, clean_view

from .fps import FPSMeter

DISPLAY_FPS = 20      # tốc độ video cho người xem (độc lập với tốc độ AI)
STALE_OVERLAY = 2.5   # khung/nhãn AI cũ hơn mức này (giây) thì không vẽ nữa
BOOST_FPS = 8         # khi nghi xô đẩy: xử lý dày tới mức này dù đang đặt thấp hơn
BOOST_HOLD = 3.0       # giữ chế độ xử lý dày thêm ngần này giây sau lần phát hiện cuối
MOTION_THRESHOLD = 6.0  # độ chênh trung bình (0-255) giữa 2 ảnh liên tiếp coi là chuyển động mạnh
DEFAULT_FPS = 2       # số hình xử lý mỗi giây cho mỗi camera (0 = không giới hạn)
MAX_WIDTH = 1280      # khung hình rộng hơn mức này được thu nhỏ trước khi xử lý
IDLE_AFTER = 8.0      # giây không thấy học sinh nào thì chuyển sang chế độ nghỉ
IDLE_INTERVAL = 0.5   # chế độ nghỉ: giây giữa 2 lần kiểm tra


def placeholder(drawer, text):
    img = np.full((360, 640, 3), 40, np.uint8)
    return drawer.draw_text(img, text)


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
        self.jpeg = engine._encode(placeholder(engine.drawer, "Camera chưa chạy"))
        # Khung BGR thô cho desktop (Qt): tránh vòng nén/giải nén JPEG của luồng web.
        # Ghi đè khung cũ, không có hàng đợi; desktop tự sao chép trước khi vẽ lên QImage.
        self.bgr_frame = placeholder(engine.drawer, "Camera chưa chạy")
        self.bgr_id = 0
        self.focus = FocusTracker(engine.data_dir / engine.cfg["output"]["log_dir"] / f"focus_{self.id}.csv")
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

    def mark_watched(self):
        """Gọi mỗi khi có ai đang thực sự xem camera này (giống watch_ts của luồng MJPEG).
        Không gọi liên tục khi không hiển thị, nếu không mất tác dụng tiết kiệm tài nguyên."""
        self.watch_ts = time.time()

    @staticmethod
    def _idle_status():
        return {"focus": None, "people": 0, "warning": 0, "fps": 0.0, "active": [], "announcements": []}

    def to_dict(self):
        return {"id": self.id, "name": self.name, "source": mask_source(self.source), "enabled": self.enabled,
                "kind": source_kind(self.source), "state": self.state, "error": self.error, "view": self.view,
                **self.status}

    def persist(self):
        return {"id": self.id, "name": self.name, "source": self.source, "enabled": self.enabled, "view": self.view}

    def latest_bgr(self):
        """(khung BGR mới nhất, số thứ tự). Desktop gọi mỗi nhịp hiển thị, không chờ."""
        with self.frame_lock:
            return self.bgr_frame, self.bgr_id

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
        self._show(placeholder(self.engine.drawer, "Camera đã dừng"))

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
            self.bgr_frame, self.bgr_id = img, self.bgr_id + 1

    # ---------------------------------------------------------- vòng lặp AI
    def _loop(self):
        eng = self.engine
        try:
            if self.pipe is None:
                self._show(placeholder(eng.drawer, "Đang nạp mô hình AI..."))
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
                    self._show(placeholder(eng.drawer, "Đang chờ điện thoại gửi hình..."))
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
