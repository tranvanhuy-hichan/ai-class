"""Mở mọi loại nguồn video: webcam máy tính, camera điện thoại, camera lớp học, file video.

  "0", "1"                                  webcam / camera USB (điện thoại cắm USB làm webcam)
  "http://192.168.1.5:8080/video"           điện thoại chạy app IP Webcam / DroidCam
  "rtsp://admin:matkhau@192.168.1.64:554/..."  camera an ninh của lớp (Hikvision, Dahua, Imou...)
  "video.mp4"                               file video

Với camera trực tiếp, một luồng riêng liên tục đọc và chỉ giữ khung hình MỚI NHẤT,
nên máy xử lý chậm cũng không bị trễ hình dần dần. Mất kết nối thì tự kết nối lại.
"""
import re
import threading
import time

import cv2
import numpy as np


def is_live(source):
    return source.isdigit() or "://" in source


class VideoSource:
    def __init__(self, source, loop=False):
        """loop=True: file video được phát lặp lại đúng tốc độ thật, như 1 camera (dùng để demo)."""
        self.source = source
        self.loop = loop and not is_live(source)
        self.live = is_live(source) or self.loop
        self.cap = self._open()
        if not self.cap.isOpened():
            safe = re.sub(r"//[^/@]+@", "//***@", source)  # không lộ mật khẩu camera
            raise RuntimeError(f"Không mở được nguồn video: {safe}\n"
                             "- Webcam: thử --source 1\n"
                             "- Điện thoại/camera IP: kiểm tra cùng mạng Wi-Fi và đúng địa chỉ")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
        self.frame = None
        self.frame_id = 0
        self.stopped = False
        self.demand = True   # bên xử lý đang chờ khung mới: chỉ khi đó mới giải mã/chuyển màu (đỡ tốn CPU khi AI xử lý chậm hơn camera)
        if self.live:
            self.lock = threading.Lock()
            threading.Thread(target=self._reader, daemon=True).start()

    def _open(self):
        if self.source.isdigit():
            return cv2.VideoCapture(int(self.source))
        cap = cv2.VideoCapture(self.source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _reader(self):
        next_t = time.time()
        while not self.stopped:
            if self.loop:
                ok, frame = self.cap.read()
            else:
                ok = self.cap.grab()   # luôn rút khung để không bị trễ hình, nhưng chỉ chuyển màu khi cần
                frame = self.cap.retrieve()[1] if ok and self.demand else None
                if ok and frame is None:
                    continue
            if not ok and self.loop:  # hết video -> phát lại từ đầu
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            if self.loop:  # giữ đúng tốc độ của video
                next_t += 1 / self.fps
                time.sleep(max(0.0, next_t - time.time()))
            if not ok:
                print("[!] Mất tín hiệu camera, đang kết nối lại...")
                self.cap.release()
                time.sleep(2)
                self.cap = self._open()
                continue
            with self.lock:
                self.frame = frame
                self.frame_id += 1
                self.demand = False

    def read(self, timeout=10.0):
        """Trả về khung hình tiếp theo, hoặc None khi hết video / camera không phản hồi."""
        if not self.live:
            ok, frame = self.cap.read()
            return frame if ok else None
        start, last_id = time.time(), getattr(self, "_last_id", 0)
        self.demand = True
        while time.time() - start < timeout:
            with self.lock:
                if self.frame_id != last_id:
                    self._last_id = self.frame_id
                    return self.frame
            time.sleep(0.005)
        return None

    def latest(self):
        """Khung hình mới nhất chưa lấy, hoặc None nếu chưa có khung mới (không chờ)."""
        self.demand = True   # báo luồng đọc chuyển màu khung kế tiếp
        with self.lock:
            if self.frame_id == getattr(self, "_last_id", 0):
                return None
            self._last_id = self.frame_id
            return self.frame

    def release(self):
        self.stopped = True
        time.sleep(0.05)
        self.cap.release()


class PushSource:
    """Nguồn video do bên ngoài đẩy khung hình vào (vd: camera điện thoại qua trình duyệt)."""

    live = True
    fps = 10

    def __init__(self):
        self.cond = threading.Condition()
        self.frame = None
        self.frame_id = 0
        self._last_id = 0
        self.last_push = 0.0

    def push_jpeg(self, data):
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return
        with self.cond:
            self.frame = frame
            self.frame_id += 1
            self.last_push = time.time()
            self.cond.notify_all()

    def read(self, timeout=1.0):
        with self.cond:
            self.cond.wait_for(lambda: self.frame_id != self._last_id, timeout=timeout)
            if self.frame_id == self._last_id:
                return None
            self._last_id = self.frame_id
            return self.frame

    def latest(self):
        with self.cond:
            if self.frame_id == self._last_id:
                return None
            self._last_id = self.frame_id
            return self.frame

    def release(self):
        pass
