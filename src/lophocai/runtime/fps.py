"""Đo FPS xử lý, làm mượt theo thời gian."""
import time


class FPSMeter:
    def __init__(self):
        self.last, self.fps = time.time(), None

    def tick(self):
        now = time.time()
        dt, self.last = now - self.last, now
        if dt > 0:
            self.fps = 1 / dt if self.fps is None else 0.9 * self.fps + 0.1 / dt
        return self.fps
