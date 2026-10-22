"""Luật suy ra hành vi theo thời gian.

Mỗi khung hình, bộ phân tích cho ra các "tín hiệu" tức thời cho từng học sinh
(vd: đầu đang thấp hơn vai, tay đang cầm điện thoại). Một tín hiệu chỉ trở thành
"hành vi bất thường" khi nó kéo dài đủ lâu -> tránh báo nhầm khi học sinh chỉ
cúi xuống nhặt bút hay liếc điện thoại 1 giây.
"""

BEHAVIOR_NAMES = {
    "phone": "Dùng điện thoại",
    "head_down": "Gục đầu xuống bàn",
    "sleeping": "Ngủ gục / ngủ gật",
}

SIGNALS = ("phone", "head_down", "eyes_closed")


class Timer:
    """Đo một tín hiệu đã kéo dài liên tục bao lâu.

    Cho phép mất tín hiệu ngắn (grace) - vd mô hình bỏ sót 1-2 khung hình -
    mà không reset bộ đếm.
    """

    def __init__(self):
        self.start = None
        self.last = None

    def update(self, active, t, grace):
        if active:
            if self.start is None or t - self.last > grace:
                self.start = t
            self.last = t
        elif self.start is not None and t - self.last > grace:
            self.start = self.last = None

    def duration(self):
        return 0.0 if self.start is None else self.last - self.start


class Student:
    def __init__(self, track_id):
        self.id = track_id
        self.timers = {s: Timer() for s in SIGNALS}
        self.last_alert = {}   # hành vi -> thời điểm cảnh báo gần nhất
        self.last_seen = None


class BehaviorRules:
    def __init__(self, timing):
        self.timing = timing
        self.students = {}

    def update(self, track_id, signals, t):
        """Cập nhật tín hiệu của 1 học sinh.

        Trả về (active, new_alerts):
          active     - dict {hành vi: số giây đã kéo dài} đang xảy ra
          new_alerts - list các hành vi cần phát cảnh báo ngay bây giờ
        """
        st = self.students.get(track_id)
        if st is None:
            st = self.students[track_id] = Student(track_id)
        # Máy yếu chạy 1-2 khung hình/giây thì khoảng cách giữa 2 khung > grace,
        # nên nới grace theo khoảng cách đó để bộ đếm không bị reset liên tục.
        grace = self.timing["grace"]
        if st.last_seen is not None:
            grace = max(grace, 2.5 * (t - st.last_seen))
        st.last_seen = t
        for name in SIGNALS:
            st.timers[name].update(bool(signals.get(name)), t, grace)

        d_phone = st.timers["phone"].duration()
        d_head = st.timers["head_down"].duration()
        d_eyes = st.timers["eyes_closed"].duration()

        active = {}
        if d_phone >= self.timing["phone"]:
            active["phone"] = d_phone
        if d_head >= self.timing["sleeping"] or d_eyes >= self.timing["eyes_closed"]:
            active["sleeping"] = max(d_head, d_eyes)
        elif d_head >= self.timing["head_down"]:
            active["head_down"] = d_head

        new_alerts = []
        for behavior in active:
            last = st.last_alert.get(behavior)
            if last is None or t - last >= self.timing["cooldown"]:
                st.last_alert[behavior] = t
                new_alerts.append(behavior)
        return active, new_alerts

    def forget_old(self, t, max_age=30.0):
        """Xoá học sinh đã rời khung hình quá lâu để không tốn bộ nhớ."""
        for tid in [k for k, s in self.students.items() if t - s.last_seen > max_age]:
            del self.students[tid]
