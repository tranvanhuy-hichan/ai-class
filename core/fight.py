"""Phát hiện đánh nhau từ khung xương, không cần mô hình riêng nên không tốn thêm tài nguyên.

Ý tưởng: đánh nhau là hành vi giữa HAI người, với các cú vung tay nhanh vào người kia lặp lại.
  - "Cú vung": cổ tay di chuyển nhanh, tốc độ tính theo đơn vị "độ rộng vai / giây" nên không phụ thuộc
    học sinh ngồi gần hay xa camera, cũng không phụ thuộc FPS.
  - "Cú đánh": cú vung có cổ tay rơi vào thân người của một học sinh khác.
  - Một cặp bị coi là đánh nhau khi trong cửa sổ vài giây có đủ số cú đánh (một chiều hoặc hai chiều),
    hoặc cả hai cùng vung tay liên tục khi đang sát nhau (xô đẩy, vật nhau).
Giơ tay phát biểu, vẫy tay, chép bài, đưa bút cho bạn chỉ có 1 cú vung đơn lẻ hoặc không chạm vào người
kia nên không đủ điều kiện.

Đây là luật do nhóm tự đặt, chưa kiểm chứng trên video đánh nhau thật. Học sinh đùa nghịch mạnh tay vẫn có
thể bị báo; chỉnh các ngưỡng ở mục `fight` trong config.yaml.
"""
from collections import deque

from . import signals as sg

WRISTS = (sg.L_WRIST, sg.R_WRIST)
MAX_SPEED = 40.0   # nhanh hơn mức này là khung xương bị nhảy (nhiễu), không phải chuyển động thật


def torso_box(box, shrink_x=0.12, top=0.12):
    """Phần thân của 1 người: thu hẹp 2 bên và bỏ phần đầu/tay thò ra ngoài."""
    w, h = box[2] - box[0], box[3] - box[1]
    return (box[0] + shrink_x * w, box[1] + top * h, box[2] - shrink_x * w, box[3])


def _inside(b, p):
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


