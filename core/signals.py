"""Tính các tín hiệu tức thời từ khung xương (keypoints) của 1 người.

Thứ tự 17 điểm khung xương chuẩn COCO mà YOLO-pose trả về:
  0 mũi, 1 mắt trái, 2 mắt phải, 3 tai trái, 4 tai phải,
  5 vai trái, 6 vai phải, 7 khuỷu trái, 8 khuỷu phải, 9 cổ tay trái, 10 cổ tay phải, ...
"""
import numpy as np

NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SHOULDER, R_SHOULDER = 5, 6
L_WRIST, R_WRIST = 9, 10
HEAD_POINTS = (NOSE, L_EYE, R_EYE, L_EAR, R_EAR)


def shoulders(kpts, thr):
    """Trả về (y trung bình của vai, độ rộng vai) hoặc None nếu không thấy rõ 2 vai."""
    ls, rs = kpts[L_SHOULDER], kpts[R_SHOULDER]
    if ls[2] < thr or rs[2] < thr:
        return None
    width = abs(ls[0] - rs[0])
    if width < 5:
        return None
    return (ls[1] + rs[1]) / 2, width


def head_ratio(kpts, thr):
    """Đầu cao hơn vai bao nhiêu, tính theo đơn vị "độ rộng vai".

    Ngồi thẳng: ~0.5-1.0. Gục xuống bàn: gần 0 hoặc âm.
    Thấy rõ vai mà không thấy điểm nào trên mặt -> mặt đang úp xuống -> trả về -1.
    Không thấy vai -> None (không đủ thông tin để kết luận).
    """
    sh = shoulders(kpts, thr)
    if sh is None:
        return None
    shoulder_y, width = sh
    head = [kpts[i] for i in HEAD_POINTS if kpts[i][2] >= thr]
    if not head:
        return -1.0
    head_y = np.mean([p[1] for p in head])
    # Trục y của ảnh hướng xuống dưới nên lấy vai - đầu
    return float((shoulder_y - head_y) / width)


def wrist_distance(kpts, point, thr):
    """Khoảng cách từ point tới cổ tay gần nhất, chia cho độ rộng vai.

    Trả về None nếu không thấy cổ tay hoặc vai.
    """
    sh = shoulders(kpts, thr)
    wrists = [kpts[i] for i in (L_WRIST, R_WRIST) if kpts[i][2] >= thr]
    if sh is None or not wrists:
        return None
    d = min(np.hypot(w[0] - point[0], w[1] - point[1]) for w in wrists)
    return float(d / sh[1])


def eye_crops(frame, kpts, thr, min_dist):
    """Cắt ảnh 2 mắt quanh điểm mắt trái/phải. Trả về [] nếu mặt quá nhỏ."""
    le, re = kpts[L_EYE], kpts[R_EYE]
    if le[2] < thr or re[2] < thr:
        return []
    d = np.hypot(le[0] - re[0], le[1] - re[1])
    if d < min_dist:
        return []
    # Cắt rộng ~1 lần khoảng cách 2 mắt, lệch lên trên để lấy cả lông mày,
    # cho giống ảnh mắt trong bộ dữ liệu huấn luyện.
    half = int(0.5 * d)
    h, w = frame.shape[:2]
    crops = []
    for x, y in ((le[0], le[1] - 0.1 * d), (re[0], re[1] - 0.1 * d)):
        x0, y0 = max(int(x) - half, 0), max(int(y) - half, 0)
        x1, y1 = min(int(x) + half, w), min(int(y) + half, h)
        if x1 - x0 > 4 and y1 - y0 > 4:
            crops.append(frame[y0:y1, x0:x1])
    return crops


def head_box(frame, kpts, thr, min_dist):
    """Vùng vuông quanh đầu (rộng ~4 lần khoảng cách 2 mắt). None nếu mặt quá nhỏ."""
    le, re = kpts[L_EYE], kpts[R_EYE]
    if le[2] < thr or re[2] < thr:
        return None
    d = np.hypot(le[0] - re[0], le[1] - re[1])
    if d < min_dist:
        return None
    cx, cy = (le[0] + re[0]) / 2, (le[1] + re[1]) / 2 + 0.3 * d
    half = 2.0 * d
    h, w = frame.shape[:2]
    x0, y0 = int(max(cx - half, 0)), int(max(cy - half, 0))
    x1, y1 = int(min(cx + half, w)), int(min(cy + half, h))
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    return x0, y0, x1, y1


def contains(box, point, pad=0.1):
    """Điểm có nằm trong khung (mở rộng thêm pad %) không."""
    x0, y0, x1, y1 = box
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    return x0 - px <= point[0] <= x1 + px and y0 - py <= point[1] <= y1 + py


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
