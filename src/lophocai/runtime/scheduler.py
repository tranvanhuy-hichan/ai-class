"""Giới hạn số camera được chạy AI cùng một lúc."""
import threading
from collections import deque


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