class FightDetector:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.swing_speed = cfg.get("swing_speed", 5.0)    # độ rộng vai / giây
        self.window = cfg.get("window", 2.5)              # giây
        self.min_strikes = cfg.get("min_strikes", 3)      # số lần đánh trúng khác thời điểm trong cửa sổ
        self.min_flails = cfg.get("min_flails", 3)        # số lần vung mỗi người khi hai bên sát nhau
        self.kp_conf = cfg.get("keypoint_conf", 0.30)
        self.strong_conf = cfg.get("flail_conf", 0.50)    # độ tin cậy khớp tay tối thiểu cho luật xô đẩy
        self.touch_iou = cfg.get("touch_iou", 0.15)       # hai khung chồng nhau tối thiểu để coi là đang xô đẩy
        self.crowd_size = cfg.get("crowd_size", 5)        # từ số người này trở lên là đám đông: đòi nhiều bằng chứng hơn
        self.n_people = 0
        self.reset()

    def reset(self):
        self.last = {}     # id -> (t, {wrist: (x, y)})
        self.events = deque()   # (t, id người vung, id người bị trúng hoặc None)
        self.seen = {}     # id -> lần cuối thấy

    # ------------------------------------------------------------------
    def update(self, people, t):
        """Gán p["signals"]["fighting"] và p["fight_with"] cho các học sinh đang đánh nhau.
        Trả về danh sách các cặp (id_a, id_b)."""
        if self.events and t < self.events[-1][0]:   # thời gian chạy lùi (video phát lại)
            self.reset()
        by_id = {p["id"]: p for p in people}
        self.n_people = len(people)
        for p in people:
            self._observe(p, people, t)
        while self.events and t - self.events[0][0] > self.window:
            self.events.popleft()
        for k in [k for k, s in self.seen.items() if t - s > 5.0]:
            self.seen.pop(k)
            self.last.pop(k, None)

        pairs = self._pairs(by_id)
        for a, b in pairs:
            for x, y in ((a, b), (b, a)):
                by_id[x]["signals"]["fighting"] = True
                by_id[x].setdefault("fight_with", y)
        return pairs

    def _observe(self, p, people, t):
        pid, kp = p["id"], p["kpts"]
        sh = sg.shoulders(kp, self.kp_conf, p["box"])
        scale = max(10.0, sh[1] if sh else (p["box"][2] - p["box"][0]) * 0.55)
        cur = {w: (float(kp[w][0]), float(kp[w][1]), float(kp[w][2])) for w in WRISTS if kp[w][2] >= self.kp_conf}
        prev = self.last.get(pid)
        self.last[pid], self.seen[pid] = (t, cur), t
        if prev is None:
            return
        dt = t - prev[0]
        if not 0.03 <= dt <= 1.0:
            return
        for w, pos in cur.items():
            if w not in prev[1]:
                continue
            ox, oy = prev[1][w][:2]
            speed = ((pos[0] - ox) ** 2 + (pos[1] - oy) ** 2) ** 0.5 / (scale * dt)
            if not self._threshold(dt) <= speed <= MAX_SPEED:
                continue
            hit = self._target(p, pos, people)
            # Tay chỉ "vung mạnh và chắc chắn" khi nhanh hơn hẳn ngưỡng và khớp tay được thấy rõ (không phải khung xương nhảy)
            strong = speed >= 1.3 * self.swing_speed and min(pos[2], prev[1][w][2]) >= self.strong_conf
            self.events.append((t, pid, hit, strong))

    def _threshold(self, dt):
        """Máy yếu đo thưa (2-5 FPS) thì tay đã đi và về giữa 2 lần đo, tốc độ thấy được thấp hơn thật.
        Hạ ngưỡng dần: nguyên mức khi dt <= 0.1 s, còn 50% khi dt >= 0.3 s."""
        k = min(1.0, max(0.0, (dt - 0.1) / 0.2))
        return self.swing_speed * (1 - 0.5 * k)

    @staticmethod
    def _target(p, pos, people):
        """Học sinh khác có thân người chứa vị trí cổ tay (gần tâm nhất nếu nhiều người).
        Cổ tay còn nằm trong thân chính mình (người đứng sát, khung chồng nhau) thì không tính là chạm người khác."""
        if _inside(torso_box(p["box"]), pos):
            return None
        best, best_d = None, None
        for q in people:
            if q["id"] == p["id"] or not _inside(torso_box(q["box"]), pos):
                continue
            c = sg.center(q["box"])
            d = (c[0] - pos[0]) ** 2 + (c[1] - pos[1]) ** 2
            if best is None or d < best_d:
                best, best_d = q["id"], d
        return best

    def _pairs(self, by_id):
        strikes, flails = {}, {}   # cặp -> tập thời điểm; id -> tập thời điểm
        crowd = self.n_people >= self.crowd_size
        need_strikes = self.min_strikes + (1 if crowd else 0)
        need_flails = self.min_flails + (2 if crowd else 0)
        for t, a, b, strong in self.events:
            if b is not None:
                strikes.setdefault(frozenset((a, b)), set()).add(round(t, 2))
            if strong:
                flails.setdefault(a, set()).add(round(t, 2))

        out = set()
        for pair, times in strikes.items():
            if len(times) >= need_strikes and pair <= by_id.keys():
                out.add(tuple(sorted(pair)))
        # Hai người sát nhau, cả hai cùng vung tay liên tục (xô đẩy, vật nhau, che đòn)
        ids = [i for i, ts in flails.items() if len(ts) >= need_flails and i in by_id]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if self._touching(by_id[a]["box"], by_id[b]["box"], self.touch_iou):
                    out.add(tuple(sorted((a, b))))
        return sorted(out)

    @staticmethod
    def _touching(b1, b2, iou=0.15):
        if sg.box_iou(b1, b2) > iou:
            return True
        gap_x = max(b1[0], b2[0]) - min(b1[2], b2[2])
        gap_y = max(b1[1], b2[1]) - min(b1[3], b2[3])
        w = ((b1[2] - b1[0]) + (b2[2] - b2[0])) / 2
        return gap_x < 0.15 * w and gap_y < 0
