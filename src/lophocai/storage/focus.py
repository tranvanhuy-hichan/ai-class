"""Chỉ số tập trung của lớp (0-100), chạy theo thời gian thực.

Mỗi học sinh trong khung hình được chấm theo trạng thái hiện tại:
    bình thường                                  -> 100%
    có dấu hiệu nhưng chưa đủ lâu để cảnh báo    ->  50%   (vd mới cúi đầu 1-2 giây)
    đang bị cảnh báo (điện thoại, gục, ngủ gật)  ->   0%
Điểm của lớp là trung bình của các học sinh nhìn thấy.

Đây là CHỈ SỐ THAM KHẢO do nhóm tự đặt công thức, chưa được kiểm chứng với đánh giá của giáo viên.
Điểm trung bình theo từng phút được lưu vào logs/focus.csv để vẽ biểu đồ cả tiết học.
"""
import csv
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

W_NORMAL, W_SIGNAL, W_ALERT = 1.0, 0.5, 0.0
SMOOTH_SECONDS = 5.0     # làm mượt con số hiển thị để không nhấp nháy
KEEP_MINUTES = 24 * 60   # nhớ tối đa 1 ngày
LOW, GOOD = 55, 80       # dưới LOW: thấp, từ GOOD trở lên: tốt


def label(score):
    if score is None:
        return "Chưa có dữ liệu"
    return "Tập trung tốt" if score >= GOOD else "Trung bình" if score >= LOW else "Dễ mất tập trung"


def student_weight(p):
    if p.get("active"):
        return W_ALERT
    if any(p.get("signals", {}).values()):
        return W_SIGNAL
    return W_NORMAL


def instant(people):
    """Điểm tức thời của khung hình, None nếu không thấy học sinh nào."""
    if not people:
        return None
    return 100.0 * sum(student_weight(p) for p in people) / len(people)


class FocusTracker:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.minutes = OrderedDict()   # "YYYY-MM-DD HH:MM" -> [tổng điểm, số mẫu, tổng số học sinh]
        self.now = None                # điểm đã làm mượt
        self.last_seen = 0.0
        self.last_t = None
        self._load()

    # ------------------------------------------------------------ nạp / ghi file
    def _load(self):
        if not self.path or not self.path.exists():
            return
        try:
            with open(self.path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))[1:]
            for r in rows[-KEEP_MINUTES:]:
                self.minutes[r[0]] = [float(r[1]), 1, float(r[2])]   # 1 mẫu = điểm trung bình đã lưu
        except (OSError, ValueError, IndexError) as e:
            print(f"[i] Không đọc được {self.path}: {e}")

    def _flush(self, key):
        if not self.path:
            return
        total, n, students = self.minutes[key]
        new = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["phut", "diem_tap_trung", "so_hoc_sinh_tb"])
            w.writerow([key, round(total / n, 1), round(students / n, 1)])

    # ------------------------------------------------------------ cập nhật mỗi khung hình
    def update(self, people, when=None):
        """Gọi mỗi khung hình. Trả về điểm đã làm mượt (hoặc None)."""
        inst = instant(people)
        t = time.time()
        with self.lock:
            if inst is None:
                if t - self.last_seen > SMOOTH_SECONDS:
                    self.now = None   # lâu không thấy ai -> không có dữ liệu
                return self.now
            dt = 0.1 if self.last_t is None else min(t - self.last_t, 2.0)
            self.last_t, self.last_seen = t, t
            a = 1 - math.exp(-dt / SMOOTH_SECONDS)
            self.now = inst if self.now is None else self.now + a * (inst - self.now)

            key = (when or datetime.now()).strftime("%Y-%m-%d %H:%M")
            if key not in self.minutes:
                if self.minutes:   # sang phút mới -> ghi phút vừa xong ra file
                    self._flush(next(reversed(self.minutes)))
                self.minutes[key] = [0.0, 0, 0.0]
                while len(self.minutes) > KEEP_MINUTES:
                    self.minutes.popitem(last=False)
            m = self.minutes[key]
            m[0] += inst
            m[1] += 1
            m[2] += len(people)
            return self.now

    def close(self):
        with self.lock:
            if self.minutes:
                last = next(reversed(self.minutes))
                if self.minutes[last][1] > 1:   # phút đang dở (chưa ghi) thì ghi nốt
                    self._flush(last)

    # ------------------------------------------------------------ truy vấn cho biểu đồ
    def series(self, minutes=60, end=None):
        """Điểm trung bình từng phút trong `minutes` phút gần nhất (None = phút không có ai)."""
        end = (end or datetime.now()).replace(second=0, microsecond=0)
        out = []
        with self.lock:
            for i in range(minutes - 1, -1, -1):
                t = end - timedelta(minutes=i)
                m = self.minutes.get(t.strftime("%Y-%m-%d %H:%M"))
                out.append({"label": t.strftime("%H:%M"),
                            "score": round(m[0] / m[1], 1) if m and m[1] else None,
                            "students": round(m[2] / m[1], 1) if m and m[1] else None})
        return out

    def summary(self, minutes=60):
        points = self.series(minutes)
        scores = [p["score"] for p in points if p["score"] is not None]
        low = min((p for p in points if p["score"] is not None), key=lambda p: p["score"], default=None)
        return {"now": None if self.now is None else round(self.now), "label": label(self.now),
                "avg": round(sum(scores) / len(scores)) if scores else None,
                "low": low, "minutes_with_data": len(scores), "points": points}
